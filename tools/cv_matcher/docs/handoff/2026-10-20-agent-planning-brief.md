# Передача проекта следующему агенту: фактическое состояние и входные данные для плана

> **Обновление UX и Skills scopes, 20.10.2026:** [Today, вакансии, рейтинг, отклики и три основы плана навыков](../integration/workspace-ux.md). 373 Python / 323 JS; Career Path от evidence к целевому профилю, без новых платных вызовов.

> **Обновление Skills Intelligence, 20.10.2026:** [реализованный модуль, контракт, использование и ограничения качества](../architecture/skills-intelligence.md). 33 навыка / 6 версионируемых треков, общие Web/Telegram рекомендации по top-K, evidence feedback и история; 369 Python / 320 JS. Live Web: 50 вакансий, API 0. Независимая массовая разметка и аудит GitHub остаются дальнейшей работой. Эта фаза реализована по отдельному явному запросу пользователя; исторический baseline ниже сохранён.

Дата: **20.10.2026, Europe/Moscow**. Область: `tools/cv_matcher` внутри существующего репозитория портфолио. Это отчёт для подготовки следующего алгоритма и плана, **не разрешение выполнять все фазы приложенного большого ТЗ**. Текущие пользовательские правки завершались отдельно; новую фазу автономного агента в рамках подготовки этого отчёта не запускали.

Исходная большая идея сохранена рядом: [входной документ](input-development-idea-2026-10-20.md). Её нужно сопоставить с этим фактическим срезом перед составлением нового плана.

## 1. Краткий вывод

Система уже существенно шире парсера: Chrome MV3, локальный FastAPI, SQLite с версиями, embeddings, доказательный анализ Luna, письма/анкеты, CRM, Telegram-управление, очередь Chrome и MCP stdio. Переписывать это с нуля не нужно.

**Полный живой Telegram → поиск компаний → Luna → черновик → заполненная форма → Telegram approval → подтверждённый результат не доказан.** Универсальной отправки на всех карьерных сайтах нет. Число пройденных unit/integration tests не закрывает этот разрыв.

Основное ограничение сейчас — связность и проверенность вертикального сценария, качество карьерного отбора и понятный следующий шаг. Новые агенты, MCP Apps, self-healing и новая инфраструктура сами по себе этот разрыв не закрывают.

## 2. Какие инструкции пользователя сохраняют приоритет

1. Evolutionary Architecture: использовать существующие алгоритмы, SQLite, очереди, интеграции и UI. Не вводить микросервисы/БД без измеренного основания.
2. **Telegram — основной мобильный пульт**: conversation, notifications, human-in-the-loop, workflow control. Логика общая; отдельного агента внутри Bot class не создавать.
3. Ближайший milestone: **Telegram → Personalized Search → Luna → Application Draft → Chrome Automation → Human Approval**. Первый live прогон остановить до реальной отправки.
4. Платные вызовы — по явному действию/сохранённой политике. Cache-only и копирование промпта не должны незаметно включать оплату.
5. Отправка/перенос полей/сообщение работодателю требуют существующего конкретного подтверждения; не ослаблять owner, operation ID, TTL, version binding, one-time claim и uncertain.
6. Похожие вакансии HH/сайта компании полезно группировать. **Не блокировать** отдельный отклик на каждом источнике только из-за семантического сходства.
7. Интересы: Pretraining, Post-training/RL, Diffusion/Flow Matching/DiT, DL Research, ML Systems/distributed training; также CUDA, Apple MLX/MPS/Metal, Automotive/ADAS, Sensors, Robotics, БПЛА, космос/Бюро 1440, признаки оборонной тематики и госзаказа.
8. Интерес не равен доказанному опыту. Курс MIT или учебный проект не превращать в production experience. Отсутствие факта в CV не доказывает отсутствие опыта.
9. Новые теги оборонной тематики — проверяемые **признаки/предположения**, не утверждение о назначении каждой вакансии. Спутники/дроны не дают такой тег автоматически; госзаказчик не равен проверенному контракту.
10. Для Ozon пользователь явно оставил только **ML и PyTorch** как поисковые запросы. Для Т-Банка — **IT-разработка / Машинное обучение**, не «Аналитика и данные».

