# Разрывы между реализацией и целевым конвейером

> Сверка 22.10.2026. Ниже сохранён реестр исторических findings. Актуальные ограничения: [current-state](current-state.md), [roadmap](../roadmap.md). G22/G24/G25 не означают отсутствие уже реализованных application layer/router/MCP. Связь Actions JSON → SQLite теперь есть; public projection тоже реализована. Полнота live E2E, качество ранжирования и LinkedIn session adapter остаются открытыми.

> **Обновление Skills Intelligence, 20.10.2026:** [реализованный модуль, контракт, использование и ограничения качества](skills-intelligence.md). 33 навыка / 6 версионируемых треков, общие Web/Telegram рекомендации по top-K, evidence feedback и история; 369 Python / 320 JS. Live Web: 50 вакансий, API 0. Независимая массовая разметка и аудит GitHub остаются дальнейшей работой. Эта фаза реализована по отдельному явному запросу пользователя; исторический baseline ниже сохранён.

> **Уточнение 20.10.2026:** [Отчёт для следующего планирования — 20.10.2026](../handoff/2026-10-20-agent-planning-brief.md) содержит актуальную таблицу Pending и Verification. G04 в части скрытого 30-minute отсечения shortlist исправлен; проверка активности перед действием сохраняется. G22/G24/G25 нельзя планировать как отсутствующие application layer/router/MCP. G09 (качество), G08 (related postings), company submit/verify, Web cap 200, единый paid-attempt guard и полный live E2E остаются открыты. Новые deterministic tags, batch Luna и ручной mark не закрывают эти пункты.

> Обновление аналитики и Telegram 19.10.2026: [Sankey, фокус, исправление Apple-тегов, единый топ-10 и подробный разбор](../integration/career-analytics-telegram.md). Политика топ-10 и пометки ⭐ в этом отчёте заменяет прежние правила короткой подборки.

> Обновление 19.10.2026, API 13 / Extension 0.11.16: [сквозная интеграция Telegram, исправления, 305 Python / 292 JS и оставшиеся ограничения](../integration/telegram-career-e2e.md). Исторические записи ниже описывают состояние на момент аудита, не отменяют уточнений в этом отчёте. Полный live E2E всех компаний не объявлен готовым.

> Обновление после аудита, 19.10.2026: общий `CareerApplication`, backend scheduler с SQLite lease, bounded conversational router, versioned task control и MCP stdio реализованы. Фактические контракты, ограничения и запуск: [Общий application layer](application-layer.md). Исторические findings ниже описывают baseline аудита; G22/G24/G25 закрыты в указанном объёме, G27 — для поддержанных стадий. G23/G26 остаются открыты.

Аудит 19 октября 2026. [Текущее состояние](current-state.md) → [целевая архитектура](target-state.md) → [порядок внедрения](../roadmap.md).

Приоритет: P0 — потеря основного сценария/опасность повторного побочного эффекта; P1 — надёжность, покрытие и качество отбора; P2 — сопровождаемость и масштабирование. **Подтверждённый дефект**, **архитектурное ограничение** и **недостаток доказательств** ниже различаются. Планы/названия новых contracts не считаются существующим кодом.

## 1. Что уже есть и не требует переписывания

| Возможность | Фактическое состояние |
|---|---|
| Архив и версия CV/JD | Есть SQLite, hashes, snapshots, versions и receipts; [ArchiveStore](../../src/archive_store.py) |
| Embeddings/ranking | Выбранное CV, цель, chunk cache, два размера модели, версия JD, cached rankings; [extension_ranking.py](../../src/extension_ranking.py) |
| Luna | Structured outputs, citations, failure diagnostics; [skill_analysis.py](../../src/skill_analysis.py) |
| Режим без API | Export/import analysis, ручные письма/ответы, CV review и selection prompt; [external_analysis.py](../../src/external_analysis.py), [external_prompt.py](../../src/external_prompt.py) |
| Поиск по расписанию | Уже запускает collection и ranking через `discovery`; утверждение «только читает старый рейтинг» устарело. При API off новые векторы не создаются |
| Доставка событий | Anti-join outbox, leases, uncertain/reconcile; [DeliveryMixin](../../src/delivery_store.py), [enqueue_event_notifications](../../src/career_application.py). Сценарий 105 событий покрыт тестом |
| HH действия | Чтение статусов/чатов, single-use approval, claim/submit/verify, неизвестный результат без слепого retry |
| Формы компаний | Capture/version/fingerprint, профиль и ответы, согласованный перенос; это ещё не универсальный submit |
| CRM/интервью | Этап applied/ai_screened, waiting/preparing/scheduled, встречи/ICS/Google OAuth; [crm_planning.py](../../src/crm_planning.py) |

