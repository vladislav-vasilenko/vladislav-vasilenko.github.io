## Career Workspace (CV Matcher)

Это локальный проект подготовки откликов внутри [общего workspace](../../docs/workspace.md). Публичное портфолио находится в корневых `src/` и `content/`. Главная точка входа персонального сервиса: `resume_import_server.py`, порт `8788`; запуск из корня — `npm run career:dev`. `server.py:8787` — прежний отдельный путь.

[Предметная модель и связи сущностей](../../docs/career-domain-model.md) · [Карьерная траектория](docs/architecture/career-trajectory.md)

Career Skills Intelligence: [треки, рекомендации обучения и подтверждения опыта](docs/architecture/skills-intelligence.md). Веб → Карта возможностей → Career Tracks; Telegram → Навыки и обучение.

Актуальный архитектурный аудит (19.10.2026): [текущее состояние](docs/architecture/current-state.md), [целевая архитектура](docs/architecture/target-state.md), [разрывы](docs/architecture/gap-analysis.md), [план развития](docs/roadmap.md). Ниже сохранены исторические описания выпусков; текущие возможности и ограничения сверяйте с аудитом и кодом.

Tools for scraping vacancies, enriching them, and building searchable vacancy
data for the site.

### Main entrypoints

- `resume_import_server.py` - the current local service (FastAPI, port 8788); see `docs/README.md`.
- `server.py` - legacy FastAPI/SSE service on port 8787 (old RAG matcher path, not the personal archive).
- `cv_matcher.py` - legacy batch matcher pipeline.
- `scripts/scrape_online.py` - automated scraper used by GitHub Actions.
- `scripts/scrape_linkedin.py`, `scripts/cluster_linkedin.py` - legacy LinkedIn connections scraper and clustering; superseded by the LinkedIn section of `hh-research-extension` and `src/linkedin_*.py`.

### Source layout

- `src/scrapers/` - scraper classes grouped by market/source family.
- `src/scrapers/parsers/` - pure parser helpers and browser-side parser scripts.
- `linkedin-scraper-extension/` - legacy 2026-05 extension and userscript; not installed alongside the main extension, kept only as history.
- `.cache/` and `.auth/` - local generated state, ignored by git. Secrets and the rule that they never enter the git index: `docs/security.md`.

### Live scraper checks

Run focused live checks when changing a scraper:

```bash
uv run python -m src.tests.scrapers.test_ru_ozon --query PyTorch --limit 500
uv run python -m src.tests.scrapers.test_ru_sber --query PyTorch --limit 500 --headed
```

Use `--out .cache/scraper-tests/<source>.json` to save captured vacancies for
manual inspection.

### Vacancy review UI

Run a local static server from this directory:

```bash
uv run python -m http.server 8765
```

Then open:

```text
http://localhost:8765/viewer/vacancies.html
```

The viewer loads `.cache/scraper-tests/sber.json` by default and can also open
any scraper JSON via the file picker.

Generated debug dumps, browser auth state, ChromaDB files, and AI caches should
stay local. Regenerate them as needed instead of committing them.

### Research Engineer search

`hh-research-extension/` contains a Chrome extension prototype and the selected
company tiers / generative modelling search profile. It reads opened HH, Avito,
Ozon and configurable corporate job boards on a user action, synchronizes HH
resume snapshots and exports JSON compatible with the vacancy viewer, without
depending on the public HH API or headhunter-mcp-server.

Generate clickable searches for Moscow and remote work in Russia:

```bash
node scripts/build_research_search.mjs
node scripts/build_research_search.mjs --daily
```

Applicant workflow: [docs/applicant_quickstart.md](docs/applicant_quickstart.md).
Version 0.5 loads all HH catalog resumes, imports reviewed Google Docs and
Pages/DOC/DOCX/TXT/PDF/MD files, crawls HH pagination and full descriptions, and
ranks saved vacancies against the explicitly selected CV inside the extension.
Huawei R&D is Top-Tier; see `docs/huawei_search.md`.

Start the private loopback import/ranking service once per work session:

```sh
.venv/bin/python resume_import_server.py
```

