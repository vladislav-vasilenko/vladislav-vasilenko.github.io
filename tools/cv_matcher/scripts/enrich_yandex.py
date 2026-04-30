import json
import time
import requests
import re
from pathlib import Path

OUTPUT = Path("public/online_scraped.json")

def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'<[^>]+>', ' ', text).strip()

def enrich_yandex():
    if not OUTPUT.exists():
        print("No online_scraped.json found.")
        return

    with open(OUTPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    vacancies = data.get("vacancies", [])
    yandex_vacs = [v for v in vacancies if v.get("id", "").startswith("yandex_")]

    print(f"Found {len(yandex_vacs)} Yandex vacancies. Starting enrichment...")

    updated_count = 0
    for i, v in enumerate(yandex_vacs):
        link = v.get("link", "")
        if not link:
            continue
        
        # Link format: https://yandex.ru/jobs/vacancies/{slug}
        slug = link.split("/")[-1]
        if not slug:
            continue
            
        url = f"https://yandex.ru/jobs/api/publications/{slug}"
        try:
            time.sleep(0.3)
            resp = requests.get(url, timeout=10)
            if resp.ok:
                d = resp.json()
                d_desc = _strip_html(d.get("description") or "")
                d_kq = _strip_html(d.get("key_qualifications") or "")
                
                parts = [v.get("description", "")]
                if d_desc and d_desc not in v["description"]:
                    parts.append("Описание:\n" + d_desc)
                if d_kq and d_kq not in v["description"]:
                    parts.append("Требования:\n" + d_kq)
                
                if len(parts) > 1:
                    v["description"] = "\n\n".join(parts)[:5000]
                    updated_count += 1
                    
            if (i + 1) % 50 == 0:
                print(f"Processed {i + 1}/{len(yandex_vacs)}...")
                
        except Exception as e:
            print(f"Error enriching {slug}: {e}")

    print(f"Finished enrichment. Updated {updated_count} vacancies.")
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    enrich_yandex()