Новый агент должен строиться поверх этого. Повторная реализация очереди, базы, бота или всех адаптеров с нуля увеличит риск.

## 2. P0: фактические сбои и обязательные инварианты

### G01 — конфликт Giga может откатить чтение остальных наблюдений HH

**Подтверждённый runtime-сбой.** В прочитанной метаистории последняя sync-команда от 19.10 была `failed`: «Это приглашение Giga уже связано с другой вакансией». [WorkflowMixin.hh_sync](../../src/application_workflow.py) обрабатывает page snapshot в одной транзакции и вызывает [GigaMixin.save_giga_invite](../../src/giga_handoff.py) внутри неё. Конфликт вызывает exception; весь текущий snapshot откатывается. Ограничение на неверную перепривязку правильно, гранулярность отказа слишком велика.

**Изменение:** сохранить запрет автоматической перепривязки; неоднозначную связь записывать как конфликт для владельца, не терять независимые валидные наблюдения и сообщения. Разделить validation failure всего envelope и изолируемый domain conflict записи/приглашения. Вернуть partial и точную причину.

**Приёмка:** snapshot с двумя корректными вакансиями и конфликтным приглашением сохраняет корректные статусы/сообщения; invite не переносится в другой case; конфликт виден в вебе/Telegram; повтор snapshot не дублирует события; сбой БД по-прежнему откатывает целостную транзакцию. Добавить проверки в [test_giga_handoff.py](../../src/tests/test_giga_handoff.py), [test_hh_auto_sync.py](../../src/tests/test_hh_auto_sync.py), [test_pipeline_reliability.py](../../src/tests/test_pipeline_reliability.py).

### G02 — неподтверждённая доступность ноутбука маскируется процессом поиска

**Обновление реализации:** очередь ожидания Chrome, recovery read-only команд и проверки 8-часового сна добавлены; см. [контракт](application-layer.md). Ниже сохранён исходный finding. Живая проверка физического сна/пробуждения остаётся отдельной приёмкой.

**Подтверждённое ограничение и runtime-симптом.** Закрытый ноутбук кратко просыпался в DarkWake; бот успевал отправлять progress/errors. Discovery завершился по времени, а не готовой подборкой. [CareerApplication.begin_digest/tick](../../src/career_application.py) и [discovery.start/advance](../../src/discovery.py) не имеют отдельной полноценной стадии ожидания пробуждения: wall-clock ожидание команды ограничено десятью минутами, crawl — четырьмя минутами.

**Изменение:** до обещания активного поиска учитывать свежесть collection capability; ввести явное ожидание executor, отдельные сроки очереди и работы, catch-up/recovery с прежним digest key. Chrome после пробуждения сверяет command lease и сохранённый scope. Сообщение «Ищу» заменять фактическим состоянием, не создавать лавину уведомлений.

**Приёмка:** моделируем сон 8 часов/короткий wake/возвращение worker. Нет ложного success и повторной отправки; не больше одного catch-up соответствующего слота; partial сохраняется; пользователь видит «Ждём Chrome». Это не обещает работу локального браузера при выключенном компьютере. 24/7 deployment — отдельное решение G14.

### G03 — защита необратимых действий должна пережить расширение адаптеров

**Существующий инвариант, не заявленный новый дефект.** HH и Telethon уже используют одноразовые claims и uncertain. Generic company submit такого пути не имеет. Добавление «автоматического отклика везде» без site-specific verify создаст риск двойной/не той отправки.

**Изменение:** перед company submit реализовать capability, version-bound intent, claim, подтверждение результата и ручную сверку. Не обходить существующие проверки ради универсальной кнопки. Не переносить разрешение между источниками похожей вакансии.

**Приёмка:** double click, закрытие Chrome, потеря HTTP ответа после submit, изменившаяся форма/CV и повтор запуска не отправляют автоматически второй отклик. Success требует конкретного evidence сайта, не факта клика/заполнения.

## 3. P1: разрывы user flow и интеллектуального отбора

