import time
import re
from urllib.parse import quote
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

class SberScraper:
    def __init__(self):
        self.base_url = "https://rabota.sber.ru"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_jobs(self, query: str = "ML Engineer", existing_ids: set = None) -> List[Dict[str, Any]]:
        print(f"🔍 Парсинг реального сайта Сбера (Playwright Native) по запросу '{query}'...")
        if existing_ids is None: existing_ids = set()
        
        vacancies = []
        
        try:
            with sync_playwright() as p:
                            # На Mac используем системный Chrome + Disable GPU для стабильности.
            # Если падает - переключаемся на нативный WebKit.
            try:
                browser = p.chromium.launch(
                    channel="chrome", 
                    headless=False, 
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
                )
            except Exception as e:
                print(f"      ⚠️ Проблема с Chrome ({e}), переключаемся на WebKit...")
                try:
                    browser = p.webkit.launch(headless=True)
                except:
                    browser = p.chromium.launch(headless=False, args=["--disable-gpu"])

                context = browser.new_context(user_agent=self.headers["User-Agent"])
                page = context.new_page()
                
                print(f"Переход на {search_url}...")
                
                # Извлекаем профессии из URL для метаданных
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(search_url)
                qs = parse_qs(parsed_url.query)
                professions = qs.get("professions", ["yandex_jobs"])
                origin_label = ", ".join(professions)

                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                
                # Умный скролл до достижения лимита или конца списка
                print("Начинаем глубокий скролл для загрузки всех вакансий...")
                last_count = 0
                max_scroll_attempts = 15
                
                for attempt in range(max_scroll_attempts):
                    # Прокрутка вниз
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    
                    # Проверка на кнопку "Показать еще" (если есть)
                    # Обычно это кнопка с текстом "Показать еще" или аналогичным
                    show_more = page.get_by_role("button", name=re.compile("Показать еще|Загрузить еще", re.I))
                    if show_more.count() > 0 and show_more.is_visible():
                        print("  Found 'Show More' button, clicking...")
                        show_more.click()
                        page.wait_for_timeout(2000)

                    # Считаем текущее кол-во ссылок
                    hrefs = page.eval_on_selector_all("a[href*='/jobs/vacancies/']", "elements => elements.map(e => e.href)")
                    current_count = len(list(set([h.split("?")[0] for h in hrefs if "/vacancies/" in h])))
                    
                    print(f"  Attempt {attempt+1}: Found {current_count} links...")
                    
                    if current_count >= 200:
                        print("  Reached target limit of 200 links.")
                        break
                    
                    if current_count == last_count and attempt > 5:
                        print("  No new vacancies loaded, stopping scroll.")
                        break
                    last_count = current_count
                
                # Собираем финальный список ссылок
                hrefs = page.eval_on_selector_all("a[href*='/jobs/vacancies/']", "elements => elements.map(e => e.href)")
                job_links = list(set([h.split("?")[0] for h in hrefs if "/vacancies/" in h]))
                
                print(f"Найдено {len(job_links)} ссылок на вакансии Яндекса. Начинаем сбор...")
                
                for idx, job_url in enumerate(job_links[:200]): # Лимит 200
                    try:
                        # Умная проверка кэша: пропускаем если ID уже в базе
                        job_id = f"yandex_{job_url.rstrip('/').split('/')[-1]}"
                        if job_id in (existing_ids or set()):
                            print(f"  ⚡ Яндекс Пропуск (уже в базе): {job_id}")
                            continue

                        page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(2000)
                        
                        # Парсим контент
                        # В Яндексе часто несколько h1 (куки, заголовки и т.д.). 
                        # Ищем заголовок по специфическому классу lc-styled-text__text или внутри main
                        title = "Yandex Vacancy"
                        try:
                            # Пытаемся найти по классу, который мы видели в логах
                            title_el = page.locator("h1.lc-styled-text__text").first
                            if title_el.count() > 0:
                                title = title_el.inner_text()
                            else:
                                # Фолбэк на заголовок в main
                                title_el = page.locator("main h1").first
                                if title_el.count() > 0:
                                    title = title_el.inner_text()
                                else:
                                    # Самый последний шанс - любой h1
                                    title = page.locator("h1").first.inner_text()
                        except:
                            pass
                        
                        # Собираем весь видимый текст описания
                        # В Яндексе это часто div с определенными классами, но попробуем по ролям
                        content_text = page.locator("main").inner_text() if page.locator("main").count() > 0 else page.locator("body").inner_text()
                        
                        # Очистка текста
                        clean_text = " ".join(content_text.split())
                        
                        job_id = job_url.rstrip("/").split("/")[-1]
                        
                        # Пытаемся найти дату в тексте (паттерны: "12 апреля", "вчера", "2 дня назад")
                        date_match = re.search(r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4})?)', clean_text, re.IGNORECASE)
                        pub_date = date_match.group(1) if date_match else "Недавно"
                        
                        vacancies.append({
                            "id": f"yandex_{job_id}",
                            "title": title,
                            "company": "Яндекс",
                            "pub_date": pub_date,
                            "description": clean_text[:3500],
                            "link": job_url,
                            "origin_query": origin_label
                        })
                        print(f"  [{idx+1}/{len(job_links)}] {title}")
                    except Exception as loop_e:
                        print(f"Пропуск вакансии {job_url}: {loop_e}")
                
                browser.close()
            return vacancies
        except Exception as e:
            print(f"❌ Ошибка парсинга Яндекса: {e}")
            return []

