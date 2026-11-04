# Stage 3: Run crawlers from the web UI

The user wants to start crawlers from the web UI, especially fast ones like Yandex and Sber. Crawling through the Chrome extension is very slow, as with hh.ru, which provides no API. Report: `reports/03-web-crawler-runs.json`.

## What was built

- `src/source_runs.py` runs whole sources one at a time, query by query, in isolated `python_collection` processes, and saves after each query. A repeat run skips vacancies that already have full text.
- Routes: `GET` and `POST /archive/source-runs` (`start`, `stop`).
- `archive-web/source-runs.js` is the "Сбор вакансий" panel on the vacancy screen: start, stop, live progress, results and failure reasons.
- `SberScraper` reads the public API the site's own search page uses, from an ordinary browser page, without stealth settings.

## Decisions

- **A dedicated runner, not `browser_commands`.** That queue models short reads with transport fallback and discovery runs with ranking. A whole-source run needs per-query progress and has no fallback.
- **Plain HTTP to Sber gets 403, and that stays respected.** Requests go through a normal browser page. A refused request is not retried.
- **hh.ru stays on Chrome.** It needs the user's authorised session, which is never passed to Python, so the panel only explains how to run it.

## Sources

`src/source_runs.py` lists them, and `src/scrapers/ats.py` lists the Greenhouse and Ashby boards. Check any new board against the company's own text or careers page, because board names can collide. `reports/03-web-crawler-runs.json` records what works, what doesn't, and why.

Other options from small checks on 2026-11-04: Avito and T-Bank work but take about 15 s per vacancy. Ozon, X5 and Wildberries returned nothing, and Alfa failed. VK and MTS rows have IDs that don't match the archive.
