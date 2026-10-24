# Code review and repository description · 24.10.2026

Scope: whole repository, with focus on `tools/cv_matcher`, its `docs/`, the Chrome extension `hh-research-extension`, and the status of `linkedin-scraper-extension`. Reviewed state: branch `main` at `cf8e6b9` plus the uncommitted working tree (51 modified files, 19 untracked). Test runs and git facts below were produced during this review. The review itself changed nothing; a follow-up pass later the same day applied the first fixes, listed here so the sections below read as the state *before* that pass:

- `tools/cv_matcher/.env` and the four `chroma_db/*.bin` files were removed from the git index (`git rm --cached`, files kept on disk) and `npm run workspace:check` now fails if `.env`, SQLite/DB files, `token.txt`, `.cache/`, `.auth/`, `chroma_db/`, `google_state.json` or `linkedin_profile/` are tracked. Credential rotation and the history rewrite remain owner actions; the checklist is in `tools/cv_matcher/docs/security.md`.
- `tools/cv_matcher/.env.example` now lists every environment variable the code reads.
- Eight superseded docs were deleted (listed at the end of `tools/cv_matcher/docs/catalog.md`), the catalog and docs README were rewritten, stale version banners now point to the README, test counts live only in `operations.md`, the duplicated preamble was removed from `telegram_user_flow.md`, and the extension README gained the real version, permission and host lists.
- Not done, still open: the published LinkedIn contact data (section 4.2), the daily bot commits (4.3), the legacy LinkedIn code (section 7) and the code findings in sections 8 and 9.

## 1. Executive summary

| # | Severity | Finding | Where |
|---|---|---|---|
| 1 | **Critical** | `tools/cv_matcher/.env` is tracked by git and the repository is **public**. The committed version (since 17.04.2026 and 01.05.2026) contains `API_SECRET`, `CV_API_URL`, `LINKEDIN_LI_AT`, `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`. The uncommitted working copy additionally holds `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`; one `git add -A` away from publication. `.gitignore` lists the file, but ignore rules never untrack an already tracked file. | `tools/cv_matcher/.env`, commits `ff34f15`, `c706d32` |
| 2 | **High** | Third-party personal data is published. `public/linkedin_clusters.json` (937 LinkedIn contacts: name, headline, profile URL) is served live at the GitHub Pages origin (HTTP 200 at review time). `tools/cv_matcher/data/linkedin_connections.json` (936 contacts) and `tools/cv_matcher/src/debug_linkedin_connections.html` (848 KB saved "Connections \| LinkedIn" page) are tracked. This contradicts `docs/portfolio-publication.md`, which promises that source documents and private data stay local. | `public/`, `tools/cv_matcher/data/`, `tools/cv_matcher/src/` |
| 3 | **Medium** | Generated data is committed into `public/` by GitHub Actions every day (`online_scraped.json` 15 MB, `online_scraped_en.json` 12.4 MB, `vacancy_tree.json` 17 MB, `cluster_map.json` 9.3 MB). 174 of 382 commits are bot commits; `.git` is 419 MB (pack 371 MB). | `.github/workflows/daily-scrape.yml`, `public/` |
| 4 | **Medium** | Ignored-but-tracked artifacts: four `tools/cv_matcher/chroma_db/**/*.bin` files (321 KB). | `tools/cv_matcher/chroma_db/` |
| 5 | **Medium** | Version drift across documentation: `hh-research-extension/manifest.json` is 0.13.2, `tools/cv_matcher/docs/README.md` says 0.12.4, `hh-research-extension/README.md` is titled 0.11.18 and lists permissions that omit `alarms`. | docs, see section 6 |
| 6 | **Low** | A parallel legacy "RAG matcher" path still lives next to the current service: `tools/cv_matcher/server.py` (FastAPI :8787, last touched 24.04.2026), `cv_matcher.py`, `viewer/`, `scratch/`, root `matcher.html`, `scrape.html`, `src/matcher.ts`, `src/scrape.ts`, `.github/workflows/rag_updater.yml` (manual only). The docs acknowledge this (gap analysis G15/G16) but nothing has been retired. | repository root, `tools/cv_matcher/` |
| 7 | **Low** | `tools/cv_matcher/linkedin-scraper-extension/` is legacy and superseded (section 7). | `tools/cv_matcher/linkedin-scraper-extension/` |
| 8 | **Medium** | The uncommitted "LinkedIn workspace v2" work is not ready to commit: the chats "collect all" flag creates orphaned contact-collection rows, contact collection has no zero-progress guard and can chain unbounded LinkedIn reads, DeepSeek job identities collapse to one, the local scrape default now launches nine Chinese portals, and preset teams split in two (section 9). | `src/linkedin_workspace.py`, `src/linkedin_contacts.py`, `src/scrapers/china.py`, `scripts/scrape_online.py`, `src/network_map.py` |
| 9 | **Medium** | Extension behaviour contradicts its README: the service token can be persisted in `storage.local`, two one-minute alarms act on queued HH and LinkedIn commands unattended, and LinkedIn automation has no off switch in the UI (section 8). | `hh-research-extension/local-service.js`, `hh-workflow.js`, `linkedin-worker.js` |

Test status at review time:

| Suite | Command | Result |
|---|---|---|
| Extension build check + Node tests | `npm run career:check` | 421 passed, 0 failed; `board-adapters.js` in sync with `adapters/*.json` |
| Isolated Python suite | `npm run career:test` | 544 passed in 25.6 s |

## 2. Repository map (what each top-level piece is)

