import json
from collections import Counter

with open('../../public/matcher_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

vacancies = data.get('vacancies', [])
valid_vacancies = [v for v in vacancies if v.get('ats_score') is not None]
valid_vacancies.sort(key=lambda x: x.get('ats_score', 0), reverse=True)

print(f"Total valid vacancies: {len(valid_vacancies)}")

print("\n--- TOP 10 VACANCIES ---")
for v in valid_vacancies[:10]:
    print(f"[{v.get('ats_score')}] {v.get('title')} at {v.get('company')} (Sphere: {v.get('sphere')}, BigTech: {v.get('is_big_tech')})")

print("\n--- SPHERES BY AVG SCORE (Count >= 2) ---")
spheres = {}
for v in valid_vacancies:
    s = v.get('sphere', 'Unknown')
    spheres.setdefault(s, []).append(v['ats_score'])

for s, scores in sorted(spheres.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
    if len(scores) >= 2:
        print(f"{s}: Avg {sum(scores)/len(scores):.1f} (Count: {len(scores)})")

print("\n--- MISSING KEYWORDS (Top 10) ---")
missing = []
for v in valid_vacancies:
    missing.extend(v.get('missing_keywords', []))
for k, c in Counter(missing).most_common(10):
    print(f"{k}: {c}")

print("\n--- MATCHED KEYWORDS (Top 10) ---")
matched = []
for v in valid_vacancies:
    matched.extend(v.get('matched_keywords', []))
for k, c in Counter(matched).most_common(10):
    print(f"{k}: {c}")