| ID | Доказательство / состояние | Требуемое изменение и критерий завершения |
|---|---|---|
| G04 | Суточный `detailFresh` в [core.js](../../hh-research-extension/core.js) и 30-minute activity filter в [CareerApplication.candidates](../../src/career_application.py) | Разделить freshness текста и activity check. Reused JD участвует в shortlist, затем дешёвая проверка активности нужных кандидатов. Тест: JD 2 часа, неизменённая выдача, готовые векторы → кандидат не исчезает молча; закрытый исключается; unknown показан явно |
| G05 | Только пять company adapters; [registry/build test](../../hh-research-extension/adapter-build.test.mjs). Reading/fill/submit не являются одной capability | Единый application flow, capabilities per site. Yandex/T-Bank/Avito/Ozon/Sber проверить отдельно. Добавить Samokat.Tech/MTS MWS только после исследования их форм. UI не обещает submit там, где лишь сбор; fixtures и живой проход на каждую capability |
| G06 | CSS/custom settings, hosts и identity распределены между manifest, JS, Python allowlists, каталогом | Один проверяемый источник деклараций плюс fixtures JS↔Python. Регистрация сайта не равна разрешению пользователя. Тесты подтверждают совпадение ID, поддержанных hosts, отказ неизвестному origin и неподдержанным операциям |
| G07 | На screenshot введено 2000, фактически выбиралось 200; [ranking.js](../../hh-research-extension/ranking.js), `/rank` cap | **Исправление подготовлено 0.11.12**: batches до 200 для выбора до 2000, global sort, aggregate usage, partial. [ranking-batch.js](../../hh-research-extension/ranking-batch.js). Веб `/archive/rank` ещё ограничен 200; discovery — отдельный путь. Завершение: общий run/batch контракт, прогресс/возобновление и одинаковые counts во всех интерфейсах |
| G08 | Нет relation похожих вакансий в `entities`; [identity](../../src/board_import.py) — source-specific; `application_channels` решает другую задачу | Добавить versioned related-posting groups в ту же SQLite, использовать готовые embeddings + company/title/location evidence. Владелец может подтвердить/отклонить. **Не блокировать** независимые отклики в разных источниках |
| G09 | Рейтинг 80/20/top-2 similarity, нет размеченных relevance labels или NDCG/Recall | Зафиксировать baseline gold set и feedback, сравнивать cascade ranking с текущим. Не считать coverage/score вероятностью найма. Только после измерений выбирать новую модель/веса |
| G10 | Политики attempts/cache различаются: cover до двух calls, skill failure reuse, resume persistent attempt, recruiter cache после success | Общий model operation/attempt ledger и cost policy в SQLite, фиксированные context IDs и версии schemas. Crash между response и save не вызывает скрытый второй платный запрос; budget и API off одинаково выполняются всеми paths |
| G11 | Export/import analysis есть, но [vacancy_selection.build](../../src/vacancy_selection.py) может создать один огромный prompt; ручной shortlist не стал единым run | Bounded packets с manifest IDs, resume/goal/comments snapshot, импорт shortlist, проверка полных JD. Малый/no API режим не должен незаметно переключаться на paid embeddings. Тест: 2000 snippets полностью покрыты пакетами, import чужого ID отклонён |
| G12 | Cache markers есть в browser record, но отсутствуют в [archive-sync-core.js](../../hh-research-extension/archive-sync-core.js) и [FIELDS](../../src/archive_store.py) | Согласовать версию sync envelope и перенос markers. Restore воспроизводит прежнюю свежесть/dirty, не требует ненужного открытия всех вкладок и не скрывает реальное изменение |
| G13 | Browser queue/receipts durable, но locks частично in-memory; `next_command` stale retries, `runBoardCrawl` cleanup зависит от successful persist в finally | Протестировать MV3 restart и отказ storage/HTTP на каждой фазе; освобождать locks гарантированно, read-only retry с fencing. Не заявлять exactly-once. Отдельно минимизировать частые перезаписи больших `vacancies`/`last_ranking` и риск quota |

G07 исправляет наблюдаемую ошибку интерфейса, но не делает всю систему масштабируемым resumable ranking engine. Успешный тест 2000 строк с fake backend не измеряет время/расход настоящего OpenAI.

## 4. P2: эксплуатация, безопасность границ и стоимость сопровождения

