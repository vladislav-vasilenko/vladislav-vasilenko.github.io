# AGENTS.md: Career Workspace (`tools/cv_matcher`)

Guidance for coding agents. **Start with [`memory/plan.md`](memory/plan.md). It indexes the work stages: a spec for each in `specs/`, and machine-readable results in `reports/`, including the investigation in `reports/00-investigation.json`. Keep the status table and reports current.**

## What this is

A personal, local job-search service. It collects vacancies, stores them with version history in SQLite, and supports reviewing and applying to them. The parent repository is the public portfolio site, so **everything committed here is public**.

| Part | Where | Notes |
| --- | --- | --- |
| Local service | `resume_import_server.py`, `src/archive_routes.py` | FastAPI on `127.0.0.1:8788`, token or cookie auth |
| Archive storage | `src/archive_store.py`, `src/analysis_store.py` | SQLite at `.cache/applications/state.sqlite3` |
| Review UI | `archive-web/` (`archive.js`, `career-analytics.js`) | Plain JS with no build step, strict CSP |
| Opportunities screen | `src/career_analytics.py`, `archive-web/career-analytics.js` | "Карта возможностей", endpoint `GET /archive/analytics` |
| Scheduled crawlers | `scripts/scrape_online.py`, `src/scrapers/` | Run by `.github/workflows/daily-scrape.yml` at the repo root |
| CI to local import | `src/github_collection_export.py`, `src/github_collection_import.py` | The Actions artifact is imported into SQLite |
| Browser crawler | `hh-research-extension/` | Chrome extension, collects through the user's own tabs |
| Legacy, do not extend | `server.py` (port 8787), `viewer/`, `linkedin-scraper-extension/`, `cv_matcher.py` | |

More background: `README.md`, `docs/README.md`, `docs/architecture/`, `docs/security.md`.

## Commands

Run from `tools/cv_matcher` unless noted.

```bash
.venv/bin/python scripts/test-isolated.py     # Python tests in a disposable copy
node --test archive-web/tests/*.test.mjs      # UI tests
.venv/bin/python resume_import_server.py      # run the service (or `npm run career:dev` from the repo root)
node hh-research-extension/scripts/check.mjs  # extension checks (`npm run career:check` from the repo root)
.venv/bin/python scripts/service.py restart    # run the service as the Dock app does: open, url, status, restart, stop
.venv/bin/python scripts/install_macos_app.py # rebuild the Dock app; rerun after moving the project
```

## Rules

- **Never run tests, benchmarks or experiments against the real database.** It holds personal data. Copy it to the session scratchpad first, then delete the copy:
  `sqlite3 "file:.cache/applications/state.sqlite3?mode=ro" ".backup <scratchpad>/copy.sqlite3"`
- **Don't commit or push unless asked.** If asked while on `main`, branch first.
- **Never commit** `.env`, `.cache/`, `.auth/`, `chroma_db/`, `linkedin_profile/`, or anything holding CV text, contacts or tokens. `node tools/workspace.mjs check` from the repo root checks the git index.
- **Reports in `reports/` are public once committed.** Use aggregate numbers only, with no vacancy text, CV content, contacts or tokens.
- **Paid API calls need explicit user action.** Page views and filters must not call OpenAI or other models.
- **Don't infer closure.** A vacancy missing from a listing is not proof it closed, and absent scores are not zero. The UI says this deliberately.
- **Migrate user data reversibly.** Relabel rather than delete, record a marker in `archive_meta`, and look at the data first.
- UI text is in Russian. Render with `textContent` through the `make()` helper, never `innerHTML` with data. The CSP forbids inline scripts and styles, so new assets must also be added to the allowlist in `src/archive_routes.py`.

## Environment quirks

- The shell is zsh on macOS: an unquoted `===` in `echo` errors out, and `timeout` isn't installed.
- `gh run view --log` returned nothing here. Use `gh api repos/<owner>/<repo>/actions/runs/<id>/logs > x.zip` and unzip it.
- The local clone can lag behind the remote, because CI commits daily data to `main`.
- `public/online_scraped.json` is about 20 MB. Read it with a script, not by printing it.
- Source lines are very long, so use `cut -c1-300` when printing them.
- Much of the code is written in a dense, long-line style. Match it in small edits, and don't reformat whole files in a functional change.
