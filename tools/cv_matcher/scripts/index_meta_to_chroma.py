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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load tools/cv_matcher/.env *before* the env-presence checks below.
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

REPO_PUBLIC = ROOT.parent.parent / "public"
INPUT_RAW = REPO_PUBLIC / "online_scraped.json"
INPUT_EN = REPO_PUBLIC / "online_scraped_en.json"
# Prefer translated EN file when present — semantic clustering benefits from
# a single-language corpus and brand-mask preprocessing below.
INPUT = INPUT_EN if INPUT_EN.exists() else INPUT_RAW
DB_PATH = str(ROOT / "chroma_db")

# ── Embedding-text preprocessing ───────────────────────────────────────
# Pipeline (run at index time; source JSON is never mutated):
#   1. Try to extract the role-specific section (Responsibilities/Qualifications/...)
#      to skip the company-intro paragraph that starts most descriptions
#   2. Strip brand & product tokens (Meta/Google/Sber/GigaChat/Workspace/...)
#   3. Strip HR/form/legal boilerplate (form fields, equal-opportunity, etc.)
#   4. Truncate to MAX_EMBED_CHARS so longer corp descriptions don't outweigh
#      shorter ones in the embedding (= fairer cross-company comparison)

MAX_EMBED_CHARS = 1600  # ≈ 400 tokens; balanced for text-embedding-3-small

BRAND_PATTERNS = [
    # English brand names + sub-products
    r"\bmeta\b", r"\bmetaverse\b", r"\bfacebook\b", r"\binstagram\b", r"\bwhatsapp\b",
    r"\bgoogle\b", r"\bgmail\b", r"\bandroid\b", r"\bworkspace\b", r"\bdeepmind\b",
    r"\bgemini\b", r"\bvertex\b", r"\bbigquery\b", r"\bgcp\b", r"\bpixel\b",
    r"\bsber(?:bank)?\b", r"\bgigachat\b", r"\bkandinsky\b", r"\bsalute\w*\b", r"\bsbol\b",
    r"\bsmartway\b", r"\bkinopoisk\b",
    r"\byandex\b", r"\balice\b",
    # Russian variants (residual, in case any RU passed through)
    r"\bсбер\w*\b", r"\bяндекс\w*\b", r"\bалиса\b", r"\bкандинский\b",
    r"\bпао\b", r"\bпjsc\b",
]
BRAND_RE = re.compile("|".join(BRAND_PATTERNS), re.IGNORECASE)

# HR / form / legal boilerplate that's nearly identical across thousands of postings
BOILERPLATE_PATTERNS = [
    # Form-field stubs (Sber)
    r"apply for the position[^.\n]*[.\n]?",
    r"vacancies career media[^.\n]*[.\n]?",
    r"last name first name email[^.\n]*[.\n]?",
    r"attach resume[^.\n]*[.\n]?",
    r"i consent to (?:the )?processing of personal data[^.\n]*[.\n]?",
    # English HR/legal blocks (Meta/Google)
    r"is (?:proud to be |an )?equal[\s\-]?opportunity employer[^.]*\.",
    r"all qualified applicants will receive consideration[^.]*\.",
    r"learn more about [a-z]+'s commitment to[^.]*\.",
    r"competitive (?:salary|benefits|compensation|pay)[^.]*\.",
    r"benefits include[^.]*\.",
    r"join our team[^.\n]*[.\n]?",
    r"why work at[^.\n]*[.\n]?",
    r"about (?:us|the company|our team)[:\.]?",
    # URLs + emails (often link to corporate pages)
    r"https?://\S+",
    r"\S+@[\w\-]+\.\w+",
    # Geographic / time markers from Sber listings ("15 April 2026 • Moscow")
    r"\b\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b",
]
BOILERPLATE_RE = re.compile("|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)

# Section markers — when found, embed text starting at the EARLIEST marker.
# Order matters only for tie-breaking; we use earliest position in the doc.
SECTION_MARKERS = [
    "responsibilities", "what you'll do", "what you will do",
    "your role", "in this role", "the role",
    "requirements", "qualifications", "skills required",
    "what we're looking for", "what we are looking for",
    "tech stack", "technical stack", "technology stack",
    "duties", "responsibilities and duties",
]
MARKER_RE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in SECTION_MARKERS) + r")\b[:\.\s]",
    re.IGNORECASE,
)


def extract_role_section(text: str) -> str:
    """If the text contains a role-section marker reasonably early (before the
    last 30%), drop everything before it. Otherwise return the text as-is —
    fallback is to skip the first 25% via subsequent truncation."""
    if not text or len(text) < 400:
        return text
    m = MARKER_RE.search(text)
    if not m:
        return text
    # Use marker only if it appears in the first 70% (avoid clipping out core content)
    if m.start() < len(text) * 0.7:
        return text[m.start():]
    return text


def clean_for_embedding(title: str, description: str) -> tuple[str, str]:
    """Strip brand/product tokens + form boilerplate, extract role section,
    truncate. Source data in online_scraped*.json is never mutated."""
    t = BRAND_RE.sub(" ", title or "")
    t = re.sub(r"\s+", " ", t).strip()

    d = description or ""
    # 1. Extract role-specific section
    d = extract_role_section(d)
    # 2. Strip brand tokens
    d = BRAND_RE.sub(" ", d)
    # 3. Strip boilerplate
    d = BOILERPLATE_RE.sub(" ", d)
    # 4. Collapse whitespace + truncate
    d = re.sub(r"\s+", " ", d).strip()
    d = d[:MAX_EMBED_CHARS]
    return t, d


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
    parser.add_argument("--no-clean", action="store_true",
                        help="Skip brand-token masking before embedding (keep raw text)")
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
    src_label = "EN-translated" if str(in_path).endswith("_en.json") else "raw"
    print(f"📦 Loaded {len(selected)} vacancies ({src_label}): {by_company}")

    if not args.no_clean:
        # Build cleaned text under _embed_* keys; preserve original title/desc
        # for ChromaDB metadata (UI shows real names; embedding sees neutralised text).
        for v in selected:
            t, d = clean_for_embedding(v.get("title", ""), v.get("description", ""))
            v["_embed_title"] = t
            v["_embed_description"] = d
        print(f"🧹 Brand-mask preprocessing applied "
              f"(strip 'Meta/Google/Sber/Yandex/...' from embed text only)")

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
