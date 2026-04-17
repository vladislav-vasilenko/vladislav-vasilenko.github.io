import os
import sys
import json
import argparse
import hashlib
import markdown
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import List
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()
from langchain_core.prompts import PromptTemplate

# Импорт модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.scraper import SberScraper
from src.rag_db import RAGDatabase

class ATSResult(BaseModel):
    is_good_match: bool = Field(description="Подходит ли кандидат на вакансию более чем на 70%?")
    ats_score_percentage: int = Field(description="Процентное совпадение CV и JD")
    missing_keywords: List[str] = Field(description="Критичные отсутствующие ключевые слова")
    reasoning: str = Field(description="Почему дана такая оценка (1-2 предложения)")
    adapted_bullets: List[str] = Field(
        description="2-3 улучшенных буллита для резюме кандидата. Ваша задача - переформулировать реальный опыт кандидата, переложив его на терминологию вакансии (например, добавив проставленные метрики или правильные ключевые слова, которых изначально не было, но которые подразумеваются его задачами)."
    )

def main():
    parser = argparse.ArgumentParser(description="AI RAG CV Matcher")
    parser.add_argument("--skip-scraping", action="store_true", help="Пропустить парсинг сайта Сбера и использовать кэшированные данные из БД")
    parser.add_argument("--use-openai", action="store_true", help="Использовать OpenAI API вместо локального Ollama")
    parser.add_argument("--openai-model", type=str, default="gpt-5.4-mini", help="Модель OpenAI (по умолчанию gpt-5.4-mini)")
    args = parser.parse_args()

    print("🔥 Запуск RAG-пайплайна матчинга вакансий...")
    
    try:
        if args.use_openai:
            if not os.environ.get("OPENAI_API_KEY"):
                print("❌ ОШИБКА: OPENAI_API_KEY не установлен в .env")
                sys.exit(1)
            print(f"🧠 Инициализация OpenAI API ({args.openai_model})...")
            llm = ChatOpenAI(model=args.openai_model, temperature=0.1)
        else:
            print("🧠 Инициализация локального Ollama (gemma4:31b)...")
            llm = ChatOllama(model="gemma4:31b", temperature=0)
    except Exception as e:
        print(f"❌ Ошибка инициализации LLM: {e}")
        sys.exit(1)
        
    db = RAGDatabase(db_path="./chroma_db")
    scraper = SberScraper()
    
    # Список самых актуальных R&D запросов для парсинга
    queries = [
        "ML",
        "LLM",
        "Audio ML",
        "Multi-Modal",
        "GenAI",
        "Diffusion",
        "RLHF",
        "Kandinsky",
        "Machine Learning Engineer"
    ]
    all_jobs = []
    
    if not args.skip_scraping:
        print("\n--- ЭТАП 1: СКРЕЙПИНГ ВАКАНСИЙ ---")
        for q in queries:
            jobs = scraper.fetch_jobs(q)
            all_jobs.extend(jobs)
            
        unique_jobs = {job["id"]: job for job in all_jobs}.values()
        
        print("\n--- ЭТАП 2: ВЕКТОРИЗАЦИЯ И РАЗМЕЩЕНИЕ В БД ---")
        db.add_vacancies(list(unique_jobs))
    else:
        print("\n--- ЭТАП 1 & 2 ПРОПУЩЕНЫ: Используем существующие вакансии из ChromaDB ---")
    
    # Извлекаем ВСЕ файлы опыта работы (кроме коротких версий)
    cv_dir = "../../content/ru/experience"
    if not os.path.exists(cv_dir):
        print(f"❌ Директория CV не найдена: {cv_dir}")
        sys.exit(1)
        
    cv_text = ""
    for f in sorted(os.listdir(cv_dir)):
        if f.endswith(".md") and not f.endswith("-short.md"):
            with open(os.path.join(cv_dir, f), "r", encoding="utf-8") as file:
                cv_text += f"--- ФАЙЛ: {f} ---\n{file.read()}\n\n"

    print("\n--- ЭТАП 3: КОСИНУСНЫЙ ПОИСК ВАКАНСИЙ (RAG) ---")
    top_jobs = db.search_similar_vacancies(query_text=cv_text, top_k=40)
    
    if not top_jobs:
        print("⚠️ Нет вакансий в базе для поиска.")
        sys.exit(1)
        
    print("\n--- ЭТАП 4: AI-ATS ПРОВЕРКА (РАНЖИРОВАНИЕ) ---")
    
    # Загружаем кэш
    cache_path = "./ai_cache.json"
    ai_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ai_cache = json.load(f)
        except:
            pass

    structured_llm = llm.with_structured_output(ATSResult)
    prompt = PromptTemplate.from_template("""You are a FAANG-level ATS Recruiter AI. 
Evaluate the candidate's Resume against the provided Job Description.

Job Description:
{vacancy}

Candidate Resume:
{cv}

1. Determine the match percentage.
2. Identify critical missing keywords.
3. Provide brief reasoning.
4. Provide 'adapted_bullets': rewrite 2-3 specific bullet points from the candidate's actual experience to perfectly align with the vacancy's specific terminology and missing keywords. Do NOT invent new experience, just re-frame their existing technical achievements using the language of the Job Description (e.g., if they built audio streaming, frame it as TTFAT/barge-in optimization if the job asks for it). Output these clearly in Russian.""")
    chain = prompt | structured_llm

    ranked_results = []
    
    cv_exports_dir = "../../public/adapted_cvs"
    os.makedirs(cv_exports_dir, exist_ok=True)
    
    for job in top_jobs:
        # Уникальный хеш для пары "Вакансия + Резюме"
        combo_text = job["document"] + cv_text
        job_hash = hashlib.md5(combo_text.encode('utf-8')).hexdigest()
        
        try:
            # 1. Проверяем кэш
            if job_hash in ai_cache:
                print(f"⚡ КЭШ: {job['metadata']['title']} (извлечено за 0мс)")
                ats_val_dict = ai_cache[job_hash]
            else:
                # 2. Идем в LLM если нет в кэше
                print(f"🤖 Оценка LLM: {job['metadata']['title']} (Cosine Dist: {job['distance']:.4f})...")
                ats_val: ATSResult = chain.invoke({
                    "vacancy": job["document"], 
                    "cv": cv_text
                })
                ats_val_dict = {
                    "ats_score_percentage": ats_val.ats_score_percentage,
                    "reasoning": ats_val.reasoning,
                    "missing_keywords": ats_val.missing_keywords,
                    "is_good_match": ats_val.is_good_match,
                    "adapted_bullets": ats_val.adapted_bullets
                }
                # Сохраняем результат в кэш словарь
                ai_cache[job_hash] = ats_val_dict
                # Инкрементальное сохранение кэша на случай отмены (Ctrl+C)
                with open(cache_path, "w", encoding="utf-8") as _f:
                    json.dump(ai_cache, _f, ensure_ascii=False, indent=2)
            
            # --- ГЕНЕРАЦИЯ HTML РЕЗЮМЕ ДЛЯ ЭТОЙ ВАКАНСИИ ---
            adapted_cv_bullets = ats_val_dict.get("adapted_bullets", [])
            job_id = job["id"]
            cv_html_path = os.path.join(cv_exports_dir, f"{job_id}.html")
            
            md_template = f"# Владислав Василенко\n\n"
            md_template += f"> **Senior AI / ML Engineer** | Опыт коммерческой разработки: 10 лет\n>\n"
            md_template += f"> *CV фокусно адаптировано под вакансию: [{job['metadata']['title']}]({job['metadata']['link']}) ({job['metadata']['company']})*\n\n"
            
            if adapted_cv_bullets:
                md_template += "## 🎯 Релевантный опыт (Ключевые компетенции для вашей команды)\n\n"
                for ab in adapted_cv_bullets:
                    md_template += f"- {ab}\n"
                md_template += "\n---\n\n"
                
            md_template += "## 💼 Детальный профессиональный опыт\n\n"
            md_template += cv_text
            
            html_body = markdown.markdown(md_template)
            
            full_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>CV_Vladislav_Vasilenko_{job_id}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 850px; margin: 40px auto; padding: 0 20px; }}
        h1, h2, h3 {{ color: #2c3e50; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; margin-top: 24px; }}
        a {{ color: #0366d6; text-decoration: none; }}
        blockquote {{ color: #6a737d; border-left: 0.25em solid #dfe2e5; background: #f6f8fa; padding: 10px 15px; border-radius: 4px; }}
        hr {{ height: 1px; background-color: #e1e4e8; border: 0; margin: 24px 0; }}
        @media print {{
            body {{ max-width: 100%; margin: 0; padding: 20px; }}
            a {{ text-decoration: none !important; color: #000 !important; }}
        }}
    </style>
</head>
<body>
{html_body}
</body>
</html>'''

            with open(cv_html_path, "w", encoding="utf-8") as f:
                f.write(full_html)
                
            # Добавляем в JSON выдачу
            ranked_results.append({
                "id": job["id"],
                "title": job["metadata"]["title"],
                "company": job["metadata"]["company"],
                "link": job["metadata"]["link"],
                "pub_date": job["metadata"].get("pub_date", "Неизвестно"),
                "ats_score": ats_val_dict["ats_score_percentage"],
                "cosine_distance": float(job["distance"]),
                "reasoning": ats_val_dict["reasoning"],
                "missing_keywords": ats_val_dict["missing_keywords"],
                "is_good_match": ats_val_dict["is_good_match"],
                "adapted_bullets": ats_val_dict.get("adapted_bullets", [])
            })
        except Exception as e:
            err_str = str(e)
            if "404" in err_str and not args.use_openai:
                print(f"❌ ОШИБКА ДЕМОНА OLLAMA: Модель 'gemma4-31b' не найдена.")
                sys.exit(1)
            else:
                print(f"Ошибка LLM для вакансии {job['metadata']['title']}: {e}")
            
    ranked_results.sort(key=lambda x: x["ats_score"], reverse=True)
    
    # 5.1 Генерация 3D Scatter (PCA)
    print("\n--- ГЕНЕРАЦИЯ 3D ПРОСТРАНСТВА (PCA) ---")
    scatter_3d_data = db.export_3d_embeddings(cv_text)
    
    print("\n--- ЭТАП 5: ЭКСПОРТ В JSON ДЛЯ ФРОНТЕНДА ---")
    output_dir = "../../public"
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "matcher_data.json")
    
    export_payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_jobs_in_db": db.collection.count(),
        "vacancies": ranked_results,
        "scatter_3d": scatter_3d_data
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Данные сохранены в {json_path}")

if __name__ == "__main__":
    main()
