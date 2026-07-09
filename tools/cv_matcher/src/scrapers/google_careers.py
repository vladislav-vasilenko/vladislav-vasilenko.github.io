"""Google Careers scraper."""

from __future__ import annotations

from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper
from .parsers.google import (
    PAGE_SIZE as GOOGLE_PAGE_SIZE,
    TOTAL_IDX as GOOGLE_TOTAL_IDX,
    extract_wiz_data,
    google_html_to_text as _google_html_to_text,
    parse_wiz_record,
)


class GoogleCareersScraper(BaseScraper):
    """careers.google.com — SSR Wiz data payload scraper.

    Google Careers is a Wiz/Angular SPA, but every listing page embeds the
    full job data (title, description, responsibilities, qualifications,
    locations) inside ``AF_initDataCallback`` blocks in the SSR HTML.

    Approach:
      1. Load the listing page with ``?q=...&page=N``.
      2. Extract the ``AF_initDataCallback`` JSON payload — 20 jobs per page,
         each containing complete structured data.
      3. Paginate via ``&page=N`` until all results are collected or limit hit.
      4. No per-job detail page loads needed — 10-50× faster than DOM scraping.
    """

    company_name = "Google"
    id_prefix = "goog"
    stealth = True

    _BASE_URL = "https://www.google.com/about/careers/applications/jobs/results/"
    _DETAIL_URL_TPL = "https://www.google.com/about/careers/applications/jobs/results/{job_id}"
    _HYDRATION_WAIT_MS = 4000

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        vacancies: List[Dict[str, Any]] = []
        page_num = 1
        total_available = None

        while True:
            # Build listing URL
            url = self._BASE_URL + f"?q={quote(query)}&page={page_num}"
            print(f"  Google: loading page {page_num}... ({url[:100]})")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(self._HYDRATION_WAIT_MS)
            except Exception as e:
                print(f"  ⚠️ Google page {page_num}: navigation error — {e}")
                break

            html = page.content()
            wiz_data = extract_wiz_data(html)

            if wiz_data is None:
                print(f"  ⚠️ Google page {page_num}: no Wiz data found in SSR HTML")
                # If page 1 fails, try increasing hydration wait and retry once
                if page_num == 1:
                    page.wait_for_timeout(3000)
                    wiz_data = extract_wiz_data(page.content())
                if wiz_data is None:
                    break

            job_records = wiz_data[0]  # list of job arrays
            if total_available is None and len(wiz_data) > GOOGLE_TOTAL_IDX:
                total_available = wiz_data[GOOGLE_TOTAL_IDX]
                print(f"  Google: {total_available} total results for query '{query}'")

            if not job_records:
                print(f"  Google page {page_num}: empty — done")
                break

            for record in job_records:
                if len(vacancies) >= self.limit:
                    break

                try:
                    parsed = parse_wiz_record(
                        record,
                        query=query,
                        existing_ids=existing_ids,
                        id_prefix=self.id_prefix,
                        company_name=self.company_name,
                        detail_url_tpl=self._DETAIL_URL_TPL,
                    )
                    if parsed:
                        vacancies.append(parsed)
                        self._emit(
                            "vacancy", id=parsed["id"], title=parsed["title"],
                            company=self.company_name, link=parsed["link"],
                        )
                except Exception as e:
                    vid = record[0] if isinstance(record, list) and len(record) > 0 else "?"
                    print(f"  ⚠️ Google record {vid}: {e}")

            print(f"  Google page {page_num}: {len(job_records)} records → {len(vacancies)} total accepted")

            if len(vacancies) >= self.limit:
                break

            # Check if there are more pages
            fetched_so_far = page_num * GOOGLE_PAGE_SIZE
            if total_available and fetched_so_far >= total_available:
                break
            if len(job_records) < GOOGLE_PAGE_SIZE:
                break  # last page was partial

            page_num += 1

        print(f"  Google: ✓ {len(vacancies)} vacancies collected across {page_num} pages")
        return vacancies