| Path | What it is | Status |
|---|---|---|
| `src/`, `content/`, `public/`, `index.html`, `vite.config.ts` | Public bilingual CV / portfolio, TypeScript + Vite. `src/main.ts` wires PWA, i18n, HH experience snapshot (`public/hh-experience.json`), minimal and full presentation styles, Markdown export. `tools/portfolio-static.mjs` prerenders EN `/` and RU `/ru/`. | Live; deployed by `.github/workflows/deploy.yml` (Bun build → Pages) |
| `tools/tests/*.test.mjs` | Four Node tests for the portfolio: Markdown exchange contract, presentation, PWA, static prerender. | Live (`npm run portfolio:test`) |
| `tools/workspace.mjs`, `workspace.projects.json` | Explicit entry points for the two projects (`portfolio`, `career`), `workspace:check` validates paths. | Live |
| `docs/` | Three living documents for the whole workspace (section 3). | Live |
| `tools/cv_matcher/` | Private "Career Intelligence" service: FastAPI + uvicorn app `resume_import_server.py` on :8788, SQLite archive, local web UI `archive-web/`, Chrome executor `hh-research-extension/`, Telegram bot `telegram_recruiter.py`, MCP stdio server `career_mcp.py`. ~15 300 lines of Python in `src/` (104 modules, 71 test files), ~3 000 lines of JS in `archive-web/`. | Live, actively developed |
| `tools/cv_matcher/server.py`, `cv_matcher.py`, `viewer/`, `scratch/`, `chroma_db/` | Earlier FastAPI + ChromaDB batch matcher and its viewer/scratch scripts. | Legacy, parallel to the SQLite service |
| `tools/cv_matcher/linkedin-scraper-extension/` | 228-line MV3 extension + Tampermonkey userscript that scrolls the LinkedIn connections page and downloads `linkedin_connections.json`. | Legacy (section 7) |
| `cv-api/` | Nine Vercel serverless functions (ATS check, analyze, adapt CV, cover letter, embeddings, translate, strategy, generate, cv). Bearer auth only when `API_SECRET` is set in the environment; the leaked `API_SECRET` in `.env` is this secret. | Historical public demo API, last touched 01.05.2026 |
| `autofill-extension/` | "JobAutoFill Magic · Workday" 1.1.1, host permissions limited to Workday and the Vercel API. | Legacy Workday companion, kept on purpose |
| `matcher.html`, `scrape.html` | Standalone pages for the old RAG matcher (`public/matcher_data.json`) and the :8787 scrape stream. | Legacy |
| `.github/workflows/` | `deploy.yml` (Pages), `daily-scrape.yml` (07:00 UTC Playwright scrape of Yandex/Google/Meta plus optional Chinese sources, commits JSON back to `main`), `rag_updater.yml` (manual only). | Live / live / dormant |

## 3. Root `docs/` (three files)

- **`docs/workspace.md`** — explains that one repository holds two independent projects with a shared candidate history; Mermaid flow from `content/` → portfolio → exported Markdown CV → manual import into Career Workspace. Tables of project roots and data owners, the `npm run *` command matrix, development boundaries ("do not mix the two extension manifests", "dist/, .cache, .auth, .env are local"), and a 22.10.2026 addendum about the two automatic links (GitHub Actions → SQLite, primary HH resume → `public/hh-experience.json`). Accurate and current.
- **`docs/career-domain-model.md`** — the domain model of the local service dated 22.10.2026: candidate, resume and resume version, source, candidate fact, skill, evidence, target profile ("track" in code), trajectory, stage, criterion, vacancy and requirement, analysis, development action, application. Mermaid ER diagram, a table of entities and rules, a list of distinctions to preserve (mention ≠ substantiation, course ≠ practical criterion), and a mapping to physical storage (`ArchiveStore` tables, `archive_meta` JSON keys, `AnalysisStore`, `ApplicationStore`). Good conceptual reference; it correctly warns that one entity is not one table.
- **`docs/portfolio-publication.md`** — English description of what the public site may receive from the local service: only the allowlisted `public/hh-experience.json`, reviewed intro text, opt-in public visuals, confirmed skills with public GitHub evidence, aggregated market charts without vacancy or employer identifiers. Describes prerendered EN/RU pages, SEO metadata, PWA/service-worker caching rules and what is verified by tests. Its privacy promise is contradicted by finding 2 above (`public/linkedin_clusters.json`, `public/network.html`, `public/cluster_map.*`, `public/online_scraped*.json`, `public/adapted_cvs/*.html` are all published and none of them is mentioned here).

`README.md` and `REPOSITORY_MAP.md` at the root are short, accurate pointers into these three files and into `tools/cv_matcher/docs/README.md`.

## 4. Security and hygiene findings (detail)

### 4.1 Secrets in a public repository

- `git ls-files tools/cv_matcher/.env` returns the file; `git log -- tools/cv_matcher/.env` shows commits `ff34f15` (17.04.2026, "added Matcher api") and `c706d32` (01.05.2026, LinkedIn scraper). The repository is `vladislav-vasilenko/vladislav-vasilenko.github.io`, visibility PUBLIC.
- Committed keys: `API_SECRET` (the Bearer secret of `cv-api`), `CV_API_URL`, `LINKEDIN_LI_AT` (session cookie), `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`.
- Uncommitted additions in the working copy: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
- Required actions, in order: (1) rotate the LinkedIn password, invalidate the `li_at` session, rotate `API_SECRET` on Vercel; treat the OpenAI key and Telegram bot token as exposed as well if the working tree was ever pushed or shared, and rotate them to be safe; (2) `git rm --cached tools/cv_matcher/.env` and commit; (3) rewrite history with `git filter-repo --path tools/cv_matcher/.env --invert-paths` (and the files in 4.2), force-push, and ask GitHub support to purge cached views; (4) add a pre-commit secret scan (for example `gitleaks`) so this cannot recur. A grep over all other tracked files found no further key-shaped strings.

### 4.2 Personal data of third parties

| File | Tracked | Content | Public URL |
|---|---|---|---|
| `public/linkedin_clusters.json` (300 KB) | yes, in `dist/` too | `points[937]` with `name`, `headline`, `url`, cluster coordinates; `clusters[37]` | `https://vladislav-vasilenko.github.io/linkedin_clusters.json` → HTTP 200 |
| `public/network.html` | yes | D3 page that loads the file above | same origin |
| `tools/cv_matcher/data/linkedin_connections.json` | yes, since `c706d32` | 936 contacts `{id,name,headline,url}` | repository only |
| `tools/cv_matcher/src/debug_linkedin_connections.html` | yes, since `c706d32` | 848 KB DOM dump of the owner's LinkedIn connections page | repository only |

Recommendation: remove all four from the working tree and from history (same filter-repo pass as 4.1), and drop `network.html` from the site or feed it only aggregated, anonymised cluster sizes.

### 4.3 Repository weight and generated data

`public/` carries about 54 MB of generated JSON and HTML that `daily-scrape.yml` and (formerly) `rag_updater.yml` re-commit; 174 of 382 commits are `github-actions[bot]`. Options: publish the scrape output as a workflow artifact and a separate `gh-pages`/data branch instead of `main`; or keep only the small `hh-experience.json` in `public/` and let the build fetch the rest at build time. At minimum, stop tracking `online_scraped_en.json` and `cluster_map.json` if nothing on the live site reads them (`src/` has no reference to `network.html`, `cluster_map.html` or `vacancy_tree.html`).

### 4.4 Ignored but tracked, and untracked newcomers

- `tools/cv_matcher/chroma_db/fc634e1b-…/{data_level0,header,length,link_lists}.bin` are tracked although `chroma_db/` is ignored. `git rm --cached -r tools/cv_matcher/chroma_db`.
- Untracked `tools/cv_matcher/.agents/skills/apple-design/SKILL.md` and `tools/cv_matcher/skills-lock.json` are a third-party agent skill download (`emilkowalski/skills`). Either commit them deliberately or add `.agents/` and `skills-lock.json` to `.gitignore`; they are unrelated to the product.
- `tools/cv_matcher/.DS_Store` files exist on disk but are not tracked (root `.gitignore` covers them). Fine.

