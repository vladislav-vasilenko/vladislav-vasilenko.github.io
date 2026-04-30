#!/usr/bin/env python3
"""Index Meta vacancies from online_scraped.json into ChromaDB.

Uses cv-api Vercel proxy by default (CV_API_URL + API_SECRET in tools/cv_matcher/.env).
Falls back to direct OpenAI if EMBEDDINGS_PROVIDER=openai. Or local Ollama
with --provider ollama.

Usage:
    uv run python scripts/index_meta_to_chroma.py                    # cv-api proxy
    uv run python scripts/index_meta_to_chroma.py --reset            # drop+rebuild Meta
    uv run python scripts/index_meta_to_chroma.py --provider ollama  # local
    uv run python scripts/index_meta_to_chroma.py --model text-embedding-3-large

Cost via cv-api: ~$0.007 (541 jobs × ~600 tokens × $0.02/M for 3-small).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INPUT = ROOT.parent.parent / "public" / "online_scraped.json"
DB_PATH = str(ROOT / "chroma_db")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--model", default="text-embedding-3-small")
    parser.add_argument("--provider", choices=("cv-api", "openai", "ollama"),
                        default="cv-api")
    parser.add_argument("--reset", action="store_true",
                        help="Delete only Meta-prefixed ids before indexing")
    args = parser.parse_args()

    os.environ["EMBEDDINGS_PROVIDER"] = args.provider
    os.environ["OPENAI_EMBEDDING_MODEL"] = args.model
    if args.provider == "cv-api":
        if not os.environ.get("CV_API_URL") or not os.environ.get("API_SECRET"):
            print("❌ cv-api provider requires CV_API_URL + API_SECRET in tools/cv_matcher/.env")
            return 1
    elif args.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("❌ openai provider requires OPENAI_API_KEY")
        return 1

    from src.rag_db import RAGDatabase  # noqa: E402

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"❌ {in_path} not found — run scripts/scrape_online.py first.")
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    meta = [v for v in data.get("vacancies", []) if v.get("id", "").startswith("meta_")]
    if not meta:
        print("❌ No Meta vacancies in input.")
        return 1
    print(f"📦 Loaded {len(meta)} Meta vacancies")

    db = RAGDatabase(db_path=args.db)

    if args.reset:
        existing = db.get_all_ids()
        meta_ids = [vid for vid in existing if vid.startswith("meta_")]
        if meta_ids:
            print(f"🗑  Removing {len(meta_ids)} existing Meta entries from collection")
            db.collection.delete(ids=meta_ids)

    db.add_vacancies(meta)
    print(f"📊 Collection size: {db.collection.count()} total documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
