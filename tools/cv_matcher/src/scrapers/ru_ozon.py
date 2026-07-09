"""Ozon career-site scraper."""

from __future__ import annotations

from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _first_non_empty_text, _safe_text


class OzonScraper(BaseScraper):
    company_name = "Ozon"
    id_prefix = "ozon"

    def __init__(self, limit: int = 30, headless: bool = True, **kwargs):
        super().__init__(limit=limit, headless=headless, **kwargs)

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        url = f"https://career.ozon.ru/vacancies/?query={quote(query)}&city=Москва"
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        link_selector = 'a[href*="/vacancy/"]'
        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            if "/vacancy/" not in clean or clean in seen:
                continue
            seen.add(clean)
            links.append(clean)
        print(f"  Ozon: {len(links)} ссылок")
        vacancies = []
        for job_url in links:
            if len(vacancies) >= self.limit:
                break
            vid = job_url.rstrip("/").split("/")[-1]
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _safe_text(page, "h1") or "Ozon Vacancy"
                desc = _first_non_empty_text(page, [
                    'div[class*="vacancy-description"]',
                    'div[class*="VacancyDescription"]',
                    "main",
                    "body",
                ])
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": "Ozon",
                    "pub_date": "Recently",
                    "description": desc[:4000],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"    [Ozon] {title}")
            except Exception as e:
                print(f"    ⚠️ {job_url}: {e}")
        return vacancies
