"""Per-site smoke tests for scrapers.

Run a single site:
    python -m src.tests.test_scrapers yandex
    python -m src.tests.test_scrapers tinkoff --query "Backend" --limit 3
    python -m src.tests.test_scrapers all --limit 2

Each test asserts:
  - fetch_jobs returns a list
  - at least one vacancy is produced (unless site is a known no-op)
  - required fields are present and non-empty
  - ids are unique and use the expected prefix
  - vacancy URLs point to the expected domain
"""

import argparse
import os
import sys
import time
from typing import Dict, Any, List

# Allow running as `python src/tests/test_scrapers.py` too.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.scraper import (  # noqa: E402
    YandexScraper, TinkoffScraper, AvitoScraper, VKScraper, X5RetailScraper,
)
from src.scrapers.faang import GoogleCareersScraper, MetaCareersScraper  # noqa: E402


REQUIRED_FIELDS = ["id", "title", "company", "pub_date", "description", "link", "origin_query"]


def _validate(jobs: List[Dict[str, Any]], expected_prefix: str, expected_host: str,
              require_non_empty: bool = True) -> List[str]:
    errors: List[str] = []
    if not isinstance(jobs, list):
        return [f"fetch_jobs returned {type(jobs).__name__}, expected list"]
    if require_non_empty and not jobs:
        errors.append("no vacancies returned")
    ids_seen = set()
    for i, j in enumerate(jobs):
        for f in REQUIRED_FIELDS:
            if f not in j:
                errors.append(f"job[{i}] missing field '{f}'")
                continue
            if f in ("id", "title", "link") and not j[f]:
                errors.append(f"job[{i}] empty field '{f}'")
        if "id" in j:
            if not j["id"].startswith(expected_prefix + "_"):
                errors.append(f"job[{i}] id '{j['id']}' missing prefix '{expected_prefix}_'")
            if j["id"] in ids_seen:
                errors.append(f"job[{i}] duplicate id {j['id']}")
            ids_seen.add(j["id"])
        if "link" in j and j["link"] and expected_host not in j["link"]:
            errors.append(f"job[{i}] link '{j['link']}' not on host '{expected_host}'")
    return errors


def test_yandex(limit: int = 2, headless: bool = True, query: str = "ML") -> bool:
    print("\n============================================================")
    print("TEST: Yandex")
    print("============================================================")
    scraper = YandexScraper(limit=limit, headless=headless)
    url = "https://yandex.ru/jobs/vacancies?professions=ml-developer"
    jobs = scraper.fetch_jobs(url)
    errors = _validate(jobs, "yandex", "yandex.ru")
    return _report("yandex", jobs, errors)


def test_tinkoff(limit: int = 2, headless: bool = True, query: str = "ML") -> bool:
    print("\n============================================================")
    print("TEST: Tinkoff / T-Bank")
    print("============================================================")
    scraper = TinkoffScraper(limit=limit, headless=headless)
    jobs = scraper.fetch_jobs(query)
    errors = _validate(jobs, "tinkoff", "tbank.ru")
    return _report("tinkoff", jobs, errors)


def test_avito(limit: int = 2, headless: bool = True, query: str = "ML") -> bool:
    print("\n============================================================")
    print("TEST: Avito")
    print("============================================================")
    scraper = AvitoScraper(limit=limit, headless=headless)
    jobs = scraper.fetch_jobs(query)
    errors = _validate(jobs, "avito", "career.avito.com")
    return _report("avito", jobs, errors)


def test_vk(limit: int = 2, headless: bool = True, query: str = "ML") -> bool:
    print("\n============================================================")
    print("TEST: VK")
    print("============================================================")
    scraper = VKScraper(limit=limit, headless=headless)
    jobs = scraper.fetch_jobs(query)
    errors = _validate(jobs, "vk", "team.vk.company")
    return _report("vk", jobs, errors)


