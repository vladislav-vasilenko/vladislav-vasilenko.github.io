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

    def fetch_jobs(self, query: str = "ML Engineer") -> List[Dict[str, Any]]:
        print(f"🔍 Парсинг реального сайта Сбера (Playwright Native) по запросу '{query}'...")
        
        vacancies = []
        
        try:
            with sync_playwright() as p:
                # Используем НАСТОЯЩИЙ Google Chrome (Mac Native), а не багованную Chromium-сборку Playwright
                # Это должно обойти Signal 10 BUS_ADRALN (ошибку Rosetta/архитектуры Apple Silicon)
                try:
                    browser = p.chromium.launch(
                        channel="chrome", 
                        headless=False,
                        args=["--disable-dev-shm-usage", "--no-sandbox"]
                    )
                except Exception as e:
                    print(f"⚠️ Не найден Google Chrome на Mac, пробуем Safari (WebKit): {e}")
                    browser = p.webkit.launch(headless=False)

                page = browser.new_page()
                page.set_extra_http_headers(self.headers)
                
                url = f"{self.base_url}/search/?query={quote(query)}"
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Скроллим страницу несколько раз, чтобы SPA подгрузило больше вакансий
                for _ in range(5):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1500)
                
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем карточки вакансий
                links = soup.find_all('a', href=True)
                
                job_links = []
                for link in links:
                    href = link['href']
                    if href.startswith("/search/") and any(c.isdigit() for c in href):
                        full_url = f"{self.base_url}{href}"
                        if full_url not in job_links:
                            job_links.append(full_url)
                            
                print(f"Нашли {len(job_links)} потенциальных ссылок на вакансии. Обходим до 120...")
                
                for idx, job_url in enumerate(job_links[:120]):
                    try:
                        page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(2000)
                        job_html = page.content()
                        job_soup = BeautifulSoup(job_html, 'html.parser')
                        
                        # Парсим контент (title обычно в h1 или большом тексте)
                        # Так как классы хэшированы, просто берем весь текст и чистим
                        text_content = job_soup.get_text(separator=" | ", strip=True)
                        
                        # Попытаться найти заголовок (H1)
                        h1 = job_soup.find('h1')
                        title = h1.get_text(strip=True) if h1 else f"Sber Job {idx+1}"
                        
                        # Более надежное извлечение ID (убираем query params и trailing слэши)
                        raw_id = job_url.rstrip("/").split("/")[-1].split("?")[0]
                        job_id = raw_id if raw_id else f"sber_job_{idx}"

                        # Ищем дату (паттерны типа "12 апреля 2026", "2 мая")
                        date_match = re.search(r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4})?)', text_content, re.IGNORECASE)
                        pub_date = date_match.group(1) if date_match else "Неизвестно"

                        vacancies.append({
                            "id": job_id,
                            "title": title,
                            "company": "Сбер",
                            "pub_date": pub_date,
                            "description": text_content[:3000],  # Первые 3000 символов (для RAG достаточно)
                            "link": job_url
                        })
                    except Exception as loop_e:
                        print(f"Ошибка парсинга отдельной вакансии {job_url}: {loop_e}")
                        
                browser.close()
                
            print(f"✅ Успешно спарсено через Playwright Native: {len(vacancies)} вакансий")
            return vacancies

        except Exception as e:
            print(f"❌ Ошибка парсинга Playwright: {e}")
            return []

if __name__ == "__main__":
    scraper = SberScraper()
    jobs = scraper.fetch_jobs("ML Engineer")
    for j in jobs:
        print(f"Vacancy: {j['title']} | Link: {j['link']}")