Приложенный большой текст предполагает, что MCP/Telegram/Telethon/часть workflow предстоит создать. Это уже устаревшее предположение. Его фраза «не начинать с Telegram» не отменяет более поздний явный приоритет пользователя Telegram Primary. Фазы из текста нужно сопоставить с кодом и перепланировать.

## 3. Фактическая архитектура: что читать

| Область | Реальная реализация | Роль/ограничение |
|---|---|---|
| HTTP backend | [resume_import_server.py](../../resume_import_server.py), [archive_routes.py](../../src/archive_routes.py), [workflow_routes.py](../../src/workflow_routes.py) | Локальный FastAPI и прежняя авторизация; API health version 13 |
| Application layer | [CareerApplication](../../src/career_application.py) | Поиск, кандидаты, расписание, подготовка, outbox; общая логика для адаптеров |
| Conversation | [career_orchestrator.py](../../src/career_orchestrator.py), [career_search_scope.py](../../src/career_search_scope.py) | Ограниченный детерминированный intent router; это не универсальный LLM planner |
| Scheduler | [career_runtime.py](../../src/career_runtime.py) | FastAPI scheduler + fallback tick бота, одна renewable SQLite lease |
| Задачи и прогресс | [agent_tasks.py](../../src/agent_tasks.py), [agent_progress.py](../../src/agent_progress.py), [discovery.py](../../src/discovery.py) | Durable search/browser/analysis IDs, revision controls, checkpoints; поддержанные стадии, не мгновенная отмена любого побочного эффекта |
| Telegram | [workflow_bot.py](../../src/workflow_bot.py), [telegram_ranking.py](../../src/telegram_ranking.py), [telegram_analysis.py](../../src/telegram_analysis.py), [telegram_presentation.py](../../src/telegram_presentation.py) | Owner-only Bot API, карточки, разбор/подборки, outbox; не отдельная бизнес-логика поиска |
| MCP | [career_mcp.py](../../career_mcp.py), [agent_routes.py](../../src/agent_routes.py) | Реализованный stdio server/тонкий клиент loopback application API. Не надо создавать второй сервер |
| Архив | [ArchiveStore](../../src/archive_store.py), [AnalysisStore](../../src/analysis_store.py) | Entities, версии, scans/membership, события, profiles, rankings, vectors, skill reviews |
| Отклики и CRM | [ApplicationStore](../../src/application_store.py), [application_workflow.py](../../src/application_workflow.py), [crm_planning.py](../../src/crm_planning.py), [application_channels.py](../../src/application_channels.py) | Кейсы/каналы/стадии отдельно от внешних статусов и подтверждения отправки |
| Письмо/анкеты | [application_preparation.py](../../src/application_preparation.py), [application_form_answers.py](../../src/application_form_answers.py), [career_application_fields.py](../../src/career_application_fields.py), [career_questionnaires.py](../../src/career_questionnaires.py) | Версии материалов, известные поля детерминированно; неизвестные требуют ввода/проверки |
| Профиль/доказательства | [candidate_profile.py](../../src/candidate_profile.py), [candidate_facts.py](../../src/candidate_facts.py), [resume_supplements.py](../../src/resume_supplements.py), [resume_review.py](../../src/resume_review.py) | Уже есть профиль и подтверждённые уточнения; полный Career Profile/skill graph ещё не реализован |
| Giga/Telegram Client | [giga_handoff.py](../../src/giga_handoff.py), [telegram_recruiter.py](../../telegram_recruiter.py) | Telethon уже есть; фактическая доступность текущей сессии и полный единый TTL не доказаны |
| Chrome extension | [manifest.json](../../hh-research-extension/manifest.json), [background.js](../../hh-research-extension/background.js), [core.js](../../hh-research-extension/core.js) | MV3 0.11.18; alarms/workers, storage/message bridge, permissions; это пользовательский Chrome executor |
| Адаптеры | [adapters/](../../hh-research-extension/adapters/), [build-adapters.mjs](../../hh-research-extension/scripts/build-adapters.mjs) | Существующие адаптеры и сборка. Сбор ≠ чтение формы ≠ заполнение ≠ submit |
| Web UI | [archive.js](../../archive-web/archive.js), [workflow.js](../../archive-web/workflow.js), [career-analytics.js](../../archive-web/career-analytics.js) | Рабочий архив, CRM, аналитика, ручная отметка, offline/API действия |

