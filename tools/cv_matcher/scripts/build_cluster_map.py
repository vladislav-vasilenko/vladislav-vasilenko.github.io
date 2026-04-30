#!/usr/bin/env python3
"""Build a 2D cluster map of Meta vacancies + your resume.

Reads:
  - chroma_db/                              (vacancy embeddings, openai or ollama)
  - content/en/{about*.md, cv.json, experience/*.md}  (resume — used for the "you" point)
  - public/vacancy_tree.json                (category/team enrichment)

Writes:
  - public/cluster_map.json

Pipeline:
  1. Pull all Meta vacancy embeddings from ChromaDB
  2. Build resume text from English content/* markdown + cv.json, embed it once
  3. UMAP-project [resume + 541 vacancies] → 2D (one fit on the joint matrix)
  4. HDBSCAN cluster the 2D points; for each cluster compute a label
     (most common category + most common role-stem)
  5. Compute cosine-distance-to-resume for each vacancy → top_matches list
  6. Compute axis-pole labels (top 3 vacancies at each end of x and y)

Usage:
    export OPENAI_API_KEY=sk-...
    uv run python scripts/build_cluster_map.py
    uv run python scripts/build_cluster_map.py --provider ollama  # use local
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent              # tools/cv_matcher
REPO = ROOT.parent.parent                                  # repo root
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

DB_PATH = str(ROOT / "chroma_db")
TREE_JSON = REPO / "public" / "vacancy_tree.json"
OUT = REPO / "public" / "cluster_map.json"
CONTENT_EN = REPO / "content" / "en"


# ──────────────────────────────────────────────────────────────────────
# Resume → text
# ──────────────────────────────────────────────────────────────────────
def _strip_md(s: str) -> str:
    """Light markdown-to-plain conversion (good enough for embeddings)."""
    s = re.sub(r"```.*?```", " ", s, flags=re.DOTALL)
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", s)            # images
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)         # links → text
    s = re.sub(r"[#*_>`]+", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _flatten_cv_json(j: Any, depth: int = 0, max_depth: int = 6) -> str:
    """Linearise cv.json (key:value pairs) into a sentence-ish string."""
    if depth > max_depth:
        return ""
    if isinstance(j, str):
        return j.strip()
    if isinstance(j, (int, float, bool)):
        return str(j)
    if isinstance(j, list):
        return ". ".join(p for p in (_flatten_cv_json(x, depth + 1, max_depth) for x in j) if p)
    if isinstance(j, dict):
        parts: List[str] = []
        for k, v in j.items():
            sub = _flatten_cv_json(v, depth + 1, max_depth)
            if sub:
                parts.append(f"{k}: {sub}")
        return ". ".join(parts)
    return ""


def load_resume_text(content_dir: Path) -> str:
    """Concatenate English about/experience markdown + cv.json into one block."""
    chunks: List[str] = []
    # cv.json (structured)
    cv_path = content_dir / "cv.json"
    if cv_path.exists():
        try:
            chunks.append(_flatten_cv_json(json.loads(cv_path.read_text(encoding="utf-8"))))
        except Exception as e:
            print(f"  ⚠️ cv.json parse error: {e}")
    # about*.md (full, not -short)
    for md in sorted(content_dir.glob("about*.md")):
        chunks.append(_strip_md(md.read_text(encoding="utf-8")))
    # experience long-form (drop -short variants — they duplicate content)
    exp_dir = content_dir / "experience"
    if exp_dir.exists():
        for md in sorted(exp_dir.glob("*.md")):
            if md.stem.endswith("-short"):
                continue
            chunks.append(_strip_md(md.read_text(encoding="utf-8")))
    return "\n\n".join(c for c in chunks if c)


# ──────────────────────────────────────────────────────────────────────
# Tree enrichment lookup
# ──────────────────────────────────────────────────────────────────────
def load_tree_index(tree_path: Path) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (id→role_node, categories_registry)."""
    if not tree_path.exists():
        return {}, []
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    idx: Dict[str, Dict[str, Any]] = {}
    for c in tree.get("clusters", []):
        for sc in c.get("sub_clusters", []):
            for b in sc.get("buckets", []):
                for r in b.get("roles", []):
                    enriched = dict(r)
                    enriched["team"] = c["name"]
                    enriched["sub_team"] = sc["name"]
                    idx[r["id"]] = enriched
    return idx, tree.get("categories", [])