## 5. `tools/cv_matcher` overview

Runtime pieces and how they fit:

- **Backend** `resume_import_server.py` (189 lines) is a FastAPI app served by uvicorn on 127.0.0.1:8788 with a global auth middleware; behaviour lives in `src/` route modules (`archive_routes.py`, `linkedin_routes.py`, `agent_routes.py`, `calendar_routes.py`, `github_collection_routes.py`, `portfolio_publication_routes.py`, `workflow_routes.py`) over SQLite stores (`archive_store.py`, `analysis_store.py`, `application_store.py`, `delivery_store.py`). Every request from the extension or web UI carries `X-Resume-Import-Token` read from `.cache/resume_import/token.txt`.
- **Domain modules**: resume intake and versions, vacancy intake/selection/terms/locations, company catalog and filter, career skills catalog/requirements/evidence/trajectory, application workflow and CRM, cover letters, recruiter answers, Telegram presentation, GitHub collection import/export/control, portfolio publication, HH auto-sync, resume bump, LinkedIn workspace (new), vacancy teams and network map (new).
- **Web UI** `archive-web/` (44 files): one `index.html` plus feature scripts (archive, applications, ranking, trajectories, LinkedIn chats/contacts/profile/job export, vacancy team/export, network map).
- **Chrome executor** `hh-research-extension/` (section 8).
- **Channels**: `telegram_recruiter.py` (Bot API controller + optional Telethon userbot), `career_mcp.py` (thin MCP stdio adapter, extra `mcp`), GitHub Actions import of `online_scraped.json`.
- **Dependencies** (`pyproject.toml`): Python ≥ 3.12, FastAPI/uvicorn (current service), sse-starlette (legacy `server.py`), chromadb, langchain-openai/ollama, sentence-transformers, umap-learn, scikit-learn (legacy RAG path and `cluster_linkedin.py`), playwright (CI scrapers), pypdf, python-calamine. Roughly half of this set serves only the legacy path and the CI scrapers.

## 6. `tools/cv_matcher/docs` inventory

66 Markdown files plus `ideas/sources/manifest.json` and a stray `.DS_Store`. Every file is linked from `catalog.md` and all 732 relative links resolve. The real problem is stale version and status text: four extension-version generations are each presented as "current", and none matches the working tree.

Status abbreviations: **Active** = «Действующая документация», **Archive** = «Архив / исходный материал», **Plan** = «План / backlog», **ADR** = «Архитектурное решение». "Bullet" = linked in `catalog.md` as a bullet under the table, without a status cell.

### 6.1 Top level

| File | Title (H1) | Claims to be | Catalog | What it covers |
|---|---|---|---|---|
| `README.md` | Career Intelligence — документация | 24.10.2026; ext 0.12.4, health 14 | Active | Entry point: start-here table, user scenarios, integrations, how to read statuses, common boundaries. |
| `catalog.md` | Каталог документации | 24.10.2026 | — | Status table of all docs plus four trailing bullets. |
| `applicant_quickstart.md` | Начало работы с Career Workspace | 22.10; ext 0.11.22, health 13 | Active | First run: `npm run career:dev`, load the extension, pair, main flow. |
| `application_crm.md` | CRM откликов · 0.9.0 | 0.9.0 (checked 22.10) | Active | Application stages, HH status kept separately, Telegram/web history. |
| `career_widgets.md` | Панели на сайтах работодателей · 0.10.5 | 0.10.5 | Active | In-page analysis and cover-letter panels on Yandex, Avito, Ozon, T-Bank. |
| `crm_ranking_modes.md` | Обновление 0.10.3: рейтинг, план отклика и два режима ИИ | 0.10.3 | Active | "Rank by resume" page, API vs no-API modes, Google Calendar OAuth. |
| `huawei_search.md` | Huawei R&D Russia — поиск для соискателя | checked 22.10 | Active | Prebuilt HH search links for Huawei research roles. |
| `job_board_testing.md` | Тест общего импорта job boards — 14 октября 2026 | 14.10; Chrome 0.3 | Active | Pilot test of Avito/Ozon scraping and semantic ranking, embedding cost notes. |
| `local_archive.md` | Локальный архив и embeddings | ext 0.11.22 | Active | SQLite archive, sync from the extension, saved rankings, skill analyses. |
| `operations.md` | Запуск, проверка и диагностика | 22.10; ext 0.11.22 | Active | Commands, test matrix (claims 472 Py / 385 JS), symptom table, Pages, backups. |
| `pipeline_audit_2026_10_16.md` | Исправления конвейера — 0.11.2 | 0.11.2 | Archive | Fixes to notification outbox, scheduled search, cost guards, connection checks. |
| `recruiter_answer_quality.md` | Ответы рекрутеру: источники и проверка качества | checked 22.10 | Active | Grounding rules (R/U/H/G sources) for recruiter answers. |
| `release_0_10.md` | Рабочий поиск 0.10.2 · 16 октября 2026 | 0.10.2–0.10.5 | Archive | 0.10.x release notes: options wizard, HH tab handling, employer sites. |
| `release_2026_10_22.md` | Срез реализации и документации — 22.10.2026 | ext 0.11.22; 478 Py tests | Active | Feature snapshot: hybrid collection, CV views, trajectories, GitHub import, portfolio. |
| `release_2026_10_23.md` | Изменения 23.10.2026 | 500 Py / 391 JS | Bullet | GitHub Actions import fixes, Meta GraphQL v2, Locations, company region filter. |
| `release_2026_10_24.md` | Обновление 24.10.2026 — контакты, чаты и управляемое чтение LinkedIn | ext 0.12.4; 530 Py / 413 JS | own wording | LinkedIn contacts/chats/jobs, read pacing, vacancy teams, Telegram reminders. |
| `research_search.md` | Поиск Research Engineer ML | checked 22.10 | Active | Generated search-link plan (no date limit); produced by `scripts/build_research_search.mjs`. |
| `research_search_daily.md` | Поиск Research Engineer ML | checked 22.10 | Active | Same plan limited to the last 3 days. |
| `resume_catalog_testing.md` | Проверка расширения 0.5.1 — 14.10.2026 | 0.5.1–0.6.3 | Active | Very old extension test log for resume catalog and import. |
| `roadmap.md` | План развития | 23.10.2026 | Plan | Implemented foundation, remaining LinkedIn acceptance, next directions. |
| `service_assessment.md` | Что решает сервис сейчас | 22.10.2026 | Active | Table of job-seeker problems, current help and limits. |
| `telegram_user_flow.md` | Telegram как пульт поиска работы — 0.10.7 (file starts with a 0.10.10 update block) | 0.10.7–0.10.10 | Active | Telegram as remote control, company forms, history, answer quality. |
| `telegram_userbot.md` | Управляемый отклик: расширение + Telethon + управляющий бот | ext 0.9.0 | Active | Telethon userbot plus control bot, setup steps. |
| `workflow_and_adapters.md` | Поиск, оценка и отклик (same 0.10.10 preamble as above) | 0.8.1–0.10.10 | Active | Collection modes, HH marks, inline HH actions, skipping closed vacancies. |

