"""X5RetailScraper implementation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _extract_date, _first_non_empty_text, _scroll_until_stable


class X5RetailScraper(BaseScraper):
    company_name = "X5 Retail"
    id_prefix = "x5"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://rabota.x5.ru/vacancies?search={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        link_selector = "a[href*='/vacancies/']"
        _scroll_until_stable(
            page,
            max_attempts=10,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Загрузить", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancies/([A-Za-z0-9\-]{8,})/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  X5: {len(links)} ссылок")

        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск: {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, [
                    "h1",
                    "[class*='vacancy-title' i]",
                    "[class*='VacancyTitle' i]",
                    "[class*='title' i]",
                ]) or "X5 Vacancy"
                title = title.split("зарплата")[0].strip() or title
                body = _first_non_empty_text(page, [
                    "[class*='VacancyContent']",
                    "[class*='vacancy-description']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Wildberries Tech
