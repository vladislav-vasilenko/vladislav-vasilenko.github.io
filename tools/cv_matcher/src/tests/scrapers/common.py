"""Shared helpers for runnable scraper smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Type

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_FIELDS = ("id", "title", "company", "pub_date", "description", "link", "origin_query")


def build_parser(site: str, default_limit: int = 500, default_query: str = "PyTorch") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Live smoke test for {site} scraper")
    parser.add_argument("--query", default=default_query)
    parser.add_argument("--limit", type=int, default=default_limit)
    parser.add_argument("--headed", action="store_true", help="Run browser with a visible window")
    parser.add_argument("--storage-state", help="Playwright storage_state JSON path")
    parser.add_argument("--min-results", type=int, default=1, help="Minimum accepted vacancies")
    parser.add_argument("--out", help="Optional path to write fetched vacancies as JSON")
    return parser


def validate_jobs(
    jobs: List[Dict[str, Any]],
    *,
    expected_prefix: str,
    expected_hosts: Sequence[str],
    query: str,
    limit: int,
    min_results: int,
) -> List[str]:
    errors: List[str] = []
    if not isinstance(jobs, list):
        return [f"fetch_jobs returned {type(jobs).__name__}, expected list"]
    if len(jobs) < min_results:
        errors.append(f"expected at least {min_results} vacancies, got {len(jobs)}")
    if len(jobs) > limit:
        errors.append(f"expected at most {limit} vacancies, got {len(jobs)}")

    seen = set()
    for i, job in enumerate(jobs):
        for field in REQUIRED_FIELDS:
            if field not in job:
                errors.append(f"job[{i}] missing field {field!r}")
            elif field in ("id", "title", "link") and not job[field]:
                errors.append(f"job[{i}] empty field {field!r}")

        jid = str(job.get("id") or "")
        if jid:
            if not jid.startswith(f"{expected_prefix}_"):
                errors.append(f"job[{i}] id {jid!r} does not start with {expected_prefix!r}")
            if jid in seen:
                errors.append(f"job[{i}] duplicate id {jid!r}")
            seen.add(jid)

        link = str(job.get("link") or "")
        if link and not any(host in link for host in expected_hosts):
            errors.append(f"job[{i}] link {link!r} is not on {expected_hosts}")

        origin_query = str(job.get("origin_query") or "")
        if origin_query != query:
            errors.append(f"job[{i}] origin_query {origin_query!r} != {query!r}")

    return errors


def run_live_scraper(
    scraper_cls: Type,
    *,
    site: str,
    expected_prefix: str,
    expected_hosts: Sequence[str],
    args: argparse.Namespace,
    stealth: bool = False,
) -> int:
    kwargs: Dict[str, Any] = {
        "limit": args.limit,
        "headless": not args.headed,
    }
    if args.storage_state:
        kwargs["storage_state_path"] = args.storage_state
    if stealth:
        kwargs["stealth"] = True

    print(f"TEST: {site} | query={args.query!r} | limit={args.limit} | headless={not args.headed}")
    started = time.time()
    scraper = scraper_cls(**kwargs)
    jobs = scraper.fetch_jobs(args.query)
    elapsed = round(time.time() - started, 1)

    errors = validate_jobs(
        jobs,
        expected_prefix=expected_prefix,
        expected_hosts=expected_hosts,
        query=args.query,
        limit=args.limit,
        min_results=args.min_results,
    )

    print(f"\nResult: {len(jobs)} vacancies in {elapsed}s")
    if jobs:
        first = jobs[0]
        print("Sample:")
        print(f"  id    = {first.get('id')}")
        print(f"  title = {first.get('title')}")
        print(f"  link  = {first.get('link')}")
        print(f"  desc  = {(first.get('description') or '')[:160]}...")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {out}")

    if errors:
        print("\nERRORS:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("\nPASS")
    return 0