### 6.2 `architecture/` and `architecture/adr/`

| File | Title | Claims to be | Catalog | What it covers |
|---|---|---|---|---|
| `application-layer.md` | Общий application layer и Career MCP | 22.10; ext 0.11.22 | Active | `CareerApplication`, runtime scheduler and lease, task IDs, MCP tools, permissions. |
| `career-trajectory.md` | Карьерная траектория · 22.10.2026 | 22.10 | Active | Editable goal, stages, criteria, evidence; matching vacancies and CVs. |
| `current-state.md` | Фактическая архитектура | 24.10; ext 0.12.4 | Active | Current components, data, adapters, ranking, execution, LinkedIn. The best "what exists now" doc. |
| `domain-model.md` | Сущности и связи | 22.10 | Active | Logical entity model over SQLite with Mermaid diagram (shorter sibling of root `docs/career-domain-model.md`). |
| `gap-analysis.md` | Разрывы между реализацией и целевым конвейером | 19–22.10; API 13 | Active | Historical gap register G01…G16 with priorities. |
| `hybrid-collection.md` | Гибридный сбор вакансий | 22.10; ext 0.11.22 | Active | Python/Chrome collection order, backfill, quota, source matrix. |
| `repository-and-autofill.md` | Корневой проект, расширения и корпоративное заполнение | 20–22.10 | Active | Map of repository folders and both extensions; corporate autofill limits. |
| `resume-portfolio-review.md` | Сравнение нескольких резюме под карьерный трек | 22.10 | Active | AI review of 2–7 CV snapshots against a track and timeline. |
| `skills-intelligence.md` | Career Skills Intelligence: аудит и границы реализации | 20.10 | Active | Skills module: requirements, evidence, priorities, quality limits. |
| `target-state.md` | Целевая архитектура | 19–22.10; API 13 | "current implementation" | Target boundaries, data contracts, ranking, unified apply flow. |
| `vacancy-teams.md` | Команды, контакты и исследовательские стримы | 24.10 | Bullet | Vacancy team, contacts, research streams; LinkedIn and HF as sources. |
| `adr/0001` … `adr/0005` | Reuse existing workflow; SQLite authoritative + Chroma legacy; thin MCP with human approval; stay local, 24/7 deferred; Telegram as primary mobile control | 19.10 (status notes 22.10) | ADR | Five decision records; each has a status preamble. |

### 6.3 `handoff/`, `ideas/`, `ideas/sources/`

| File | Claims to be | Catalog | What it covers |
|---|---|---|---|
| `handoff/2026-10-19-architecture-audit.md` | 19–20.10 | Archive | Original audit of components, extension, sources, stores, embeddings, Luna. |
| `handoff/2026-10-20-agent-planning-brief.md` | 20.10 | Archive | Handoff of the actual state to the next planning agent (health 13, 0.11.18). |
| `handoff/input-development-idea-2026-10-20.md` | 20.10 | Archive | 1 233-line user brief; a near-identical copy of `ideas/sources/evolutionary-career-platform.md` (2 lines differ). |
| `ideas/README.md` | 20.10 | Plan | Backlog index. |
| `ideas/01-market-radar.md` … `06-learning-and-evidence.md` | none | Plan | Six backlog ideas: market radar, career value and feedback, adaptive extraction, application agent, evolutionary architecture, learning and evidence. |
| `ideas/llm-adapter-repair.md` | status 22.10 | Plan | LLM-proposed selector repair for broken adapters; not implemented. |
| `ideas/sources/ai-native-extraction.md`, `evolutionary-career-platform.md`, `supervised-application-agent.md`, `market-intelligence-chat.md` | 20.10 | Archive | Verbatim or paraphrased user inputs; `manifest.json` stores sizes and SHA-256 of the three verbatim ones. |

### 6.4 `integration/` and `usage/`

| File | Title | Claims to be | Catalog | What it covers |
|---|---|---|---|---|
| `career-analytics-telegram.md` | Карта возможностей и единый Telegram-рейтинг | 19.10; health 13 | Active | `/archive/analytics`, Sankey, shared top-10 ranking in Telegram. |
| `github-import-and-portfolio.md` | GitHub collection + primary HH portfolio | 22.10 | Active | GitHub Runs import to SQLite; HH CV feeding the public portfolio. |
| `hh-resume-bump.md` | Бесплатное поднятие HH-резюме | 20.10; ext 0.11.17/18 | Active | Opt-in, owner-confirmed free HH resume bump. |
| `linkedin-adapters.md` | LinkedIn: локальное управление через Chrome Extension | 24.10; ext 0.12.4 | "implemented; live check per capability" | Profile, jobs, chats, contacts via the extension; verification limits. Most complete LinkedIn doc. |
| `linkedin-chat-advice.md` | Анализ переписки и карьерные рекомендации | 24.10 | status cell holds a description | Chat analysis via API or clipboard prompt with JSON import. |
| `public-portfolio.md` | Публичное портфолио: данные, визуализации и мобильная версия | 22.10 | Active | Public site data sources, visuals, mobile, SEO, PWA. |
| `resume-comparison.md` | Resume document comparison and workspace reading (English) | 22.10 | Active | CV snapshot chunk comparison, alluvial view, document import. |
| `telegram-career-e2e.md` | Telegram → … → Human Review | 19.10; ext 0.11.16 | Archive (but README.md:24 links it as current) | End-to-end Telegram-driven path with state per step. |
| `telegram-notifications.md` | Telegram: расписание и очередь действий | 24.10 | Bullet | Scheduled reminders from Today/CRM queue. |
| `workspace-ux.md` | Фокус рабочего места | 20.10 | Active | UI refactor: Today next action, vacancies, rating, applications. |
| `usage/company-filter.md` | Компании, регионы и пакетный расчёт | none | Bullet, no status | Company region/tier filters, batch ranking of saved vacancies. |

### 6.5 Consistency problems found