# ──────────────────────────────────────────────────────────────────────
# Cluster labelling
# ──────────────────────────────────────────────────────────────────────
def _cluster_label(members: List[Dict[str, Any]]) -> str:
    """Concise 2-4 word label from member roles (no LLM)."""
    cats = Counter(m["category"] for m in members)
    teams = Counter(m["team"] for m in members)
    stems = Counter(m["stem"] for m in members)
    top_team = teams.most_common(1)[0][0]
    top_stem = stems.most_common(1)[0][0]
    top_cat = cats.most_common(1)[0][0]
    # Prefer team if it dominates (>40%); fall back to a stem-based label
    if teams.most_common(1)[0][1] / len(members) >= 0.4:
        return top_team
    return f"{top_cat.title()} · {top_stem.title()[:30]}"


def axis_pole_labels(points: np.ndarray, ids: List[str], id_to_role: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """For each axis end, list the 3 most extreme vacancies for visual orientation."""
    def pole(arr_idx: int, sign: int) -> List[Dict[str, Any]]:
        order = np.argsort(points[:, arr_idx] * sign)[:5]
        return [
            {
                "id": ids[i],
                "title": id_to_role.get(ids[i], {}).get("title", ids[i]),
                "team": id_to_role.get(ids[i], {}).get("team", ""),
                "category": id_to_role.get(ids[i], {}).get("category", ""),
            }
            for i in order
        ]
    return {
        "x_left":  pole(0, -1),  # most negative X
        "x_right": pole(0,  1),
        "y_bottom":pole(1, -1),
        "y_top":   pole(1,  1),
    }


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--provider", choices=("cv-api", "openai", "ollama"), default="cv-api")
    parser.add_argument("--model", default=None,
                        help="Embedding model (default: text-embedding-3-small / embeddinggemma)")
    parser.add_argument("--n-neighbors", type=int, default=15,
                        help="UMAP n_neighbors (lower → more local clumps)")
    parser.add_argument("--min-dist", type=float, default=0.10,
                        help="UMAP min_dist (lower → tighter clusters)")
    parser.add_argument("--top-matches", type=int, default=30)
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
            print("❌ OPENAI_API_KEY not set; pass --provider cv-api or --provider ollama")
            return 1
        if args.model:
            os.environ["OPENAI_EMBEDDING_MODEL"] = args.model
    else:
        if args.model:
            os.environ["OLLAMA_EMBEDDING_MODEL"] = args.model

    from src.rag_db import RAGDatabase  # noqa: E402

    SUPPORTED_PREFIXES = ("meta_", "yandex_", "goog_")
    db = RAGDatabase(db_path=args.db)
    data = db.collection.get(include=["embeddings", "metadatas", "documents"])
    keep = [i for i, vid in enumerate(data["ids"]) if vid.startswith(SUPPORTED_PREFIXES)]
    if not keep:
        print(f"❌ No supported vacancies in ChromaDB. Run scripts/index_meta_to_chroma.py first.")
        return 1
    vacancy_ids = [data["ids"][i] for i in keep]
    vacancy_vecs = np.array([data["embeddings"][i] for i in keep], dtype=np.float32)
    vacancy_companies = [(data["metadatas"][i] or {}).get("company") or "Unknown" for i in keep]
    company_counts: Dict[str, int] = {}
    for c in vacancy_companies:
        company_counts[c] = company_counts.get(c, 0) + 1
    print(f"📦 Loaded {len(vacancy_ids)} vacancy embeddings (dim={vacancy_vecs.shape[1]}) — {company_counts}")

    # ── Resume embedding ──────────────────────────────────────────────
    resume_text = load_resume_text(CONTENT_EN)
    if not resume_text or len(resume_text) < 200:
        print(f"❌ Resume text too short ({len(resume_text)} chars) — check {CONTENT_EN}")
        return 1
    print(f"📄 Resume text: {len(resume_text):,} chars from {CONTENT_EN}")
    cv_vec = np.array(db.embeddings.embed_query(resume_text), dtype=np.float32)

    # ── UMAP joint projection ─────────────────────────────────────────
    print("🌀 UMAP fit on resume + vacancies (cosine metric)…")
    import umap  # noqa: E402
    joint = np.vstack([cv_vec[None, :], vacancy_vecs])
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=args.n_neighbors,
        min_dist=args.min_dist,
        metric="cosine",
        random_state=42,
    )
    coords2d = reducer.fit_transform(joint).astype(np.float32)
    cv_xy = coords2d[0]
    vac_xy = coords2d[1:]

    # ── Cosine distances to resume ────────────────────────────────────
    cv_norm = cv_vec / max(1e-9, np.linalg.norm(cv_vec))
    vac_norm = vacancy_vecs / np.maximum(1e-9, np.linalg.norm(vacancy_vecs, axis=1, keepdims=True))
    cos_sim = vac_norm @ cv_norm
    cos_dist = 1 - cos_sim

    # ── Tree enrichment ───────────────────────────────────────────────
    id_to_role, categories = load_tree_index(TREE_JSON)
    if not id_to_role:
        print(f"⚠️ {TREE_JSON} not found or empty — points won't have category/team labels")

    # ── HDBSCAN clusters in 2D ────────────────────────────────────────
    from sklearn.cluster import HDBSCAN  # noqa: E402
    print("🔗 HDBSCAN clustering on 2D coords…")
    cluster_labels = HDBSCAN(min_cluster_size=8, min_samples=3).fit_predict(vac_xy)

    points: List[Dict[str, Any]] = []
    cluster_members: Dict[int, List[Dict[str, Any]]] = {}
    for i, vid in enumerate(vacancy_ids):
        info = id_to_role.get(vid, {})
        pt = {
            "id": vid,
            "x": float(vac_xy[i, 0]),
            "y": float(vac_xy[i, 1]),
            "title": info.get("title", vid),
            "company": info.get("company") or vacancy_companies[i],
            "team": info.get("team", ""),
            "sub_team": info.get("sub_team", ""),
            "category": info.get("category", "engineering"),
            "category_emoji": info.get("category_emoji", "⚙️"),
            "level": info.get("level", "IC"),
            "level_rank": info.get("level_rank", 2),
            "compensation": info.get("compensation", ""),
            "link": info.get("link", ""),
            "is_research": bool(info.get("is_research", False)),
            "is_product": bool(info.get("is_product", False)),
            "cluster": int(cluster_labels[i]),
            "distance_to_cv": float(cos_dist[i]),
            "first_seen": info.get("first_seen", ""),
        }
        points.append(pt)
        cluster_members.setdefault(int(cluster_labels[i]), []).append(pt)

    cluster_summary: List[Dict[str, Any]] = []
    for cid, members in sorted(cluster_members.items()):
        if cid == -1:                                     # noise
            continue
        xs = np.array([m["x"] for m in members])
        ys = np.array([m["y"] for m in members])
        cluster_summary.append({
            "id": cid,
            "size": len(members),
            "label": _cluster_label([{**m, "stem": id_to_role.get(m["id"], {}).get("stem", "")} for m in members]),
            "centroid_x": float(xs.mean()),
            "centroid_y": float(ys.mean()),
            "category_counts": dict(Counter(m["category"] for m in members)),
            "team_counts": dict(Counter(m["team"] for m in members)),
        })

    # ── Top matches to resume ─────────────────────────────────────────
    order = np.argsort(cos_dist)[: args.top_matches]
    top_matches = [
        {
            "id": vacancy_ids[int(i)],
            "title": points[int(i)]["title"],
            "company": points[int(i)]["company"],
            "team": points[int(i)]["team"],
            "sub_team": points[int(i)]["sub_team"],
            "category": points[int(i)]["category"],
            "category_emoji": points[int(i)]["category_emoji"],
            "level": points[int(i)]["level"],
            "compensation": points[int(i)]["compensation"],
            "link": points[int(i)]["link"],
            "distance": float(cos_dist[int(i)]),
            "similarity": float(cos_sim[int(i)]),
        }
        for i in order
    ]

    payload = {
        "company": " + ".join(sorted(set(vacancy_companies))) if vacancy_companies else "Unknown",
        "companies": sorted(set(vacancy_companies)),
        "company_counts": company_counts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": {
            "umap_n_neighbors": args.n_neighbors,
            "umap_min_dist": args.min_dist,
            "embedding_provider": args.provider,
            "embedding_model": os.environ.get(
                "OPENAI_EMBEDDING_MODEL" if args.provider == "openai" else "OLLAMA_EMBEDDING_MODEL",
                "default"),
        },
        "stats": {
            "vacancies": len(points),
            "clusters": len(cluster_summary),
            "noise_points": sum(1 for p in points if p["cluster"] == -1),
            "resume_chars": len(resume_text),
        },
        "categories": categories,
        "cv": {
            "x": float(cv_xy[0]),
            "y": float(cv_xy[1]),
            "label": "You",
        },
        "vacancies": points,
        "clusters": cluster_summary,
        "axis_poles": axis_pole_labels(vac_xy, vacancy_ids, id_to_role),
        "top_matches": top_matches,
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Wrote {args.out} ({Path(args.out).stat().st_size:,} bytes)")
    print(f"   {len(points)} vacancies, {len(cluster_summary)} clusters, "
          f"{sum(1 for p in points if p['cluster'] == -1)} noise points")
    print(f"   Top match: {top_matches[0]['title']} (sim={top_matches[0]['similarity']:.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