Расширенная базовая карта: [current-state](../architecture/current-state.md), [application-layer](../architecture/application-layer.md), [интеграционный отчёт](../integration/telegram-career-e2e.md). Некоторые абзацы старых документов исторические; этот срез и датированные уточнения имеют приоритет при расхождении.

## 4. Хранение и состояния

Рабочая SQLite: `.cache/applications/state.sqlite3`. Это локальный однопользовательский контур. Секреты находятся отдельно; **не передавать `.env`, pairing token, Telethon session или содержимое production DB в промпты/публичный пакет**.

- Источники: `entities`, `versions`, `profiles`, `scans`, `membership`, `events`.
- Embeddings/рейтинг: `embedding_vectors`, `document_embeddings`, `ranking_runs`, `archive_meta`.
- Анализ: `skill_analyses`, `skill_analysis_sources`, `skill_analysis_failures`, `external_analysis_requests`; review CV — отдельные existing tables.
- Отклики: `applications`, workflow/drafts/approvals/discussion/events, CRM/appointments, channel/form/field versions.
- Исполнение: `browser_commands`, `discovery_runs`, `application_preparations`, `agent_task_controls`, `agent_task_events`, `career_leases`, `browser_command_progress`.
- Доставка: `workflow_delivery` с сохранёнными попытками/receipts/uncertain.
- Новое: `analysis_batches` в той же БД — очередь пакетного Luna. Ручные отметки — namespace `manual-application:` в существующем `archive_meta`, история в `events`; отдельной БД нет.

`Application` source-specific и `application_channels` не являются готовой группировкой похожих вакансий HH/компании. Повторные публикации пока учитываются отдельно.

Полный сон ноутбука останавливает **локальные** Python и Chrome. Backend сохраняет ожидание, а не будит выключенный executor. Доставка ранее отправленного Telegram сообщения или получение его другим устройством не доказывает исполнение нового crawl во сне. 24/7 — отдельное архитектурное решение, не выполненное в этой итерации.

## 5. Что существовало до последних правок — Already Implemented

- DOM/structured extraction, source-specific identities, импорт одной вакансии/резюме, каталог компаний и настройки.
- Сбор поисковой выдачи и полных описаний; суточная свежесть JD и повторное использование кэша. Discovery имеет лимиты/partial; это не полный охват всего сайта.
- Cached embeddings, отдельные выбранные CV/цель/model, глобальная сортировка рейтинга. Extension умеет проходить большой набор пакетами; web `/archive/rank` ещё ограничен 200 за запуск.
- Luna с JSON Schema, R/J-источниками и проверкой цитат; письма, review CV, offline export/import; факт изучения отделён от практики.
- Telegram top-10 из полного актуального рейтинга, исключение известных откликов/closed/«не моё», подробный разбор без создания application на чтении.
- Общий application layer, bounded conversation, scheduler lease, outbox, pause/resume/cancel поддержанных задач и реальный MCP stdio.
- HH workflow с owner approval/claim/verify/uncertain, поддержанное заполнение company fields, CRM и часть Telethon/Giga.
- Sankey/история/карта и теги Flow Matching/CUDA/Apple. Исправлены false positives bare-metal и физического metal conductor.

