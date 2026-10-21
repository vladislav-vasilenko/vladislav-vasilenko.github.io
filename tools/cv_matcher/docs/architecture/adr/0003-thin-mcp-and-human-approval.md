# ADR 0003 — Тонкий MCP adapter, разрешения принадлежат backend и владельцу

> Реализация 19.10.2026: [application layer и MCP](../application-layer.md). Документ ниже сохраняет исходное решение; ограничения/фактические tools уточнены в описании реализации.

Дата: 19.10.2026. Статус: проект интерфейса; MCP сервер и tools ниже **ещё не реализованы**.

## Контекст и решение

Поиск реализаций MCP в `tools/cv_matcher`, `cv-api`, корневых `src`/package manifests не обнаружил server/tool registration. Упоминание `headhunter-mcp-server` в генераторе инструкций прямо говорит, что он не используется. Это отсутствие в исследованной области репозитория, не утверждение об установленных приложениях пользователя.

Первый MCP adapter должен вызывать существующий `:8788` API или общий application service, а не дублировать business rules/SQL. Предпочтительный начальный transport — локальный stdio для клиентов, которые его поддерживают. Поддержка ChatGPT/другого клиента зависит от его transport/deployment, а не от названия MCP; удалённый HTTP transport требует отдельного решения по auth и размещению. Новый SDK, если понадобится, должен быть optional dependency с обоснованием, не скрытым обновлением всей среды.

## Минимальный целевой набор tools

Имена в таблице — **предлагаемые**, не фактические endpoints или callable tools текущего продукта.

| Tool | Контракт | Existing backend mapping |
|---|---|---|
| `career.get_state` | Выбранный CV/цель, capabilities, connected/last-success и next action; без секретов | `GET /archive/journey`, `GET /archive/workflow`, `ApplicationStore.browser_status` |
| `career.search` | Начать/найти существующий run, явные scope/limits/cost mode; вернуть run ID | `POST /archive/workflow op=discovery_start`, `discovery.start`; повтор до запуска сверяет pending run |
| `career.get_task` | Прочитать существующий discovery/collection run и counts/partial/needs-input | `op=discovery_status`, `collection_status`, чтение command/workflow; unified response — обязанность adapter |
| `career.control_task` | Запрос pause/resume/cancel по operation ID/version, только на поддержанных стадиях | Общая application operation ещё требуется; нынешние Telegram `/pause` и `/cancel` её не заменяют. Нельзя отменить уже принятый сайтом отклик этим tool |
| `career.rank` | CV/version + selection/goal + policy; кэш, затем только разрешённый расчёт | `POST /archive/rank` / `POST /rank`, `rank_vacancies`; учитывать текущие batch limits |
| `career.analyze` | Для выбранной пары: cached report, API request по budget policy либо export/import без API | `/archive/skill-analysis`, `/archive/skill-external`, `skill_analysis` / `external_analysis` |
| `career.prepare_application` | Создать/открыть case и сохранить проверенный draft/ответы; опционально поставить безопасный browser prepare | `op=make`, `draft`, `field_answer`, `prepare`; `ApplicationStore` и `FormAnswersMixin` |
| `career.get_application` | Актуальный case, источники, история, форма и следующие шаги | `GET /archive/workflow?app_id=…`, связанные analysis lookups по CV/JD context |
| `career.review_action` | Read-only preview нужного согласования и ссылка в существующий пульт; не разрешает отправку | `op=intent` / `career_fill_intent`, workflow view; текущий human UI в вебе/Telegram |

Не добавлять в MCP произвольный `SQL`, `eval`, `navigate_any_url`, `send_telegram`, `claim`, `next`, `result` или инструмент «approve=true». Browser result может подтверждать только доверенный executor; модель не может подделать receipt. Фактическое согласование продолжает существующий владелец в Telegram/вебе; его нельзя вывести из фразы модели «пользователь согласен».

Tools, меняющие состояние/вызывающие API, не считаются безопасными только из-за readOnlyHint/названия. Backend проверяет source allowlist, CV/JD revisions, capability, cost policy, idempotency и scope. `allow_api` из свободного аргумента модели не заменяет сохранённую политику владельца. При отсутствии разрешения tool возвращает requires-input/approval и способ продолжить без API.

Pairing token принадлежит adapter runtime; он не возвращается в tool output/промпт. Output по умолчанию содержит минимально необходимые facts/IDs/summary; тексты CV/JD выдаются только для конкретной операции, не dump всех локальных данных. Input JSON schema необходима, но повторяет проверку backend, а не заменяет её.

## Первый сквозной сценарий

1. `get_state`: получить CV, goal, доступность Chrome и policy. Нет worker → явное ожидание.
2. `search` / `get_task`: existing discovery собирает JD и пересчитывает рейтинг по разрешённому режиму. MCP не запускает второй поиск/рейтинг, если run уже делает это.
3. `analyze`: проверить выбранный shortlist, сохранить report с context hash или выдать prompt без API. Отсутствующий cache не запускает платный fallback.
4. `prepare_application`: existing case, draft, вопросы и browser prepare. Company unsupported action → ручной next step, не generic submit.
5. `get_application` / `review_action`: показать форму/ответы/intent владельцу и **остановиться на human approval**. После его действия текущая очередь выполняет claim/submit/verify, затем состояние читается обычным tool.

## Доказательство и оставшаяся работа

[test_architecture_flow.py](../../../src/tests/test_architecture_flow.py) подтверждает backend-цепочку и запрет чтения browser queue через обычную web session. Он не является MCP protocol test. Перед реализацией adapter нужны tools schema/transport tests, request replay, malicious document/tool arguments, explicit cost denial, context mutation и проверка, что без человеческого approval `execute` не возникает.

Сегодня report можно найти по CV/JD/hash/goal, а case — по vacancy/context, но между discovery run, analysis key и application нет единой неизменяемой correlation chain. Первое расширение domain layer — добавить такие ссылки, затем MCP сможет объяснить, почему подготовлен конкретный отклик, не восстанавливая историю эвристически из последних записей.

Telegram остаётся основным мобильным пультом; MCP — независимый adapter тех же operations. Четыре функции Telegram, ownership длительных задач и общий TTL/actor/operation approval описаны в [ADR 0005](0005-telegram-primary-control.md). Предлагаемый минимальный набор теперь включает девять tools с управлением поддержанными задачами, а не отдельный agent для каждого интерфейса.
