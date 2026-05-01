import json
import os
import sys
import time
import requests
import re
from pathlib import Path
from dotenv import load_dotenv

# Configuration
# The user mentioned 'gpt-5-mini', we'll use 'gpt-4o-mini' as it's the current real equivalent
# unless they have a specific custom model name.
MODEL = "gpt-5.4-mini" 
BATCH_SIZE = 25 

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    tools_root = Path(__file__).resolve().parent.parent
    load_dotenv(tools_root / ".env")
    
    api_url = os.environ.get("CV_API_URL")
    api_secret = os.environ.get("API_SECRET")
    
    if not api_url or not api_secret:
        print("❌ CV_API_URL or API_SECRET not found in tools/cv_matcher/.env")
        return

    # Derive translation endpoint from ATS endpoint
    translate_url = api_url.replace("/api/ats", "/api/translate")
    
    input_file = root / "public" / "online_scraped.json"
    output_file = root / "public" / "online_scraped_en.json"
    
    if not input_file.exists():
        print(f"❌ Input file {input_file} not found")
        return
    
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    vacancies = data.get("vacancies", [])
    
    # Identify Russian vacancies that need translation
    to_translate = []
    already_en = []
    
    for v in vacancies:
        company = v.get("company", "")
        is_ru = company in ["Яндекс", "Сбер", "Yandex", "Sber"] or bool(re.search('[а-яА-Я]', v["title"]))
        if is_ru:
            to_translate.append(v)
        else:
            already_en.append(v)
            
    print(f"📦 Total vacancies: {len(vacancies)}")
    print(f"🇷🇺 To translate: {len(to_translate)}")
    print(f"🇺🇸 Already English: {len(already_en)}")

    translated_results = []
    
    # Batch processing
    for i in range(0, len(to_translate), BATCH_SIZE):
        batch = to_translate[i : i + BATCH_SIZE]
        print(f"🚀 Processing batch {i//BATCH_SIZE + 1}/{(len(to_translate)-1)//BATCH_SIZE + 1} ({len(batch)} items)...")
        
        items_to_translate = []
        for v in batch:
            items_to_translate.append({
                "id": v["id"],
                "title": v["title"],
                "description": v["description"][:1200]
            })
            
        system_prompt = (
            "You are a professional translator. Translate job vacancies from Russian to English. "
            "Preserve technical terms and professional tone. "
            "Output ONLY a JSON object with a 'results' key containing the translated items. "
            "Keep the original IDs."
        )
        
        user_prompt = f"Translate the following vacancies to English:\n\n{json.dumps(items_to_translate, ensure_ascii=False)}"
        
        try:
            response = requests.post(
                translate_url,
                headers={"Authorization": f"Bearer {api_secret}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "response_format": {"type": "json_object"}
                },
                timeout=120
            )
            
            if response.status_code != 200:
                print(f"❌ Proxy Error {response.status_code}: {response.text}")
                translated_results.extend(batch)
                continue
                
            data_resp = response.json()
            batch_result = json.loads(data_resp["choices"][0]["message"]["content"])
            results = batch_result.get("results", [])
            
            id_to_translated = {r["id"]: r for r in results}
            
            for v in batch:
                tr = id_to_translated.get(v["id"])
                if tr:
                    v_en = v.copy()
                    v_en["title_ru"] = v["title"]
                    v_en["description_ru"] = v["description"]
                    v_en["title"] = tr["title"]
                    v_en["description"] = tr["description"]
                    translated_results.append(v_en)
                else:
                    print(f"⚠️ Warning: Could not find translation for {v['id']}")
                    translated_results.append(v)
                    
        except Exception as e:
            print(f"❌ Error in batch: {e}")
            translated_results.extend(batch)
            
        # Intermediate save
        final_list = already_en + translated_results
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({"vacancies": final_list}, f, ensure_ascii=False, indent=2)

    print(f"✅ Done! Saved {len(already_en) + len(translated_results)} vacancies to {output_file}")

if __name__ == "__main__":
    main()
