## CV Matcher

Tools for scraping vacancies, enriching them, and building searchable vacancy
data for the site.

### Main entrypoints

- `server.py` - local FastAPI/SSE service for scraping and matching workflows.
- `cv_matcher.py` - legacy batch matcher pipeline.
- `scripts/scrape_online.py` - automated scraper used by GitHub Actions.
- `scripts/scrape_linkedin.py` - manual LinkedIn connections scraper.

### Source layout

- `src/scrapers/` - scraper classes grouped by market/source family.
- `src/scrapers/parsers/` - pure parser helpers and browser-side parser scripts.
- `linkedin-scraper-extension/` - browser extension and userscript assets.
- `.cache/` and `.auth/` - local generated state, ignored by git.

### Live scraper checks

Run focused live checks when changing a scraper:

```bash
uv run python -m src.tests.scrapers.test_ru_ozon --query PyTorch --limit 500
uv run python -m src.tests.scrapers.test_ru_sber --query PyTorch --limit 500 --headed
```

Use `--out .cache/scraper-tests/<source>.json` to save captured vacancies for
manual inspection.

### Vacancy review UI

Run a local static server from this directory:

```bash
uv run python -m http.server 8765
```

Then open:

```text
http://localhost:8765/viewer/vacancies.html
```

The viewer loads `.cache/scraper-tests/sber.json` by default and can also open
any scraper JSON via the file picker.

Generated debug dumps, browser auth state, ChromaDB files, and AI caches should
stay local. Regenerate them as needed instead of committing them.
