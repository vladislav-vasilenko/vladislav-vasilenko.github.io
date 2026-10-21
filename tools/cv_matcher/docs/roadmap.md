# Roadmap Career Intelligence Platform

> **Идеи дальнейшего развития, 20.10.2026:** [каталог предложений и полные исходные тексты](ideas/README.md). Связаны с существующими модулями; не являются запуском новой фазы.

> **Обновление UX и Skills scopes, 20.10.2026:** [Today, вакансии, рейтинг, отклики и три основы плана навыков](integration/workspace-ux.md). 373 Python / 323 JS; Career Path от evidence к целевому профилю, без новых платных вызовов.

> **Обновление Skills Intelligence, 20.10.2026:** [реализованный модуль, контракт, использование и ограничения качества](architecture/skills-intelligence.md). 33 навыка / 6 версионируемых треков, общие Web/Telegram рекомендации по top-K, evidence feedback и история; 369 Python / 320 JS. Live Web: 50 вакансий, API 0. Независимая массовая разметка и аудит GitHub остаются дальнейшей работой. Эта фаза реализована по отдельному явному запросу пользователя; исторический baseline ниже сохранён.

> **Не запускать фазы автоматически.** Перед новым планом прочитать [handoff 20.10.2026](handoff/2026-10-20-agent-planning-brief.md). Пользователь запросил отчёт до выполнения следующего задания. Этот roadmap исторический: Telegram/application layer/MCP уже существуют; последние UI, market taxonomy и manual mark завершены отдельно. Следующий план должен выбирать проверяемый вертикальный milestone и измерять quality/связность, а не заново добавлять уже имеющиеся компоненты.

> Обновление аналитики и Telegram 19.10.2026: [Sankey, фокус, исправление Apple-тегов, единый топ-10 и подробный разбор](integration/career-analytics-telegram.md). Политика топ-10 и пометки ⭐ в этом отчёте заменяет прежние правила короткой подборки.

> Обновление 19.10.2026, API 13 / Extension 0.11.16: [сквозная интеграция Telegram, исправления, 305 Python / 292 JS и оставшиеся ограничения](integration/telegram-career-e2e.md). Исторические записи ниже описывают состояние на момент аудита, не отменяют уточнений в этом отчёте. Полный live E2E всех компаний не объявлен готовым.

> Выполнено 19.10.2026: общий application layer, backend scheduler, bounded router, task controls и десять MCP tools. См. [реализованный контракт](architecture/application-layer.md). Дальше: G23 provenance, G26 Giga TTL и controlled live сценарий после загрузки расширения 0.11.13.

Состояние на 19 октября 2026. Основание: [current-state](architecture/current-state.md), [target-state](architecture/target-state.md), [gap-analysis](architecture/gap-analysis.md). Эволюционное развитие существующего `tools/cv_matcher`, без новых инфраструктурных зависимостей на первых этапах.

Это план с критериями приёмки, а не обещание, что перечисленные функции уже работают. Порядок определяется блокировками пользователя и риском побочных эффектов. До завершения аудита не запускались платные расчёты/отклики для демонстрации.

**Telegram — основной мобильный пульт:** запросы естественным языком, notifications, human approval и управление поддержанными operations. Все интерфейсы используют общий application layer; отдельный Career Agent внутри Telegram не создаётся. [ADR 0005](architecture/adr/0005-telegram-primary-control.md) уточняет текущие возможности и целевой сценарий.

## 0. Зафиксированный baseline и изменение в ходе аудита

