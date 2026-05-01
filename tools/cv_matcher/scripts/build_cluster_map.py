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
    """Concise 2-4 word label from member roles (no LLM, used as fallback)."""
    cats = Counter(m["category"] for m in members)
    teams = Counter(m["team"] for m in members)
    stems = Counter(m["stem"] for m in members)
    top_team = teams.most_common(1)[0][0]
    top_stem = stems.most_common(1)[0][0]
    top_cat = cats.most_common(1)[0][0]
    # Prefer team if it dominates (>40%) AND is not the placeholder "Other"
    if top_team not in ("Other", "", None) and teams.most_common(1)[0][1] / len(members) >= 0.4:
        return top_team
    return f"{top_cat.title()} · {top_stem.title()[:30]}"


def _signature(titles: List[str]) -> str:
    """Stable cache key for a cluster — sorted top-N titles."""
    import hashlib
    canon = "|".join(sorted(t.strip().lower() for t in titles[:10]))
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:16]


def llm_label_clusters(
    cluster_summary: List[Dict[str, Any]],
    cluster_members: Dict[int, List[Dict[str, Any]]],
    cv_api_url: str,
    api_secret: str,
    model: str = "gpt-5.4-nano",
    cache_path: Path = None,
) -> Dict[int, str]:
    """Generate concise semantic labels via cv-api /translate (gpt-5.4-nano).
    Returns {cluster_id: label}. Cached by cluster signature so repeat runs
    only LLM-call clusters whose membership changed."""
    import requests

    cache: Dict[str, str] = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    # Build prompt input — only for clusters not already cached
    sigs: Dict[int, str] = {}
    to_label: Dict[str, List[str]] = {}
    for c in cluster_summary:
        cid = c["id"]
        members = cluster_members.get(cid, [])
        # Pick the 8 most representative titles (closest to centroid would be ideal,
        # but first 8 sorted by distance_to_cv works as a stable proxy)
        sample_titles = [m["title"] for m in members[:10] if m.get("title")]
        sig = _signature(sample_titles)
        sigs[cid] = sig
        if sig not in cache:
            to_label[str(cid)] = sample_titles[:8]

    if to_label:
        print(f"🏷️  LLM-labelling {len(to_label)} clusters via {model}…")
        system_msg = (
            "You label clusters of similar job vacancies. For each cluster you receive "
            "a sample of role titles. Return a CONCISE 2–5 word semantic label that "
            "captures the dominant role-type, team, or technology. NEVER include company "
            "names. Be specific (e.g. 'ML Infrastructure', 'Cloud DevOps', 'Search Ranking', "
            "'Data Engineering', 'Computer Vision Research', 'Mobile iOS', 'Trust & Safety', "
            "'TPM / Program Management'). Avoid generic 'Engineering' or 'Other'.\n\n"
            "Output STRICTLY a JSON object {\"labels\": {\"<cluster_id>\": \"<label>\", ...}} "
            "with one entry per input cluster."
        )
        user_msg = "Label these clusters:\n" + json.dumps(to_label, ensure_ascii=False)
        try:
            url = cv_api_url.rstrip("/")
            if url.endswith("/ats") or url.endswith("/embeddings"):
                url = url.rsplit("/", 1)[0]
            url = url + "/translate"
            r = requests.post(
                url,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                },
                headers={"Authorization": f"Bearer {api_secret}", "Content-Type": "application/json"},
                timeout=120,
            )
            r.raise_for_status()
            resp = r.json()
            # OpenAI /v1/responses shape: output[0].content[0].text → JSON string
            text = ""
            if "output" in resp and isinstance(resp["output"], list):
                for item in resp["output"]:
                    cont = item.get("content") or []
                    for c in cont:
                        if c.get("type") in ("output_text", "text"):
                            text += c.get("text", "")
            if not text:
                raise RuntimeError(f"empty LLM response: {str(resp)[:200]}")
            parsed = json.loads(text)
            new_labels = parsed.get("labels", {})
            # Map back: for each cluster_id we just labelled, store under signature
            for cid_str, label in new_labels.items():
                try:
                    cid_int = int(cid_str)
                except ValueError:
                    continue
                if cid_int in sigs:
                    cache[sigs[cid_int]] = (label or "").strip()
            print(f"   ✓ {len(new_labels)} new labels generated")
        except Exception as e:
            print(f"   ⚠️ LLM-label call failed ({type(e).__name__}: {e}); using heuristic fallback")
    else:
        print(f"🏷️  All {len(cluster_summary)} clusters served from cache")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    return {cid: cache.get(sig, "") for cid, sig in sigs.items()}


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
    parser.add_argument("--n-neighbors", type=int, default=30,
                        help="UMAP n_neighbors (higher → smoother global topology, "
                             "less local company-clumping). Default tuned for cross-company "
                             "semantic clusters.")
    parser.add_argument("--min-dist", type=float, default=0.25,
                        help="UMAP min_dist (higher → less tight clusters; helps semantic "
                             "groups merge across employer boundaries)")
    parser.add_argument("--top-matches", type=int, default=30)
    parser.add_argument("--debias", action="store_true", default=True,
                        help="Subtract per-company mean from each embedding before "
                             "UMAP/HDBSCAN to break company-segregated clusters "
                             "(default: True). Pass --no-debias to disable.")
    parser.add_argument("--no-debias", dest="debias", action="store_false")
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

    SUPPORTED_PREFIXES = ("meta_", "yandex_", "goog_", "sber_")
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

    # ── PCA-based company-debias (used only for clustering geometry) ──
    # Per-company mean subtraction kills only ONE direction. Better: build
    # the subspace spanned by all company-centroid differences (top-K via SVD)
    # and project that subspace OUT of every embedding. Removes K dimensions
    # of "company-style" variance instead of just K=1. Source vectors are
    # preserved for honest cosine-distance-to-CV computation below.
    vac_for_clustering = vacancy_vecs
    cv_for_clustering = cv_vec.copy()
    if args.debias:
        company_to_indices: Dict[str, List[int]] = {}
        for i, c in enumerate(vacancy_companies):
            company_to_indices.setdefault(c, []).append(i)
        # Stack per-company centroid vectors
        centroids = np.array([
            vacancy_vecs[idxs].mean(axis=0)
            for co, idxs in company_to_indices.items() if len(idxs) >= 2
        ])
        if centroids.shape[0] >= 2:
            # Centre, then SVD → orthonormal basis of company-variance subspace
            centred = centroids - centroids.mean(axis=0)
            n_comp = min(centroids.shape[0] - 1, 3)  # keep at most 3 directions
            _U, _S, Vt = np.linalg.svd(centred, full_matrices=False)
            basis = Vt[:n_comp]                                        # (k, dim)
            # Project all vectors onto basis and SUBTRACT the projection
            proj_coefs = vacancy_vecs @ basis.T                        # (n, k)
            debiased = vacancy_vecs - proj_coefs @ basis               # (n, dim)
            cv_proj_coefs = cv_vec @ basis.T                           # (k,)
            cv_for_clustering = cv_vec - cv_proj_coefs @ basis
            # Re-normalise so cosine geometry stays meaningful in UMAP
            norms = np.linalg.norm(debiased, axis=1, keepdims=True)
            debiased = debiased / np.maximum(norms, 1e-9)
            cv_for_clustering = cv_for_clustering / max(
                1e-9, np.linalg.norm(cv_for_clustering)
            )
            vac_for_clustering = debiased.astype(np.float32)
            print(f"⚖️  PCA-debias: removed top-{n_comp} company-variance directions "
                  f"({centroids.shape[0]} companies)")
        else:
            print("⚠️  Skipping debias (need ≥2 companies)")

    # ── UMAP joint projection ─────────────────────────────────────────
    print(f"🌀 UMAP fit (n_neighbors={args.n_neighbors}, min_dist={args.min_dist}, cosine)…")
    import umap  # noqa: E402
    joint = np.vstack([cv_for_clustering[None, :], vac_for_clustering])
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

    # ── Per-vacancy nearest neighbours (3 lenses) ─────────────────────
    # For each vacancy we compute three top-N lists:
    #   • similar_same_co  — most similar within the SAME employer
    #   • similar_other_co — most similar across all OTHER employers
    #   • cross_lang_top10 — most similar in the OPPOSITE language family
    # The UI uses these as separate panels: internal mobility vs external
    # competition vs cross-language market scan.
    LANG_BY_COMPANY = {
        "Meta": "en",
        "Google": "en",
        "Яндекс": "ru",
        "Сбер": "ru",
        "Sber": "ru",
    }
    TOP_N = 10
    company_arr = np.array(vacancy_companies)
    lang_arr = np.array([LANG_BY_COMPANY.get(c, "en") for c in vacancy_companies])
    full_sim = vac_norm @ vac_norm.T                       # (n, n) cosine sim
    np.fill_diagonal(full_sim, -np.inf)                    # exclude self
    similar_same: Dict[str, List[Dict[str, Any]]] = {}
    similar_other: Dict[str, List[Dict[str, Any]]] = {}
    cross_lang_top: Dict[str, List[Dict[str, Any]]] = {}
    for i, vid in enumerate(vacancy_ids):
        co = company_arr[i]
        my_lang = lang_arr[i]
        same_mask = (company_arr == co)
        same_mask[i] = False
        other_mask = ~(company_arr == co)                  # excludes self by company
        other_mask[i] = False
        cross_lang_mask = (lang_arr != my_lang)            # opposite language family
        cross_lang_mask[i] = False
        for label, mask, sink in (
            ("same",  same_mask,       similar_same),
            ("other", other_mask,      similar_other),
            ("xlang", cross_lang_mask, cross_lang_top),
        ):
            if not mask.any():
                sink[vid] = []
                continue
            sims = np.where(mask, full_sim[i], -np.inf)
            order = np.argsort(-sims)[:TOP_N]
            sink[vid] = [
                {"id": vacancy_ids[int(j)], "similarity": float(full_sim[i, int(j)])}
                for j in order if sims[j] != -np.inf
            ]
    print(f"🏢 Neighbours computed: same-co + other-co + cross-lang (top-{TOP_N} each)")

    # ── Tree enrichment ───────────────────────────────────────────────
    id_to_role, categories = load_tree_index(TREE_JSON)
    if not id_to_role:
        print(f"⚠️ {TREE_JSON} not found or empty — points won't have category/team labels")

    # ── HDBSCAN clusters in 2D ────────────────────────────────────────
    from sklearn.cluster import HDBSCAN  # noqa: E402
    print("🔗 HDBSCAN clustering on 2D coords…")
    cluster_labels = HDBSCAN(min_cluster_size=8, min_samples=3).fit_predict(vac_xy)

    # ── Calculate promising threshold ──
    # Top 50 closest vectors
    promising_threshold = float(np.sort(cos_dist)[min(50, len(cos_dist)-1)]) if len(cos_dist) > 0 else 1.0

    points: List[Dict[str, Any]] = []
    cluster_members: Dict[int, List[Dict[str, Any]]] = {}
    for i, vid in enumerate(vacancy_ids):
        info = id_to_role.get(vid, {})
        title_str = info.get("title", vid)
        is_res = bool(info.get("is_research", False))
        is_prod = bool(info.get("is_product", False))
        is_lin = (
            info.get("category", "engineering") == "engineering"
            and not is_res
            and not is_prod
            and "Forward Deployed" not in title_str
            and "Applied AI" not in title_str
            and "GenAI" not in title_str
        )
        
        pt = {
            "id": vid,
            "x": float(vac_xy[i, 0]),
            "y": float(vac_xy[i, 1]),
            "title": title_str,
            "company": info.get("company") or vacancy_companies[i],
            "team": info.get("team", ""),
            "sub_team": info.get("sub_team", ""),
            "category": info.get("category", "engineering"),
            "category_emoji": info.get("category_emoji", "⚙️"),
            "level": info.get("level", "IC"),
            "level_rank": info.get("level_rank", 2),
            "compensation": info.get("compensation", ""),
            "link": info.get("link", ""),
            "is_research": is_res,
            "is_product": is_prod,
            "is_linear": is_lin,
            "is_promising": float(cos_dist[i]) <= promising_threshold,
            "cluster": int(cluster_labels[i]),
            "distance_to_cv": float(cos_dist[i]),
            "first_seen": info.get("first_seen", ""),
            "similar_same_co": similar_same.get(vid, []),
            "similar_other_co": similar_other.get(vid, []),
            "cross_lang_top10": cross_lang_top.get(vid, []),
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

    # ── LLM-based semantic labels via cv-api /translate (gpt-5.4-nano) ──
    cv_api_url = os.environ.get("CV_API_URL")
    api_secret = os.environ.get("API_SECRET")
    if cv_api_url and api_secret:
        cache_path = ROOT / ".cache" / "cluster_labels.json"
        llm_labels = llm_label_clusters(
            cluster_summary, cluster_members,
            cv_api_url=cv_api_url, api_secret=api_secret,
            model="gpt-5.4-nano", cache_path=cache_path,
        )
        # Override "Other" / generic labels with LLM versions when available
        for c in cluster_summary:
            new = (llm_labels.get(c["id"]) or "").strip()
            if new and new.lower() not in ("other", ""):
                c["label"] = new
    else:
        print("⚠️  CV_API_URL or API_SECRET not set — skipping LLM-labelling")

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
