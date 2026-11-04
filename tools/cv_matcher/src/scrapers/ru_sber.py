"""Sber scraper."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Set
from urllib.parse import urlencode
from playwright.sync_api import Page

from ._base import BaseScraper
from .parsers.sber import (
    SBER_API_VERSION,
    SBER_PUBLICATIONS_URL,
    compose_sber_publication,
    sber_compensation,
)


class SberScraper(BaseScraper):
    """rabota.sber.ru, read through the public API its own search page uses.

    One list request carries full vacancy text, so no detail pages are needed.
    """

    company_name = "Сбер"
    id_prefix = "sber"
    api_page_size = 50
    api_timeout_ms = 15000

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        page.goto("https://rabota.sber.ru/search/", wait_until="domcontentloaded", timeout=60000)
        vacancies: List[Dict[str, Any]] = []
        q_lower = query.strip().lower()
        skip = 0
        while True:
            params = {"skip": skip, "take": self.api_page_size, **({"searchString": query.strip()} if query.strip() else {})}
            try:
                items, total = self._read_page(page, params)
            except Exception as e:
                self._fail(f"public API stopped at {skip}: {type(e).__name__}")
                break
            self.report["listed"] += len(items)
            for item in items:
                if self.limit and len(vacancies) >= self.limit:
                    break
                row = self._publication(item, query, q_lower, existing_ids)
                if row:
                    vacancies.append(row)
                    self._emit("vacancy", id=row["id"], title=row["title"], company=self.company_name, link=row["link"])
            skip += len(items)
            if not items or skip >= total or (self.limit and len(vacancies) >= self.limit):
                break
            time.sleep(0.3)
        self._finish_coverage(len(vacancies))
        print(f"  Сбер: собрано {len(vacancies)} новых вакансий, просмотрено {self.report['listed']}")
        return vacancies

    def _read_page(self, page: Page, params: Dict[str, Any]) -> Any:
        """A single request occasionally hangs, so retry once. Being refused is never retried."""
        url = f"{SBER_PUBLICATIONS_URL}?{urlencode(params)}"
        for attempt in range(2):
            try:
                response = page.request.get(url, timeout=self.api_timeout_ms)
            except Exception:
                if attempt:
                    raise
                time.sleep(2)
                continue
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status}")
            data = response.json()["data"]
            return data["vacancies"], data["total"]

    def _publication(self, item: Dict[str, Any], query: str, q_lower: str, existing_ids: Set[str]) -> Any:
        vid = str(item.get("internalId") or "")
        title = str(item.get("title") or "").strip()
        jid = f"{self.id_prefix}_{vid}"
        if not vid or not title or jid in existing_ids:
            return None
        description = compose_sber_publication(item)
        # The site's search is broader than an exact term; keep only rows that mention it.
        if q_lower and q_lower not in title.lower() and q_lower not in " ".join(description.split()).lower():
            return None
        return {
            "id": jid,
            "title": title,
            "company": str(item.get("company") or self.company_name),
            "pub_date": str(item.get("publicationDate") or "Recently"),
            "description": description,
            "description_quality": "full" if item.get("duties") and item.get("requirements") and len(description) > 150 else "needs_review",
            "adapter_version": SBER_API_VERSION,
            "link": f"https://rabota.sber.ru/search/{vid}",
            "locations": [city for city in [str(item.get("city") or "").strip()] if city],
            "teams": [item["specialization"]] if item.get("specialization") else [],
            "compensation": sber_compensation(item),
            "origin_query": query,
        }