- Аудит исходников, контрактов, SQL, Chrome workers, моделей, Python scrapers, Telegram и CI выполнен; архитектурные документы находятся в `docs/architecture`.
- Входной offline baseline: **276 JavaScript / 262 Python** теста прошли. Команды ниже; live coverage каждого сайта этим не подтверждено.
- По отдельной жалобе подготовлена версия расширения **0.11.12**: максимум расчёта до 2000, запросы до 200, общий рейтинг/usage и partial при прерывании; серверный архив принимает до 2000 строк. UI «Подготовить отклик» теперь соответствует текущему действию. Это не добавляет company submit.
- Regression scenarios: 718 → четыре пакета, 2000 → десять пакетов, общий sort и usage, ошибка второго пакета без retry, несовпадение CV hash, восстановление/показ более 200 строк, синхронизация объединённого рейтинга. Финальный прогон: **283 JavaScript / 264 Python**, все прошли; реальные API для проверки этого исправления не вызывались. Дополнительный architecture flow test довёл Python suite до 264; финальный Python-прогон выполнен в отдельной временной копии исходников без локальных секретов и рабочей БД.
- Работающий процесс API и установленный Chrome не следует перезапускать посреди пользовательского платного расчёта. Обновление исходников/ZIP и активация обновления в Chrome — разные шаги.

## 1. Восстановить надёжность текущих операций — G01, G02, G03

Уточнение приоритета: после устранения блокирующих сбоев ниже сначала замкнуть **интеграционный vertical slice** из раздела 2. Подключение новых сайтов, новая модель, Mini App и инфраструктура не должны отодвигать работоспособную цепочку на уже имеющихся возможностях.

**Сначала G01:** изолировать неоднозначное приглашение Giga в `WorkflowMixin.hh_sync` / `GigaMixin.save_giga_invite`. Не перепривязывать token молча. Корректные наблюдения и сообщения должны сохраняться, conflict — виден владельцу. Протестировать replay, транзакционный rollback при настоящем DB failure и отсутствие двойных уведомлений.

**Затем G02:** расширить существующие `discovery`/`WorkflowBot` состоянием ожидания доступного worker и recovery после сна. Явно отличать «запланировано» от «Chrome начал сбор». Не оплачивать model retry из-за пропущенного wake. Приёмка: simulated sleep/resume, десятиминутная очередь, partial crawl и один catch-up слота; уведомления о проблеме не выдаются за новые рекомендации.

**G03:** сохранить и усилить проверки одноразовых действий при каждом следующем адаптере. Negative tests: double click, истёкшее разрешение, changed CV/JD/form, потеря transport после отправки, crash перед receipt. Не начинать rollout company submit до прохождения этих проверок.

Выход этапа: один небольшой сквозной сценарий HH проходит после sleep/restart с читаемым статусом в вебе/Telegram; неопределённые действия требуют сверки. Это ещё не универсальная поддержка сайтов.

## 2. Унифицировать контракты и следующий шаг — G05, G06, G12, G17

Первый рабочий сценарий: **MCP → Career Agent planning → existing discovery/ranking → Luna analysis → CRM → Chrome prepare queue → Human Approval**. Решения: [ADR 0001](architecture/adr/0001-reuse-existing-workflow.md), [ADR 0002](architecture/adr/0002-sqlite-and-chroma.md), [ADR 0003](architecture/adr/0003-thin-mcp-and-human-approval.md), [ADR 0004](architecture/adr/0004-local-availability.md).

Порядок vertical slice: (а) имеющийся изолированный `test_architecture_flow.py` как backend baseline; (б) извлечение domain tick/selection из `WorkflowBot` и versioned ссылки discovery/ranking/analysis→case (G23/G25); (в) conversational intent и task control как общие application operations (G24/G27), единый owner/operation/TTL/version approval (G26); (г) тонкий MCP adapter и девять tools из ADR, без повторной business logic (G22); (д) protocol/permissions/replay tests; (е) controlled live read/prepare уже поддержанного HH и остановка на human approval в существующем пульте. Работа adapter не является разрешением на платный вызов/отправку. MCP сервер в данном аудите ещё не создан.

Межклиентская приёмка: начать поиск запросом в Telegram → продолжить тот же run/case в Codex через MCP → открыть форму в Chrome → отредактировать данные в Web → проверить обновлённый preview и подтвердить в Telegram → получить подтверждённый результат в CRM/уведомлении. Закрытие диалога или недоступность Telegram не теряют operation. Проверки старой кнопки, wrong owner/task, TTL, version mutation и pause/cancel обязательны; план не выдаёт все существующие `/pause`/`/cancel` за готовое универсальное управление.

Chroma не мигрировать в SQLite или обратно: проверить имеющийся bridge из `BaseScraper.fetch_jobs`, определить namespaces и workload; актуальный локальный semantic ranking уже использует векторы SQLite. Добавлять ANN index только после измерения, не восстанавливать старый сервер ради функции, которая уже есть.

Развивать уже существующий case в `ApplicationStore`, routes и web/Telegram views. Ввести типизированные request/result contracts и capability schema адаптеров; проверить совместимость JS/Python. Сохранить защиту origin и tokens. Миграции добавлять в ту же SQLite, с backup/restore и повторным запуском на существующей базе.

Профиль, черновик, анкета и согласование должны отображаться одной версией во всех интерфейсах. На кнопке — действие текущего этапа: «Подготовить», «Открыть анкету», «Ответить на вопросы», «Проверить», «Разрешить отправку», «Проверить результат». Список технических ограничений не заменяет next action.

Приёмка: открытие одной вакансии из рейтинга, веба и Telegram приводит к одному case; UI не обещает unsupported submit. Настройка custom selector изменяет только допустимую capability чтения. Sync/restore сохраняет freshness markers, исходные версии и отложенные receipts. Расширение нельзя обновить так, чтобы старый протокол молча принял новую опасную команду.

## 3. Довести отбор до масштаба архива — G04, G07, G09, G10, G11, G18

1. Разделить JD cache 24 часа и activity check shortlist; сохранить правило «отсутствие не равно закрытие».
2. Перенести batch/run semantics из исправления расширения в общий Python/application contract: веб, расширение и discovery с одинаковыми selection/progress/partial counts. Persist run/batch IDs, успешные результаты и безопасное продолжение без повторной оплаты готовых chunks.
3. Ввести общую политику model budget/attempts. Сначала snapshot и claim, затем вызов; отсутствие API означает отсутствие расходов. Отдельно назвать cache-only ranking и ручной ChatGPT workflow.
4. Разбивать большие prompt exports по размеру, импортировать shortlist с manifest/context IDs; затем проверять полные JD.
5. Добавить feedback и baseline качества: первоначально разметить, например, не менее 50 вакансий нескольких источников самим владельцем, отложить holdout. Предлагаемые показатели: NDCG@10, Recall@20, полезных позиций на подборку, время до первого полезного отклика, API tokens на полезную позицию. Это проектные критерии, не текущие достижения.

Приёмка: 718/2000 jobs не исчезают после первых 200; показ 10/200 строк не вызывает пересчёт; изменение CV/цели отменяет прежний context; прерывание и API off проверены; сравнение нового ранжирования с baseline проводится на одних labels/scope. Новая reranking-модель добавляется только после такой оценки.

## 4. Связать похожие вакансии — G08

Переиспользовать company aliases и готовые векторы, добавить небольшую relation таблицу в SQLite. Сначала company/role candidate blocking, затем cosine плюс source ID/title/location/tasks; ручное подтверждение и отклонение. Не использовать один глобальный cosine threshold как доказательство дубликата.

Приёмка: размеченные пары same/similar/different, контроль ложных объединений и цепочек A≈B≈C, stale links после смены JD. UI показывает источники и историю каждого отклика; отклики HH и job board разрешены независимо, как выбрал пользователь. Связь не переносит approvals и не удаляет source records.

## 5. Завершать отклик по одному company board — G03, G05, G13

Стартовый порядок: Yandex → T-Bank → Avito → Ozon → Sber; затем Samokat.Tech и MTS MWS. Это порядок разработки, не статус поддержки. Предпочтение очередной реальной вакансии пользователя может менять порядок. Для новых sites сначала исследуются точные hosts/страницы/формы, затем добавляются декларации/permissions с явной выдачей доступа.

