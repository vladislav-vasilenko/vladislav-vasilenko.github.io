import os
import sys
import json
import argparse
import hashlib
import markdown
import requests
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
    parser.add_argument("--use-cloud-api", action="store_true", help="Использовать Vercel API Gateway (скрывает OpenAI ключ)")
    parser.add_argument("--openai-model", type=str, default="gpt-5.4-mini", help="Модель OpenAI (по умолчанию gpt-5.4-mini)")
    args = parser.parse_args()

    print("🔥 Запуск RAG-пайплайна матчинга вакансий...")
    
    # Инициализация LLM
    llm = None
    chain = None
    if args.use_cloud_api:
        print("☁️ Выбран облачный Vercel API Gateway. Ланчейн не инициализируем.")
    else:
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
    
    # 3. ПОДГОТОВКА ДАННЫХ РЕЗЮМЕ ДЛЯ ПОИСКА И ОТОБРАЖЕНИЯ
    cv_dir = "../../content/ru/experience"
    cv_json_path = "../../content/ru/cv.json"
    
    if not os.path.exists(cv_json_path):
        print(f"❌ CV JSON не найден: {cv_json_path}")
        sys.exit(1)
        
    with open(cv_json_path, "r", encoding="utf-8") as f:
        cv_data = json.load(f)

    # Собираем полный текст для RAG-поиска (все файлы)
    cv_search_text = ""
    structured_experience = [] # Для красивого рендеринга в HTML
    
    # Сначала добавим информацию "Обо мне" из файла (если есть)
    about_path = "../../content/ru/about.md"
    about_text = ""
    if os.path.exists(about_path):
        with open(about_path, "r", encoding="utf-8") as f:
            about_text = f.read()
            cv_search_text += f"{about_text}\n\n"

    # Теперь проходим по опыту работы из JSON
    for exp in cv_data.get("experience", []):
        exp_id = exp["id"]
        period = exp.get("period", "")
        
        # Фильтр на 8 лет (от 2018 года)
        # Ищем любые 4 цифры года в строке периода
        years = [int(s) for s in period.split() if s.isdigit() and len(s) == 4]
        # Если в периоде есть годы, и все они меньше 2018 - пропускаем (кроме случаев 'настоящее время')
        if years and max(years) < 2018 and "настоящее" not in period.lower():
            continue

        md_path = os.path.join(cv_dir, f"{exp_id}.md")
        
        description_md = ""
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                description_md = f.read()
        
        # Добавляем в текст для поиска
        cv_search_text += f"Company: {exp['company']}\nRole: {exp['role']}\n{description_md}\n\n"
        
        # Сохраняем структуру для HTML
        structured_experience.append({
            "company": exp["company"],
            "role": exp["role"],
            "period": exp["period"],
            "desc_html": markdown.markdown(description_md)
        })

    print("\n--- ЭТАП 3: КОСИНУСНЫЙ ПОИСК ВАКАНСИЙ (RAG) ---")
    top_jobs = db.search_similar_vacancies(query_text=cv_search_text, top_k=40)
    
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

    if llm:
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
        combo_text = job["document"] + cv_search_text
        job_hash = hashlib.md5(combo_text.encode('utf-8')).hexdigest()
        
        try:
            # 1. Проверяем кэш
            if job_hash in ai_cache:
                print(f"⚡ КЭШ: {job['metadata']['title']} (извлечено за 0мс)")
                ats_val_dict = ai_cache[job_hash]
            else:
                # 2. Идем в LLM или Cloud API
                print(f"🤖 Оценка: {job['metadata']['title']} (Cosine Dist: {job['distance']:.4f})...")
                
                if args.use_cloud_api:
                    api_secret = os.environ.get("API_SECRET", "")
                    headers = {"Content-Type": "application/json"}
                    if api_secret:
                        headers["Authorization"] = f"Bearer {api_secret}"
                    
                    req_payload = {
                        "vacancyText": job["document"],
                        "cvText": cv_search_text
                    }
                    
                    api_url = os.environ.get("CV_API_URL")
                    if not api_url:
                        print("❌ ОШИБКА: Добавьте CV_API_URL в файл .env. Например: CV_API_URL=https://ваше-приложение.vercel.app/api/ats")
                        sys.exit(1)
                        
                    res = requests.post(api_url, json=req_payload, headers=headers)
                    res.raise_for_status()
                    data = res.json()
                    
                    ats_val_dict = {
                        "ats_score_percentage": data.get("ats_score_percentage", 0),
                        "reasoning": data.get("reasoning", ""),
                        "missing_keywords": data.get("missing_keywords", []),
                        "is_good_match": data.get("is_good_match", False),
                        "adapted_bullets": data.get("adapted_bullets", [])
                    }
                else:
                    ats_val: ATSResult = chain.invoke({
                        "vacancy": job["document"], 
                        "cv": cv_search_text
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
            
            # Рендерим блок "Обо мне"
            about_html = markdown.markdown(about_text)
            
            # Строим блок опыта
            exp_html_parts = []
            for exp in structured_experience:
                part = f'''
                <div class="experience-item">
                    <div class="exp-header">
                        <span class="company">{exp['company']}</span>
                        <span class="period">{exp['period']}</span>
                    </div>
                    <div class="role">{exp['role']}</div>
                    <div class="description">{exp['desc_html']}</div>
                </div>'''
                exp_html_parts.append(part)
            
            all_experience_html = "\\n".join(exp_html_parts)
            
            # Рендерим адаптированные буллиты
            bullets_li = "".join([f"<li>{b}</li>" for b in adapted_cv_bullets])
            adapted_section = f'''
            <div class="adapted-section">
                <h2>🎯 Релевантный опыт (Focus for {job['metadata']['company']})</h2>
                <ul>{bullets_li}</ul>
            </div>''' if adapted_cv_bullets else ""

            full_html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>CV_Vladislav_Vasilenko_{job_id}</title>
    <style>
        :root {{ --primary: #2c3e50; --accent: #3498db; --text: #333; --light-bg: #f8f9fa; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
            line-height: 1.5; color: var(--text); max-width: 900px; margin: 0 auto; padding: 40px; 
            background: #fff;
        }}
        .header {{ border-bottom: 2px solid var(--primary); padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }}
        .header h1 {{ margin: 0; color: var(--primary); font-size: 2.2em; letter-spacing: -0.5px; }}
        .header .contacts {{ text-align: right; font-size: 0.9em; color: #666; }}
        
        .summary {{ background: var(--light-bg); padding: 20px; border-radius: 8px; border-left: 4px solid var(--accent); margin-bottom: 30px; }}
        .adapted-section {{ background: #ebf5fb; padding: 20px; border-radius: 8px; border: 1px solid #aed6f1; margin-bottom: 30px; }}
        .adapted-section h2 {{ margin-top: 0; color: #21618c; font-size: 1.2em; text-transform: uppercase; letter-spacing: 1px; }}
        .adapted-section ul {{ margin: 0; padding-left: 20px; }}
        .adapted-section li {{ margin-bottom: 8px; font-weight: 500; color: #1b4f72; }}

        h2 {{ color: var(--primary); border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 40px; text-transform: uppercase; font-size: 1.1em; letter-spacing: 1.5px; }}
        
        .experience-item {{ margin-bottom: 25px; page-break-inside: avoid; }}
        .exp-header {{ display: flex; justify-content: space-between; font-weight: bold; font-size: 1.1em; color: var(--primary); }}
        .company {{ color: var(--accent); }}
        .role {{ font-style: italic; color: #555; margin-bottom: 8px; }}
        .description ul {{ padding-left: 20px; margin-top: 5px; }}
        .description li {{ margin-bottom: 4px; }}
        
        .vacancy-meta {{ font-size: 0.85em; color: #999; margin-top: 50px; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }}
        
        @media print {{
            body {{ padding: 0; margin: 0; }}
            .adapted-section {{ border: 2px solid #aed6f1; background: #fff !important; }}
            h2 {{ border-bottom: 2px solid #eee; }}
            a {{ text-decoration: none; color: inherit; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Василенко Владислав</h1>
            <div style="color: var(--accent); font-weight: 500;">Senior AI / ML Engineer</div>
        </div>
        <div class="contacts">
            <div>{cv_data['contact']['email']}</div>
            <div>Telegram: <a href="https://vsvladis.t.me/">@vsvladis</a></div>
            <div><a href="https://vladislav-vasilenko.github.io">vladislav-vasilenko.github.io</a></div>
        </div>
    </div>

    <div class="summary">
        {about_html}
    </div>

    {adapted_section}

    <h2>💼 Профессиональный опыт</h2>
    {all_experience_html}

    <div class="vacancy-meta">
        CV фокусно адаптировано для вакансии {job['metadata']['title']} в {job['metadata']['company']}<br>
        Оригинал: <a href="{job['metadata']['link']}">{job['metadata']['link']}</a>
    </div>
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
            if "404" in err_str and not args.use_openai and not args.use_cloud_api:
                print(f"❌ ОШИБКА ДЕМОНА OLLAMA: Локальная модель Ollama не найдена.")
                sys.exit(1)
            else:
                print(f"❌ СЕТЕВАЯ ОШИБКА (Vercel API) для вакансии {job['metadata']['title']}: {e}")
                
                if args.use_cloud_api and "404" in err_str:
                     print("   -> Подсказка: Vercel возвращает 404. Возможно вы ошиблись в домене CV_API_URL в .env, или деплой на Vercel еще не завершился! Подождите 1 минуту.")
                sys.exit(1)
            
    ranked_results.sort(key=lambda x: x["ats_score"], reverse=True)
    
    # 5.1 Генерация 3D Scatter (PCA)
    print("\n--- ГЕНЕРАЦИЯ 3D ПРОСТРАНСТВА (PCA) ---")
    scatter_3d_data = db.export_3d_embeddings(cv_search_text)
    
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
