# ADR 0005 — Telegram как основной мобильный пульт общего Career Agent

> Реализация 19.10.2026: [application layer и MCP](../application-layer.md). Документ ниже сохраняет исходное решение; ограничения/фактические tools уточнены в описании реализации.

Дата: 19.10.2026. Статус: целевое требование пользователя принято в архитектурный план; описанные расширения ещё не внедрены.

## Контекст: что уже реализовано

Изучены [OperatorBot / run](../../../telegram_recruiter.py), [WorkflowBot](../../../src/workflow_bot.py), [RecruiterController](../../../src/recruiter_controller.py), [DeliveryMixin](../../../src/delivery_store.py), [WorkflowMixin](../../../src/application_workflow.py), [CareerFieldsMixin](../../../src/career_application_fields.py) и существующие Telegram/reliability tests.

| Роль Telegram | Реальное состояние |
|---|---|
| Conversational Interface | Slash commands, callbacks и направленный ввод: редактирование письма/ответа, пожелания, факты, план встречи. `WorkflowBot.update` принимает произвольный текст только при установленном waiting context; общего natural-language routing к Career Orchestrator пока нет |
| Notification Center | Персональные подборки, HH events/messages, подготовленная анкета, Giga, CRM/reminders и результаты задач; durable outbox с dedupe/lease/uncertain. Это не гарантирует чтение всех employer boards |
| Human-in-the-loop | Owner/private chat checks; HH exact intent с expires и одноразовым claim; company fields — отдельный approved intent с TTL 900 с и profile/form revisions. Giga использует current-question fingerprint, draft token и single-use turn claim, но не общий approval record с явным TTL |
| Workflow Control | Есть `/today`, `/sync_hh`, просмотр кейсов/диалога; `/pause` приостанавливает активный Giga application; `/cancel` завершает текущий режим ввода. Они не являются универсальными pause/cancel discovery/ranking/browser operation |

Часть application-политики находится прямо в `WorkflowBot`: candidate selection, завершение discovery, расписание, преобразование events в notifications. `telegram_recruiter.run` вызывает `workflow.tick` после цикла getUpdates. Следовательно, backend-очередь уже долговечна, но продвижение discovery сейчас зависит от работающего процесса бота. Один общий application layer ещё не выделен полностью. Нельзя просто дать MCP вызывать копию этой логики.

## Решение

**Career Intelligence Platform** — ядро данных/политик/интеграций; **Career Agent** — интеллектуальный исполнитель поверх общих application operations; **MCP** — адаптер внешних AI-клиентов; **Chrome Extension** — чтение/действия в браузере; **Telegram** — основной мобильный пульт коммуникации и подтверждения; **CRM** — долговременная память кейса; **Luna** — аналитический компонент.

Telegram, MCP, Web Dashboard и Chrome Extension взаимодействуют с одним application layer. Не создавать Career Agent внутри Telegram и не делать Telegram транспорт владельцем business state. Сначала извлечь существующие обязанности из `WorkflowBot` в переиспользуемые application operations, сохраняя SQL, validators, approvals, cache и outbox. Это рефакторинг внутри текущего Python-проекта, не новый микросервис.

Telegram отвечает за проверку update/actor/chat, отображение карточек, ввод и передачу пользовательского намерения. Orchestrator отвечает за разрешённый план, context, task state, budget, capabilities и переходы. Conversation parsing может быть модельным или детерминированным, но выдаёт только структурированный intent, который проходит общую policy validation. Текст вакансии/работодателя не получает полномочий команды владельца.

## Целевой conversational contract

Пример: «Найди свежие вакансии по моему CV и подготовь отклик на первую подходящую». Система:

1. Связывает запрос с аутентифицированным владельцем и выбранными CV/целью; уточняет неоднозначность, не подставляет случайное CV.
2. Общий application layer создаёт/переиспользует operation с context/scope/cost policy.
3. Telegram получает task ID и фактическую стадию; закрытие диалога не отменяет operation.
4. Browser executor собирает, backend ранжирует/анализирует, сохраняет case/draft/form.
5. Telegram показывает краткий результат и одно следующее действие; неизвестные обязательные поля запрашиваются с привязкой к operation/application/form version.
6. Владелец проверяет точный состав и разрешает конкретное действие. Без API предлагается snapshot/prompt/import с теми же context IDs.