## 6. Последние изменения — Implemented Now

### 6.1. Карта и экспорт

Уточнение 20.10: Бюро 1440 убрано из taxonomy/primary categories. Это работодатель и выбирается фильтром компании. Его вакансии сохраняют тег «Космос / Спутниковые системы» с явным основанием по работодателю; отдельного потока Бюро 1440 нет. Сохранённый старый focus-tag `bureau1440` переходит в `space`. Числа отдельных тегов Бюро 1440 ниже — исторический срез до этого уточнения.

[career-charts.js](../../archive-web/career-charts.js) и [career-analytics.js](../../archive-web/career-analytics.js):

- Два режима: X = CV cosine или Luna coverage; Y = cosine к цели. Неизвестные оценки не становятся нулями.
- **По диапазону данных / Полная шкала**. Автомасштаб линейный, включает все точки текущей выборки, допускает ноль/отрицательные значения; оценки и рейтинг не меняет. Меньшие полупрозрачные точки уменьшают перекрытие.
- Sankey увеличивает высоту при большом числе категорий: потоки не исчезают из-за нулевого масштаба. Длинные подписи сокращены с полным текстом в доступном имени.
- **На весь экран / Esc** и **Скачать PNG**. PNG захватывает весь SVG вне прокрутки, включает CV/count/date, белый фон и стили. Canvas ограничен 20 млн пикселей; нет внешних изображений/сети/API. Имя файла использует локальную дату.
- В fullscreen столбцы пересчитывают горизонтальные позиции под соотношение сторон экрана, сохраняя высоты потоков и пропорции шрифтов. «Вписать» учитывает ширину **и высоту**; все категории остаются видимыми. Зум 50–400%, кнопки, перетаскивание. Trackpad pinch обрабатывается через ctrl+wheel; обычная двухпальцевая прокрутка остаётся нативной. Для мыши есть отдельный флажок «Зум прокруткой» (по умолчанию выключен). Исходный SVG/viewBox не обрезается при зуме, экспорт сохраняет всю диаграмму.

### 6.2. Пакетный Luna top-50

[luna_batch.py](../../src/luna_batch.py), `/archive/analytics-batch`:

1. `preview` берёт до 50 лучших из **существующего актуального** embedding-рейтинга и текущих фильтров, исключает closed/неполные. Не вызывает модель.
2. Закрепляет IDs, CV/JD hashes, goal/model. Показывает cache/new-call counts. Owner отдельно подтверждает `start`; preview действует 15 минут.
3. Scheduler обрабатывает по одному элементу через `CareerApplication.analyze_context`, сохраняет результат и attempt перед внешним вызовом. Не обещает мгновенную обработку 50.
4. Pause/cancel кооперативны после текущего вызова; ambiguous/crashed/failed item не повторяется автоматически. Resume продолжает необработанные. Статус виден в Web и `/tasks` как `analysis:…`.
5. `export`: CV один раз, цель, полные JD, R/J-ID и schema; `import`: разрешённые export IDs, точные цитаты, версии и текущая открытость. Частичные ошибки перечисляются; кэш результатов общий.

Фактически проверены живые preview/export **50 / 6 cached / до 44 новых**, промпт 227672 символа, **0 API calls**. Paid `start` на реальных данных не нажимался. Это не проверка качества Luna на 50 заданиях.

### 6.3. Аудит и расширение категорий

[career_taxonomy.py](../../src/career_taxonomy.py) расширяет существующий [classify](../../src/career_analytics.py):

