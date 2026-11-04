# Stage 3: Run crawlers from the web UI

The user wants to start crawlers from the web UI, especially fast ones like Yandex and Sber. Crawling through the Chrome extension is very slow, as with hh.ru, which provides no API. Report: `reports/03-web-crawler-runs.json`.

## What already exists

- `src/python_collection.py` runs scrapers in an isolated subprocess, and `src/hybrid_collection.py` queues them through `browser_commands` with Python/Chrome fallback.
- UI entry points: `discovery_start` in `archive-web/intake.js:103`, `collect_one` for one vacancy, and "GitHub Runs" (`archive-web/github-runs.js`) for cloud runs.
- `docs/architecture/hybrid-collection.md` describes the modes and limits.

## Known obstacles

- **Deadline and row cap:** `execute` kills the worker after 75 s and `persist` accepts at most 100 rows, so a full source run can't finish.
- **Sber:** `collect` forces `stealth=False` (`src/python_collection.py`), while `SberScraper` declares it needs stealth for a JS challenge. An HTTP check on 2026-10-20 also found a dynamic page with no extracted vacancies. **Sber may not work headless from Python at all. Test this before promising speed.**
- **Sber WAF:** comments in `scripts/scrape_online.py` say it blocks CI and should run from a Russian IP, so a local run may fare better than CI. Unverified.
- **Yandex:** it uses a public JSON API but fetches each detail page with a 0.6 s pause, so speed is mostly listing size × detail requests. Skipping known IDs helps most.
- **Full rescans:** `collect` passes `existing_ids=set()`, re-reading known jobs.
- **Concurrency:** `run_pending` runs one Python read at a time.
- **HH stays in Chrome.** It needs the user's authorised session, which is deliberately never passed to Python.

## Design to confirm while building

- A "Сбор" panel listing each source with its transport, last run, new/listed/error counts, and a Start/Stop button.
- Source-level runs with a longer deadline and batched `persist` calls so progress is saved as it goes. Reuse the queue and its pause/cancel controls rather than adding a second runner.
- Pass known IDs so only new vacancies get detail requests.
- Live status from the existing task state: progress bar, current source, last error. Polling is enough.
- Measure real speed per source and put it in the report.
- Do not add measures to get past a site's bot checks. If Sber blocks automated reads, report that and leave it on the Chrome route.
