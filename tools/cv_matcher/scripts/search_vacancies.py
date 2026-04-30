#!/usr/bin/env python3
"""Semantic vacancy search — find jobs by meaning, not just keywords.

Uses the existing ChromaDB vector database to find vacancies most similar
to a natural-language query.

Examples:
    uv run python scripts/search_vacancies.py "HR technologies + ML"
    uv run python scripts/search_vacancies.py "computer vision for autonomous driving" --top 20
    uv run python scripts/search_vacancies.py "NLP research scientist" --company Google
    uv run python scripts/search_vacancies.py "backend python" --company Яндекс --top 10
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.rag_db import RAGDatabase  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="Semantic search over scraped vacancies in ChromaDB",
    )
    parser.add_argument("query", help="Natural-language search query (e.g. 'HR tech + ML')")
    parser.add_argument("--top", type=int, default=15, help="Number of results (default: 15)")
    parser.add_argument("--company", help="Filter by company name (substring, case-insensitive)")
    parser.add_argument("--min-chars", type=int, default=0,
                        help="Only show vacancies with description >= N chars")
    args = parser.parse_args()

    db = RAGDatabase(db_path=str(ROOT / "chroma_db"))
    total = db.collection.count()
    print(f"📊 Database: {total} vacancies indexed\n")

    # Fetch more than needed so we can filter by company afterwards
    fetch_k = args.top * 5 if args.company else args.top
    results = db.search_similar_vacancies(args.query, top_k=fetch_k)

    if args.company:
        cf = args.company.lower()
        results = [r for r in results if cf in (r["metadata"].get("company", "")).lower()]

    if args.min_chars:
        results = [r for r in results if len(r.get("document", "")) >= args.min_chars]

    results = results[:args.top]

    if not results:
        print("❌ No matching vacancies found.")
        return

    print(f"🔍 Top-{len(results)} results for: \"{args.query}\"\n")
    print("=" * 80)

    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        dist = r["distance"]
        similarity = max(0, 1 - dist)  # cosine distance → similarity

        title = meta.get("title", "Unknown")
        company = meta.get("company", "Unknown")
        link = meta.get("link", "")
        sphere = meta.get("sphere", "")

        # Extract a snippet from the document (skip the Title/Company/Date header)
        doc = r.get("document", "")
        # Find the description part after the header
        desc_start = doc.find("Description:")
        snippet = doc[desc_start + 12:].strip() if desc_start >= 0 else doc
        snippet = snippet[:200].replace("\n", " ").strip()

        print(f"\n  #{i}  [{similarity:.0%} match]  {title}")
        print(f"      🏢 {company}  {'🌐 ' + sphere if sphere else ''}")
        print(f"      📝 {snippet}...")
        print(f"      🔗 {link}")

    print("\n" + "=" * 80)
    print(f"Showing {len(results)} of {total} indexed vacancies")


if __name__ == "__main__":
    main()
