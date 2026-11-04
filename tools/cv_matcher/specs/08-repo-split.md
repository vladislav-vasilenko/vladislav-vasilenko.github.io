# Stage 8: Separate repositories

Proposed, not yet approved. Report: `reports/08-repo-split.json`. Start after the portfolio block review branch is merged.

## Goal

Keep the resume website in the current public repository. Move `tools/cv_matcher`, including its local web interface and Chrome extension, to a new private repository.

Reasons: this is a personal job-search tool whose commits are all public today, the `.git` directory is 406 MB, and bot data commits are mixed into the site's history. The site needs one file from the service.

## Contract between the repositories

The only runtime link is `public/hh-experience.json`. The service writes it to the site repository through the GitHub Contents API with a SHA check, and the site validates it in `src/features/hhExperience.ts`. Keep this one-way link, and document the schema in the site repository.

## What moves and what stays

| Item | Destination | Note |
| --- | --- | --- |
| `src/`, `content/`, `public/hh-experience.json`, `deploy.yml`, portfolio tests | Site | |
| `tools/cv_matcher/`, `career-tests.yml` | Service | Paths in the workflow lose the `tools/cv_matcher` prefix |
| `daily-scrape.yml` | Service | Its Actions artifact feeds the local import |
| `rag_updater.yml` | Decide | Runs the legacy `cv_matcher.py`, which also reads `content/ru` |
| `matcher.html`, `scrape.html`, `src/matcher.ts`, `src/scrape.ts` | Decide | Public matcher pages read generated data or the legacy local server |
| `public/online_scraped*.json`, `vacancy_tree*`, `cluster_map*`, `matcher_data.json` | Decide | Written by service scripts and published by the site today |
| `autofill-extension/`, `cv-api/` | Decide | Check their remaining use first |
| `tools/workspace.mjs`, `workspace.projects.json` | Rewrite | They assume one repository |

## Code changes

- `REPOSITORY` in `src/github_collection_api.py` currently means both the data source and the publication target. Split it into a service repository for Actions and a site repository for `hh-experience.json`.
- Give `gh` access to both repositories, and keep Contents write access limited to what publication needs.
- Move or copy the Google and Meta storage state secrets to the service repository.
- Check the Dock app and `scripts/install_macos_app.py` after the folder moves. The installer must be rerun.
- `.cache/`, `.auth/` and the local SQLite database stay on disk and must not enter the new repository.

## Steps

1. Agree the "Decide" rows above.
2. Create the private repository from a filtered history of `tools/cv_matcher`, excluding generated data. Scan the filtered history for secrets before the first push.
3. Move the workflows, split `REPOSITORY`, and pass all tests in the new repository.
4. Run one daily scrape, one local import and one portfolio publication from the new repository.
5. Only after step 4, remove the moved paths from the site repository in a normal commit.

## Risks

- **Secrets stay public:** `.env` appears in 3 commits of the public history, and removing the folder doesn't erase them. Rotate those keys whatever is decided here. Rewriting public history is a separate decision.
- **Published history stays public:** earlier service code and scraped data remain in the site's history.
- **Actions limits:** private repositories have a monthly minutes quota, unlike public ones. Measure the daily scrape's minutes before moving it.
- **Overlap with stage 7:** moving generated data out of git is also proposed there. Decide both together.

## Verification

- The site builds and deploys with no `tools/cv_matcher` folder present.
- A service publication changes only `public/hh-experience.json` in the site repository.
- `node tools/workspace.mjs check` or its replacement passes in both repositories.
- The old local database opens unchanged in the new location.