| ID | Факт | Следующий шаг |
|---|---|---|
| G14 | Два локальных Python процесса + Chrome, не 24/7 hosted service. GitHub daily public scraper — отдельный контур | Сначала local availability telemetry и ожидание G02. Затем ADR: действительно ли нужны гарантированные подборки при спящем ноутбуке; если да — обосновать один always-on узел, приватность/синхронизацию и доступные браузерные capabilities |
| G15 | [server.py](../../server.py)/Chroma и [cv-api](../../../../cv-api/api) живут параллельно личной SQLite | Обозначить ownership. Связать только нужный public discovery через существующий [collection_contract.py](../../src/collection_contract.py), не переносить личные CV/отклики в публичные JSON. На одну и ту же входную вакансию сравнить identity/quality/score двух paths |
| G16 | [server.py](../../server.py) без pairing middleware; [embeddings.js](../../../../cv-api/api/embeddings.js) проверяет auth условно при наличии env secret | Не объявлять утечку без проверки deployment. Для сохраняемого legacy API сделать fail-closed auth при ожидаемом protected режиме, ограничить body/timeouts; протестировать отсутствие секрета, неверный token и CORS. CORS не считается авторизацией |
| G17 | DDL в конструкторах/mixins, версии protocol/manifest/pyproject не связаны; manual dict API | Нумерованные миграции и backup/restore tests; Pydantic contracts существующих routes, compatibility schema JS↔Python, version negotiation. Точечное выделение модулей после тестов, без переписывания всего проекта |
| G18 | Есть diagnostics/usage/events, нет общей trace и продуктовых SLO | Correlation chain, redacted logs и локальная панель по очередям, failed/partial/missing delivery, source quality, бюджету и времени до отклика. Не собирать текст CV в telemetry без необходимости |
| G19 | Offline suites есть, обязательного запуска в текущих GitHub workflows нет; некоторые route fixtures вызывают `create_app` без `archive_path` | До CI обеспечить временный archive_path/отключение фонового scheduler во всех таких fixtures; model/browser doubles не гарантируют изоляцию локального файла. Затем CI без секретов/live crawling. Новый architecture flow test использует временную SQLite. Live checks отдельно; fixture drift сайта не маскируется общей зелёной галочкой |
| G20 | README/docstrings содержат устаревшие версии/описания; Python `SOURCE_GROUPS['ru']` пропускает Sber; direct imports openai/httpx не перечислены напрямую в pyproject | Выправить документы/registry tests/dependency declarations. Не выполнять массовое обновление пакетов одновременно с domain refactor |
| G21 | Calendar connected = наличие refresh token; HH/collection/Giga используют другие проверки | Единая терминология configured/reachable/authenticated/capable/busy/last-success, сохраняя раздельность. Проверять свежую RPC там, где UI обещает live connection |

## 5. Неизвестное, которое нельзя заменить предположением

Дополнительные интеграционные приоритеты: **G22 (P1)** — MCP adapter отсутствует; реализовать только тонкий ограниченный интерфейс по [ADR 0003](adr/0003-thin-mcp-and-human-approval.md), не копировать SQL/queue/approval. **G23 (P1)** — в CRM нет обязательных ссылок на discovery run / ranking run / analysis key; `make` берёт CV/JD/goal, поэтому жизненный цикл пока восстанавливается частично. Добавить явный versioned provenance reference в existing domain, а не второй workflow engine. [Сквозной backend test](../../src/tests/test_architecture_flow.py) подтверждает швы до human approval, но не устраняет отсутствие MCP и correlation chain.

**G24 (P1)** — нет общего conversational intent routing: произвольный текст Telegram обслуживает directed edit, а не широкий Career Agent. **G25 (P1, до rollout MCP)** — продвижение discovery/selection/schedule частично принадлежит `WorkflowBot.tick`, вызываемому Telegram loop. Извлечь эти существующие обязанности в общий application layer/scheduler с единственным владельцем lease, а не создавать нового агента в Telegram; протестировать работу при недоступном Telegram и продолжение из Web/MCP.

**G26 (P1)** — не все критичные действия имеют единый owner/operation/TTL/version approval contract: HH/company имеют expired/claimed checks, Giga draft/start используют другие tokens без общего явного TTL. Обобщить текущие механизмы, не ослабляя current-question validation. **G27 (P1)** — нет универсального backend pause/resume/cancel; Telegram `/pause` относится к Giga, `/cancel` к вводу. Реализовать только поддержанные checkpoints; submitted/uncertain не объявлять отменёнными. Все четыре требования Telegram и критерии межклиентской приёмки зафиксированы в [ADR 0005](adr/0005-telegram-primary-control.md).

- Полное текущее покрытие/валидность selector каждого сайта и успешная company submit: этим аудитом не доказаны.
- Облачный deployment, актуальные GitHub runs и наличие secrets: не проверялись; YAML лишь описывает намерение запуска.
- Средняя relevance рекомендаций, экономия времени, расход на полезный отклик: нет baseline измерений.
- Google OAuth и перенос каждого типа файла/сложного control в production: наличие кода и fake tests не подтверждает live success.
- Круглосуточная работоспособность Giga при закрытой крышке: не подтверждается тем, что в DarkWake было доставлено уведомление.

## 6. Критерий замкнутого конвейера

Для конкретного источника цепочка считается завершённой, когда один trace показывает: прочитанную версию вакансии и CV → обоснованный отбор → готовые письмо/ответы → поддержанную форму → конкретное согласование → исполнение расширением → подтверждённый сайтом результат → запись SQLite/веба → уведомление владельцу. Partial, manual, unsupported и unknown должны быть видны как таковые.

Сегодня есть значительная часть этой цепочки для HH и отдельные возможности для компаний. Нельзя назвать сервис универсальным автономным агентом только на основании наличия кнопки «Откликнуться», модели Luna или большого числа тестов.