- Добавлены роли Data Engineering, аналитика, Backend/Python, образование, QA, Embedded, Security, DevOps, CV/NLP, научные вычисления, Quant, management, AI-автоматизация/разметка, Frontend/Mobile, поддержка.
- Отдельные пересекающиеся теги: Automotive/ADAS, Sensors/Sensor Fusion, Robotics, дроны, космос/спутниковые системы, Бюро 1440, оборонные признаки, госзаказчики.
- Роли выводятся по title; прикладные признаки — по тексту, Бюро 1440 — по employer. Основание/цитата/source/basis показываются в карточке. Это **правила**, а не уже внедрённый embedding classifier.
- По текущему архиву: **1996 записей / 921 full / 1073 snippet / 2 needs_review / 6 CV**. Остаток правил уменьшился **1124 → 150** (94 snippet, 54 full, 2 needs_review). Последние показатели переснять перед новым экспериментом.
- Теги во всём архиве: дроны 40; Robotics 107; Automotive 16; Sensors 31; космос 18; Бюро 1440 10; оборонные признаки 15; госзаказчики 1. Они пересекаются и не суммируются.
- В исходных 317 полных без категории было 300 с готовыми актуальными 3-small vectors и 17 без них. Готовые векторы можно использовать дальше локально, но нужны проверенные примеры/пороги/abstain, не CV score как категория.
- Остались ошибочные CTA-карточки Т-Банка «Откликнуться» и посторонние профессии. Исправление качества сбора открыто. Снижение `other` не является доказанной точностью; gold set ещё нет.

### 6.4. Быстрая ручная отметка «Отклик сделан»

[manual_applications.py](../../src/manual_applications.py), POST `/archive/workflow` с `op=manual_application`:

- Вакансия + boolean + revision. Один клик и отмена, без CV/полного JD, генерации и отправки.
- Источник `user`, `site_confirmed=false`; повтор одинакового запроса идемпотентен. На карточке явно «Отмечено вами».
- Отметка глобальна для source-specific vacancy ID, переживает изменение CV/перезапуск, исключает эту запись из Telegram top без откликов и учитывается в аналитике/CRM manual section.
- Undo меняет только ручную отметку; реальные HH/CRM статусы сохраняются. Похожие публикации другого источника не отмечаются автоматически.
- Новая подготовка/active send для этой записи блокируется, пока отметка активна. Queued external writes отзываются; running write не объявляется отменённым и ручная отметка ждёт результата.
- Не создаётся фиктивное HH observation или receipt отправки. Это не полноценная миграция существующего application case в `submitted`.
- UI: список, рейтинг, detail, analytics cards, отдельная группа в разделе откликов. MCP отдельный manual-mark tool не добавлялся; кнопку в Telegram для этой операции пока не добавляли.

### 6.5. Диагностика

`CareerBatch is not defined` исправлено определением модуля до использования в том же asset. Web показывает operation, endpoint без query, HTTP status, request ID, error type/stack, время и copy diagnostics. После legacy `notice(e.message)` подробности сохраняются. URL tokens маскируются, CV/JD/request body/headers не выводятся. JavaScript error больше не считается автоматически ошибкой входа. Backend добавляет `X-Career-Request-Id`; неожиданные 500 логируют frames без payload/query/header/exception value.

### 6.6. Поднять резюме в поиске HH

Добавлено opt-in бесплатное автоподнятие выбранных HH-CV: [контракт и проверки](../integration/hh-resume-bump.md). Общая SQLite policy/queue, одноразовый claim, проверка выбранной карточки, перерыв 4h после подтверждения, при сне — очередь ожидания, после uncertain — ручная сверка. Выбор CV в Web, управление основным CV и пауза в Telegram. Скрытые/неопубликованные резюме не публикуются, платные услуги не подключаются. **По умолчанию выключено, пользователь оставил включение себе. Во время приёмки он уже включил одно основное CV; очередь/claim есть, подтверждённого receipt ещё нет.** Нужна версия расширения 0.11.18. Это не изменение правил согласования откликов.

## 7. Реальные ограничения — Pending

