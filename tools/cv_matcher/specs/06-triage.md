# Stage 6: Vacancy triage

Proposed, not yet approved. Report: `reports/06-triage.json`.

There is no way to mark a vacancy as seen, rejected or shortlisted, only "applied".

- Triage states, stored reversibly and kept across re-imports.
- Separate quality, embedding and availability filters: one dropdown mixes all three (`archive-web/index.html`). Add a location filter and sort control.
- Rethink the default "full only" filter, which hides about half the archive (`archive.js:120`).
- "New since last visit" and keyboard navigation.
- Relevance filter or tagging: by a rough title regex, only 736 of 2,867 Google and 326 of 1,444 Meta jobs look ML/AI.
- Group same-title rows with an expander. 460 groups cover 1,140 rows, but only 58 rows are exact text duplicates, so don't merge them blindly.
- Stop `changed` events for metadata-only changes: 468 of 2,384 have identical title and description (`_content`, `src/archive_store.py:166`).
