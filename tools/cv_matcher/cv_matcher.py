import os
import sys
import json
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import List
from langchain_ollama import ChatOllama
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

def main():
    print("🔥 Запуск RAG-пайплайна матчинга вакансий...")
    
    try:
        llm = ChatOllama(model="gemma4:31b", temperature=0)
    except Exception as e:
        print(f"❌ Ошибка инициализации LLM (Ollama работает?): {e}")
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
    
    print("\n--- ЭТАП 1: СКРЕЙПИНГ ВАКАНСИЙ ---")
    for q in queries:
        jobs = scraper.fetch_jobs(q)
        all_jobs.extend(jobs)
        
    unique_jobs = {job["id"]: job for job in all_jobs}.values()
    
    print("\n--- ЭТАП 2: ВЕКТОРИЗАЦИЯ И РАЗМЕЩЕНИЕ В БД ---")
    db.add_vacancies(list(unique_jobs))
    
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
    top_jobs = db.search_similar_vacancies(query_text=cv_text, top_k=10)
    
    if not top_jobs:
        print("⚠️ Нет вакансий в базе для поиска.")
        sys.exit(1)
        
    print("\n--- ЭТАП 4: AI-ATS ПРОВЕРКА (РАНЖИРОВАНИЕ) ---")
    structured_llm = llm.with_structured_output(ATSResult)
    prompt = PromptTemplate.from_template("""You are a FAANG-level ATS Recruiter AI. 
Evaluate the candidate's Resume against the provided Job Description.

Job Description:
{vacancy}

Candidate Resume:
{cv}

Determine the match percentage, identify critical missing keywords, and provide brief reasoning.""")
    chain = prompt | structured_llm

    ranked_results = []
    
    for job in top_jobs:
        print(f"🤖 Оценка: {job['metadata']['title']} (Cosine Dist: {job['distance']:.4f})...")
        try:
            ats_val: ATSResult = chain.invoke({
                "vacancy": job["document"], 
                "cv": cv_text
            })
            ranked_results.append({
                "id": job["id"],
                "title": job["metadata"]["title"],
                "company": job["metadata"]["company"],
                "link": job["metadata"]["link"],
                "pub_date": job["metadata"].get("pub_date", "Неизвестно"),
                "ats_score": ats_val.ats_score_percentage,
                "cosine_distance": float(job["distance"]),
                "reasoning": ats_val.reasoning,
                "missing_keywords": ats_val.missing_keywords,
                "is_good_match": ats_val.is_good_match
            })
        except Exception as e:
            err_str = str(e)
            if "404" in err_str:
                print(f"❌ ОШИБКА ДЕМОНА OLLAMA: Модель 'gemma4-31b' не найдена.")
                print(f"   Пожалуйста, введите в соседнем терминале: ollama pull gemma4-31b")
                print(f"   (Либо поменяйте 'gemma4-31b' в cv_matcher.py на ту модель, что у вас скачана, например Llama3)")
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
        "vacancies": ranked_results,
        "scatter_3d": scatter_3d_data
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Данные сохранены в {json_path}")

if __name__ == "__main__":
    main()
