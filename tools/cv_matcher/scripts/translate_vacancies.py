import json
import os
import sys
import time
import re
from pathlib import Path
import requests

# Use gemma4 for translation as requested
MODEL = "gemma4:latest"
OLLAMA_URL = "http://localhost:11434/api/generate"

def is_russian(text):
    if not text: return False
    # Check if contains any cyrillic characters
    return bool(re.search('[а-яА-Я]', text))

def translate_text(text, target_lang="English"):
    if not text or len(text.strip()) < 2:
        return text
    
    if not is_russian(text):
        return text
        
    prompt = f"Translate to English. Only output the translation:\n\n{text}"
    
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 1024}
            },
            timeout=120
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            print(f"Error from Ollama: {response.status_code}")
            return text
    except Exception as e:
        print(f"Translation failed: {e}")
        return text

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    input_file = root / "public" / "online_scraped.json"
    output_file = root / "public" / "online_scraped_en.json"
    
    if not input_file.exists():
        print(f"Input file {input_file} not found")
        return
    
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    vacancies = data.get("vacancies", [])
    total = len(vacancies)
    
    # Load existing progress if any
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                output_data = json.load(f)
                translated_vacs = {v["id"]: v for v in output_data.get("vacancies", [])}
        except:
            translated_vacs = {}
    else:
        translated_vacs = {}

    print(f"Starting translation of {total} vacancies...")
    
    new_vacs = []
    count = 0
    
    for i, v in enumerate(vacancies):
        vid = v["id"]
        
        # If already in the list from current run, skip (though this loop is fresh)
        
        # If already translated in previous run, reuse
        if vid in translated_vacs:
            new_vacs.append(translated_vacs[vid])
            continue
            
        company = v.get("company", "")
        # Only translate Russian companies (Яндекс, Сбер) or if clearly Russian
        needs_translation = company in ["Яндекс", "Сбер", "Yandex", "Sber"] or is_russian(v["title"])
        
        if needs_translation:
            print(f"[{i+1}/{total}] Translating {company}: {v['title']}...")
            
            # Translate Title (Essential)
            en_title = translate_text(v["title"])
            
            # Translate first 500 chars of Description (Enough for semantics)
            desc = v["description"]
            # Remove common boilerplate if possible (simple heuristic)
            desc = desc.split("Условия")[0].split("Политика")[0]
            if len(desc) > 500:
                desc = desc[:500]
            
            en_description = translate_text(desc)
            
            v_en = v.copy()
            v_en["title_ru"] = v["title"]
            v_en["description_ru"] = v["description"]
            v_en["title"] = en_title
            v_en["description"] = en_description
            new_vacs.append(v_en)
            count += 1
            
            # Save every 5 translations
            if count % 5 == 0:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump({"vacancies": new_vacs + vacancies[i+1:]}, f, ensure_ascii=False, indent=2)
        else:
            new_vacs.append(v)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"vacancies": new_vacs}, f, ensure_ascii=False, indent=2)
        
    print(f"Done! Saved {len(new_vacs)} vacancies to {output_file}")

if __name__ == "__main__":
    main()
