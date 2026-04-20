import os
import re
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
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None
from dotenv import load_dotenv

load_dotenv()
from langchain_core.prompts import PromptTemplate

# Версия логики оценки (инкрементировать при изменении промпта или структуры данных)
# v10: rubric-based scoring (4 axes), is_good_match детерминирован в Python, adapted_bullets guardrails.
# v11: + improvement_tips (что поправить в CV под первый этап ATS-отсева) и application_message
#      (готовый текст отклика для модальной формы работодателя). Рассуждения рассчитаны на топ-модели
#      (Claude Opus 4.7 / GPT-5.4).
PROMPT_VERSION = "v11"

# Список Tier-1 IT компаний (Big Tech)
BIG_TECH_COMPANIES = [
    "Яндекс", "Yandex", "Сбер", "Sber", "Т-Банк", "T-Bank", "Тинькофф", "Tinkoff",
    "VK", "Mail.ru", "Авито", "Avito", "Ozon", "Озон", "Альфа-Банк", "Alfa-Bank",
    "ВТБ", "VTB", "Касперский", "Kaspersky", "Positive Technologies", "Wildberries",
    "МТС", "MTS", "МегаФон", "MegaFon", "Билайн", "Beeline", "Ростелеком", "Rostelecom", 
    "X5", "X5 Tech", "Циан", "Cian", "Selectel", "HeadHunter", "HH", "Газпромбанк", "GPB",
    "2ГИС", "2GIS", "Lamoda", "Ламода", "Совкомбанк", "Raiffeisen", "Райффайзен"
]

# Глобальные тех-гиганты (International Big Tech)
GLOBAL_TECH_GIANTS = [
    "Google", "Alphabet", "Meta", "Facebook", "Amazon", "Microsoft", "Apple", "Netflix",
    "OpenAI", "Anthropic", "Mistral", "Cohere", "NVIDIA", "Tesla", "Twitter", "X.com",
    "Cisco", "IBM", "Intel", "AMD", "Oracle", "Uber", "Airbnb", "Spotify", "Spotify",
    "DeepMind", "DeepL", "HuggingFace", "Palantir", "Databricks", "Snowflake"
]

def is_big_tech(company_name: str) -> bool:
    name_lower = company_name.lower()
    return any(bt.lower() in name_lower for bt in BIG_TECH_COMPANIES + GLOBAL_TECH_GIANTS)

def get_is_foreign(company_name: str, link: str) -> bool:
    # 1. Проверка по списку глобальных гигантов
    name_lower = company_name.lower()
    if any(gt.lower() in name_lower for gt in GLOBAL_TECH_GIANTS):
        return True
        
    # 2. Проверка по домену ссылки
    if not link:
        return False
        
    # Если ссылка содержит международные домены и не содержит .ru
    domain_match = re.search(r'\.(com|io|net|dev|ai|org|edu|gov|eu|uk|us)\b', link.lower())
    russian_match = re.search(r'\.(ru|su|рф)\b', link.lower())
    
    if domain_match and not russian_match:
        return True
        
    return False

# Импорт модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import src.scraper as scr
from src.rag_db import RAGDatabase