class HHScraper:
    def __init__(self, limit=50):
        self.limit = limit

    def fetch_jobs(self, query: str, existing_ids: set = None) -> List[Dict[str, Any]]:
        vacancies = []
        if existing_ids is None: existing_ids = set()
        
        base_url = "https://hh.ru/search/vacancy"
        
        with sync_playwright() as p:
                        # На Mac используем системный Chrome + Disable GPU для стабильности.
            # Если падает - переключаемся на нативный WebKit.
            try:
                browser = p.chromium.launch(
                    channel="chrome", 
                    headless=False, 
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
                )
            except Exception as e:
                print(f"      ⚠️ Проблема с Chrome ({e}), переключаемся на WebKit...")
                try:
                    browser = p.webkit.launch(headless=True)
                except:
                    browser = p.chromium.launch(headless=False, args=["--disable-gpu"])

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                page_num = 0
                while len(vacancies) < self.limit:
                    search_url = f"{base_url}?text={query}&area=1&page={page_num}"
                    print(f"  HH: Парсинг страницы {page_num+1} ({query})...")
                    
                    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000) 
                    
                    # Локатор для ссылок на вакансии
                    links_elements = page.locator('a[data-qa="serp-item__title"]').all()
                    if not links_elements:
                        print("  HH: Вакансии больше не найдены.")
                        break
                        
                    job_urls = []
                    for link_el in links_elements:
                        href = link_el.get_attribute("href")
                        if href:
                            clean_url = href.split('?')[0]
                            job_urls.append(clean_url)
                    
                    for job_url in job_urls:
                        if len(vacancies) >= self.limit:
                            break
                            
                        job_id = f"hh_{job_url.split('/')[-1]}"
                        if job_id in existing_ids:
                            print(f"  ⚡ HH Пропуск: {job_id}")
                            continue

                        try:
                            page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                            
                            title = page.locator('h1[data-qa="vacancy-title"]').inner_text()
                            company = page.locator('a[data-qa="vacancy-company-name"]').first.inner_text()
                            description = page.locator('div[data-qa="vacancy-description"]').inner_text()
                            
                            job_id = job_url.split('/')[-1]
                            
                            vacancies.append({
                                "id": f"hh_{job_id}",
                                "title": title,
                                "company": company,
                                "pub_date": "Recently",
                                "description": description[:4000],
                                "link": job_url,
                                "origin_query": query
                            })
                            print(f"    [HH] {title} ({company})")
                            page.wait_for_timeout(1000)
                        except Exception as inner_e:
                            print(f"    Ошибка при парсинге {job_url}: {inner_e}")
                            
                    page_num += 1
                    if page_num > 3: # Глубина поиска
                        break
                        
            except Exception as e:
                print(f"❌ Ошибка в HHScraper: {e}")
            finally:
                browser.close()
                
        return vacancies

