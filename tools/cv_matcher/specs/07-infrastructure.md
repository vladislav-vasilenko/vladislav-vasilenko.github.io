# Stage 7: Infrastructure

Proposed, not yet approved. Report: `reports/07-infrastructure.json`.

- Move generated data out of git: two JSON files take 183 MiB of the 376 MiB pack. CI also checks out with `fetch-depth: 0`.
- Split CI into a read-only scrape job and a separate publish job: Chromium runs `--no-sandbox` on third-party sites in a job with `contents: write`.
- Trim overlapping Google queries: 199 pages for 63 new jobs on Nov 3, and "Machine Learning" and "Deep Learning" both report 609 results.
- Test removing the stealth settings rather than upgrading them. They're inconsistent: always macOS and Chrome 131 headers with a rotating user agent.
- Run or remove unscheduled adapters: Sber and 9 China adapters never run on schedule.
- Retire `viewer/` and `server.py`.
- Declare authorization per route instead of the allowlists in `src/archive_routes.py:20-23`.
- Split up `archive.js`, especially the repeated `setTab` branches.
- Add the API-based job boards to the daily schedule. Do this after moving data out of git: the new boards would take `online_scraped.json` past the 32 MiB export limit.
