"""FAANG scrapers (iter 1: Google + Meta; Amazon/Netflix/Apple — TODO)."""

import re
import random
from typing import List, Dict, Any, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _scroll_until_stable, _first_non_empty_text


class GoogleCareersScraper(BaseScraper):
    """careers.google.com — authed profile gives richer listings.

    Pass storage_state via env GOOGLE_STORAGE_STATE for authed browsing.
    """

    company_name = "Google"
    id_prefix = "goog"
    stealth = True  # datacenter IPs + aggressive bot detection

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = (
            "https://www.google.com/about/careers/applications/jobs/results/"
            f"?q={quote(query)}"
        )
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)

        link_selector = "a[href*='/jobs/results/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=2500,
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/jobs/results/(\d+)(?:-[a-z0-9\-]+)?", re.I)
        seen, links = set(), []
        for h in hrefs:
            m = id_re.search(h)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            links.append((h.split("?")[0], vid))
        print(f"  Google: {len(links)} ссылок")

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
                page.wait_for_timeout(3000 + int(random.random() * 3000))
                title = _first_non_empty_text(page, [
                    "h2[jsname]", "h2", "h1",
                ]) or "Google Vacancy"
                body = _first_non_empty_text(page, [
                    "[jsname='d6wfac']",
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
                    "pub_date": "Recently",
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


class MetaCareersScraper(BaseScraper):
    """metacareers.com — GraphQL-driven, selectors chosen for stability.

    Pass storage_state via env META_STORAGE_STATE for authed browsing.
    """

    company_name = "Meta"
    id_prefix = "meta"
    stealth = True

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://www.metacareers.com/jobs?q={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)

        try:
            page.get_by_role("button", name=re.compile(r"Accept|Allow all", re.I)).first.click(timeout=1500)
        except Exception:
            pass

        link_selector = "a[href*='/jobs/']"
        _scroll_until_stable(page, max_attempts=12, delay_ms=2500,
                             link_selector=link_selector, target_count=self.limit * 2)

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/jobs/(\d+)(?:/|\?|$)")
        seen, links = set(), []
        for h in hrefs:
            m = id_re.search(h)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            links.append((h.split("?")[0], vid))
        print(f"  Meta: {len(links)} ссылок")

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
                page.wait_for_timeout(3000 + int(random.random() * 3000))
                title = _first_non_empty_text(page, ["h1", "h2"]) or "Meta Vacancy"
                body = _first_non_empty_text(page, [
                    "[data-testid='job-description']",
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
                    "pub_date": "Recently",
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies
