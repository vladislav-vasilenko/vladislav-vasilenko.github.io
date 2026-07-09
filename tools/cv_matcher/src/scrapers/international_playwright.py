"""Playwright-based international scrapers."""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, _first_non_empty_text, _scroll_until_stable


class IndeedScraper(BaseScraper):
    """Indeed global search. Cloudflare Turnstile often blocks headless.

    If blocked, run with `headless=False` once to pass the challenge
    and save storage_state (cookies), then reuse as authed site.
    """

    company_name = "Indeed"
    id_prefix = "indeed"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://www.indeed.com/jobs?q={quote(query)}&sort=date"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        try:
            if page.locator("iframe[src*='challenges.cloudflare']").count() > 0:
                print("  ⚠️ Indeed: Cloudflare challenge detected. Pass storage_state or run headed.")
                return []
        except Exception:
            pass

        link_selector = "a[href*='/viewjob?jk='], a[href*='/rc/clk'], a[data-jk]"
        _scroll_until_stable(page, max_attempts=10, delay_ms=2000,
                             link_selector=link_selector, target_count=self.limit * 2)

        hrefs = page.eval_on_selector_all(
            link_selector,
            "els => els.map(e => ({href: e.href, jk: e.getAttribute('data-jk')}))"
        )
        seen, links = set(), []
        for item in hrefs:
            jk = item.get("jk")
            if not jk:
                m = re.search(r"[?&]jk=([a-z0-9]+)", item.get("href") or "", re.I)
                jk = m.group(1) if m else None
            if not jk or jk in seen:
                continue
            seen.add(jk)
            links.append((f"https://www.indeed.com/viewjob?jk={jk}", jk))
        print(f"  Indeed: {len(links)} ссылок")

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
                page.wait_for_timeout(1500 + int(random.random() * 1500))
                title = _first_non_empty_text(page, [
                    "h1[data-testid='jobsearch-JobInfoHeader-title']",
                    "h1.jobsearch-JobInfoHeader-title",
                    "h1",
                ]) or "Indeed Vacancy"
                company = _first_non_empty_text(page, [
                    "[data-testid='inlineHeader-companyName']",
                    "[data-company-name]",
                    "a[href*='/cmp/']",
                ]) or "Indeed"
                body = _first_non_empty_text(page, [
                    "#jobDescriptionText",
                    "[data-testid='jobsearch-JobComponent-description']",
                    "main",
                ])
                clean = " ".join(body.split())
                if q_lower and q_lower not in clean.lower() and q_lower not in title.lower():
                    continue
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": company,
                    "pub_date": "Recently",
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=company or self.company_name, link=job_url)
                print(f"  ✓ {title} ({company})")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Welcome to the Jungle (was Otta)
# ---------------------------------------------------------------------------
class WelcomeJungleScraper(BaseScraper):
    """https://www.welcometothejungle.com/en/jobs?query=...

    The public search is open without login, but results are rendered by JS.
    """

    company_name = "Welcome to the Jungle"
    id_prefix = "wttj"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://www.welcometothejungle.com/en/jobs?query={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        try:
            page.get_by_role("button", name=re.compile(r"Accept|Agree", re.I)).first.click(timeout=1500)
        except Exception:
            pass

        link_selector = "a[href*='/jobs/']"
        _scroll_until_stable(page, max_attempts=10, delay_ms=1500,
                             link_selector=link_selector, target_count=self.limit * 2)

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/jobs/([a-z0-9\-]+)(?:\?|$|/)", re.I)
        seen, links = set(), []
        for h in hrefs:
            m = id_re.search(h)
            if not m:
                continue
            slug = m.group(1)
            if slug in ("search", "", "apply"):
                continue
            if slug in seen:
                continue
            seen.add(slug)
            links.append((h.split("?")[0], slug))
        print(f"  WTTJ: {len(links)} ссылок")

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
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, ["h1", "[class*='JobTitle' i]"]) or "WTTJ Vacancy"
                company = _first_non_empty_text(page, [
                    "[class*='CompanyName' i]",
                    "a[href*='/companies/']",
                ]) or "WTTJ"
                body = _first_non_empty_text(page, [
                    "[class*='JobDescription' i]",
                    "[data-testid*='job-section' i]",
                    "main",
                ])
                clean = " ".join(body.split())
                if q_lower and q_lower not in clean.lower() and q_lower not in title.lower():
                    continue
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": company,
                    "pub_date": "Recently",
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=company or self.company_name, link=job_url)
                print(f"  ✓ {title} ({company})")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Wellfound (ex-AngelList Talent) — most roles require login
# ---------------------------------------------------------------------------
class WellfoundScraper(BaseScraper):
    """https://wellfound.com/jobs — search page.

    Best-effort: most detail pages require authentication. Pass
    `storage_state_path` after logging in manually via `playwright codegen`.
    """

    company_name = "Wellfound"
    id_prefix = "wellfound"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://wellfound.com/jobs?q={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        link_selector = "a[href*='/jobs/']"
        _scroll_until_stable(page, max_attempts=10, delay_ms=2000,
                             link_selector=link_selector, target_count=self.limit * 2)

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/jobs/(\d+)-([a-z0-9\-]+)", re.I)
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
        print(f"  Wellfound: {len(links)} ссылок")

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
                page.wait_for_timeout(1800 + int(random.random() * 1500))
                if "sign in" in page.content().lower()[:4000] and "description" not in page.content().lower()[:4000]:
                    print(f"  ⚠️ Wellfound: {job_url} требует логин — пропуск")
                    continue
                title = _first_non_empty_text(page, ["h1", "[class*='job-title' i]"]) or "Wellfound Vacancy"
                company = _first_non_empty_text(page, [
                    "[class*='startup-name' i]",
                    "[class*='company-name' i]",
                    "a[href*='/company/']",
                ]) or "Wellfound"
                body = _first_non_empty_text(page, [
                    "[class*='job-description' i]",
                    "main",
                ])
                clean = " ".join(body.split())
                if q_lower and q_lower not in clean.lower() and q_lower not in title.lower():
                    continue
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": company,
                    "pub_date": "Recently",
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=company or self.company_name, link=job_url)
                print(f"  ✓ {title} ({company})")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies
