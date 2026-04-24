#!/usr/bin/env python3
"""Online vacancy scraper — runs under GitHub Actions.

Scope (iter 1): Yandex, Sber, Google, Meta — with stealth + optional storage_state.

Design:
  - No ChromaDB / embeddings in CI (those run locally via cv_matcher.py).
  - Output: public/online_scraped.json — append-only over runs, deduped by id.
  - Each scraper runs with stealth=True and respects STORAGE_STATE env vars.

Behaviour on error: individual scraper failures are logged but don't fail the job.
"""

import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.scrapers import (  # noqa: E402
    YandexScraper, SberScraper, GoogleCareersScraper, MetaCareersScraper,
)

OUTPUT = ROOT.parent.parent / "public" / "online_scraped.json"

# Default queries — short because each scraper has its own rate limits / captcha risk
QUERIES = [
    "Machine Learning Engineer",
    "LLM Engineer",
    "GenAI",
    "Applied Scientist",
]

# Yandex special — its URL filter is far more efficient than per-keyword iteration
YANDEX_URLS = [
    (
        "https://yandex.ru/jobs/vacancies?"
        "professions=ml-developer&professions=backend-developer"
        "&professions=database-developer"
    ),
]


def _source_plan():
    """Build (key, factory, queries) list. Storage state is env-driven."""
    google_state = os.environ.get("GOOGLE_STORAGE_STATE")
    meta_state = os.environ.get("META_STORAGE_STATE")

    return [
        ("yandex",
         lambda: YandexScraper(limit=40, stealth=True),
         YANDEX_URLS),
        ("sber",
         lambda: SberScraper(limit=25, stealth=True),
         QUERIES),
        ("google",
         lambda: GoogleCareersScraper(limit=20, stealth=True, storage_state_path=google_state),
         QUERIES),
        ("meta",
         lambda: MetaCareersScraper(limit=20, stealth=True, storage_state_path=meta_state),
         QUERIES),
    ]


def _load_existing() -> dict:
    """Read existing online_scraped.json into id→vacancy map, pruning entries older than 30 days."""
    if not OUTPUT.exists():
        return {}
    try:
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    kept: dict = {}
    for v in data.get("vacancies", []):
        first_seen = v.get("first_seen")
        try:
            ts = datetime.fromisoformat(first_seen) if first_seen else None
        except Exception:
            ts = None
        if ts is None or ts >= cutoff:
            kept[v["id"]] = v
    print(f"📦 Loaded {len(kept)} existing vacancies (after 30-day prune)")
    return kept


def main() -> int:
    print(f"🚀 Online scrape @ {datetime.now(timezone.utc).isoformat()}")
    by_id = _load_existing()
    stats: dict[str, dict[str, int]] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for key, factory, queries in _source_plan():
        stats[key] = {"new": 0, "errors": 0}
        print(f"\n── {key} ──")
        try:
            scraper = factory()
        except Exception as e:
            print(f"  ✗ {key}: init failed — {e}")
            stats[key]["errors"] += 1
            continue

        for q in queries:
            try:
                jobs = scraper.fetch_jobs(q, existing_ids=set(by_id.keys()))
                for j in jobs:
                    jid = j["id"]
                    if jid not in by_id:
                        j["first_seen"] = now_iso
                        j["last_seen"] = now_iso
                        by_id[jid] = j
                        stats[key]["new"] += 1
                    else:
                        by_id[jid]["last_seen"] = now_iso
            except Exception as e:
                print(f"  ✗ {key} on '{q}': {e}")
                traceback.print_exc(limit=2, file=sys.stderr)
                stats[key]["errors"] += 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated": now_iso,
        "total": len(by_id),
        "stats_last_run": stats,
        "vacancies": sorted(by_id.values(), key=lambda v: v.get("first_seen", ""), reverse=True),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    total_new = sum(s["new"] for s in stats.values())
    print(f"\n✅ Done. {total_new} new, {len(by_id)} total → {OUTPUT}")
    for k, s in stats.items():
        print(f"   {k}: +{s['new']} new, {s['errors']} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
