# Stage 5: Crawl lifecycle

Proposed, not yet approved. Report: `reports/05-crawl-lifecycle.json`.

**Problem:** scrapers drop known IDs before returning (`ru_yandex.py:88`, `parsers/google.py:96`, Meta candidates), so `scrape_online.py:194` effectively never runs for existing jobs and `last_seen` stays equal to `first_seen`. Cleanup prunes by `first_seen` at 30 days, so live jobs vanish and return as "new", and closed jobs linger. About 1,700 rows from Oct 23 are due around Nov 22.

- Scrapers return every ID seen in the listing, with details fetched only for new IDs.
- Update `last_seen` for all seen IDs, and clean up by `last_seen`.
- Send complete-listing scans to the local archive so "missing" events work beyond HH. Only a complete listing counts, and absence is still not closure.
- Also stop the local `last_seen` being overwritten by re-imports.
- One-time repair of existing data, including the 2,616 `needs_review` GitHub rows.
- Treat a corrupt `online_scraped.json` as an error: `_load_existing` currently returns `{}` and would overwrite history.