| Приоритет | Пробел | Основание / желаемый критерий |
|---|---|---|
| P0 | Полный Telegram E2E не доказан | [Живой отчёт](../integration/telegram-career-e2e.md). Требуется один trace request → run → recommendation → cited analysis → draft → Chrome fill → owner preview → CRM, без реальной отправки на первом прогоне |
| P0 | Company open-form/submit/verify не универсальны | Нужен capability matrix на каждый источник, current DOM fixtures и отдельный live check. Generic fill не означает право/возможность submit |
| P0 | Контроль оплаченных попыток между всеми entrypoints | Batch использует общий owner helper, но прямые `skill_analysis.analyze` entrypoints есть в Web/inline/discovery/preparation. Отдельно проверить конкуренцию двух каналов и restart; не объявлять global exactly-once billing доказанным |
| P1 | Детерминированная очередь «с чего начинать» | Существующий рейтинг — 80/20 cosine, он не реализует пользовательский Career Value + readiness policy. Предложение ниже — **не внедрённый алгоритм** |
| P1 | Нет разметки качества taxonomy/ranking | Составить gold/holdout, precision редких тегов, nDCG/Recall/полезность. Уменьшение unknown и число тестов не являются этими метриками |
| P1 | Неполные/ошибочные карточки и source coverage | 1073 snippet; CTA вместо title. Разделить extraction quality, confidence, unknown, non-target. Не считать пустой crawl отсутствием вакансий |
| P1 | Структурированный Career Profile/предпочтения | Профиль/факты/цель уже есть; веса, команды, отрасли, salary/location constraints и evidence skills ещё не объединены в единый versioned контракт |
| P1 | Связь похожих публикаций | Source IDs есть, related-posting groups/owner confirmation ещё нет; не создавать запрет откликов между источниками |
| P1 | Большой рейтинг Web vs extension/discovery | Web cap 200; единый run/progress/checkpoint на весь archive всё ещё нужен |
| P1 | Approval/TTL унификация Giga | Telethon существует; current session connectivity и общий TTL всех веток не доказаны |
| P2 | Автовыбор резюме | Несколько CV есть, выбранный CV используется явно; автоматический лучший CV по вакансии не реализован |
| P2 | Зарплаты и география | В аналитике нет сохранённой структурированной зарплаты. Не делать из неизвестного hard fail/выдуманный размер точки |
| P2 | Observability, numbered migrations, cost ledger | Есть events/usage/request IDs; нет полного единого dashboard качества/стоимости/SLA и калиброванной цены кандидата |
| Позже | Self-healing/LLM recovery/новые infra | Сначала стабильный вертикальный сценарий и измерения. Пока нет production self-modifying extractor или универсального computer-use executor |

## 8. Предложение алгоритма очереди — вход для следующего планировщика

Пользователь запросил воспроизводимый порядок откликов и фокус на компаниях/командах. **Не смешивать это с уже существующей сортировкой по embeddings** и не выдавать предложенные веса за утверждённые пользователем.

### 8.1. Предлагаемый контракт

`ApplicationPriorityPolicy(version, selected_cv_hash, career_profile_revision, constraints, track_order, fit_buckets, diversity_limits, tie_breakers)` и snapshot `ApplicationQueueItem(vacancy_version, company, team, track, fit_evidence, missing_information, readiness, reason, next_action)`. Это проектные имена, в коде таких сущностей ещё нет.

Порядок детерминированный и лексикографический:

1. Отдельная очередь blocked: closed/отправленные/ручные marks/явное нарушение заданных constraints. Unknown salary/location не трактовать как нарушение.
2. Развести **карьерный приоритет**: обучение/архитектуры generative models; ML systems/CUDA; Embodied AI/Robotics; прочие прикладные AI. Новые отраслевые интересы пользователя оформить как настройки, не молча переписать старую цель.
3. Отдельная стадия review для неизвестного Luna fit; отсутствие анализа не считать нулём компетенций. Сначала анализировать ценные неизвестные позиции, затем возвращать в очередь.
4. Внутри трека учитывать подтверждённые must-gaps, readiness материалов, затем сохранённые goal/CV similarity. Закрепить policy version и единый stable tie-breaker (source ID).
5. Опционально ограничить подряд идущие вакансии одной команды; дубли источников группировать в UI, но сохранять независимые действия.
6. После каждого результата выдать конкретный next step: проверить активность, разобрать требования, дополнить факт, подготовить письмо, открыть форму, согласовать. Не бесконечно пересчитывать рынок вместо отклика.

