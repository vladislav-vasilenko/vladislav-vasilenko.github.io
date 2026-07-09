"""TinkoffScraper implementation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _extract_date, _first_non_empty_text, _scroll_until_stable


class TinkoffScraper(BaseScraper):
    company_name = "Т-Банк"
    id_prefix = "tinkoff"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = "https://www.tbank.ru/career/vacancies/it/"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        try:
            page.get_by_role("button", name=re.compile(r"Принять|OK", re.I)).first.click(timeout=1500)
        except Exception:
            pass

        try:
            search_box = page.locator("input[type='search'], input[placeholder*='Поиск']").first
            if search_box.count() > 0:
                search_box.fill(query)
                page.wait_for_timeout(2000)
        except Exception:
            pass

        link_selector = "a[href*='/career/it/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=15,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать ещё|Показать еще|Загрузить", re.I),
            link_selector=link_selector,
            target_count=self.limit * 3,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        seen, links = set(), []
        uuid_re = re.compile(r"/([0-9a-f\-]{32,})/?$", re.I)
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            if clean in seen or not uuid_re.search(clean):
                continue
            seen.add(clean)
            links.append(clean)
        print(f"  Т-Банк: {len(links)} ссылок")

        q_lower = query.lower()
        if q_lower:
            def score(u):
                slug = u.rstrip("/").split("/")[-2]
                return -slug.lower().count(q_lower[:3])
            links.sort(key=score)

        vacancies = []
        for job_url in links:
            if len(vacancies) >= self.limit:
                break
            uid = uuid_re.search(job_url).group(1)
            jid = f"{self.id_prefix}_{uid}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск: {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, ["h1", "[data-test*='title']"]) or "T-Bank Vacancy"
                body = _first_non_empty_text(page, [
                    "[data-test*='vacancy']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                if query and q_lower not in clean.lower() and q_lower not in title.lower():
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
# Avito
