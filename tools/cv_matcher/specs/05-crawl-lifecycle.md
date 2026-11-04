# Stage 5: Crawl lifecycle and vacancy freshness

Approved by the user, who also asked for a mechanism to check whether vacancies are still current. Report: `reports/05-crawl-lifecycle.json`.

## Problem

Scrapers dropped known IDs before returning them, so `last_seen` stayed equal to `first_seen`. Cleanup pruned by `first_seen` at 30 days, so live jobs vanished and returned as "new", and closed jobs lingered. Closure detection existed only for HH.

## How it works

- **Listings report everything they saw.** Each scraper fills `seen_ids`, including IDs it skips as known. Details are still read only for new ones. China adapters don't do this yet, so they stay untracked (`tracked=False`).
- **Observations.** `ArchiveStore.record_listing` writes to the existing `scans` and `membership` tables under client `listing-observer`, for both panel runs and the daily import. The scope is per source (`source_runs.scope_of`).
- **Absence needs a whole listing.** Only a listing with `coverage == 'listing_exhausted'`, no errors, and every query finished can mark absence.
- **Absence never means closed.** The state is `gone`, shown as "Исчезла из выдачи". `availability` stays reserved for what the vacancy's own page confirms.
- **Site-fault guard.** A listing that falls below half of what was last present is treated as partial.
- **Which rows a listing can speak for.** `universe()` adds saved rows never observed before, without events, so the first run doesn't flood the Changes feed. `whole=False` sources (Yandex, Sber) only track rows they have seen, because their queries cover part of the site. Google's universe excludes DeepMind rows, and DeepMind's is DeepMind rows only.
- **Several scopes.** The latest observation wins, so a role absent from one listing and later seen in another counts as listed.

## User-facing

- Tags on rows, and filters "Есть в выдаче сейчас" and "Исчезли из выдачи".
- A "Проверить актуальность" button in the vacancy card. It re-runs the vacancy's source, or queues a Chrome read for HH.
- "Движение за 7 дней" by company on the Changes screen.
- Backfill skips vacancies gone from their listing.

## Daily run

`scrape_online.py` refreshes `last_seen` for all seen IDs, prunes by `last_seen`, takes the worst coverage across queries, and fails on a corrupt file instead of replacing the history. The importer passes observations on through `github_collection_import.record_listings`.
