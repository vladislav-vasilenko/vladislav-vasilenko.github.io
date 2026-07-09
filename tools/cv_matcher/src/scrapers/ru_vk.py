"""VKScraper implementation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _extract_date, _first_non_empty_text, _scroll_until_stable


class VKScraper(BaseScraper):
    company_name = "VK"
    id_prefix = "vk"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = "https://team.vk.company/vacancy/"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        try:
            search_box = page.locator(
                "input[type='search'], input[placeholder*='Поиск'], input[placeholder*='Найти']"
            ).first
            if search_box.count() > 0:
                search_box.fill(query)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)
        except Exception:
            pass

        link_selector = "a[href*='/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/(\d+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  VK: {len(links)} ссылок")

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
                title = _first_non_empty_text(page, ["h1", "[class*='VacancyHeader']"]) or "VK Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='VacancyContent']",
                    "[class*='vacancy-content']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                if query and query.lower() not in clean.lower() and query.lower() not in title.lower():
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
# X5 Retail
