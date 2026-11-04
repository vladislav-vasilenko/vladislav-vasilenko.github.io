# Plan index

Started 2026-11-04. A new agent session should be able to continue from this file alone.

- Each stage has a spec in `specs/NN-name.md` (what and how) and, once started, a report in `reports/NN-name.json` (what actually happened and what was measured).
- The investigation behind all stages is in [`reports/00-investigation.json`](../reports/00-investigation.json).
- **Keep this table and the reports current.** Mark something done only after it has been verified, and record what could not be verified.
- Stages 1 to 4 are merged to `main` through PR #2 (`bf86b05`). Check `git status` and `git diff` for later work in progress. Commit or push only when asked.

| Stage | Spec | Status |
| --- | --- | --- |
| 1 | [Quick fixes](../specs/01-quick-fixes.md) | Merged; CI tests passed ([report](../reports/01-quick-fixes.json)) |
| 2 | [Web performance and progress](../specs/02-web-performance.md) | Merged ([report](../reports/02-web-performance.json)) |
| 3 | [Run crawlers from the web UI](../specs/03-web-crawler-runs.md) | Merged ([report](../reports/03-web-crawler-runs.json)) |
| 4 | [macOS Dock app](../specs/04-macos-dock-app.md) | Merged; installed and in use ([report](../reports/04-macos-dock-app.json)) |
| 5 | [Crawl lifecycle and freshness](../specs/05-crawl-lifecycle.md) | Committed on `career/stage-5-crawl-lifecycle`, not pushed ([report](../reports/05-crawl-lifecycle.json)) |
| 6 | [Vacancy triage](../specs/06-triage.md) | Not started |
| 7 | [Infrastructure](../specs/07-infrastructure.md) | Not started |
| 8 | [Separate repositories](../specs/08-repo-split.md) | Not started; proposed, not approved |

The user approved stage 1 and asked for stages 2, 3 and 4 as additions. The user approved stage 5. Stages 6 and 7 were proposed in the review and are not yet approved.

## Portfolio block review

On branch `portfolio/kandinsky-and-block-review`. `src/portfolio_blocks.py` and `archive-web/portfolio-blocks.js` compare the published `public/hh-experience.json` with the latest primary HH capture, block by block, and apply keep, accept or rewrite decisions. The contract is in `docs/integration/github-import-and-portfolio.md`. Tested in isolation and on a copy of the real database (no pending differences, block-mode text equal to the site, no publish triggered). A real publish through the UI has not been run. Block mode is off until the owner enables it, and the running service needs a restart to load the new code.

## Visualisation notes

The opportunities screen already draws a Sankey diagram (`funnel` in `archive-web/career-analytics.js`, layout in `career-charts.js`), and resume comparison already has an alluvial chart (`archive-web/resume-compare.js`). "Market Evolution" is a stacked area chart. A category alluvial over time was offered to the user on 2026-11-04 and is not scheduled. It needs several months of history; the archive had two calendar months.

## Embeddings

The user asked how to embed the whole archive. Estimated about 8.5M tokens and $0.17 with `text-embedding-3-small`, with 3,199 of 31,735 chunks done. Recommended paying rather than compressing. Figures are in `reports/03-web-crawler-runs.json`.

## Raised with the user

`.env` appears in 3 commits of this public repo's history. Tracking stopped on 2026-10-24. Nobody has verified that those keys were rotated.