- **Extension version claimed as current**: 0.12.4 (README, release_24, linkedin-adapters, current-state); 0.11.22 (quickstart, application-layer, release_22, local_archive, operations, career_widgets, workflow_and_adapters, hybrid-collection, repository-and-autofill); 0.11.18 (planning brief, hh-resume-bump, audit); 0.11.16 (telegram-career-e2e, career-analytics-telegram, gap-analysis, target-state); 0.10.5 (career_widgets:9 tells the reader to install that folder); 0.9.0 (telegram_userbot:5). Actual: `manifest.json` is 0.12.0 at HEAD, 0.12.4 in the index, 0.13.2 in the working tree; `resume_import_server.py:91` returns health version 14 and collection protocol 2, so "health 14 / protocol 2" is correct.
- **Test counts** claimed as current: operations.md:37 says 472 Py / 385 JS, release_22 says 478, release_23 says 500 / 391, release_24 says 530 / 413. Measured today: 544 Py / 421 JS. Keep the number in one place or drop it.
- **Catalog structure**: four files are trailing bullets without a status (`release_2026_10_23.md`, `usage/company-filter.md`, `architecture/vacancy-teams.md`, `integration/telegram-notifications.md`, catalog.md:71–76); catalog.md:48 has a description instead of a status; catalog titles differ from the H1 for five files; `telegram_user_flow.md` and `workflow_and_adapters.md` start with a byte-identical 22-line 0.10.9/0.10.10 preamble.
- **Old docs still labelled Active**: `resume_catalog_testing.md` (0.5.1), `job_board_testing.md` (Chrome 0.3), `telegram_userbot.md` (0.9.0), `career_widgets.md` (0.10.5), `release_2026_10_22.md`.
- **Status mismatches**: `telegram-career-e2e.md` is Archive in the catalog but the README presents it as the current live-verification doc; `target-state.md` is labelled "current implementation" while carrying the API 13 / 0.11.16 banner; the audit calls the planning brief the "current snapshot" although both are archived.
- **Paths and ports are fine**: every referenced `scripts/*`, `src/*`, `hh-research-extension/*`, `archive-web/*` path and npm script exists; 8788 is the main service everywhere and 8787 appears only as legacy.
- **Generated docs**: `research_search*.md` come from `scripts/build_research_search.mjs`, which does not emit the manual "Сверка 22.10.2026" header, so regenerating will drop it (inferred from the script, not run).

### 6.6 Overlaps worth merging

`research_search.md` + `research_search_daily.md` (same generator); `telegram_user_flow.md` + `workflow_and_adapters.md` (shared preamble, both stale); `handoff/input-development-idea…` + `ideas/sources/evolutionary-career-platform.md` (same 1 200-line brief twice, keep the `sources/` copy with its checksum); audit + `gap-analysis.md` + `target-state.md` (same stacked 19–20.10 banners; `current-state.md` supersedes them); six Telegram docs of which only `telegram-notifications.md` and ADR 0005 reflect the current state; `applicant_quickstart.md` + `operations.md` (same commands, both at 0.11.22).

### 6.7 Verdict on the docs folder

Navigable and fully linked, but the catalog's "Active" label hides that roughly a third of the "active" docs are historical release notes. Three cleanups fix most of it: keep the extension version, health version and test counts in exactly one file; re-label old docs as Archive and move the four trailing bullets into the table; delete the duplicate brief, the shared Telegram preamble, the stacked banners and `.DS_Store`.

## 7. Is `linkedin-scraper-extension` legacy? Yes.

Evidence:

| Signal | Old path | Current path |
|---|---|---|
| Files | `linkedin-scraper-extension/{manifest.json,content.js,popup.html,popup.js,userscript.user.js}` (228 lines, author header "Antigravity", v1.0, MV3 with `host_permissions: *://*.linkedin.com/*` and `downloads`) | `hh-research-extension/linkedin-core.js` (64), `linkedin-content.js` (282), `linkedin-worker.js` (142) behind optional host permission `https://www.linkedin.com/*` |
| What it does | Scrolls `/mynetwork/invite-connect/connections/`, collects `a[href*="/in/"]`, downloads `linkedin_connections.json` | Paced, resumable contact walks driven by backend commands (`src/linkedin_contacts.py`, table `linkedin_contact_collections` joined to `browser_commands`), plus profile, job, and chat capture (`src/linkedin_workspace.py`, 732 lines) with pacing rules (`src/linkedin_pacing.py`) |
| Consumers | `scripts/cluster_linkedin.py` (bge-m3 + UMAP → `public/linkedin_clusters.json`), `public/network.html` | `src/network_map.py` (source-backed team/stream/person/vacancy graph in SQLite, no public export) |
| Alternative scraper of the same era | `scripts/scrape_linkedin.py` (Playwright, injects `LINKEDIN_LI_AT` from `.env`, writes `data/linkedin_connections.json`) | not needed; the extension reads the logged-in tab |
| Last commits | `c706d32` 01.05.2026, `f87d547` 09.07.2026 | `db418fb` 23.10.2026, `cf8e6b9` 24.10.2026 and the current uncommitted work |
| References | one bullet in `tools/cv_matcher/README.md:25` (and `:19` for `scrape_linkedin.py`); nothing in `docs/`, `catalog.md`, `workspace.projects.json`, manifests or tests | documented in `docs/integration/linkedin-adapters.md`, `linkedin-chat-advice.md`, `release_2026_10_24.md` |

Retire as one unit: `linkedin-scraper-extension/`, `scripts/scrape_linkedin.py`, `scripts/cluster_linkedin.py`, `data/linkedin_connections.json`, `src/debug_linkedin_connections.html`, the `LINKEDIN_*` keys in `.env`, the ignored `linkedin_profile/` Chrome profile directory, `public/linkedin_clusters.json` and `public/network.html`, and the two README bullets. If the old userscript is worth keeping as a reference, move it under `docs/handoff/` as text rather than leaving an installable extension next to the main one; `docs/workspace.md` already forbids mixing the two manifests.

## 8. `hh-research-extension` review

Manifest V3, version 0.13.2 in the working tree (0.12.0 at HEAD). 90 source files, 68 Node test files, adapters compiled from `adapters/*.json` into `board-adapters.js` (verified in sync by `scripts/build-adapters.mjs --check` and by `adapter-build.test.mjs`). Paths below are relative to `tools/cv_matcher/hh-research-extension/` unless stated; "confirmed" means the code path was read end to end during this review.

### 8.1 Findings, ranked

