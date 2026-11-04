# Stage 1: Quick fixes

Small, low-risk fixes. Report: `reports/01-quick-fixes.json`.

## 1.1 False "reopened" events

`_entity` (`src/archive_store.py:162`) logs `reopened` for any availability change that isn't to `closed`, so unknown → active counts as reopening. All 1,150 existing `reopened` events have no earlier `closed`.

- New event `confirmed_active` for unknown → active. `reopened` is only for closed → active.
- Add a label in `archive-web/archive.js:6`.
- One-time migration guarded by an `archive_meta` marker: relabel `reopened` events with no earlier `closed` for that entity. Relabel, don't delete.
- `src/career_analytics.py:108` rebuilds history from `closed` and `reopened`. A relabelled event had no earlier closure, so it doesn't change the result.

## 1.2 Newest vacancies first

`last_seen` is overwritten on each import, so `ORDER BY e.last_seen DESC,e.id` degrades into reverse-ID order. Use `first_seen DESC, id` for vacancies. Resumes keep their current order.

## 1.3 Honest source errors

Silent failures:

- `src/scrapers/_base.py:184` swallows exceptions and returns `[]`.
- `src/scrapers/ru_yandex.py:161` fallback is a stub, and pagination failures only print.
- `src/scrapers/ru_sber.py:58,71` return `[]` on a challenge or parser failure.
- `src/scrapers/google_careers.py:61-67` breaks on missing data with no error.
- `src/scrapers/meta_careers.py:265` only prints failed detail pages.
- `scripts/scrape_online.py:207` always returns 0.

Design:

- Every scraper fills `self.report` like `ChinaScraper`: `listed`, `accepted`, `errors`, `coverage`.
- `BaseScraper.fetch_jobs` keeps returning `[]` on failure, because `src/python_collection.py` relies on that plus its `error` event, but records the failure in `report`.
- `scrape_online.py` sums `listed` and `errors` per source and marks a source `failed` if it listed nothing. A China source raises its own error for an unrecognised listing, and "listed" excludes known rows there, so the empty-listing rule is off for those adapters.
- The job still publishes partial results. A last workflow step fails the run if any source failed, so results are saved **and** the run goes red.
- `errors` must stay a non-negative int: `src/github_collection_export.py` and `src/github_collection_import.py` validate it.

## 1.4 Tests in CI

No workflow runs the tests. Add `.github/workflows/career-tests.yml` for changes under `tools/cv_matcher/`. It can only be verified after a push.
