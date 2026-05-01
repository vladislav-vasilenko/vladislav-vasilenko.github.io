import json

with open("public/cluster_map.json") as f:
    data = json.load(f)

for i, m in enumerate(data.get("top_matches", [])[:20]):
    v = next((x for x in data["vacancies"] if x["id"] == m["id"]), {})
    print(f"{i+1}. {m['title']} ({v.get('company', '')}) - sim: {m.get('similarity', 0):.3f} | team: {v.get('team')} | track: {v.get('track')} | category: {v.get('category')} | id: {v.get('id')}")