| # | Severity | Finding | Evidence |
|---|---|---|---|
| E1 | Medium | The service token is persisted to `chrome.storage.local` when the user ticks "remember" in setup, and every request falls back to that copy. README.md:191 claims the code lives only in `storage.session`. Only `pairing_forget` erases it. Blast radius is limited to 127.0.0.1:8788, but the doc statement is false. | `local-service.js:11`, `:21`; `setup.js:37`; `hh-connection.js:76`. Confirmed. |
| E2 | Medium | README.md:195 says collection never runs on a schedule, but two one-minute alarms do: `hh-workflow` claims automatic sync commands and opens a disposable HH tab; `linkedin-workspace` claims and performs LinkedIn reads and the mutations `profile.fill/save` and `network.execute` on every service-worker wake. The user is told the extension is passive while it acts on queued commands unattended. | `hh-workflow.js:131-135`, `:36-42`; `linkedin-worker.js:139-141`. Confirmed. |
| E3 | Medium | LinkedIn automation has an "on" switch but no "off". Setup sends `linkedin_enable`, the worker stores `enabled=true` in IndexedDB `linkedin-receipts-v1`; nothing in the extension or `archive-web/` writes `linkedin_enabled=false` or deletes the key. The only client-side stop is revoking the host permission; otherwise only the server-side `paused` flag. | `setup.js:56`; `linkedin-worker.js:133`, `:140`; grep for `linkedin_disable` returns nothing. Confirmed. |
| E4 | Medium | Docs drift. README.md:1 says 0.11.18, manifest says 0.13.2; README.md:181 lists permanent permissions `activeTab, scripting, storage` but manifest.json:10 adds `alarms`; README.md:183-186 lists only 127.0.0.1 and Google as optional hosts while manifest.json:22-31 adds hh.ru, Avito, Ozon ×2, Yandex ×2, Sber, T-Bank ×2 and LinkedIn; README and DEVELOPMENT.md contain zero mentions of LinkedIn although it is now the largest subsystem; README.md:31 "283 JS / 264 Python tests" is stale (421 / 544 today). | Confirmed. |
| E5 | Medium | DEVELOPMENT.md module map (lines 16-32) omits `linkedin-core/content/worker.js`, `hh-cleanup-*.js`, `resume-bump-*.js`, `hh-connection-probe.js`, `workspace-bridge.js`, `hh-cleanup.html`. Its security sentence (page code never receives the token) and diagnostics claims are accurate. | Confirmed. |
| E6 | Medium | `ready(id,url)` never checks that the tab reached the requested URL (the parameter is unused); `managed()` reuses a stored tab; `jobs.navigate` is an SPA click after which `ready` returns at once. In content, only `network.list` asserts the current URL equals the requested one; `jobsListing` and `messagesListing` do not, whereas `job()` and `thread()` do. Cards from a stale or wrong listing can be checkpointed under a command that asked for another URL. | `linkedin-worker.js:11-12`, `:68`; `linkedin-content.js:101-118`, `:134-138`, `:159`, `:169`, `:227`. Plausible, not reproduced. |
| E7 | Medium | LinkedIn pacing is partly client-side and aggressive for contacts: jobs/messages loops up to `max(150, 3×limit)` passes with a click every `interval_ms` (default 3 s); `network.list` up to `min(2000, 100+known)` passes at 900 ms. Server pacing (`src/linkedin_pacing.py`: batches 8-12, 3-8 s delay, 60 s pause) is applied through `claim`/`progress.wait_ms` only to `jobs.*` and `messages.*`; contact listing has no server pacing. `activate()` steals window focus by design. Account-restriction risk. | `linkedin-worker.js:70`, `:81`, `:85`; `src/linkedin_workspace.py` `claim`. Plausible. |
| E8 | Low | `network.execute` injects into a server-supplied `snapshot.tab_id` without checking the tab URL, unlike `current()`. Fails safe only because the content gate rejects non-LinkedIn URLs and `execute()` re-compares the target fingerprint. | `linkedin-worker.js:60`, `:13`; `linkedin-content.js:8`, `:250`. Confirmed mitigation. |
| E9 | Low | HH response cleanup is approved in the extension UI only (confirm flag, matching `plan_id`, keys validated with a 10-minute expiry, plan consumed before execution); the backend only receives `observe`. Per-item guards are strong (key re-match, dialog title check, single click, verify loop, `uncertain` on doubt), but this deviates from the "backend approves each irreversible item" model used by HH submit and resume bump. The scan tab is never closed after execution. | `hh-cleanup-worker.js:56`, `:59-66`, `:89-92`; `hh-cleanup-core.js:10-14`; `hh-cleanup-content.js:36-60`. Confirmed. |
| E10 | Low | A persistent content script is registered for `http://127.0.0.1/*` (all ports); `workspace-bridge.js` self-exits unless the origin is `:8788`, and the worker checks origin, but the script is still injected into unrelated local dev servers. Use `http://127.0.0.1:8788/*`. | `hh-connection.js:63`; `workspace-bridge.js:2`, `:4-6`. Confirmed. |
| E11 | Low | Several `onMessage` handlers validate only `sender.id`: `archive-sync.js:68`, `board-crawl.js:4`, `hh-crawl.js:4`, `resume-worker.js:69` (then injects into `message.tabId`), `linkedin-worker.js:140`. Not exploitable today (no `externally_connectable`, no `postMessage` listener except the pinned bridge, isolated world), but the sensitive handlers (`diagnostics-worker.js:3`, `hh-cleanup-worker.js:74`, `hh-workflow.js:121`, `hh-connection.js:73`, `hh-badges-background.js:23`) are stricter and the rest should match. | Confirmed defence-in-depth gap. |
| E12 | Low | `resumes.js:42-45` bypasses `LocalResumeService`: reads the token straight from `storage.session` and fetches `/extract` directly, so there is no path allowlist and no remembered-token fallback; after a restart with "remember" ticked this page says "connect" while others work. | Confirmed. |
| E13 | Low | `dom()` re-injects 44 KB (`linkedin-core.js` + `linkedin-content.js`) before every per-pass call in a listing run; a presence check on `globalThis.LinkedInSession` would avoid hundreds of injections. | `linkedin-worker.js:10`. Confirmed. |
| E14 | Low | Exception used as control flow for "see more": the content script clicks the expander then throws; after 24 retries the message text surfaces as the `needs_input` reason. | `linkedin-content.js:177`; `linkedin-worker.js:108-123`. Confirmed. |
| E15 | Low | The `board-core.js` diff adds hash-fragment IDs for `app.mokahr.com` and `zhaopin.kuaishou.cn`, mirrored in `src/board_import.py:19-21` (parity OK), but no `*.test.mjs` covers either host and neither host is in `optional_host_permissions`, so only Python can crawl them. DEVELOPMENT.md:43 requires both sides to change together; the JS side is untested. | `board-core.js:7-9`. Confirmed. |
| E16 | Low | 24 of the 68 test files in this folder test `../archive-web/*.js` (the web UI), including 7 of the 8 new ones; only `linkedin-navigation.test.mjs` and the `linkedin.test.mjs` diff test extension code. `scripts/check.mjs:20` reports them all as extension checks, and a ZIP built from the folder ships web-UI tests. | Confirmed. |
| E17 | Low | Density rather than length: no file exceeds 331 lines, but `linkedin-content.js` is 44.7 KB in 282 lines (one IIFE, lines over 600 characters), `hh-inline-ui.js` 34 KB, `popup.js` 27.8 KB, `linkedin-worker.js` 24 KB with a 107-line `perform()`. A `visible` helper is re-implemented in 8 files, the timeout-race helper 5 times, and every UI test declares its own fake-DOM class. The core/content/worker split is mostly honoured; exceptions are inline DOM functions in workers (`hh-workflow.js:58`, `browser-navigation.js:35-44`) and `hh-badges-background.js` mixing orchestration with validation. | Confirmed. |
| E18 | Low | Only `resume-profile.example.json` is referenced by nothing; every other file is reachable from the manifest, an HTML page, `importScripts`, an `executeScript` file list, a test or Python. A `.DS_Store` sits in the folder (ignored, but would be zipped). | Confirmed. |