def test_x5(limit: int = 2, headless: bool = True, query: str = "ML") -> bool:
    print("\n============================================================")
    print("TEST: X5 Retail")
    print("============================================================")
    scraper = X5RetailScraper(limit=limit, headless=headless)
    jobs = scraper.fetch_jobs(query)
    errors = _validate(jobs, "x5", "rabota.x5.ru")
    return _report("x5", jobs, errors)


def _report(site: str, jobs: List[Dict[str, Any]], errors: List[str]) -> bool:
    print(f"\nResult for {site}: {len(jobs)} jobs, {len(errors)} validation errors")
    if jobs:
        j = jobs[0]
        print("  sample:")
        print(f"    id     = {j.get('id')}")
        print(f"    title  = {j.get('title')}")
        print(f"    link   = {j.get('link')}")
        print(f"    desc   = {(j.get('description') or '')[:120]}...")
    if errors:
        print("  ERRORS:")
        for e in errors:
            print(f"    - {e}")
        return False
    print(f"  ✅ {site}: PASS")
    return True


def test_google(limit: int = 2, headless: bool = True, query: str = "Machine Learning Engineer") -> bool:
    print("\n============================================================")
    print("TEST: Google Careers")
    print("============================================================")
    scraper = GoogleCareersScraper(limit=limit, headless=headless, stealth=True)
    jobs = scraper.fetch_jobs(query)
    errors = _validate(jobs, "goog", "google.com")
    # Extra: check structured fields extraction
    for i, j in enumerate(jobs):
        if not j.get("description") or len(j["description"]) < 50:
            errors.append(f"job[{i}] description too short ({len(j.get('description', ''))})")
        if not j.get("locations"):
            # Not a hard fail — some listings don't have locations
            print(f"  ⚠️ job[{i}] '{j.get('title')}': no locations extracted")
        if j.get("compensation"):
            print(f"  💰 job[{i}] compensation: {j['compensation']}")
        else:
            print(f"  ⚠️ job[{i}] '{j.get('title')}': no compensation extracted")
    return _report("google", jobs, errors)


def test_meta(limit: int = 3, headless: bool = True, query: str = "") -> bool:
    print("\n============================================================")
    print("TEST: Meta Careers")
    print("============================================================")
    scraper = MetaCareersScraper(limit=limit, headless=headless, stealth=True)
    jobs = scraper.fetch_jobs(query)
    errors = _validate(jobs, "meta", "metacareers.com")
    for i, j in enumerate(jobs):
        if not j.get("description") or len(j["description"]) < 100:
            errors.append(f"job[{i}] description too short ({len(j.get('description', ''))})")
        if not j.get("teams"):
            print(f"  ⚠️ job[{i}] '{j.get('title')}': no teams")
        if j.get("compensation"):
            print(f"  💰 job[{i}] compensation: {j['compensation']}")
    return _report("meta", jobs, errors)


TESTS = {
    "yandex": test_yandex,
    "tinkoff": test_tinkoff,
    "avito": test_avito,
    "vk": test_vk,
    "x5": test_x5,
    "google": test_google,
    "meta": test_meta,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("site", choices=list(TESTS) + ["all"])
    parser.add_argument("--query", default="ML")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--headed", action="store_true", help="show browser (non-headless)")
    args = parser.parse_args()

    targets = list(TESTS.keys()) if args.site == "all" else [args.site]
    results = {}
    for name in targets:
        t0 = time.time()
        try:
            ok = TESTS[name](limit=args.limit, headless=not args.headed, query=args.query)
        except Exception as e:
            print(f"❌ {name}: exception — {e}")
            ok = False
        results[name] = (ok, round(time.time() - t0, 1))

    print("\n============================================================")
    print("SUMMARY")
    print("============================================================")
    for name, (ok, dt) in results.items():
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:<8} {dt}s")

    sys.exit(0 if all(ok for ok, _ in results.values()) else 1)


if __name__ == "__main__":
    main()