class OzonScraper:
    def __init__(self, limit=30):
        self.limit = limit

    def fetch_jobs(self, query: str, existing_ids: set = None) -> List[Dict[str, Any]]:
        vacancies = []
        if existing_ids is None: existing_ids = set()
        # Город Москва по умолчанию (согласно запросу пользователя)
        base_url = f"https://career.ozon.ru/vacancy/?query={query}&city=Москва"
        
        with sync_playwright() as p:
                        # На Mac используем системный Chrome + Disable GPU для стабильности.
            # Если падает - переключаемся на нативный WebKit.
            try:
                browser = p.chromium.launch(
                    channel="chrome", 
                    headless=False, 
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
                )
            except Exception as e:
                print(f"      ⚠️ Проблема с Chrome ({e}), переключаемся на WebKit...")
                try:
                    browser = p.webkit.launch(headless=True)
                except:
                    browser = p.chromium.launch(headless=False, args=["--disable-gpu"])

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                print(f"  Ozon: Переход на {base_url}...")
                page.goto(base_url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(3000)
                
                # Ищем все ссылки на вакансии
                # Озон использует динамическую подгрузку, подождем немного
                job_links_elements = page.locator('a[href*="/vacancy/"]').all()
                
                print(f"  Ozon: Найдено {len(job_links_elements)} потенциальных ссылок.")
                
                seen_urls = set()
                job_urls = []
                for el in job_links_elements:
                    href = el.get_attribute("href")
                    if href:
                        # Приводим к полному URL
                        full_url = href if href.startswith("http") else f"https://career.ozon.ru{href}"
                        clean_url = full_url.split('?')[0].rstrip('/')
                        if clean_url not in seen_urls and "/vacancy/" in clean_url:
                            seen_urls.add(clean_url)
                            job_urls.append(clean_url)

                for job_url in job_urls:
                    if len(vacancies) >= self.limit:
                        break
                    
                    job_id = f"ozon_{job_url.split('/')[-1]}"
                    if job_id in existing_ids:
                        print(f"  ⚡ Ozon Пропуск: {job_id}")
                        continue

                    try:
                        print(f"    Парсинг {job_url}...")
                        page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                        page.wait_for_timeout(1500)
                        
                        # Селекторы Ozon могут меняться, используем более общие
                        title = page.locator('h1').inner_text()
                        
                        # Ищем описание (обычно это несколько блоков или один большой контейнер)
                        # Пробуем разные варианты
                        description = ""
                        desc_selectors = ['div[class*="vacancy-description"]', 'div[class*="VacancyDescription"]', 'main']
                        for sel in desc_selectors:
                            if page.locator(sel).count() > 0:
                                description = page.locator(sel).first.inner_text()
                                break
                        
                        if not description:
                            description = page.locator('body').inner_text()

                        job_id = job_url.split('/')[-1]
                        
                        vacancies.append({
                            "id": f"ozon_{job_id}",
                            "title": title,
                            "company": "Ozon",
                            "pub_date": "Recently",
                            "description": description[:4000],
                            "link": job_url,
                            "origin_query": query
                        })
                        print(f"      [Ozon] {title}")
                    except Exception as inner_e:
                        print(f"      Ошибка при парсинге {job_url}: {inner_e}")

            except Exception as e:
                print(f"❌ Ошибка в OzonScraper: {e}")
            finally:
                browser.close()
                
        return vacancies

class AvitoScraper:
    def __init__(self, limit=20):
        self.limit = limit

    def fetch_jobs(self, query: str, existing_ids: set = None) -> List[Dict[str, Any]]:
        vacancies = []
        if existing_ids is None: existing_ids = set()
        base_url = f"https://career.avito.com/vacancies/?q={query}&action=filter"
        
        with sync_playwright() as p:
                        # На Mac используем системный Chrome + Disable GPU для стабильности.
            # Если падает - переключаемся на нативный WebKit.
            try:
                browser = p.chromium.launch(
                    channel="chrome", 
                    headless=False, 
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
                )
            except Exception as e:
                print(f"      ⚠️ Проблема с Chrome ({e}), переключаемся на WebKit...")
                try:
                    browser = p.webkit.launch(headless=True)
                except:
                    browser = p.chromium.launch(headless=False, args=["--disable-gpu"])

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                print(f"  Avito: Переход на {base_url}...")
                page.goto(base_url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(3000)
                
                # Ищем все ссылки на вакансии
                job_links_elements = page.locator('a[href*="/vacancies/"]').all()
                
                print(f"  Avito: Найдено {len(job_links_elements)} потенциальных ссылок.")
                
                seen_urls = set()
                job_urls = []
                for el in job_links_elements:
                    href = el.get_attribute("href")
                    if href:
                        full_url = href if href.startswith("http") else f"https://career.avito.com{href}"
                        clean_url = full_url.split('?')[0].rstrip('/')
                        if clean_url not in seen_urls and re.search(r'/\d+/?$', clean_url):
                            seen_urls.add(clean_url)
                            job_urls.append(clean_url)

                for job_url in job_urls:
                    if len(vacancies) >= self.limit:
                        break
                    
                    job_id_match = re.search(r'/(\d+)/?$', job_url)
                    job_id_val = job_id_match.group(1) if job_id_match else job_url.split('/')[-1]
                    job_id = f"avito_{job_id_val}"
                    
                    if job_id in existing_ids:
                        print(f"  ⚡ Avito Пропуск (уже в базе): {job_id}")
                        continue

                    try:
                        print(f"    Парсинг {job_url}...")
                        page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                        page.wait_for_timeout(1500)
                        
                        title = page.locator('h1').inner_text()
                        
                        description = ""
                        desc_selectors = ['[class*="Vacancy_description"]', '[class*="vacancy-description"]', 'article', 'main']
                        for sel in desc_selectors:
                            if page.locator(sel).count() > 0:
                                description = page.locator(sel).first.inner_text()
                                break
                        
                        if not description:
                            description = page.locator('body').inner_text()

                        vacancies.append({
                            "id": job_id,
                            "title": title,
                            "company": "Avito",
                            "pub_date": "Recently",
                            "description": description[:4000],
                            "link": job_url,
                            "origin_query": query
                        })
                        print(f"      [Avito] {title}")
                    except Exception as inner_e:
                        print(f"      Ошибка при парсинге {job_url}: {inner_e}")

            except Exception as e:
                print(f"❌ Ошибка в AvitoScraper: {e}")
            finally:
                browser.close()
                
        return vacancies

if __name__ == "__main__":
    import sys
    
    test_query = "ML Engineer"
    
    # Можно запускать тесты отдельных скрейперов
    if "--sber" in sys.argv:
        scraper = SberScraper()
        jobs = scraper.fetch_jobs(test_query, existing_ids=set())
        print(f"Sber found: {len(jobs)}")
    
    if "--yandex" in sys.argv:
        scraper = YandexScraper()
        yandex_url = "https://yandex.ru/jobs/vacancies?professions=ml-developer"
        jobs = scraper.fetch_jobs(yandex_url, existing_ids=set())
        print(f"Yandex found: {len(jobs)}")

    if "--hh" in sys.argv:
        scraper = HHScraper(limit=5)
        jobs = scraper.fetch_jobs(test_query, existing_ids=set())
        print(f"HH found: {len(jobs)}")

    if "--ozon" in sys.argv:
        scraper = OzonScraper(limit=5)
        jobs = scraper.fetch_jobs("ML", existing_ids=set())
        print(f"Ozon found: {len(jobs)}")

    if "--avito" in sys.argv:
        scraper = AvitoScraper(limit=5)
        jobs = scraper.fetch_jobs("LLM", existing_ids=set())
        print(f"Avito found: {len(jobs)}")