class ATSResult(BaseModel):
    # Computed by Python from ats_score_percentage — LLM should not decide this.
    is_good_match: bool = Field(
        default=False,
        description="IGNORE — runtime sets this to (ats_score_percentage >= 70). Always output false."
    )
    ats_score_percentage: int = Field(
        description="Integer 0-100. Sum of four 25-pt axes from the rubric: tech stack, seniority, domain fit, soft signals."
    )
    sphere: str = Field(description="Сфера вакансии: NLP / LLM, Audio ML, Backend Go, Data Eng и т.д.")
    matched_keywords: List[str] = Field(
        description="Навыки/инструменты, явно присутствующие И в CV, И в JD (до 12 элементов)."
    )
    missing_keywords: List[str] = Field(
        description="Критичные требования JD, НЕ подтверждённые в CV (до 8 элементов)."
    )
    reasoning: str = Field(
        description="1-2 предложения на русском со ссылкой на конкретные оси рубрики, которые определили балл."
    )
    adapted_bullets: List[str] = Field(
        description=(
            "2-3 буллита из существующего опыта кандидата, переформулированных под терминологию JD. "
            "ЗАПРЕЩЕНО выдумывать технологии, команды, метрики, которых нет в CV. "
            "Разрешено: заменять эквивалентные термины, выносить метрики, уже подразумеваемые достижениями. "
            "Вывод на русском."
        )
    )
    improvement_tips: List[str] = Field(
        default_factory=list,
        description=(
            "3-5 точечных советов, что поменять/добавить в резюме, чтобы пройти первый этап ATS-отсева "
            "именно этой вакансии. Фокус — на формулировках, ключевых словах из JD, порядке блоков, "
            "секциях headline/summary/skills. Каждый совет — одно действие с конкретикой "
            "(что именно дописать/перенести/переформулировать). Без общих фраз. Вывод на русском."
        )
    )
    application_message: str = Field(
        default="",
        description=(
            "Готовый текст отклика (120-220 слов), который кандидат вставит в модальную форму отклика "
            "на сайте работодателя. Формат: короткое приветствие → почему именно эта роль "
            "(1-2 сигнала из JD) → 3 конкретных подтверждения опыта из CV (через запятую, не буллитами) → "
            "готовность к следующему шагу (созвон, тестовое). Без markdown, без шапки 'Dear Hiring Manager', "
            "без вставных плейсхолдеров. Язык — совпадает с языком вакансии (RU/EN)."
        )
    )