### 8.2 What is done well

- Token hygiene in the browser: content scripts never receive the token; `local-service.js:3` allowlists endpoints and `:16` validates the 43-character code; the diagnostics report is a projection of booleans, counts and host names (`diagnostics-core.js:6-26`) served only to `diagnostics.html`.
- No `innerHTML`, `insertAdjacentHTML`, `eval` or `new Function` anywhere in the extension or in `archive-web/`; LinkedIn links are canonicalised and `javascript:`, credentialed and `localhost` targets are rejected (`linkedin-core.js:5-14`, `:49`, with tests).
- HH submit is genuinely one-shot: claim with form fingerprint before any click (`hh-workflow.js:71` → `src/application_workflow.py:355`), `verifyApproved` re-reads the form and compares every field to the approved answers (`hh-apply-core.js:15-20`), CV hash check, single click, then `uncertain` rather than retry; the server blocks new actions while `sending/uncertain`.
- Resume bump: `resume_bump_claim` before the click, fingerprint + 15 s expiry + per-command click latch in the page, server refuses re-claim (`src/resume_bump.py:82`).
- LinkedIn mutations fail closed: unknown or ambiguous buttons throw, dialogs with extra inputs stop, message and invite forms are rejected for fill, lost results become `uncertain` after 180 s and are never re-queued.
- Tests are behaviour-level: fake-DOM traversal of 83 jobs across pagination and infinite scroll asserting 80 unique IDs, URL-canonicalisation security cases, "no generate call happened" assertions in UI tests.

### 8.3 Verdict

The irreversible paths (HH submit, HH deletion, resume bump, LinkedIn profile save and connection actions) are gated with fingerprints, one-time claims and "uncertain, never retry" semantics on both sides; that design is sound and consistently implemented. The gaps inside the extension are about operational honesty rather than exploits: the token can live in `storage.local`, two one-minute alarms act unattended while the README promises no scheduling, and LinkedIn automation cannot be switched off from the UI. The new LinkedIn modules work but are dense 25-45 KB files with client-side pacing, unverified navigation targets and heavy re-injection; they need a URL check in `ready()`, listing-page assertions and an off switch before daily reliance. README (0.11.18) and DEVELOPMENT.md are two minor versions behind the code and omit LinkedIn, cleanup, bump and the extra permissions entirely.

## 9. Review of the uncommitted working tree

Scope: 51 modified and 19 untracked files under `tools/cv_matcher` plus `.github/workflows/daily-scrape.yml`; the extension part is covered in section 8 and `.env` in section 4. All changed Python files pass `py_compile` and all changed JS files pass `node --check`; the two suites pass (section 1).

### 9.1 What the diff adds

This is "LinkedIn workspace v2" plus adjacent features. LinkedIn job collection becomes paced (persisted random batch size 8-12, 3-8 s delays, 60 s breaks, auto-pause on a login or verification message); cards and full job descriptions are separated, with logos, apply/ATS URLs and visible signals, and jobs enter the main archive only through an explicit import action. Contacts gain multi-scope collection with durable "collect all" batches and only-new continuation, a full-database search with headline-based relevance classification, and a local, reversible review plan (keep/unfollow/disconnect as a plan only). Chats get a message reader with ID-based merge and pagination, and an opt-in chat-advice analysis (OpenAI with explicit confirmation and a single paid attempt per context key, or copy-prompt/import-JSON without API). Vacancies gain a "team" tab (hiring team via the extension, Hugging Face organisation members via public API) with evidence-backed stream annotations, a network-map tab, and a clipboard vacancy export with résumé and trajectory context; profile editing adds open/fill/save with a verification re-read and version history. Nine Chinese employer scrapers (Moka, Feishu, Tencent, Kuaishou, Alibaba portals) are registered for CI and the company catalog, with SPA-fragment job identities for Moka and Kuaishou. Docs and the 24.10 release note are updated accordingly.

### 9.2 Checked and found sound

- The backend is FastAPI (`resume_import_server.py:45`) with a global middleware that requires `X-Resume-Import-Token` or an archive cookie session for every request except `GET /`, `/archive`, `/assets/*`, the calendar callback and `POST /archive/login`. All four new routes (`/archive/vacancy-export`, `/archive/network`, `/archive/vacancy-team`, `/archive/linkedin-chat-analysis`) sit on that app and are added to the cookie allow-list with an Origin check (`src/archive_routes.py:20-23`); tests assert 401 without auth. Extension-only operations stay token-gated (`src/linkedin_routes.py:26`).
- All SQL read is parameterised; request bodies are bounded (40 KB / 500 KB / 1.5 MB); asset names are whitelisted; no `innerHTML` in the changed front-end; `external()` emits only http(s) links; every `$('id')` used by the new scripts exists in `index.html`.
- No `ALTER TABLE`: every new table and index is `CREATE … IF NOT EXISTS` inside a lazily called `init()`, so existing databases upgrade in place.
- OpenAI is called only in `linkedin_chat_analysis.run` with `confirmed=True`, one attempt per context key, behind a confirmation dialog; nothing sends LinkedIn or Telegram messages. The chat-advice cache key is a digest of the full context (resume hash, goal, trajectory, model, per-thread source hashes).
- `daily-scrape.yml` changes only the input description; scheduled default sources are unchanged and no new secret handling is introduced. `linkedin_pacing.py` math is epoch-based and correct; `linkedin_messages.merge` ordering is correct for prepend, append and interleave.
- New tests are behavioural (pacing maths with serialisation round-trip, message merge order, quote/speaker validation, cached single API call with injected client, 401/Origin checks, Hugging Face mocked); none needs network or `.env`.

### 9.3 Findings, ranked (no critical or high)

