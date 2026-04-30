#!/usr/bin/env python3
"""Backfill full descriptions for Yandex vacancies in online_scraped.json.

The listing API only carries `short_summary` (~150 chars). The detail
endpoint /api/publications/{slug} returns description + duties +
key_qualifications + ... — needed for meaningful embedding quality
against an English resume.

Idempotent: only fetches details for records whose `description` is
shorter than the configured threshold. Re-run to backfill new arrivals.

Usage:
    uv run python scripts/enrich_yandex_descriptions.py
    uv run python scripts/enrich_yandex_descriptions.py --min-length 800 --force
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers.ru import _strip_html, compose_yandex_description  # noqa: E402

INPUT = ROOT.parent.parent / "public" / "online_scraped.json"
DETAIL_URL = "https://yandex.ru/jobs/api/publications/{slug}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def fetch_detail(slug: str, timeout: int = 15) -> dict:
    url = DETAIL_URL.format(slug=urllib.parse.quote(slug, safe=""))
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  ⚠️ {slug}: {e}")
        return {}
    return {
        "description": _strip_html(d.get("description") or ""),
        "duties": _strip_html(d.get("duties") or ""),
        "key_qualifications": _strip_html(d.get("key_qualifications") or ""),
        "additional_requirements": _strip_html(d.get("additional_requirements") or ""),
        "conditions": _strip_html(d.get("conditions") or ""),
        "our_team": _strip_html(d.get("our_team") or ""),
        "tech_stack": _strip_html(d.get("tech_stack") or ""),
    }


def slug_from_link(link: str) -> str:
    if not link or "/vacancies/" not in link:
        return ""
    return link.rstrip("/").rsplit("/", 1)[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--min-length", type=int, default=400,
                        help="Skip records whose description is already at least this long")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even already-enriched records")
    parser.add_argument("--delay", type=float, default=0.4,
                        help="Seconds between requests (rate-limit friendliness)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after N updates (0 = unlimited; useful for sanity-checks)")
    args = parser.parse_args()

    p = Path(args.input)
    data = json.loads(p.read_text(encoding="utf-8"))
    yand = [v for v in data["vacancies"] if v["id"].startswith("yandex_")]
    todo = [v for v in yand if args.force or len(v.get("description") or "") < args.min_length]
    print(f"📋 Yandex total: {len(yand)} | needing enrichment: {len(todo)}")

    if not todo:
        print("✅ Nothing to do.")
        return 0

    updated = 0
    for i, v in enumerate(todo, 1):
        if args.limit and updated >= args.limit:
            break
        slug = slug_from_link(v.get("link") or "")
        if not slug:
            continue
        detail = fetch_detail(slug)
        if not detail:
            continue
        # Pull profession from existing description if present (pattern "Профессия: …"),
        # otherwise leave blank.
        old_desc = v.get("description") or ""
        profession = ""
        if "Профессия:" in old_desc:
            profession = old_desc.split("Профессия:", 1)[-1].split("\n", 1)[0].strip()
        short = old_desc.split("\n", 1)[0].strip() if old_desc else ""
        new_desc = compose_yandex_description(short, profession, detail)
        if new_desc and new_desc != old_desc:
            v["description"] = new_desc[:5000]
            updated += 1
            if i % 25 == 0 or updated <= 5:
                print(f"  [{i}/{len(todo)}] {v['title'][:60]} ({len(new_desc)} chars)")
        time.sleep(args.delay)

    # Save once at the end (atomic via temp file would be safer, but OK for local).
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Updated {updated} records → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