На каждом сайте отдельно пройти: listing/detail → open form → read required fields → defaults/profile без LLM → ответы API/без API → preview в Telegram/вебе → fill → submit intent/claim → success verification → сохранение и уведомление. Нет generic автоклика «Отправить» на всех сайтах.

Для каждого adapter release нужны fixtures списка, full/closed/drift, формы, option controls, validation error и success evidence; данные/версии/история анкет сохраняются. Первый живой перенос делается на согласованной форме; реальную отправку проверяют отдельным конкретным разрешением, не автоматической массовой рассылкой для теста. Unknown/captcha/file/consent имеют ясную ручную ветку.

Готовность объявляется **по capability и сайту**, а не единственным флагом «поддерживается». У Samokat/MWS сейчас нет готового отдельного Chrome adapter; наличие MTS в старом Python registry этого не меняет.

## 6. Сопровождение и автономность — G14–G21

Добавить обязательный offline CI для существующих suites, contract tests и проверку generated bundles. Live crawling и реальные модельные запросы — отдельный контур, с разрешениями/бюджетом и датой последнего успеха. В diagnostics объединить correlation IDs, source coverage, queue age, missing deliveries и model attempts; не публиковать CV/контакты/секреты в логах.

Старый Chroma/public path интегрировать через существующий `collection_contract`, если он приносит полезные вакансии; не заставлять локальную CRM читать public JSON как доверенное приватное состояние. Устранить drift README/registry/dependencies и fail-open auth configurations там, где API должен быть защищён. Не совмещать эти шаги с массовым upgrade зависимостей.

После измерения local availability принять отдельный ADR о режиме 24/7. Если без ноутбука обязательны две подборки в день, обосновать один always-on узел для discovery/бота и границы хранения. HH Chrome по-прежнему требует доступного executor и сессии; удалённый browser не появляется автоматически от переноса бота. Не переносить secrets, не разворачивать VPS и не менять режим сна в рамках этого аудита.

## Проверки и релизные условия

Из каталога `tools/cv_matcher`:

```sh
node hh-research-extension/scripts/check.mjs
.venv/bin/python -m unittest discover -s src/tests -t .
```

Дополнительно для каждой стадии: необходимые fixtures/contract tests → controlled live read/fill → отдельная проверка подтверждённого действия. Release фиксирует версию исходников, manifest/protocol, применённые migrations, результат tests и границу live verification. Secrets, личные SQLite, сессии Chrome/Telethon и модельные cache не входят в публикуемый ZIP/репозиторий.

Критерий ценности: полезные проверенные вакансии приходят вовремя, владелец видит один следующий шаг и тратит меньше времени на подготовку/сверку отклика. Число сервисов, агентных фреймворков и кнопок не является критерием завершения.

## Product backlog clarification — 20.10.2026

The requested requirement strictness and grounded cover-letter capabilities already have implementations; extend them instead of creating parallel pipelines:

- `src/career_skill_requirements.py` distinguishes required/preferred/mentioned and explicit hard/standard/nice strictness with quoted source text. `src/career_skills.py` weights explicit hard requirements more strongly in skill priorities. Next acceptance work: labeled examples and calibration of false hard-blocker classifications; unknown evidence must remain distinct from a confirmed skill gap, including UI labels and application gating. Do not claim that the semantic embedding score itself is a verified hard-requirement pass rate.
- `src/cover_letter.py` accepts CV, project/research and motivation passages, requires one candidate source and a vacancy source per drafted claim, and checks repository URLs against supplied project evidence. Existing application controls are the generation entry point. Next acceptance work: explicit project-to-requirement traceability in the review UI and fixtures for missing, stale or conflicting project evidence. A repository URL alone is not independent verification of its contents. Paid generation remains an explicit action; draft generation and employer submission remain separate.
- `docs/integration/resume-comparison.md` records the shipped document-flow comparison, offline prompt export, vacancy reader and dedicated learning workspace. These features do not establish universal live E2E coverage of all employer forms.
