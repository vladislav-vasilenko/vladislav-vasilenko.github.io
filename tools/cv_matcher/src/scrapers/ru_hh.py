"""HH.ru job-board scraper."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page, TimeoutError as PWTimeout

from ._base import BaseScraper, _safe_text


def _goto_with_retry(page: Page, url: str, *, timeout: int = 60000,
                     attempts: int = 3, base_delay: float = 1.2,
                     wait_until: str = "domcontentloaded") -> bool:
    """Navigate with exponential backoff on Playwright timeouts.

    Returns True if any attempt succeeded. Used for sites whose detail pages
    occasionally hang under sustained load (HH.ru is the canonical example).
    """
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except PWTimeout as e:
            last_err = e
            if i < attempts - 1:
                wait = base_delay * (2 ** i) + random.random() * 0.4
                print(f"    ⤳ retry {url} in {wait:.1f}s (timeout {timeout}ms)")
                time.sleep(wait)
        except Exception as e:
            last_err = e
            break  # non-timeout errors are not transient
    if last_err:
        print(f"    ⚠️ {url}: {last_err}")
    return False


class HHScraper(BaseScraper):
    company_name = "HH.ru"
    id_prefix = "hh"

    def __init__(self, limit: int = 50, headless: bool = True, **kwargs):
        super().__init__(limit=limit, headless=headless, **kwargs)

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        vacancies = []
        base_url = "https://hh.ru/search/vacancy"
        page_num = 0
        while len(vacancies) < self.limit and page_num < 4:
            url = f"{base_url}?text={quote(query)}&area=1&page={page_num}"
            print(f"  HH: страница {page_num+1}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
            except PWTimeout:
                break

            items = page.locator('a[data-qa="serp-item__title"]').all()
            if not items:
                break
            urls = []
            for el in items:
                href = el.get_attribute("href")
                if href:
                    urls.append(href.split("?")[0])

            for job_url in urls:
                if len(vacancies) >= self.limit:
                    break
                vid = job_url.rstrip("/").split("/")[-1]
                jid = f"{self.id_prefix}_{vid}"
                if jid in existing_ids:
                    continue
                # 60s timeout + 3 attempts with backoff. HH detail pages
                # frequently hang on the first hit under Actions network load.
                if not _goto_with_retry(page, job_url, timeout=60000, attempts=3):
                    continue
                try:
                    title = _safe_text(page, 'h1[data-qa="vacancy-title"]')
                    company = _safe_text(page, 'a[data-qa="vacancy-company-name"]')
                    desc = _safe_text(page, 'div[data-qa="vacancy-description"]')
                    if not title:
                        continue
                    vacancies.append({
                        "id": jid,
                        "title": title,
                        "company": company or "HH.ru",
                        "pub_date": "Recently",
                        "description": desc[:4000],
                        "link": job_url,
                        "origin_query": query,
                    })
                    self._emit("vacancy", id=jid, title=title, company=company or self.company_name, link=job_url)
                    print(f"    [HH] {title} ({company})")
                except Exception as e:
                    print(f"    ⚠️ {job_url}: {e}")
                # Inter-request jitter (0.6-1.4s) — keeps HH's per-IP rate-limit happy.
                page.wait_for_timeout(int(600 + random.random() * 800))
            page_num += 1
        return vacancies


# ---------------------------------------------------------------------------
# Ozon
# ---------------------------------------------------------------------------
