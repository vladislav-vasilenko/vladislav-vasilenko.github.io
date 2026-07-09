#!/usr/bin/env python3
"""Online vacancy scraper — runs under GitHub Actions.

Scope (iter 1): Yandex, Google, Meta — with stealth + optional storage_state.
(Sber removed from automation due to WAF/blocking in CI, run manually from RU IP).

Design:
  - Outputs: public/online_scraped.json — append-only over runs, deduped by id.
  - Embd/Clusters: GitHub Actions now runs index_meta_to_chroma.py + build_cluster_map.py 
    after this script, utilizing the cv-api proxy.
  - Each scraper runs with stealth=True and respects STORAGE_STATE env vars.

Behaviour on error: individual scraper failures are logged but don't fail the job.
"""

import argparse
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

# Google gets server-side filtering so broader queries cover more relevant roles
GOOGLE_QUERIES = [
    "Machine Learning",
    "AI Engineer",
    "Deep Learning",
    "NLP",
    "Computer Vision",
    "Applied Scientist",
    "Research Scientist",
]

# Yandex special — its URL filter is far more efficient than per-keyword iteration
YANDEX_URLS = [
    (
        "https://yandex.ru/jobs/vacancies?"
        "professions=ml-developer&professions=backend-developer"
        "&professions=database-developer"
    ),
]

# Sber: only ML/AI-relevant roles — narrow keyword set instead of full catalog.
SBER_QUERIES = [
    "ML", "LLM", "VAE", "DPO", "RLHF", "Diffusion", "Audio",
    "Speech", "ASR", "TTS",
    "NLP", "RAG", "Search",
    "Research",
]


def _source_plan(headless: bool = True, include_sber: bool = False):
    """Build (key, factory, queries) list. Storage state is env-driven."""
    google_state = os.environ.get("GOOGLE_STORAGE_STATE")
    meta_state = os.environ.get("META_STORAGE_STATE")

    plan = [
        ("yandex",
         lambda limit=0: YandexScraper(limit=limit or 500, stealth=True, headless=headless),
         YANDEX_URLS),
        ("google",
         lambda limit=0: GoogleCareersScraper(
             limit=limit or 200,
             stealth=True,
             storage_state_path=google_state,
             headless=headless,
         ),
         GOOGLE_QUERIES),
        ("meta",
         lambda limit=0: MetaCareersScraper(limit=limit or 0, stealth=True, storage_state_path=meta_state, headless=headless),
         [""]),
    ]

    # Sber is WAF-sensitive. Run locally by default; in CI it must be
    # explicitly enabled with --include-sber, --scrapers=sber, or env.
    if include_sber or not os.environ.get("GITHUB_ACTIONS"):
        plan.append((
            "sber",
            lambda limit=0: SberScraper(limit=limit or 5000, stealth=True, headless=headless),
            SBER_QUERIES,
        ))

    return plan


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


def _save(by_id: dict, stats: dict, now_iso: str):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated": now_iso,
        "total": len(by_id),
        "stats_last_run": stats,
        "vacancies": sorted(by_id.values(), key=lambda v: v.get("first_seen", ""), reverse=True),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scrapers", help="Comma-separated list of scrapers to run (e.g. yandex,google)")
    parser.add_argument("--limit", type=int, help="Override default vacancy limit per scraper")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser with a visible window (helps bypass WAF/JS-challenge on Sber)")
    parser.add_argument("--include-sber", action="store_true",
                        help="Opt into Sber scraping in CI; local runs include it by default")
    args = parser.parse_args()

    print(f"🚀 Online scrape @ {datetime.now(timezone.utc).isoformat()}")
    by_id = _load_existing()
    stats: dict[str, dict[str, int]] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    allowed = {s.strip() for s in args.scrapers.split(",") if s.strip()} if args.scrapers else None
    include_sber = (
        args.include_sber
        or bool(allowed and "sber" in allowed)
        or os.environ.get("ENABLE_SBER_SCRAPER") == "1"
    )

    for key, factory, queries in _source_plan(headless=not args.headed, include_sber=include_sber):
        if allowed and key not in allowed:
            continue
            
        stats[key] = {"new": 0, "errors": 0}
        print(f"\n── {key} ──")
        try:
            scraper = factory(limit=args.limit or 0)
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
                # Save after EACH query for maximum safety
                _save(by_id, stats, now_iso)
            except Exception as e:
                print(f"  ✗ {key} on '{q}': {e}")
                traceback.print_exc(limit=2, file=sys.stderr)
                stats[key]["errors"] += 1

    total_new = sum(s["new"] for s in stats.values())
    print(f"\n✅ Done. {total_new} new, {len(by_id)} total → {OUTPUT}")
    for k, s in stats.items():
        print(f"   {k}: +{s['new']} new, {s['errors']} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
