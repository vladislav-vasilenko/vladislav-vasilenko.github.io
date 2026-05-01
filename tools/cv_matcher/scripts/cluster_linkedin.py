#!/usr/bin/env python3
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np

def main():
    parser = argparse.ArgumentParser(description="Cluster LinkedIn connections using bge-m3")
    parser.add_argument("--input", default="data/linkedin_connections.json", help="Input JSON from scraper")
    parser.add_argument("--out", default="../../public/linkedin_clusters.json", help="Output JSON for visualization")
    parser.add_argument("--n-neighbors", type=int, default=15, help="UMAP n_neighbors")
    parser.add_argument("--min-dist", type=float, default=0.1, help="UMAP min_dist")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
         print(f"❌ Error: {args.input} not found. Run the scraper first.")
         return 1
         
    with open(input_path, "r", encoding="utf-8") as f:
         connections = json.load(f)
         
    if not connections:
         print("❌ No connections found in input file.")
         return 1

    texts = []
    for c in connections:
        # We embed the name and headline to group similar roles/companies
        text = f"{c.get('name', '')} - {c.get('headline', '')}"
        texts.append(text)

    print(f"📦 Loaded {len(texts)} connections from {args.input}")

    print("🧠 Loading BAAI/bge-m3 embedder...")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("❌ Error: sentence-transformers is not installed. Run: pip install sentence-transformers")
        return 1

    model = SentenceTransformer("BAAI/bge-m3")
    
    print("⏳ Generating embeddings (this might take a moment)...")
    embeddings = model.encode(texts, show_progress_bar=True)
    embeddings = np.array(embeddings, dtype=np.float32)

    print("🌀 Running UMAP projection to 2D...")
    try:
        import umap
    except ImportError:
        print("❌ Error: umap-learn is not installed. Run: pip install umap-learn")
        return 1
        
    n_neighbors = min(args.n_neighbors, len(texts) - 1)
    if n_neighbors < 2:
         n_neighbors = 2
         
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=args.min_dist,
        metric="cosine",
        random_state=42
    )
    coords2d = reducer.fit_transform(embeddings).astype(np.float32)

    print("🔗 Running HDBSCAN clustering...")
    try:
        from sklearn.cluster import HDBSCAN
    except ImportError:
        print("❌ Error: scikit-learn (HDBSCAN) is not installed. Run: pip install scikit-learn")
        return 1
        
    # Adjust min_samples and min_cluster_size based on dataset size
    min_cluster = max(3, min(10, len(texts) // 10))
    cluster_labels = HDBSCAN(min_cluster_size=min_cluster, min_samples=2).fit_predict(coords2d)

    points = []
    cluster_members = {}
    
    for i, c in enumerate(connections):
        pt = {
            "id": c.get("id", str(i)),
            "name": c.get("name", ""),
            "headline": c.get("headline", ""),
            "url": c.get("url", ""),
            "x": float(coords2d[i, 0]),
            "y": float(coords2d[i, 1]),
            "cluster": int(cluster_labels[i])
        }
        points.append(pt)
        cluster_members.setdefault(int(cluster_labels[i]), []).append(pt)

    cluster_summary = []
    for cid, members in sorted(cluster_members.items()):
        if cid == -1:
            continue
        xs = np.array([m["x"] for m in members])
        ys = np.array([m["y"] for m in members])
        
        # Simple label extraction: most common words in headline
        words = []
        import re
        for m in members:
            hw = re.sub(r'[^a-zA-Zа-яА-Я0-9\s]', '', m["headline"]).split()
            # Filter out common stop words if needed, here just length > 3
            words.extend([w.title() for w in hw if len(w) > 3])
        
        common = Counter(words).most_common(2)
        label = " · ".join([w[0] for w in common]) if common else f"Cluster {cid}"

        cluster_summary.append({
            "id": cid,
            "size": len(members),
            "label": label,
            "centroid_x": float(xs.mean()),
            "centroid_y": float(ys.mean()),
        })

    payload = {
        "stats": {
            "connections": len(points),
            "clusters": len(cluster_summary),
            "noise_points": sum(1 for p in points if p["cluster"] == -1),
        },
        "points": points,
        "clusters": cluster_summary
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
         json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved cluster map to {out_path}")
    print(f"📊 Stats: {len(points)} connections, {len(cluster_summary)} clusters, {payload['stats']['noise_points']} noise points")
    return 0

if __name__ == "__main__":
    sys.exit(main())
