# Stage 2: Web performance and progress

The user reports that the opportunities screen is very slow with 8k+ vacancies and wants it drawn dynamically with a spinner. "Discovery job opportunities screen" was taken to mean "Карта возможностей" (`GET /archive/analytics`). The vacancy tab gets the same treatment in case both were meant.

Report: `reports/02-web-performance.json`. Baseline numbers: `reports/00-investigation.json`.

## Causes

`ArchiveStore.entities` (`src/archive_store.py:221`):

- All rows with full payloads are loaded and computed in Python before pagination.
- The correlated `membership` subquery has no usable index, because the primary key starts with `client_id`.
- `chunks()` and `text_hash` are recalculated for every row on every request.
- `_profile` in `src/career_trajectory_matching.py` has an `lru_cache(maxsize=2048)`, smaller than the row count, so it thrashes on a full scan.

`snapshot()` (`src/career_analytics.py:94`):

- `classify` runs 22,985 times, about 3× per vacancy, once in `snapshot` and again per version and month in `history()`. It accounts for 56 s of 67 s.
- The response is 11.3 MB, of which `rows` is 10.88 MB.
- The UI waits on one request with a 60 s timeout (`archive-web/career-analytics.js:199`) and shows only plain text. Measured time is over that limit, so the screen can fail outright.
- The map draws one SVG circle per point in one go, and all sections render synchronously.

## Design

Server:

- Add index `membership(kind,entity_id,present)`.
- Add a persistent derived table keyed by `(kind, id, content_hash, engine)` holding quality, text hash, chunk count, trajectory profile and analytics classification. A rule change bumps `engine`, which invalidates it.
- Fill it lazily in short batches and warm it in the background at service start and after imports. `_entity` is the only writer to `entities` (checked by grep), so keying on `content_hash` needs no write-path hooks.
- Before relying on it, confirm that `content_hash` covers every field each derived value reads. `_content` covers title, company, description, quality, locations, location and city.
- `history()` works on old versions, so cache its classification by version content too.
- Query without payloads, filter and paginate in SQL when no Python-only filter applies, and compute analysis state only for the visible page unless a filter or ranking sort needs all rows.
- `analysis_states` has a legacy fallback comparing `collected_at` for ranking items with no `vacancy_hash`. Keep it by loading the payload only for those rows.
- Split the analytics endpoint so the page can appear in stages, for example rows first and then history. Check whether `classification_evidence` can load on demand.

UI:

- One shared spinner component, with CSS in a stylesheet because of the CSP, `role="status"`, and reduced-motion support.
- Show the page frame immediately with a spinner per section, fill sections as data arrives, and render heavy sections across animation frames so the page stays responsive.
- Add a spinner to the vacancy list and detail panel, with `aria-busy`.

## Done means

Measured on a copy of the archive and recorded in the report: list page well under 1 s, trajectory filter and opportunities data inside the UI's timeouts on a warm cache, and a cold-cache path that shows progress rather than failing. Browser rendering time has not been measured yet, so measure it here.
