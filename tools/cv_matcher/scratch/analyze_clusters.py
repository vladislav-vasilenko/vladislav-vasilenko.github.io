import json
data = json.load(open('../../public/cluster_map.json'))
top = data.get('top_matches', [])
print('Top Matches:', len(top))
for m in top[:20]:
    print(f"[{m.get('ats_score')}] {m.get('title')} @ {m.get('company')} (Dist: {m.get('distance'):.3f}) - Cluster: {m.get('cluster_id')}")

clusters = data.get('clusters', [])
# Find clusters that have top matches
top_ids = {m['id'] for m in top[:50]}
target_clusters = []
for c in clusters:
    c_vacs = c.get('vacancies', [])
    intersect = len([v for v in c_vacs if v['id'] in top_ids])
    if intersect > 0:
        target_clusters.append((c['name'], intersect, len(c_vacs), c.get('category')))

target_clusters.sort(key=lambda x: x[1], reverse=True)
print("\nTop Clusters for User:")
for c in target_clusters[:10]:
    print(f"{c[0]} (Category: {c[3]}) - {c[1]} top matches out of {c[2]} total")
