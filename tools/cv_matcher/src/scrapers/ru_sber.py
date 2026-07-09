"""Sber scraper."""

from __future__ import annotations

import random
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page, TimeoutError as PWTimeout

from ._base import BaseScraper, _extract_date
from .parsers.sber import (
    SBER_DEEP_PARSE_JS,
    SBER_PARSER_VERSION,
    compose_sber_description,
    sber_id_from_url,
    sber_locations,
)


class SberScraper(BaseScraper):
    """rabota.sber.ru — browser-side deep parser for Sber vacancies."""

    company_name = "Сбер"
    id_prefix = "sber"
    stealth = True  # requires stealth to bypass the JS challenge
    detail_concurrency = 4
    detail_delay_ms = 400
    detail_timeout_ms = 15000
    scroll_delay_ms = 1500
    max_empty_scrolls = 12

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        page.on("console", lambda msg: print(f"  browser: {msg.text}") if msg.text.startswith("[sber-parser]") else None)
        print(
            f"  Сбер parser={SBER_PARSER_VERSION} "
            f"(detail_concurrency={self.detail_concurrency}, detail_timeout_ms={self.detail_timeout_ms})"
        )

        # Empty query → unfiltered full catalog. Sber rejects ?query= with no value
        # (ERR_ABORTED), so we drop the param entirely in that case.
        listing_url = (
            "https://rabota.sber.ru/search/"
            if not query.strip()
            else f"https://rabota.sber.ru/search/?query={quote(query)}"
        )
        try:
            page.goto(listing_url, wait_until="networkidle", timeout=60000)
        except PWTimeout:
            # networkidle can be flaky on long-polling SPAs; fall back to DOM load
            page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        # human-like settle time — anti-bot checks timing of first interaction
        page.wait_for_timeout(3500 + int(random.random() * 1500))

        # sometimes a challenge page shows up — detect and bail early
        html_head = (page.content() or "").lower()[:2000]
        if "проверк" in html_head and ("человек" in html_head or "робот" in html_head):
            print("  ⚠️ Сбер: JS-challenge detected — requires storage_state or headed mode")
            return []

        try:
            raw_items = page.evaluate(SBER_DEEP_PARSE_JS, {
                "limit": self.limit,
                "detailConcurrency": self.detail_concurrency,
                "detailDelayMs": self.detail_delay_ms,
                "detailTimeoutMs": self.detail_timeout_ms,
                "maxEmptyScrolls": self.max_empty_scrolls,
                "scrollDelayMs": self.scroll_delay_ms,
            })
        except Exception as e:
            print(f"  ⚠️ Сбер browser parser failed: {e}")
            return []

        q_lower = query.lower()
        vacancies: List[Dict[str, Any]] = []
        for raw in raw_items or []:
            if len(vacancies) >= self.limit:
                break
            job_url = str(raw.get("url") or "")
            if not job_url:
                continue
            vid = sber_id_from_url(job_url)
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue

            title = str(raw.get("title") or "Sber Vacancy").strip()
            details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
            description = compose_sber_description(details)
            if not description:
                description = " ".join(str(raw.get(k) or "") for k in ("title", "city", "company")).strip()
            clean = " ".join(description.split())
            if q_lower and q_lower not in clean.lower() and q_lower not in title.lower():
                continue

            pub_date = str(raw.get("date") or "").strip() or _extract_date(clean)
            vacancies.append({
                "id": jid,
                "title": title,
                "company": self.company_name,
                "pub_date": pub_date,
                "description": description[:5000],
                "link": job_url,
                "locations": list(sber_locations(raw)),
                "origin_query": query,
            })
            self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
            print(f"  ✓ {title}")

        print(f"  Сбер: собрано {len(vacancies)} вакансий через browser-side parser")
        return vacancies
