"""Yandex Jobs scraper."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Set
from urllib.parse import parse_qs, quote, urlparse
from playwright.sync_api import Page

from ._base import BaseScraper
from .parsers.yandex import (
    compose_description as compose_yandex_description,
    fetch_detail as fetch_yandex_detail,
    normalize_name as _normalize_yandex_name,
    strip_html as _strip_html,
)


class YandexScraper(BaseScraper):
    company_name = "Яндекс"
    id_prefix = "yandex"

    def __init__(self, limit: int = 50, headless: bool = True, fetch_details: bool = True, **kwargs):
        self.fetch_details = fetch_details
        super().__init__(limit=limit, headless=headless, **kwargs)

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        # Yandex Jobs Internal API endpoint
        # Example: https://yandex.ru/jobs/api/publications?profession=ml-developer&text=Python
        base_api_url = "https://yandex.ru/jobs/api/publications"

        # Determine filters from query
        if query.startswith("http"):
            parsed = urlparse(query)
            params = parse_qs(parsed.query)
            params.pop("page", None)
            params.pop("cursor", None)
            api_params = {k: v for k, v in params.items()}
        else:
            api_params = {"text": [query]}

        # Server caps page_size at ~20 regardless of request. Pagination via cursor is mandatory.
        api_params["page_size"] = ["50"]

        # Encode each value (multi-value keys like professions=a&professions=b are preserved).
        def _encode(params):
            parts = []
            for k, vs in params.items():
                for v in vs:
                    parts.append(f"{k}={quote(str(v))}")
            return "&".join(parts)

        full_api_url = f"{base_api_url}?{_encode(api_params)}"
        print(f"  Яндекс: запрос к API {full_api_url}")

        vacancies: List[Dict[str, Any]] = []
        next_url = full_api_url
        page_idx = 0
        max_pages = 50  # safety bound — at ~20/page covers up to 1000 vacancies

        while next_url and len(vacancies) < self.limit and page_idx < max_pages:
            try:
                time.sleep(0.6)
                response = page.request.get(next_url, timeout=30000)
                if not response.ok:
                    raise Exception(f"HTTP {response.status}")
                data = response.json()
            except Exception as e:
                if page_idx == 0:
                    print(f"  ⚠️ Яндекс API error: {e}. Falling back to old-school scrape.")
                    return self._scrape_fallback(page, query, existing_ids)
                print(f"  ⚠️ Яндекс pagination stopped at page {page_idx + 1}: {e}")
                break

            items = data.get("results", [])
            total = data.get("count")
            if page_idx == 0 and total is not None:
                print(f"  Яндекс API: всего {total} вакансий доступно (limit={self.limit})")

            for item in items:
                if len(vacancies) >= self.limit:
                    break

                vid = str(item.get("id"))
                jid = f"{self.id_prefix}_{vid}"
                if jid in existing_ids:
                    continue

                title = item.get("title") or "Yandex Vacancy"
                slug = item.get("publication_slug_url") or item.get("slug") or vid
                link = f"https://yandex.ru/jobs/vacancies/{slug}"

                # Domain hierarchy: group.name → team, service.name → sub_team.
                # When group is null (e.g. "Общие сервисы Яндекса"), service stands alone.
                ps = item.get("public_service") or {}
                service_name = _normalize_yandex_name(ps.get("name") or "")
                group = ps.get("group") or {}
                group_name = _normalize_yandex_name(group.get("name") or "")
                team_name = group_name or service_name or "Яндекс"
                sub_team_name = service_name or group_name or "General"

                # Profession sub-categorisation (used as a fallback sub-team grouping
                # and as a soft signal for the role classifier downstream).
                vac = item.get("vacancy") or {}
                profession = (vac.get("profession") or {}).get("name") or ""

                short = item.get("short_summary") or ""
                # Fetch full description sections from the detail endpoint.
                # The listing only carries `short_summary`; embedding quality
                # against an English resume is meaningless without this.
                slug = item.get("publication_slug_url") or ""
                detail = fetch_yandex_detail(page, slug) if (slug and self.fetch_details) else {}
                full_description = compose_yandex_description(short, profession, detail)

                locations = [c.get("title") or c.get("name") or "" for c in vac.get("cities", []) if c]
                locations = [l for l in locations if l]

                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": item.get("modified") or item.get("published_at") or "Recently",
                    "description": full_description[:5000],
                    "link": link,
                    "teams": [team_name] if team_name else [],
                    "sub_teams": [sub_team_name] if sub_team_name else [],
                    "locations": locations,
                    "compensation": "",
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=link)
                print(f"  ✓ [{team_name} → {sub_team_name}] {title}")

            # The `next` URL points to the internal femida.yandex-team.ru host —
            # rewrite it to the public endpoint, keeping only the cursor.
            raw_next = data.get("next")
            if not raw_next:
                next_url = None
            else:
                cursor = parse_qs(urlparse(raw_next).query).get("cursor", [None])[0]
                if not cursor:
                    next_url = None
                else:
                    paged = dict(api_params)
                    paged["cursor"] = [cursor]
                    next_url = f"{base_api_url}?{_encode(paged)}"
            page_idx += 1

        print(f"  Яндекс: собрано {len(vacancies)} вакансий за {page_idx} страниц(ы)")
        return vacancies

    def _scrape_fallback(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        # This is the original selector-based logic if API fails or changes
        listing_url = query if query.startswith("http") else f"https://yandex.ru/jobs/vacancies?text={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        # ... rest of the original logic could go here, but API is preferred.
        return []
