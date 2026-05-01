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

# Load tools/cv_matcher/.env *before* the env-presence checks below.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

INPUT = ROOT.parent.parent / "public" / "online_scraped.json"
DB_PATH = str(ROOT / "chroma_db")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT))
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--model", default=None,
                        help="Embedding model. Defaults: text-embedding-3-small (cv-api/openai), "
                             "embeddinggemma (ollama).")
    parser.add_argument("--provider", choices=("cv-api", "openai", "ollama"),
                        default="cv-api")
    parser.add_argument("--reset", action="store_true",
                        help="Drop the collection before indexing (rebuild from scratch)")
    parser.add_argument("--prefixes", default="meta_,yandex_,goog_,sber_",
                        help="Comma-separated id prefixes to include (default: all supported)")
    args = parser.parse_args()

    os.environ["EMBEDDINGS_PROVIDER"] = args.provider
    if args.provider == "cv-api":
        if not os.environ.get("CV_API_URL") or not os.environ.get("API_SECRET"):
            print("❌ cv-api provider requires CV_API_URL + API_SECRET in tools/cv_matcher/.env")
            return 1
        if args.model:
            os.environ["OPENAI_EMBEDDING_MODEL"] = args.model
    elif args.provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            print("❌ openai provider requires OPENAI_API_KEY")
            return 1
        if args.model:
            os.environ["OPENAI_EMBEDDING_MODEL"] = args.model
    else:  # ollama
        if args.model:
            os.environ["OLLAMA_EMBEDDING_MODEL"] = args.model

    from src.rag_db import RAGDatabase  # noqa: E402

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"❌ {in_path} not found — run scripts/scrape_online.py first.")
        return 1
    data = json.loads(in_path.read_text(encoding="utf-8"))
    prefixes = tuple(p.strip() for p in args.prefixes.split(",") if p.strip())
    selected = [v for v in data.get("vacancies", []) if v.get("id", "").startswith(prefixes)]
    if not selected:
        print(f"❌ No vacancies with prefixes {prefixes} in input.")
        return 1
    by_company: dict[str, int] = {}
    for v in selected:
        co = v.get("company") or "Unknown"
        by_company[co] = by_company.get(co, 0) + 1
    print(f"📦 Loaded {len(selected)} vacancies: {by_company}")

    db = RAGDatabase(db_path=args.db)

    if args.reset:
        # Drop the whole collection. Mixed embedding-dimension spaces (e.g. old
        # 768-dim Ollama vs new 1536-dim OpenAI) cannot coexist in one ChromaDB
        # collection, so we recreate from scratch when --reset is passed.
        try:
            db.client.delete_collection(name=db.collection_name)
            print(f"🗑  Dropped collection '{db.collection_name}'")
        except Exception as e:
            print(f"  (no existing collection to drop: {e})")
        db.collection = db.client.get_or_create_collection(
            name=db.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    db.add_vacancies(selected)
    print(f"📊 Collection size: {db.collection.count()} total documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