| # | Severity | Finding | Evidence |
|---|---|---|---|
| D1 | Medium | `collect_all` leaks from chats into contact collections. The `collect_all` branch in `enqueue` runs for any action carrying the flag; `messages.list` sets it (`linkedin_workspace.py:223`) and the chats UI defaults it to true (`archive-web/linkedin-chats.js:5`). One click on "Собрать диалоги" inserts a `linkedin_contact_collections` row with scope `all` that `result()` never finalises (contacts `observe()` is only reached for `network.list`), so the Contacts tab shows a bogus "0 contacts / Ожидается расширение" collection that flips to `needs_input` forever, and the next chats run resumes that row and injects `only_new=True, known_contacts=[]` into the messages payload. | `src/linkedin_workspace.py:304-322`; `src/linkedin_contacts.py:25`. Confirmed. |
| D2 | Medium | No zero-progress guard in contact collection. Termination relies on the worker returning an empty list; a batch that returns only already-known profiles (links non-empty, `observed` unchanged) still enters the `else` branch and enqueues another 300-contact `network.list`. Any URL-normalisation mismatch between `known_contacts` and the worker's skip list chains unbounded automated LinkedIn reads until the owner presses stop. Fix: stop when `len(observed)==len(data['links'])`. | `src/linkedin_contacts.py:50-54`. Confirmed. |
| D3 | Medium | DeepSeek identity collapses. The portal is `https://talent.deepseek.com/` with `#/job/<id>` links, but `identity()` keeps SPA fragments only for `app.mokahr.com` and `zhaopin.kuaishou.cn` and strips the fragment for every other host, so all DeepSeek anchors canonicalise to the portal root with one shared `board_` id; `seen` dedups after the first and the run yields at most one DeepSeek vacancy. The `source_key=='deepseek' and seen` special case at `china.py:195` suggests this was already observed. | `src/scrapers/china.py:173-177`; `src/board_import.py:18-25`, `:57-60`; `hh-research-extension/search-profile.json:463`. Plausible. |
| D4 | Medium | Local default scrape plan now includes all nine China adapters. `_source_plan` appends them unconditionally and `--scrapers` has no default (`allowed=None` runs the whole plan). A plain local `python scripts/scrape_online.py` (the documented way to run Sber) now launches headless Chromium against nine Chinese portals, each up to 1000 pagination passes. CI is unaffected because the workflow always passes `--scrapers`. | `scripts/scrape_online.py:94-95`, `:142`, `:160`. Confirmed. |
| D5 | Medium | Preset teams split in two. `link_contact` resolves `preset:*` with `company=''` while `link_vacancy` resolves the same preset with the vacancy's company; the team id is `digest({company,name})`, so selecting virtual "GigaChat", linking a contact and then a vacancy creates two different "GigaChat" teams, both listed in the directory. | `src/network_map.py:24-31`, `:97-105`; `archive-web/network-map.js:44`. Confirmed. |
| D6 | Low | `pacing.complete()` runs for every terminal `jobs.detail` / `messages.thread` outcome including cancelled and failed, so cancelling a batch still consumes pacing slots and can trigger the 60 s pause before the next legitimate read. | `src/linkedin_workspace.py:539-540`. Confirmed. |
| D7 | Low | Contact search is `instr(casefold(payload||notes), ?)` over raw JSON, so keys and URLs match: queries like "in", "http", "name" or "scope" match every contact, and names containing a double quote never match because of JSON escaping. | `src/linkedin_workspace.py:594-595`. Confirmed. |
| D8 | Low | In chat analysis the owner's messages are tagged `candidate` only when a `profile.read` snapshot exists and the sender equals its title exactly; otherwise they become `participant_N`, so the "strong or negative interest needs a quote from the other side" check can be satisfied by the owner's own message before the first profile read. | `src/linkedin_chat_analysis.py:54-62`, `:114`. Confirmed. |
| D9 | Low | `collect_huggingface` lets `requests` ConnectionError/Timeout escape (they are not `ValueError`), so clicking the Hugging Face button offline returns a generic 500 instead of a 422 message. | `src/vacancy_team.py:103`, `:153`. Confirmed. |
| D10 | Low | Legacy `import_on_capture` path: for jobs commands queued before this release, `head` is built from the new record payload (includes `apply`, `recommendation_sections`) and written straight into `entities`, bypassing the `FIELDS` filter that `import_jobs` applies. A stale pre-upgrade `jobs.list` completing after restart stores non-schema keys in the entity payload. | `src/linkedin_workspace.py:507-509`, `:559`. Confirmed. |
| D11 | Low (privacy) | CSP `img-src` now allows `media.licdn.com` and `static.licdn.com`, so rendering the contacts and jobs lists fetches per-person avatars from LinkedIn's CDN. `referrerPolicy=no-referrer` is set, but where third-party cookies are allowed LinkedIn can observe which saved contacts the dashboard renders. | `src/archive_routes.py:85`; `archive-web/linkedin-contacts.js:31`; `linkedin.js:25`. Confirmed. |
| D12 | Low (hygiene) | `.agents/skills/apple-design/SKILL.md` and `skills-lock.json` are untracked and not ignored (`git check-ignore` exit 1): a vendored third-party AI skill unrelated to the product. Ignore or commit deliberately. | Confirmed. |
| D13 | Low (tests) | No test at all for `src/scrapers/china.py` (`parse_feed`, `moka_detail`, identity for Moka/Kuaishou fragments); none for D1, D2 or D5; and `test_linkedin_workspace.queue()` now zeroes `read_pacing.next_at` before every claim, which hides pacing interactions from the older tests. | Confirmed. |

### 9.4 Readiness

Not ready to commit as is. Fix D1 and D2 (the chats flag leaking into contact collections, and the zero-progress guard), decide on the DeepSeek identity (D3), gate the China adapters out of the local default plan (D4), and ignore `.agents/` and `skills-lock.json` (D12) first; everything else can follow in later commits. Above all, do not run `git add -A` while `.env` is tracked (section 4.1).

## 10. Recommended order of work

1. Rotate credentials, untrack `.env`, purge history (4.1, 4.2) — today.
2. Remove published LinkedIn contact data from `public/` and redeploy (4.2).
3. Decide what to do with daily bot commits of 54 MB JSON (4.3).
4. Delete the legacy LinkedIn pipeline (section 7) and the tracked ChromaDB binaries (4.4).
5. Fix the version numbers and permission lists in the three READMEs (finding 5) and apply the docs cleanup in section 6.
6. Before committing the current working tree: fix D1, D2, D4, D5 and decide D3 (section 9.3); add the LinkedIn off switch, the URL check in `ready()` and the `127.0.0.1:8788` match pattern (E3, E6, E10); then update the extension README and DEVELOPMENT.md for 0.13.x, `alarms`, the full optional-host list and the LinkedIn, cleanup and bump modules (E4, E5).
7. Schedule the retirement of the FastAPI/Chroma path (`server.py`, `cv_matcher.py`, `viewer/`, `scratch/`, `matcher.html`, `scrape.html`, `src/matcher.ts`, `src/scrape.ts`, `rag_updater.yml`) or move it under a clearly named `legacy/` folder, and prune the unused dependencies from `pyproject.toml` afterwards.