Set `OPENAI_API_KEY` only in the local service environment or `.env`. Pair the
extension using `.cache/resume_import/token.txt`; the OpenAI key never reaches it.
The embedding model is selectable (`text-embedding-3-small` / `text-embedding-3-large`)
and unchanged chunks are cached. See `hh-research-extension/README.md` for limits,
permissions and the distinction between semantic ranking and detailed LLM review.

`cv_matcher.py --vacancies-json ... --resume-bundle ... --resume-source bundle`
remains available for detailed scoring. Daily scheduling and application submission
are not implemented. Tests use mocked browser/API calls; see
`docs/operations.md` for the verification matrix and its limits.
# Отклики и Telegram-userbot · 0.6.0

В рейтинге добавлена кнопка «Откликнуться» с привязкой к CV/версии, вакансии
и карьерной цели. Канал HH поддерживает чтение формы, редактируемые ответы,
перенос в HH и отдельную отправку/переход к следующему шагу с проверками.
Канал Telegram создаёт локальную очередь для Telethon и управляющего Bot API бота.
Черновики Luna/Terra/Sol можно править или заменить своим ответом; отправка явная.

Подключение, команды и ограничения живой проверки:
[docs/telegram_userbot.md](docs/telegram_userbot.md).
Пример имён локальных настроек: `telegram.env.example`; текущий `.env` не заменять.

## Пожелания и длина письма · 0.6.2

В карточке рейтинга доступны комментарий с личной мотивацией и выбор 1–50 предложений основного текста. Опыт берётся из выбранного CV; мотивация — из комментария. Источники показываются отдельно, варианты кэшируются с учётом настроек. [Как пользоваться](docs/applicant_quickstart.md#короткий-сопроводительный-текст).

## CV + вакансия для ChatGPT · 0.6.3

В карточке рейтинга можно скопировать выбранный CV, полную вакансию и готовый
промпт для сравнения навыков, рекомендации по отклику и продолжения разговора
по вопросам рекрутера/HH. Необязательные пожелания и вопрос добавляются перед
копированием. Работает локально без API и Python-сервиса.


## Локальный архив и статусы embeddings

Версия расширения 0.7.1 синхронизирует CV, вакансии и рейтинги с локальной SQLite-базой. Сервис сохраняет embeddings, а сайт показывает их статус для каждого описания и выбранной модели. [Подключение, история и восстановление](docs/local_archive.md).


Обновление 0.8.1: [пять шагов поиска, фильтр компаний, адаптеры и отметки HH](docs/workflow_and_adapters.md). Разборы Luna и их исходные версии доступны на локальном сайте в «История разборов резюме».


## CRM откликов · 0.9.0

На локальном сайте появился раздел «Отклики»: этапы общения/трёх интервью/отказа/оффера, история с заметками, обсуждение и версии письма, прочитанные ответы HH и разрешение на конкретную отправку. Управляющий @baniartbot работает независимо от авторизации Telethon: `/hh`, `/today`, `/sync_hh`. Подборки — 10:00 и 19:00 по Москве; только после проверки активности через явно подключённую вкладку расширения.

[Подключение, поведение и границы проверки](docs/application_crm.md).

[Актуальная оценка пользы сервиса и разрывов конвейера · 16.10.2026](docs/service_assessment.md).

Обновление 0.10.2 (подключение HH, ChatGPT без API): исторические заметки удалены 24.10.2026; текущее описание — [workflow_and_adapters](docs/workflow_and_adapters.md).

Поддержка этапов и планирования интервью, Google Calendar, отдельный веб-рейтинг с фильтром компании и режимы «API / Без API»: [инструкция 0.10.3](docs/crm_ranking_modes.md).


### Обновление 0.10.5

В локальном веб-сервисе появились **О сервисе**, **Настройки компаний** и чекбоксы нескольких компаний / tiers в архиве и рейтинге. Каталог компаний редактируется и сохраняется в SQLite; тот же редактор открывается из расширения. Панели Яндекса, Avito, Ozon и T-Bank поддерживают разбор и письмо через API / без API.

[Как включить панели и настроить источники](docs/career_widgets.md) · [Разрывы конвейера](docs/architecture/gap-analysis.md).

Общий Career application layer, управление задачами Telegram/Web/MCP и запуск stdio-сервера: [инструкция](docs/architecture/application-layer.md).