Название будущего Orchestrator/intent API — проектное понятие, не существующий endpoint. Реальные переиспользуемые функции перечислены в [current-state](../current-state.md) и [ADR 0003](0003-thin-mcp-and-human-approval.md).

## Долгие операции и управление

Состояние хранится в backend: owner, operation ID/type, immutable context refs, stage/state, parent/child tasks, version, progress/counts, checkpoint, lease/fencing, timestamps, next action и причина ожидания. Это расширение существующих `discovery_runs`, `browser_commands`, application records/истории; не отдельный Telegram state store.

Pause/resume/cancel допускаются только по capability операции:

- queued/read-only crawl — cooperative stop на безопасной границе, сохранение partial и возможность продолжить;
- ranking/model request — остановить следующие batches, сохранить уже полученные векторы/ответы; отмена не обещает возврат уже потраченных токенов;
- неподтверждённая отправка — можно отозвать pending intent/command до claim;
- claimed/sending/uncertain — не объявлять отменённой отправку, которую сайт мог принять; необходима сверка;
- уже подтверждённый submitted — это результат, не cancellable task; дальнейший отзыв отклика является отдельным действием.

Бизнес-цикл продвижения операции должен работать независимо от Telegram getUpdates/диалога; один scheduler owner/lease предотвращает два конкурентных orchestrator ticks. Сначала перенести существующий tick/advance, затем разрешать MCP и Web стартовать те же операции. Сон ноутбука остаётся ограничением executor по [ADR 0004](0004-local-availability.md).

## Общий human approval contract

Для критичных действий сохраняется одноразовое подтверждение с owner/actor identity, operation/application ID, source/site/channel, intent hash, CV/JD/draft/answers/form/profile revisions, сроком действия и состоянием approved/claimed/revoked/expired/uncertain. Изменения данных, пользователь/операция не совпали, TTL истёк или token уже использован → отказ и новый preview.

Actor identity берётся из аутентификации доверенного adapter, не из свободного текста/аргумента модели. MCP не получает инструмент self-approve; согласование может прийти из Telegram или существующего Web UI, но проверяется общим backend. Telegram callback содержит непрозрачный ID, не письмо/секреты. Перед claim executor заново проверяет текущую форму и ownership. Нельзя считать простую строку «да» подтверждением без привязки к единственному актуальному preview.

HH/company approvals уже дают основу: их надо обобщить, а не заменить. Для Giga turn send/start нужно добавить недостающий TTL и единые operation/actor references, сохранив существующую проверку актуального вопроса и запрет повторной отправки.

## Уведомления и мобильный UX

Переиспользовать durable outbox. Категории: рекомендации/результат поиска; ответ работодателя/приглашение; требуется ввод/подтверждение; завершение/partial/ошибка операции. Progress обновляет одну карточку либо приходит только при существенной смене стадии; успешные фоновые polls молчат. Сохранять dedupe и recovery, не выдавать факт доставки за факт выполненного crawl/отклика.

Карточка содержит роль/компанию, CV/цель, основание рекомендации или требуемое действие, состояние и один primary button. Подробные источники, история, длинные анкеты и diagnostics доступны в вебе. Mini App возможен позже как ещё один UI того же application layer; он не нужен для создания второго workflow.

## Приёмка межклиентского сценария

Начать поиск в Telegram → прочитать тот же run/case через MCP в Codex → открыть vacancy/form в Chrome → обновить ответы через Web → получить **обновлённый** preview в Telegram → подтвердить → executor проверяет claim/versions → результат сохраняется в CRM и доставляется владельцу.

Обязательные tests: owner mismatch, wrong task, expired/replayed callback, изменённое CV/поле после preview, переключение клиентов, restart/lease, Telegram outage и повтор update, pause/cancel на каждой поддержанной стадии. Без owner approval `execute` отсутствует. Потеря Telegram соединения не теряет/не дублирует operation. Текущий backend flow test подтверждает лишь существующую основу до preview; весь cross-client MCP сценарий ещё предстоит реализовать и проверить вживую.

## Последствия

Telegram получает приоритет по мобильному UX и уведомлениям. Backend получает единую ответственность за долгие задачи/политики. Другие интерфейсы остаются равноправными точками продолжения; ни Telegram chat ID, ни конкретная Chrome вкладка не заменяют operation context. Новая инфраструктура и отдельный Telegram agent не создаются.
