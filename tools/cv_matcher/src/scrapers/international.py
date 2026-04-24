"""International job site scrapers (API-based and Playwright)."""

import re
import html
import random
from typing import List, Dict, Any, Optional, Set
from urllib.parse import quote
from playwright.sync_api import Page

from ._base import BaseScraper, UA, _scroll_until_stable, _first_non_empty_text, _extract_date

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# RemoteOK (public JSON API)
# ---------------------------------------------------------------------------
class RemoteOKScraper(BaseScraper):
    """https://remoteok.com/api returns the full current feed as JSON.

    No Playwright needed — filter client-side by query.
    """

    company_name = "RemoteOK"
    id_prefix = "remoteok"

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        if existing_ids is None:
            existing_ids = set()
        if requests is None:
            print("❌ RemoteOK: пакет 'requests' не установлен")
            return []
        print(f"🔍 RemoteOK: запрос '{query}' (limit={self.limit})")
        self._emit("source_start", company=self.company_name, query=query, limit=self.limit)
        try:
            res = requests.get(
                "https://remoteok.com/api",
                headers={"User-Agent": UA, "Accept": "application/json"},
                timeout=30,
            )
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            print(f"❌ RemoteOK: {e}")
            self._emit("error", company=self.company_name, query=query, message=str(e))
            return []

        jobs = [d for d in data if isinstance(d, dict) and d.get("id")]
        q_lower = (query or "").lower()

        def matches(j: Dict[str, Any]) -> bool:
            if not q_lower:
                return True
            hay = " ".join([
                str(j.get("position", "")),
                str(j.get("description", "")),
                " ".join(j.get("tags", []) or []),
            ]).lower()
            return q_lower in hay

        vacancies: List[Dict[str, Any]] = []
        for j in jobs:
            if len(vacancies) >= self.limit:
                break
            if not matches(j):
                continue
            jid = f"{self.id_prefix}_{j['id']}"
            if jid in existing_ids:
                continue
            desc = _strip_html(j.get("description", ""))
            link = j.get("url") or j.get("apply_url") or ""
            pos = j.get("position") or j.get("title") or "RemoteOK Vacancy"
            comp = j.get("company") or "RemoteOK"
            vacancies.append({
                "id": jid,
                "title": pos,
                "company": comp,
                "pub_date": (j.get("date") or "")[:10] or "Recently",
                "description": desc[:3500],
                "link": link,
                "origin_query": query,
            })
            self._emit("vacancy", id=jid, title=pos, company=comp, link=link)
        print(f"  RemoteOK: {len(vacancies)} вакансий")
        self._emit("source_done", company=self.company_name, query=query, count=len(vacancies))
        return vacancies


