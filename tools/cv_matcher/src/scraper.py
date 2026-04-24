"""Backward-compatibility shim — new code should import from src.scrapers instead."""
# ruff: noqa: F401, F403
from src.scrapers import *
from src.scrapers import SCRAPER_REGISTRY, SOURCE_GROUPS, BaseScraper

if __name__ == "__main__":
    import sys, json
    args = sys.argv[1:]
    if not args:
        print("Usage: python scraper.py <site> [query] [--limit N] [--headed]")
        print(f"Sites: {', '.join(SCRAPER_REGISTRY)}")
        sys.exit(1)
    site = args[0]
    query = args[1] if len(args) > 1 and not args[1].startswith("--") else "ML"
    limit = 5
    headless = True
    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if a == "--headed":
            headless = False
    cls = SCRAPER_REGISTRY[site]
    scraper = cls(limit=limit, headless=headless)
    jobs = scraper.fetch_jobs(query)
    print(f"\n=== {len(jobs)} вакансий ===")
    for j in jobs[:3]:
        print(json.dumps({k: v for k, v in j.items() if k != "description"}, ensure_ascii=False, indent=2))