def main():
    parser = argparse.ArgumentParser(description="AI RAG CV Matcher")
    parser.add_argument("--skip-scraping", action="store_true", help="Пропустить скрейпинг и использовать кэшированные вакансии из ChromaDB")
    parser.add_argument(
        "--sources",
        type=str,
        default="yandex,hh,ozon,avito,tinkoff,vk,x5",
        help="CSV-список источников для скрейпинга. Доступно: yandex,hh,ozon,avito,tinkoff,vk,x5,sber (sber по умолчанию отключён — anti-bot).",
    )
    parser.add_argument("--use-openai", action="store_true", help="Использовать OpenAI API вместо локального Ollama")
    parser.add_argument("--use-claude", action="store_true", help="Использовать Anthropic Claude API (топ-модель для reasoning)")
    parser.add_argument("--use-cloud-api", action="store_true", help="Использовать Vercel API Gateway (скрывает OpenAI ключ)")
    parser.add_argument("--openai-model", type=str, default="gpt-5.4", help="Модель OpenAI (по умолчанию gpt-5.4 — топ-модель)")
    parser.add_argument("--claude-model", type=str, default="claude-opus-4-7", help="Модель Anthropic Claude (по умолчанию claude-opus-4-7)")
    parser.add_argument("--clear-cache", action="store_true", help="Полностью очистить локальный кэш LLM-ответов")
    parser.add_argument("--top-k", type=int, default=40, help="Сколько вакансий взять из RAG-поиска для ATS-оценки (по умолчанию 40)")
    parser.add_argument("--rag-pooling", choices=["min", "mean"], default="min", help="Стратегия пулинга дистанций между чанками CV и вакансиями: 'min' (лучший матч любого чанка) или 'mean' (усреднение)")
    args = parser.parse_args()

    print("🔥 Запуск RAG-пайплайна матчинга вакансий...")
    
    # Инициализация LLM
    llm = None
    chain = None
    if args.use_cloud_api:
        print("☁️ Выбран облачный Vercel API Gateway. Ланчейн не инициализируем.")
    else:
        try:
            if args.use_claude:
                if ChatAnthropic is None:
                    print("❌ ОШИБКА: langchain-anthropic не установлен. Запустите: uv pip install langchain-anthropic")
                    sys.exit(1)
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    print("❌ ОШИБКА: ANTHROPIC_API_KEY не установлен в .env")
                    sys.exit(1)
                print(f"🧠 Инициализация Anthropic Claude ({args.claude_model})...")
                llm = ChatAnthropic(model=args.claude_model, temperature=0.1, max_tokens=4096)
            elif args.use_openai:
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
    
    # Получаем список уже изученных вакансий (Scraping Cache)
    existing_ids = db.get_all_ids()
    print(f"📊 В базе уже есть {len(existing_ids)} вакансий. Они будут пропущены при сборе.")
    
    # Список R&D запросов для keyword-based источников.
    queries = [
        "ML",
        "LLM",
        "Audio ML",
        "Multi-Modal",
        "GenAI",
        "Diffusion",
        "RLHF",
        "Kandinsky",
        "Machine Learning Engineer",
    ]

    # Более короткий набор — для сайтов с меньшим объёмом вакансий.
    short_queries = ["ML", "LLM", "Generative AI"]

    # Специальный URL для Яндекса — фильтр по всем dev-профессиям разом.
    yandex_listing_url = (
        "https://yandex.ru/jobs/vacancies?"
        "professions=backend-developer&professions=database-developer"
        "&professions=desktop-developer&professions=frontend-developer"
        "&professions=full-stack-developer&professions=ml-developer"
        "&professions=mob-app-developer&professions=mob-app-developer-android"
        "&professions=mob-app-developer-ios&professions=noc-developer"
        "&professions=system-developer"
    )

    # Конфиг: source_key → (фабрика, список запросов).
    # Каждый вызов фабрики должен возвращать свежий scraper (каждый держит свою сессию Playwright).
    source_plan = {
        "yandex": (lambda: scr.YandexScraper(limit=200), [yandex_listing_url]),
        "hh":     (lambda: scr.HHScraper(limit=30), queries),
        "ozon":   (lambda: scr.OzonScraper(limit=20), ["ML", "Machine Learning", "Python"]),
        "avito":  (lambda: scr.AvitoScraper(limit=20), short_queries),
        "tinkoff":(lambda: scr.TinkoffScraper(limit=20), short_queries),
        "vk":     (lambda: scr.VKScraper(limit=20), short_queries),
        "x5":     (lambda: scr.X5RetailScraper(limit=20), short_queries),
        "sber":   (lambda: scr.SberScraper(limit=20), ["ML"]),
    }

    requested_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in requested_sources if s not in source_plan]
    if unknown:
        print(f"⚠️ Неизвестные источники: {unknown}. Доступно: {list(source_plan)}")
        requested_sources = [s for s in requested_sources if s in source_plan]

    all_jobs = []

    if not args.skip_scraping:
        print(f"\n--- ЭТАП 1: СКРЕЙПИНГ ВАКАНСИЙ (sources: {','.join(requested_sources)}) ---")
        for key in requested_sources:
            factory, qs = source_plan[key]
            print(f"🔍 Запуск парсинга {key} ({len(qs)} запросов)...")
            scraper = factory()
            for q in qs:
                jobs = scraper.fetch_jobs(q, existing_ids=existing_ids)
                all_jobs.extend(jobs)
            
        # Агрегация уникальных вакансий и их источников
        unique_jobs_map = {}
        for job in all_jobs:
            jid = job["id"]
            if jid in unique_jobs_map:
                # Добавляем новый источник, если его еще нет
                q = job.get("origin_query", "unknown")
                if "origin_queries" not in unique_jobs_map[jid]:
                     unique_jobs_map[jid]["origin_queries"] = [unique_jobs_map[jid].get("origin_query", "unknown")]
                if q not in unique_jobs_map[jid]["origin_queries"]:
                    unique_jobs_map[jid]["origin_queries"].append(q)
            else:
                job["origin_queries"] = [job.get("origin_query", "unknown")]
                unique_jobs_map[jid] = job
        
        unique_jobs = list(unique_jobs_map.values())
        
        print("\n--- ЭТАП 2: ВЕКТОРИЗАЦИЯ И РАЗМЕЩЕНИЕ В БД ---")
        db.add_vacancies(unique_jobs)
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

    # Собираем отдельные чанки CV для multi-chunk RAG-поиска.
    # about.md и каждая позиция — отдельный вектор. Поиск пулится (min/mean)
    # чтобы, например, NLP-вакансия находила релевантный кусок даже если
    # большая часть опыта в резюме — backend.
    cv_chunks: List[str] = []
    structured_experience = [] # Для красивого рендеринга в HTML

    about_path = "../../content/ru/about.md"
    about_text = ""
    if os.path.exists(about_path):
        with open(about_path, "r", encoding="utf-8") as f:
            about_text = f.read()
            if about_text.strip():
                cv_chunks.append(about_text)

    # Регэкспы для определения текущей позиции. Поддерживаем ru/en формулировки
    # и обозначения вроде "2020 — н.в." и "2020 – present".
    _current_position_markers = re.compile(
        r"(настоящ|по\s+настоящ|н\.\s*в\.|present|current|now)", re.IGNORECASE
    )

    for exp in cv_data.get("experience", []):
        exp_id = exp["id"]
        period = exp.get("period", "")

        # Фильтр: оставляем опыт ≥ 2018 г. ИЛИ любую текущую позицию.
        years = [int(s) for s in period.split() if s.isdigit() and len(s) == 4]
        is_current = bool(_current_position_markers.search(period))
        if years and max(years) < 2018 and not is_current:
            continue

        md_path = os.path.join(cv_dir, f"{exp_id}.md")

        description_md = ""
        if os.path.exists(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                description_md = f.read()

        # Отдельный чанк на каждую позицию.
        cv_chunks.append(
            f"Company: {exp['company']}\nRole: {exp['role']}\nPeriod: {period}\n\n{description_md}"
        )

        structured_experience.append({
            "company": exp["company"],
            "role": exp["role"],
            "period": exp["period"],
            "desc_html": markdown.markdown(description_md)
        })

    # Объединённый текст сохраняем для обратной совместимости с ATS-оценкой,
    # кэш-хешем и 3D-PCA — туда нужен единый текст.
    cv_search_text = "\n\n".join(cv_chunks)

    print("\n--- ЭТАП 3: КОСИНУСНЫЙ ПОИСК ВАКАНСИЙ (RAG, multi-chunk) ---")
    top_jobs = db.search_similar_vacancies_multi_chunk(
        cv_chunks=cv_chunks,
        top_k=args.top_k,
        pooling=args.rag_pooling,
    )
    
    if not top_jobs:
        print("⚠️ Нет вакансий в базе для поиска.")
        sys.exit(1)
        
    print("\n--- ЭТАП 4: AI-ATS ПРОВЕРКА (РАНЖИРОВАНИЕ) ---")
    
    # Загружаем кэш
    cache_path = "./ai_cache.json"
    
    if args.clear_cache and os.path.exists(cache_path):
        print("🗑️ Очистка локального кэша по запросу (--clear-cache)...")
        os.remove(cache_path)
        
    ai_cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ai_cache = json.load(f)
        except:
            pass

    # Хеш резюме для кэширования
    cv_hash = hashlib.md5(cv_search_text.encode('utf-8')).hexdigest()

    if llm:
        structured_llm = llm.with_structured_output(ATSResult)
        prompt = PromptTemplate.from_template("""You are a FAANG-level ATS Recruiter AI. Evaluate the candidate's Resume against the provided Job Description and output a calibrated, structured assessment.

Job Description:
{vacancy}

Candidate Resume:
{cv}

## Scoring rubric (MUST follow)
Score on a 0-100 scale using FOUR equal axes (each worth 25 points):
  • Tech stack overlap (25 pts) — languages, frameworks, libraries, ML techniques explicitly required.
  • Seniority / scope (25 pts) — level (Junior/Middle/Senior/Staff), team size, project complexity.
  • Domain fit (25 pts) — industry, product area (NLP / CV / audio / search / recsys / backend / etc.).
  • Soft signals (25 pts) — language (RU/EN), location/remote fit, leadership, research / production profile.

Bucket interpretation (for self-calibration — the final number is the sum of axes):
  • 90-100: near-perfect fit, candidate can start immediately.
  • 70-89: strong match, 1-2 minor gaps.
  • 50-69: partial match, notable gaps in 1-2 axes.
  • <50: weak match, fundamental mismatch on stack/seniority/domain.
Be strict: do NOT inflate scores. A Senior ML role with 0% NLP experience in the CV cannot exceed 65.

## Output fields (enforce all)
  • ats_score_percentage — integer 0-100 (sum of the four axes above).
  • sphere — short category label (e.g. "NLP / LLM", "Audio ML", "Backend Go", "Data Eng").
  • matched_keywords — concrete skills/tools that appear in BOTH the CV and the JD (≤12 items).
  • missing_keywords — critical JD requirements NOT evidenced in the CV (≤8 items).
  • reasoning — 1-2 sentences in Russian referencing the specific axes that drove the score.
  • adapted_bullets — 2-3 rewritten CV bullets (see rules below).
  • improvement_tips — 3-5 точечных советов по CV (см. правила ниже).
  • application_message — готовый текст отклика для модальной формы (см. правила ниже).
  • is_good_match — leave for the runtime to compute; set to false by default.

## adapted_bullets rules (CRITICAL)
Rewrite 2-3 of the candidate's EXISTING bullet points using the JD's terminology.
DO NOT INVENT new experience, technologies, companies, or metrics the candidate never mentioned.
You may:
  • substitute equivalent terms (e.g. "real-time audio streaming" → "TTFAT / barge-in latency optimization" IF JD asks for it);
  • surface metrics/scales already implied by the candidate's achievements;
  • translate Russian bullets to English or vice-versa if JD is in a different language.
You MUST NOT:
  • claim experience with a tool/framework not mentioned in the CV;
  • fabricate numbers, team sizes, user counts.
Output adapted_bullets in Russian.

## improvement_tips rules
Дай 3-5 конкретных, действенных советов, что изменить/добавить в резюме, чтобы пройти
ПЕРВЫЙ ЭТАП ATS-отсева по этой вакансии. Каждый совет — одно действие с конкретикой.
Фокусируйся на:
  • ключевых словах из JD, которых не хватает в CV, — где именно их поднять (headline / summary / skills / bullet конкретной позиции);
  • переформулировках, где у кандидата есть эквивалентный опыт, но он назван иначе;
  • структурных сигналах (seniority, scope, команда, production/research);
  • порядке и приоритизации опыта под данную JD.
Запрещено: советовать выдумывать опыт, технологии, метрики. Только перегруппировка/переформулировка РЕАЛЬНОГО опыта.
Формат каждого совета: "Действие + место в CV + конкретная формулировка". Русский.
Пример: "В headline добавь 'Realtime LLM WebRTC' — у тебя Severstal GPT-Realtime это прямо подтверждает, но сейчас не видно в первой строке профиля."

## application_message rules
Составь текст отклика (120-220 слов), который кандидат дословно вставит в модальную форму на сайте работодателя.
Структура (одним связным текстом, без markdown, без подзаголовков):
  1. Короткое приветствие (1 строка).
  2. Почему именно эта роль — 1-2 конкретных сигнала из JD (продукт / стэк / задача).
  3. 3 подтверждения из реального опыта CV — плотно, через запятую, с тех-стэком и ролью.
  4. Готовность к следующему шагу (созвон / тестовое / доступ к код-сэмплам).
Требования:
  • язык совпадает с языком JD (русский JD → русский отклик; английский JD → английский);
  • НЕ использовать «Уважаемый работодатель», «Dear Hiring Manager» и подобные штампы-плейсхолдеры;
  • НЕ выдумывать то, чего нет в CV;
  • тон — уверенный, конкретный, без канцелярита и без самохвальства;
  • финал — одно короткое предложение с call-to-action.""")
        chain = prompt | structured_llm

    ranked_results = []
    
    cv_exports_dir = "../../public/adapted_cvs"
    os.makedirs(cv_exports_dir, exist_ok=True)
    
    for job in top_jobs:
        # Уникальный стабильный ключ для кэша: Job ID + CV Hash + Version
        job_id = job["id"]
        job_hash = hashlib.md5(f"{job_id}_{cv_hash}_{PROMPT_VERSION}".encode('utf-8')).hexdigest()
        
        try:
            # 1. Проверяем кэш
            # Также проверяем наличие поля matched_keywords, если мы хотим принудительно обновить старый кэш
            is_in_cache = job_hash in ai_cache
            has_new_fields = is_in_cache and "matched_keywords" in ai_cache[job_hash]
            
            if is_in_cache and has_new_fields:
                print(f"⚡ КЭШ: {job['metadata']['title']} (извлечено за 0мс)")
                ats_val_dict = ai_cache[job_hash]
                # Всегда пересчитываем is_good_match из актуального скора — старые
                # записи кэша могли нести LLM-решение, которое расходится со скором.
                ats_val_dict["is_good_match"] = ats_val_dict.get("ats_score_percentage", 0) >= 70
            else:
                if is_in_cache and not has_new_fields:
                    print(f"🔄 ОБНОВЛЕНИЕ: {job['metadata']['title']} (добавление новых полей)...")
                else:
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
                        "sphere": data.get("sphere", "Unknown"),
                        "matched_keywords": data.get("matched_keywords", []),
                        "missing_keywords": data.get("missing_keywords", []),
                        "reasoning": data.get("reasoning", ""),
                        "adapted_bullets": data.get("adapted_bullets", []),
                        "improvement_tips": data.get("improvement_tips", []),
                        "application_message": data.get("application_message", ""),
                    }
                else:
                    ats_val: ATSResult = chain.invoke({
                        "vacancy": job["document"],
                        "cv": cv_search_text
                    })
                    ats_val_dict = {
                        "ats_score_percentage": ats_val.ats_score_percentage,
                        "sphere": ats_val.sphere,
                        "matched_keywords": getattr(ats_val, "matched_keywords", []),
                        "missing_keywords": ats_val.missing_keywords,
                        "reasoning": ats_val.reasoning,
                        "adapted_bullets": ats_val.adapted_bullets,
                        "improvement_tips": getattr(ats_val, "improvement_tips", []),
                        "application_message": getattr(ats_val, "application_message", ""),
                    }

                # is_good_match вычисляется Python'ом — не доверяем LLM.
                ats_val_dict["is_good_match"] = ats_val_dict.get("ats_score_percentage", 0) >= 70

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
                
            job_id = job["id"]
            company_name = job["metadata"]["company"]
            job_link = job["metadata"].get("link", "")
            big_tech_status = is_big_tech(company_name)
            foreign_status = get_is_foreign(company_name, job_link)
            
            # Добавляем в JSON выдачу
            ranked_results.append({
                "id": job_id,
                "title": job["metadata"]["title"],
                "company": company_name,
                "is_big_tech": big_tech_status,
                "is_foreign": foreign_status,
                "pub_date": job["metadata"].get("pub_date", "Неизвестно"),
                "sphere": ats_val_dict.get("sphere", "Unknown"),
                "matched_keywords": ats_val_dict.get("matched_keywords", []),
                "missing_keywords": ats_val_dict.get("missing_keywords", []),
                "origin_queries": job["metadata"].get("origin_queries", []),
                "link": job["metadata"]["link"],
                "ats_score": ats_val_dict.get("ats_score_percentage", 0),
                "cosine_distance": float(job["distance"]),
                "reasoning": ats_val_dict.get("reasoning", ""),
                "is_good_match": ats_val_dict.get("is_good_match", False),
                "adapted_bullets": adapted_cv_bullets,
                "improvement_tips": ats_val_dict.get("improvement_tips", []),
                "application_message": ats_val_dict.get("application_message", ""),
            })
        except Exception as e:
            err_str = str(e)
            if "404" in err_str and not args.use_openai and not args.use_cloud_api:
                print(f"❌ ОШИБКА ДЕМОНА OLLAMA: Локальная модель Ollama не найдена. Убедитесь, что Ollama запущена.")
                sys.exit(1)
            elif "re' is not defined" in err_str:
                print(f"❌ ОШИБКА ВНУТРЕННЕЙ ЛОГИКИ: Библиотека 're' не инициализирована. {e}")
            else:
                # Если ошибка пришла от API
                if args.use_cloud_api:
                    print(f"❌ СЕТЕВАЯ ОШИБКА (Vercel API) для вакансии {job['metadata']['title']}: {e}")
                else:
                    print(f"❌ ОШИБКА ОБРАБОТКИ для вакансии {job['metadata']['title']}: {e}")
                
                if args.use_cloud_api and "404" in err_str:
                     print("   -> Подсказка: Vercel возвращает 404. Возможно вы ошиблись в домене CV_API_URL в .env, или деплой на Vercel еще не завершился! Подождите 1 минуту.")
                sys.exit(1)
            
    ranked_results.sort(key=lambda x: x["ats_score"], reverse=True)
    
    # 5.1 Генерация 3D Scatter (PCA)
    print("\n--- ГЕНЕРАЦИЯ 3D ПРОСТРАНСТВА (PCA) ---")
    ats_score_map = {res["id"]: res["ats_score"] for res in ranked_results}
    bt_status_map = {res["id"]: res.get("is_big_tech", False) for res in ranked_results}
    foreign_status_map = {res["id"]: res.get("is_foreign", False) for res in ranked_results}
    
    scatter_3d_data = db.export_3d_embeddings(
        cv_search_text, 
        ats_scores=ats_score_map, 
        bt_statuses=bt_status_map,
        foreign_statuses=foreign_status_map
    )
    
    # 5. ГЕНЕРАЦИЯ СОПРОВОДИТЕЛЬНЫХ ПИСЕМ (ТОП-3)
    print("\n--- ЭТАП 5: ГЕНЕРАЦИЯ COVER LETTERS (TOP-3) ---")
    output_dir = "../../public"
    cl_dir = os.path.join(output_dir, "cover_letters")
    os.makedirs(cl_dir, exist_ok=True)
    
    # Сортируем по ATS баллу
    top_matches = sorted(ranked_results, key=lambda x: x["ats_score"], reverse=True)[:3]
    
    for match in top_matches:
        if match["ats_score"] < 50:
            continue
            
        cl_filename = f"cl_{match['id']}.txt"
        cl_path = os.path.join(cl_dir, cl_filename)
        
        if os.path.exists(cl_path):
            print(f"⚡ CL КЭШ: Сопроводительное для {match['title']} уже есть.")
            match["cl_path"] = f"cover_letters/{cl_filename}"
            continue
            
        print(f"🤖 Генерируем Cover Letter для {match['title']} ({match['company']})...")
        try:
            cl_api_url = os.environ.get("CV_API_URL", "").replace("/ats", "/coverletter")
            if not cl_api_url:
                cl_api_url = "https://vladislav-vasilenko.github.io/api/coverletter"
                
            cl_payload = {
                "vacancyText": next(j["document"] for j in search_results if j["id"] == match["id"]),
                "matchedKeywords": match.get("matched_keywords", []),
                "sphere": match.get("sphere", "General"),
                "lang": "ru" # Или детектировать по языку вакансии
            }
            
            headers = {"Content-Type": "application/json"}
            api_secret = os.environ.get("API_SECRET", "")
            if api_secret:
                headers["Authorization"] = f"Bearer {api_secret}"

            res = requests.post(cl_api_url, json=cl_payload, headers=headers)
            res.raise_for_status()
            cl_text = res.json().get("coverLetter", "")
            
            with open(cl_path, "w", encoding="utf-8") as f:
                f.write(cl_text)
            
            match["cl_path"] = f"cover_letters/{cl_filename}"
            print(f"✅ Готово: {cl_filename}")
        except Exception as e:
            print(f"❌ Ошибка генерации CL для {match['id']}: {e}")

    print("\n--- ЭТАП 6: ЭКСПОРТ В JSON ДЛЯ ФРОНТЕНДА ---")
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
