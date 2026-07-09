"""MTSScraper implementation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _extract_date, _first_non_empty_text, _scroll_until_stable


class MTSScraper(BaseScraper):
    """job.mts.ru — публичная выдача вакансий с поиском по query-param."""

    company_name = "МТС"
    id_prefix = "mts"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://job.mts.ru/vacancy?search={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        link_selector = "a[href*='/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Загрузить|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/([A-Za-z0-9\-_]+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  МТС: {len(links)} ссылок")

        q_lower = query.lower()
        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1200)
                title = _first_non_empty_text(page, ["h1", "[class*='vacancy-header' i]"]) or "MTS Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='vacancy-content' i]",
                    "[class*='description' i]",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                if q_lower and q_lower not in clean.lower() and q_lower not in title.lower():
                    continue
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
# Альфа-Банк