# ---------------------------------------------------------------------------
# We Work Remotely (RSS feed)
# ---------------------------------------------------------------------------
class WeWorkRemotelyScraper(BaseScraper):
    """Parse https://weworkremotely.com/remote-jobs.rss + search page.

    RSS is the stable machine-readable surface; site HTML changes often.
    """

    company_name = "We Work Remotely"
    id_prefix = "wwr"

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        if existing_ids is None:
            existing_ids = set()
        if requests is None:
            print("❌ WWR: пакет 'requests' не установлен")
            return []
        print(f"🔍 WWR: запрос '{query}' (limit={self.limit})")
        self._emit("source_start", company=self.company_name, query=query, limit=self.limit)
        try:
            res = requests.get(
                "https://weworkremotely.com/remote-jobs.rss",
                headers={"User-Agent": UA},
                timeout=30,
            )
            res.raise_for_status()
            xml = res.text
        except Exception as e:
            print(f"❌ WWR: {e}")
            self._emit("error", company=self.company_name, query=query, message=str(e))
            return []

        item_re = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        field_re = lambda tag: re.compile(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", re.DOTALL)  # noqa: E731
        q_lower = (query or "").lower()
        vacancies: List[Dict[str, Any]] = []
        for block in item_re.findall(xml):
            if len(vacancies) >= self.limit:
                break
            def pick(tag: str) -> str:
                m = field_re(tag).search(block)
                return (m.group(1).strip() if m else "")
            title = pick("title")
            link = pick("link")
            desc = _strip_html(pick("description"))
            pub = pick("pubDate")
            if not link or not title:
                continue
            if q_lower and q_lower not in f"{title} {desc}".lower():
                continue
            slug = link.rstrip("/").split("/")[-1]
            jid = f"{self.id_prefix}_{slug}"
            if jid in existing_ids:
                continue
            # Title on WWR is "Company: Role"
            if ":" in title:
                company, role = title.split(":", 1)
                company, role = company.strip(), role.strip()
            else:
                company, role = "WWR", title
            vacancies.append({
                "id": jid,
                "title": role,
                "company": company,
                "pub_date": pub[:16] or "Recently",
                "description": desc[:3500],
                "link": link,
                "origin_query": query,
            })
            self._emit("vacancy", id=jid, title=role, company=company, link=link)
        print(f"  WWR: {len(vacancies)} вакансий")
        self._emit("source_done", company=self.company_name, query=query, count=len(vacancies))
        return vacancies


# ---------------------------------------------------------------------------
# Hacker News "Who is hiring" (Algolia API)
# ---------------------------------------------------------------------------
class HackerNewsHiringScraper(BaseScraper):
    """Latest 'Ask HN: Who is hiring?' thread via Algolia, then expand comments."""

    company_name = "HN Who is hiring"
    id_prefix = "hn"

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        if existing_ids is None:
            existing_ids = set()
        if requests is None:
            print("❌ HN: пакет 'requests' не установлен")
            return []
        print(f"🔍 HN Who-is-hiring: запрос '{query}' (limit={self.limit})")
        self._emit("source_start", company=self.company_name, query=query, limit=self.limit)
        try:
            search = requests.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={"query": "Ask HN: Who is hiring?", "tags": "story,author_whoishiring"},
                headers={"User-Agent": UA},
                timeout=30,
            )
            search.raise_for_status()
            hits = search.json().get("hits", [])
            if not hits:
                return []
            thread_id = hits[0]["objectID"]
            thread = requests.get(
                f"https://hn.algolia.com/api/v1/items/{thread_id}",
                headers={"User-Agent": UA},
                timeout=30,
            )
            thread.raise_for_status()
            data = thread.json()
        except Exception as e:
            print(f"❌ HN: {e}")
            self._emit("error", company=self.company_name, query=query, message=str(e))
            return []

        q_lower = (query or "").lower()
        vacancies: List[Dict[str, Any]] = []
        for c in data.get("children", []) or []:
            if len(vacancies) >= self.limit:
                break
            text = _strip_html(c.get("text") or "")
            if not text or len(text) < 80:
                continue
            if q_lower and q_lower not in text.lower():
                continue
            cid = c.get("id")
            jid = f"{self.id_prefix}_{cid}"
            if jid in existing_ids:
                continue
            head = text.split(".")[0][:160]
            company = head.split("|")[0].strip() or "HN"
            link = f"https://news.ycombinator.com/item?id={cid}"
            vacancies.append({
                "id": jid,
                "title": head,
                "company": company,
                "pub_date": (c.get("created_at") or "")[:10] or "Recently",
                "description": text[:3500],
                "link": link,
                "origin_query": query,
            })
            self._emit("vacancy", id=jid, title=head, company=company, link=link)
        print(f"  HN: {len(vacancies)} вакансий")
        self._emit("source_done", company=self.company_name, query=query, count=len(vacancies))
        return vacancies


# ---------------------------------------------------------------------------
# LinkedIn (requires storage_state — authenticated session)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Indeed (heavy anti-bot — best-effort)
# ---------------------------------------------------------------------------
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
