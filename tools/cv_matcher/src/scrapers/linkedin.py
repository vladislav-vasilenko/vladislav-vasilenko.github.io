"""LinkedIn job scraper."""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _extract_date, _first_non_empty_text, _scroll_until_stable


class LinkedInScraper(BaseScraper):
    """Search LinkedIn jobs under an authenticated session.

    Generate auth state once:
        playwright codegen --save-storage=linkedin_state.json https://www.linkedin.com
    After login completes, close the window; the JSON has your cookies.

    Without storage_state LinkedIn shows the guest page (few results, no detail).
    Pass `storage_state_path='linkedin_state.json'` via LinkedInScraper(...) or
    via the LINKEDIN_STORAGE_STATE env var (checked by cv_matcher.py plan).

    Human-like pacing is enforced — LinkedIn bans aggressive parsers quickly.
    """

    company_name = "LinkedIn"
    id_prefix = "linkedin"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://www.linkedin.com/jobs/search/?keywords={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)

        link_selector = "a[href*='/jobs/view/'], a[href*='/jobs-guest/']"
        _scroll_until_stable(
            page,
            max_attempts=14,
            delay_ms=2500,
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/jobs/view/(\d+)|currentJobId=(\d+)|/jobPosting/(\d+)")
        seen, links = set(), []
        for h in hrefs:
            m = id_re.search(h)
            if not m:
                continue
            jid_raw = next(g for g in m.groups() if g)
            if jid_raw in seen:
                continue
            seen.add(jid_raw)
            canonical = f"https://www.linkedin.com/jobs/view/{jid_raw}/"
            links.append((canonical, jid_raw))
        print(f"  LinkedIn: {len(links)} ссылок")

        q_lower = query.lower()
        vacancies: List[Dict[str, Any]] = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(3000 + int(random.random() * 4000))
                title = _first_non_empty_text(page, [
                    "h1.top-card-layout__title",
                    "h1.job-details-jobs-unified-top-card__job-title",
                    "h1",
                ]) or "LinkedIn Vacancy"
                company = _first_non_empty_text(page, [
                    "a.topcard__org-name-link",
                    "a.job-details-jobs-unified-top-card__company-name",
                    "[class*='company-name' i]",
                ]) or "LinkedIn"
                try:
                    page.get_by_role("button", name=re.compile(r"See more|Показать", re.I)).first.click(timeout=1200)
                    page.wait_for_timeout(400)
                except Exception:
                    pass
                body = _first_non_empty_text(page, [
                    "div.show-more-less-html__markup",
                    "div.jobs-description__content",
                    "[class*='job-details' i]",
                    "main",
                ])
                clean = " ".join(body.split())
                if q_lower and q_lower not in clean.lower() and q_lower not in title.lower():
                    continue
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": company,
                    "pub_date": _extract_date(clean) if re.search(r"[А-Яа-я]", clean) else "Recently",
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=company or self.company_name, link=job_url)
                print(f"  ✓ {title} ({company})")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies
