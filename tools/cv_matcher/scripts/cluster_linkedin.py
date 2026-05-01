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

    # Add the user's own profile to the dataset so they appear on the map
    connections.append({
        "id": "you",
        "name": "Vladislav Vasilenko",
        "headline": "AI/ML Engineer | Multi-Agent Systems, RAG, Post-Training SFT/LoRA/QLoRA/DPO, Realtime-LLM via WebRTC | ex-Lead iOS",
        "about": "As a Lead Software Development Expert at Severstal, I specialize in architecting multi-agent systems and developing innovative voice multi-agent solutions using cutting-edge technologies like OpenAI Agents SDK, GPT-Realtime, and advanced GPT models. My role involves engineering web interfaces with Next.js and WebRTC for low-latency voice transmission, building backend supervisors with hierarchical orchestration, and creating knowledge base search agents supported by automated embeddings pipelines. I also contribute to seamless multi-user integrations with Google Auth for Gmail and Google Calendar APIs. With over three years of expertise in large language models (LLMs) and Python, I excel in delivering advanced solutions for real-time AI systems. My focus lies in leveraging technologies such as WebRTC and Realtime-GPT to innovate voice and knowledge-based applications. I am committed to driving technological growth through robust systems engineering and collaboration.",
        "url": "https://www.linkedin.com/in/vladislav-vasilenko/",
        "is_user": True
    })

    texts = []
    for c in connections:
        # We embed the name, headline, and about (if present) to group similar roles/companies
        text = f"{c.get('name', '')} - {c.get('headline', '')}"
        if c.get('about'):
            text += f" - {c['about']}"
        texts.append(text)

    print(f"📦 Loaded {len(texts)} connections from {args.input}")

    print("🧠 Requesting embeddings via local Ollama (bge-m3)...")
    import requests
    embeddings = []
    
    print(f"⏳ Generating {len(texts)} embeddings...")
    # Attempt to use the batch API /api/embed
    try:
        res = requests.post("http://localhost:11434/api/embed", json={"model": "bge-m3", "input": texts})
        if res.status_code == 200 and "embeddings" in res.json():
            embeddings = res.json()["embeddings"]
            print("✅ Batch embedding successful!")
        else:
            raise ValueError(f"Batch API failed: {res.status_code} {res.text}")
    except Exception as e:
        print(f"Batch embedding failed, falling back to sequential... ({e})")
        for i, text in enumerate(texts):
            try:
                res = requests.post("http://localhost:11434/api/embeddings", json={"model": "bge-m3", "prompt": text})
                if res.status_code == 200:
                    embeddings.append(res.json()["embedding"])
                else:
                    embeddings.append([0.0] * 1024) # fallback dummy
            except Exception:
                embeddings.append([0.0] * 1024)
                
            if (i+1) % 50 == 0:
                print(f"Processed {i+1}/{len(texts)}...")
                
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
