"""Ozon career-site scraper."""

from __future__ import annotations

from typing import Any, Dict, List, Set
from urllib.parse import quote, urlsplit
from playwright.sync_api import Page

from ._base import BaseScraper, _first_non_empty_text, _safe_text
from ..board_import import identity


class OzonScraper(BaseScraper):
    company_name = "Ozon"
    id_prefix = "ozon"

    def __init__(self, limit: int = 30, headless: bool = True, **kwargs):
        super().__init__(limit=limit, headless=headless, **kwargs)

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        url = query if urlsplit(query).scheme == "https" and urlsplit(query).hostname in ("career.ozon.ru", "ozon.tech") else f"https://career.ozon.ru/vacancy/?query={quote(query)}&city=Москва"
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        link_selector = 'a[href*="/vacancy"], a[href*="ozon.tech/vacancies/"]'
        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        seen, links = set(), []
        for h in hrefs:
            job = identity(h)
            if not job or not job["id"].startswith("ozon_") or job["id"] in seen:
                continue
            seen.add(job["id"])
            links.append(job)
        print(f"  Ozon: {len(links)} ссылок")
        vacancies = []
        for job in links:
            if len(vacancies) >= self.limit:
                break
            job_url, jid = job["link"], job["id"]
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _safe_text(page, "h1") or "Ozon Vacancy"
                desc = _first_non_empty_text(page, ['[class*="descriptionHtml"]', '[class*="_description_"]'])
                if not desc:
                    raise ValueError("Full vacancy description not found; use browser export")
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": "Ozon",
                    "pub_date": "Recently",
                    "description": desc,
                    "description_quality": "full",
                    "source": "ozon_browser",
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"    [Ozon] {title}")
            except Exception as e:
                print(f"    ⚠️ {job_url}: {e}")
        return vacancies