Для согласования рассмотреть дневной пакет **3 целевых + 1 смежная + 1 более доступная**. Это рекомендация для обсуждения, не текущая настройка/автоматизация. Приоритетные компании/команды нужно хранить раздельно от prestige tier.

### 8.2. Конкретные кандидаты из архива для будущего пилота

В момент проверки `CareerApplication.candidates()` вернул 843 актуально ранжированных записи после существующих исключений. Это не 843 проверенных подходящих/открытых вакансии. Часть имеет unknown activity; перед откликом нужна проверка.

- **Yandex Alice AI ART**: [вакансия 11031](https://yandex.ru/jobs/vacancies/mlrazrabotchik-v-komandu-generatsii-izobrazheniy-alice-ai-art-11031). На официальной странице есть pretrain/SFT/RL, image editing, distillation, distributed training. Наиболее прямой кандидат для generative image research по заявленному интересу.
- **Yandex Alice AI LLM — инфраструктура претрейна**: [44391](https://yandex.ru/jobs/vacancies/mlrazrabotchik-v-komandu-infrastrukturi-pretreyna-alice-ai-llm-44391). Официально описаны RL training efficiency, распределённые коммуникации, Triton/CUDA/CuTe. Оценить реальные gaps распределённого обучения.
- **Yandex робот доставки — World Models & RL**: [42988](https://yandex.ru/jobs/vacancies/senior-ml-researcherengineer-world-models-rl-v-komandu-robota-dostavki-42988). Официально DiT/Flow Matching, video/world models, MBRL, multi-node. Высокий тематический интерес, но требования экспертного JAX/масштабного обучения требуют предметной проверки; не объявлять готовым соответствием.
- **Сбер GigaChat Post-training / RL**, **Navio симуляция/3DGS/ML-планер**, **Сбер Центр аэрологистики**, **MWS AI inference** — есть конкретные позиции в архиве. Это кандидаты по snapshot, а не подтверждение доступности сейчас; HH страницы через web tool не открылись.
- **Бюро 1440**: в архиве 10 публикаций, среди ранжированных кандидатов встречаются Embedded C++ и бортовые алгоритмы Python/математика. Орбитальные алгоритмы/радиосвязь/embedded — дополнительная карьерная ветка; она не эквивалентна Diffusion/Pretraining.

Никакие отклики по этому списку не отправлялись. Компании не получили автоматический новый приоритет в production ranking. Официальные страницы Яндекса читались для предложения; других публичных статусов не выдумывали.

## 9. Verification — что действительно проверено

### Автоматически

Финальный исходный срез: **350 Python tests, 318 JS tests — успешно**. Сюда входят unit/интеграционные fixtures; это не число живых отправок. Внешние модели/работодатели не вызывались тестами.

- [test_career_market_tags.py](../../src/tests/test_career_market_tags.py): домены, отрицания, employer evidence, отсутствие автоматического оборонного назначения у спутников/дронов, car benefits/военный билет, title vs generic skills.
- [test_manual_applications.py](../../src/tests/test_manual_applications.py): restart, idempotency, undo, независимость HH observations, auth/Origin, snippet без CV, ranking exclusion, queued/running write guards.
- [test_luna_batch.py](../../src/tests/test_luna_batch.py): top order/filter, preview expiry, versions, cache/offline import, pause/restart, ambiguous attempts, closed jobs, auth.
- [career-charts.test.mjs](../../hh-research-extension/career-charts.test.mjs): conservation, focus union, unknown, axes/negative/single points, много категорий, PNG pixel bound, широкая компоновка, зум вокруг указателя, fit по высоте, wheel/pinch/pan/drag и подавление случайного click после drag.
- [archive-diagnostics.test.mjs](../../hh-research-extension/archive-diagnostics.test.mjs), [manual-applications.test.mjs](../../hh-research-extension/manual-applications.test.mjs): безопасная диагностика и один локальный quick-mark click/undo без открытия карточки/вызова модели.

### Живые проверки / пределы

- Backend/Telegram процессы обновлялись, health API 13 проверялся. Исходники расширения обновлены до 0.11.18 для opt-in поднятия резюме; до этой функции UI/аналитические изменения работали с 0.11.16.
- Живой API preview/export top-50 подтверждён, 0 model API calls, только `preview` в `analysis_batches` на момент среза.
- В Chrome были видны оба режима карты, переключатели масштаба и 847 точек из 1996. Повторное подключение через существующую страницу расширения выполнено.
- Тесты manual mark используют временные вакансии. Не ставить фиктивный «отклик сделан» на реальную вакансию ради демонстрации.
- Fullscreen проверен в реальном Chrome. Срез всех 1996 вакансий показан со всеми категориями по высоте и столбцами по ширине экрана; пользователь подтвердил вписывание по высоте. PNG для выборки 256 записей действительно скачан и визуально проверен (2900×1480); весь граф и подписи присутствуют. Этот файл был создан до расширения fullscreen-компоновки по ширине. Новый wide PNG отдельно не проверен.
- Физический multi-touch pinch дистанционно не воспроизводился. Его ctrl+wheel-контракт, нативная прокрутка без модификаторов и drag проверены fixtures, что не заменяет пользовательскую проверку реального жеста.
- Полный live Telegram E2E, фактический платный batch-50, реальный company submit и 24/7 не проверялись/не включались.

## 10. Как воспроизвести проверки безопасно

Из `tools/cv_matcher`:

```sh
.venv/bin/python scripts/test-isolated.py
node hh-research-extension/scripts/check.mjs
```

[Изолированный runner](../../scripts/test-isolated.py) копирует только исходники/UI/fixtures/docs/pyproject во временную папку и удаляет credential-related environment variables. `.env`, `.cache` и реальные sessions не копируются. Это важно: часть старых тестов по умолчанию использует относительные cache paths. Не запускать полный discovery тестов в рабочем каталоге с production defaults.

Перед runtime restart проверить активные browser writes, model preparations и `analysis_batches`. Нельзя ради обновления оборвать оплаченный/claimed write и затем автоматически повторить его. При перезапуске backend cookie session может потребовать повторного открытия сайта через «Локальный архив → Открыть сайт анализа и истории» в расширении. Секретный код не выводить в отчёты.

## 11. Что следующий агент должен вернуть сначала

1. Сверку этого отчёта с изменившимся кодом/данными; список расхождений, а не повтор исходного ТЗ.
2. Реальный capability matrix источников: listing/detail/form-read/fill/submit/verify, fixtures/live даты, explicit manual fallback.
3. Минимальный следующий вертикальный milestone с зависимостями и Definition of Done. Согласовать API policy и точку остановки до отправки.
4. Конкретный алгоритм Career Value/очереди откликов, разделяющий fit/alignment/readiness/unknown; версионированные настройки и объяснения.
5. План проверки качества taxonomy/ranking и конкуренции оплаченных запросов; baseline, gold/holdout, сценарии отказов.
6. Точные задачи по файлам с критериями приёмки, migration/backward-compatibility и проверкой экономии/рисков. Новые инструменты/БД предлагать только с обоснованием.

**Не считать этот отчёт разрешением отправлять отклики, запускать массовые платные модели или выполнять весь следующий roadmap.** Следующий план должен учитывать, что работающий локальный стек и пользовательский workflow уже существуют.
