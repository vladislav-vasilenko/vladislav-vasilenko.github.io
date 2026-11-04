# Plan index

Started 2026-11-04. A new agent session should be able to continue from this file alone.

- Each stage has a spec in `specs/NN-name.md` (what and how) and, once started, a report in `reports/NN-name.json` (what actually happened and what was measured).
- The investigation behind all stages is in [`reports/00-investigation.json`](../reports/00-investigation.json).
- **Keep this table and the reports current.** Mark something done only after it has been verified, and record what could not be verified.
- The user has not asked for commits. Check `git status` and `git diff` for work in progress.

| Stage | Spec | Status |
| --- | --- | --- |
| 1 | [Quick fixes](../specs/01-quick-fixes.md) | Implemented and tested locally, not committed; CI workflow unverified ([report](../reports/01-quick-fixes.json)) |
| 2 | [Web performance and progress](../specs/02-web-performance.md) | Implemented and running on the real archive, not committed ([report](../reports/02-web-performance.json)) |
| 3 | [Run crawlers from the web UI](../specs/03-web-crawler-runs.md) | Not started |
| 4 | [macOS Dock app](../specs/04-macos-dock-app.md) | Installed and in use, not committed ([report](../reports/04-macos-dock-app.json)) |
| 5 | [Crawl lifecycle](../specs/05-crawl-lifecycle.md) | Not started |
| 6 | [Vacancy triage](../specs/06-triage.md) | Not started |
| 7 | [Infrastructure](../specs/07-infrastructure.md) | Not started |

The user approved stage 1 and asked for stages 2, 3 and 4 as additions. Stages 5 to 7 were proposed in the review, and the user has not yet approved them.

## Visualisation notes

The opportunities screen already draws a Sankey diagram (`funnel` in `archive-web/career-analytics.js`, layout in `career-charts.js`), and resume comparison already has an alluvial chart (`archive-web/resume-compare.js`). "Market Evolution" is a stacked area chart. A category alluvial over time was offered to the user on 2026-11-04 and is not scheduled. It needs several months of history; the archive had two calendar months.

## Raised with the user

`.env` appears in 3 commits of this public repo's history. Tracking stopped on 2026-10-24. Nobody has verified that those keys were rotated.
