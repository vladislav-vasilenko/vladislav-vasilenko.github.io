"""FAANG scrapers (iter 1: Google + Meta; Amazon/Netflix/Apple — TODO)."""

import asyncio
import json
import re
import random
import time
from typing import List, Dict, Any, Set, Optional, Awaitable, Callable
from urllib.parse import quote
from html import unescape
from playwright.sync_api import Page
from pydantic import BaseModel, Field, ValidationError

from ._base import BaseScraper, _scroll_until_stable, _first_non_empty_text
from ._stealth import STEALTH_INIT_JS


class GoogleCareersScraper(BaseScraper):
    """careers.google.com — DOM scraper with Angular hydration wait.

    Google Careers is a Wiz/Angular SPA that renders job cards client-side.
    We must wait for JS hydration before extracting links. Works best with
    storage_state (GOOGLE_STORAGE_STATE env var) for authenticated access.
    Detail pages embed JSON-LD JobPosting — we parse that for structured data.
    """

    company_name = "Google"
    id_prefix = "goog"
    stealth = True

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = (
            "https://www.google.com/about/careers/applications/jobs/results/"
            f"?q={quote(query)}"
        )
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        # Wait for Angular/Wiz hydration — job cards appear late
        page.wait_for_timeout(5000)

        # Google renders job cards as <a> elements with long numeric IDs in the href.
        # We need to wait for these to appear after JS hydration.
        # Try multiple selectors Google has used historically:
        job_link_selectors = [
            "a[href*='/jobs/results/'][href*='-']",     # /jobs/results/12345-slug
            "li[data-id] a",                             # list items with data-id
            "gc-card a[href*='/jobs/']",                  # gc-card components
        ]

        hrefs = []
        for sel in job_link_selectors:
            try:
                found = page.eval_on_selector_all(sel, "els => els.map(e => e.href)")
                if found:
                    hrefs = found
                    print(f"  Google: found {len(found)} links via '{sel}'")
                    break
            except Exception:
                continue

        if not hrefs:
            # Last resort: grab ALL links and filter
            all_hrefs = page.eval_on_selector_all("a", "els => els.map(e => e.href)")
            hrefs = [h for h in all_hrefs if re.search(r"/jobs/results/\d{10,}", h)]
            if hrefs:
                print(f"  Google: found {len(hrefs)} links via full-page scan")

        if not hrefs:
            print("  ⚠️ Google: no job links found — page may not have hydrated. "
                  "Try providing GOOGLE_STORAGE_STATE or running --headed.")
            return []

        # Deduplicate by numeric ID
        id_re = re.compile(r"/jobs/results/(\d{10,})", re.I)
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
        print(f"  Google: {len(links)} unique job links")

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

                # Wait for Angular hydration — the real title and JSON-LD
                # only appear after Wiz renders the detail view.
                try:
                    page.wait_for_selector(
                        "h2[jsname], script[type='application/ld+json']",
                        timeout=8000,
                    )
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                html = page.content()

                # ── JSON-LD extraction (same parser as Meta) ──
                detail = _meta_parse_detail(html)

                title = detail.get("title") or _first_non_empty_text(page, [
                    "h2[jsname]", "h2", "h1",
                ]) or "Google Vacancy"

                # If title is the generic page title, extract from URL slug
                if title in ("Jobs Search Results", "Google Vacancy", "Google Careers"):
                    slug = job_url.rstrip("/").split("/")[-1]
                    # Remove numeric prefix: "142249-machine-learning-engineer" → "machine-learning-engineer"
                    slug_parts = slug.split("-")
                    text_parts = [p for p in slug_parts if not p.isdigit()]
                    if text_parts:
                        title = " ".join(p.capitalize() for p in text_parts)

                full_desc = _build_full_description(detail)

                # If JSON-LD failed, fall back to raw DOM text
                if not full_desc or len(full_desc) < 50:
                    body = _first_non_empty_text(page, [
                        "[jsname='d6wfac']",
                        "main", "article", "body",
                    ])
                    full_desc = " ".join(body.split())

                if q_lower and q_lower not in full_desc.lower() and q_lower not in title.lower():
                    continue

                # ── Locations ──
                locations = []
                try:
                    loc_els = page.locator(
                        "[class*='location' i], [data-field='locations'] span, "
                        "[class*='workplaceType' i]"
                    ).all()
                    for el in loc_els[:10]:
                        t = (el.inner_text() or "").strip()
                        if t and len(t) < 80 and t not in locations:
                            locations.append(t)
                except Exception:
                    pass

                compensation = detail.get("compensation", "")

                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": detail.get("date_posted") or "Recently",
                    "description": full_desc[:5000],
                    "link": job_url,
                    "locations": locations,
                    "compensation": compensation,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies




# Meta detail-page extraction patterns. The detail page is server-rendered and
# embeds a JSON-LD JobPosting object — we read fields directly from it instead
# of waiting for React hydration (5x faster, more reliable).
_RE_META_LD = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)
# The "$X/year to $Y/year + bonus + equity + benefits" span is hydrated late;
# we parse the JSON-form values that are already in the SSR HTML instead.
_RE_META_COMP_MIN = re.compile(
    r'"compensation_amount_minimum"\s*:\s*"\$([0-9,.]+)\\?/\s*(year|hour|month)"',
    re.IGNORECASE,
)
_RE_META_COMP_MAX = re.compile(
    r'"compensation_amount_maximum"\s*:\s*"\$([0-9,.]+)\\?/\s*(year|hour|month)"',
    re.IGNORECASE,
)
# As a secondary pass, if the rendered span has materialised, capture its full text
# (catches the "+ bonus + equity + benefits" suffix).
_RE_META_COMP_SPAN = re.compile(
    r"\$[\d,]+(?:\.\d+)?\s*/\s*(?:year|hour|month)[^<\n]*",
    re.IGNORECASE,
)


def _meta_html_to_text(s: str) -> str:
    """Strip HTML tags + decode entities; collapse internal whitespace."""
    s = unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace(" ", " ")
    # collapse 3+ newlines, keep paragraph breaks
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _meta_parse_detail(html: str) -> Dict[str, Any]:
    """Extract title/description/responsibilities/qualifications/compensation
    from a Meta job-detail HTML page.

    Strategy: prefer the JSON-LD JobPosting block (stable contract, server-rendered);
    compensation is rendered as a span and pulled via regex.
    """
    out: Dict[str, Any] = {
        "title": "",
        "description": "",
        "responsibilities": "",
        "qualifications": "",
        "compensation": "",
        "date_posted": "",
    }

    for raw in _RE_META_LD.findall(html):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        # JSON-LD type can be "JobPosting" or absent on Meta
        if "title" not in obj or "description" not in obj:
            continue
        out["title"] = obj.get("title", "")
        out["description"] = _meta_html_to_text(obj.get("description", ""))
        out["responsibilities"] = _meta_html_to_text(obj.get("responsibilities", ""))
        out["qualifications"] = _meta_html_to_text(obj.get("qualifications", ""))
        out["date_posted"] = obj.get("datePosted", "")
        break

    # Compensation: prefer the rendered span (richest, includes "+ bonus + equity + benefits"),
    # fall back to the JSON-form min/max which is reliably in the SSR HTML.
    span = _RE_META_COMP_SPAN.search(html)
    if span:
        out["compensation"] = span.group().strip()
    else:
        m_min = _RE_META_COMP_MIN.search(html)
        m_max = _RE_META_COMP_MAX.search(html)
        if m_min and m_max:
            unit = m_min.group(2)
            out["compensation"] = f"${m_min.group(1)}/{unit} to ${m_max.group(1)}/{unit}"
        elif m_min:
            out["compensation"] = f"${m_min.group(1)}/{m_min.group(2)}"
    return out


def _build_full_description(parts: Dict[str, Any]) -> str:
    """Concatenate Meta job sections into one readable description."""
    blocks = []
    if parts.get("description"):
        blocks.append(parts["description"])
    if parts.get("responsibilities"):
        blocks.append("Responsibilities:\n" + parts["responsibilities"])
    if parts.get("qualifications"):
        blocks.append("Qualifications:\n" + parts["qualifications"])
    if parts.get("compensation"):
        blocks.append(parts["compensation"])
    return "\n\n".join(blocks)


class MetaVacancy(BaseModel):
    """Validated Meta job record. Catches schema drift early — if Meta renames
    a JSON-LD field, ``description`` (required) becomes empty and validation
    raises instead of writing a half-broken row downstream."""

    id: str = Field(min_length=5)
    title: str = Field(min_length=1)
    company: str = "Meta"
    locations: List[str] = Field(default_factory=list)
    teams: List[str] = Field(default_factory=list)
    sub_teams: List[str] = Field(default_factory=list)
    compensation: str = ""
    description: str = Field(min_length=50)
    link: str = Field(pattern=r"^https://www\.metacareers\.com/jobs/\d+/?$")
    pub_date: str = "Recently"
    origin_query: str = ""


async def _retry_async(
    coro_fn: Callable[[], Awaitable[Any]],
    attempts: int = 3,
    base_delay: float = 0.6,
    label: str = "",
) -> Any:
    """Run ``coro_fn()`` with exponential backoff (0.6s, 1.2s, 2.4s).

    Each attempt is fully independent — the caller is responsible for setting
    up/tearing down per-attempt resources (e.g. a fresh ``Page``) inside the
    coroutine.
    """
    last_err: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return await coro_fn()
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                wait = base_delay * (2 ** i)
                print(f"  ⤳ retry {label} in {wait:.1f}s ({type(e).__name__}: {e})")
                await asyncio.sleep(wait)
    assert last_err is not None
    raise last_err


class MetaCareersScraper(BaseScraper):
    """metacareers.com — full-board scraper with concurrent detail fetching.

    Approach (works around Meta's anti-bot + Relay/SSR quirks):
      1. Navigate to https://www.metacareers.com/jobs and intercept the
         GraphQL response carrying ``job_search_with_featured_jobs.all_jobs`` —
         a single payload covers all ~552 active vacancies (the UI's
         ``?page=N`` is a client-side slice of the same data).
      2. Concurrently fetch each detail page (``detail_concurrency`` parallel
         pages on one ``BrowserContext``); parse the JSON-LD ``JobPosting``
         block embedded in the SSR markup. Avoids waiting for React hydration.
      3. Each detail fetch retries with exponential backoff on transient
         failures; result is validated via :class:`MetaVacancy` before return.

    When ``query`` is empty, returns the full board. When set, filters by
    case-insensitive substring against title/description/teams.
    """

    company_name = "Meta"
    id_prefix = "meta"
    stealth = True

    listing_url = "https://www.metacareers.com/jobs"
    paginated_url_tpl = "https://www.metacareers.com/jobsearch?source=cp_chatbot&page={page}"
    detail_url_tpl = "https://www.metacareers.com/jobs/{job_id}/"

    detail_timeout_ms = 30000
    inter_request_pause_ms = (200, 600)
    detail_concurrency = 5
    detail_attempts = 3

    pagination_fallback_limit = 60

    # ---- Public sync entry point — overrides BaseScraper.fetch_jobs ----

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        if existing_ids is None:
            existing_ids = set()
        print(
            f"🔍 {self.company_name}: запрос '{query}' "
            f"(limit={self.limit}, headless={self.headless}, "
            f"concurrency={self.detail_concurrency})"
        )
        self._emit("source_start", company=self.company_name, query=query, limit=self.limit)
        try:
            result = asyncio.run(self._async_scrape(query, existing_ids))
            self._emit("source_done", company=self.company_name, query=query, count=len(result))
            return result
        except Exception as e:
            print(f"❌ {self.company_name}: ошибка — {e}")
            self._emit("error", company=self.company_name, query=query, message=str(e))
            return []

    # ---- Async core ----

    async def _async_scrape(self, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        from playwright.async_api import async_playwright  # local to avoid hard import in sync paths

        async with async_playwright() as p:
            common_args = [
                "--disable-dev-shm-usage", "--no-sandbox",
                "--disable-gpu", "--disable-software-rasterizer",
            ]
            try:
                browser = await p.chromium.launch(channel="chrome", headless=self.headless, args=common_args)
            except Exception as e:
                print(f"      ⚠️ Системный Chrome недоступен ({e}), используем bundled chromium")
                browser = await p.chromium.launch(headless=self.headless, args=["--disable-gpu"])

            ctx_kwargs = self._context_kwargs()
            context = await browser.new_context(**ctx_kwargs)
            if self.stealth:
                await context.add_init_script(STEALTH_INIT_JS)

            async def block_heavy(route):
                t = route.request.resource_type
                if t in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", block_heavy)

            try:
                raw_jobs = await self._capture_listing_async(context)
                print(f"  Meta: {len(raw_jobs)} вакансий получено из GraphQL")
                self._emit("listing_captured", company=self.company_name, count=len(raw_jobs))
                if not raw_jobs:
                    return []
                results = await self._fetch_details_async(context, raw_jobs, query, existing_ids)
                print(f"  Meta: ✓ {len(results)} вакансий собрано")
                return results
            finally:
                try:
                    await context.close()
                finally:
                    await browser.close()

    async def _capture_listing_async(self, context) -> List[Dict[str, Any]]:
        """Open /jobs, capture the GraphQL listing payload (with pagination fallback)."""
        captured: List[Dict[str, Any]] = []
        page = await context.new_page()

        async def handle_response(resp):
            if "graphql" not in resp.url.lower():
                return
            try:
                body = await resp.text()
            except Exception:
                return
            if "job_search_with_featured_jobs" not in body:
                return
            for line in body.splitlines() or [body]:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                jobs = (
                    obj.get("data", {})
                    .get("job_search_with_featured_jobs", {})
                    .get("all_jobs")
                )
                if jobs:
                    captured.extend(jobs)
                    return

        page.on("response", lambda r: asyncio.create_task(handle_response(r)))
        try:
            await page.goto(self.listing_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)
            for _ in range(30):
                if captured:
                    break
                await page.wait_for_timeout(500)

            by_id = self._dedup_by_id(captured)
            expected = await self._read_total_from_pagination_async(page)
            if expected and len(by_id) < int(expected * 0.9):
                print(
                    f"  ⚠️ Meta: GraphQL gave {len(by_id)} jobs, page header says ~{expected}. "
                    "Falling back to page-by-page walk."
                )
                await self._walk_pagination_async(page, captured, expected)
                by_id = self._dedup_by_id(captured)
            elif expected:
                print(
                    f"  Meta: pagination indicator ~{expected}, GraphQL captured {len(by_id)} unique — within tolerance."
                )
            return list(by_id.values())
        finally:
            await page.close()

    async def _fetch_details_async(
        self, context, raw_jobs: List[Dict[str, Any]], query: str, existing_ids: Set[str],
    ) -> List[Dict[str, Any]]:
        """Concurrent detail fetch + parse + validate. Stops early once cap is met."""
        q_lower = (query or "").strip().lower()
        cap = self.limit if self.limit and self.limit > 0 else len(raw_jobs)

        candidates = [
            r for r in raw_jobs
            if r.get("id") and f"{self.id_prefix}_{r['id']}" not in existing_ids
        ]

        sem = asyncio.Semaphore(self.detail_concurrency)
        results: List[Dict[str, Any]] = []
        idx = 0
        total = len(candidates)
        # Process in chunks of `detail_concurrency` so we can stop early when
        # `cap` is hit (without query, every candidate yields a result).
        while idx < total and len(results) < cap:
            batch = candidates[idx: idx + self.detail_concurrency]
            idx += self.detail_concurrency
            tasks = [self._fetch_one_async(context, raw, query, q_lower, sem) for raw in batch]
            outputs = await asyncio.gather(*tasks, return_exceptions=True)
            for raw, out in zip(batch, outputs):
                if isinstance(out, Exception):
                    print(f"  ⚠️ meta_{raw.get('id')}: {type(out).__name__}: {out}")
                    continue
                if out is None:
                    continue  # query-filtered or validation rejected
                results.append(out)
                self._emit(
                    "vacancy",
                    id=out["id"], title=out["title"], company=self.company_name,
                    link=out["link"], locations=out["locations"], teams=out["teams"],
                    compensation=out["compensation"],
                )
                if len(results) >= cap:
                    break
            print(f"  … {min(idx, total)}/{total} обработано, {len(results)} принято")
        return results

    async def _fetch_one_async(
        self, context, raw: Dict[str, Any], query: str, q_lower: str, sem: asyncio.Semaphore,
    ) -> Optional[Dict[str, Any]]:
        async with sem:
            vid = str(raw.get("id"))
            job_url = self.detail_url_tpl.format(job_id=vid)

            async def attempt() -> Dict[str, Any]:
                page = await context.new_page()
                try:
                    await page.goto(job_url, wait_until="domcontentloaded", timeout=self.detail_timeout_ms)
                    detail = _meta_parse_detail(await page.content())
                    if not detail.get("description"):
                        await page.wait_for_timeout(800)
                        detail = _meta_parse_detail(await page.content())
                    if not detail.get("description"):
                        # Treat as transient — let the retry layer re-attempt.
                        raise RuntimeError("empty description on this attempt")
                    return detail
                finally:
                    await page.close()

            try:
                detail = await _retry_async(
                    attempt, attempts=self.detail_attempts, base_delay=0.6, label=f"meta:{vid}",
                )
            except Exception as e:
                print(f"  ⚠️ {job_url} failed after {self.detail_attempts} attempts: {e}")
                return None

            if not self._matches_query(raw, detail, q_lower):
                return None

            title = detail.get("title") or raw.get("title") or "Meta Vacancy"
            full_desc = _build_full_description(detail) or raw.get("title", "")
            try:
                vac = MetaVacancy(
                    id=f"{self.id_prefix}_{vid}",
                    title=title,
                    locations=list(raw.get("locations") or []),
                    teams=list(raw.get("teams") or []),
                    sub_teams=list(raw.get("sub_teams") or []),
                    compensation=detail.get("compensation", ""),
                    description=full_desc,
                    link=job_url,
                    pub_date=detail.get("date_posted") or "Recently",
                    origin_query=query or "",
                )
            except ValidationError as e:
                # Schema drift — log loudly so it shows up in CI logs.
                print(f"  ⚠️ schema validation failed for meta_{vid}: {e}")
                return None

            lo, hi = self.inter_request_pause_ms
            await asyncio.sleep(random.uniform(lo, hi) / 1000.0)
            return vac.model_dump()

    # ---- Helpers ----

    @staticmethod
    def _dedup_by_id(jobs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for j in jobs:
            jid = str(j.get("id") or "")
            if jid and jid not in out:
                out[jid] = j
        return out

    @staticmethod
    async def _read_total_from_pagination_async(page) -> Optional[int]:
        """Parse 'Page X of Y' from the listing UI (Y * 10 = approx total)."""
        try:
            html = await page.content()
        except Exception:
            return None
        m = re.search(r"Page\s+\d+\s+of\s+(\d+)", html)
        if not m:
            return None
        try:
            return int(m.group(1)) * 10
        except ValueError:
            return None

    async def _walk_pagination_async(self, page, sink: List[Dict[str, Any]], expected: int) -> None:
        """Walk ``?page=N`` until ``sink`` reaches ``expected``, plateaus, or is capped.

        Stops early after 3 consecutive pages add zero new jobs (Meta loops the
        same payload on subsequent navigations).
        """
        last_unique = len(self._dedup_by_id(sink))
        plateau = 0
        for n in range(1, self.pagination_fallback_limit + 1):
            try:
                url = self.paginated_url_tpl.format(page=n)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)
            except Exception as e:
                print(f"  ⚠️ Meta page {n}: {e}")
                continue
            unique = len(self._dedup_by_id(sink))
            print(f"    walk page={n}: cumulative unique jobs={unique}")
            if unique >= expected:
                return
            if unique == last_unique:
                plateau += 1
                if plateau >= 3:
                    print(f"  Meta: plateau hit at {unique} jobs after page {n}; stopping walk.")
                    return
            else:
                plateau = 0
            last_unique = unique

    def _matches_query(self, raw: Dict[str, Any], detail: Dict[str, Any], q_lower: str) -> bool:
        if not q_lower:
            return True
        haystacks = [
            raw.get("title", ""),
            " ".join(raw.get("teams") or []),
            " ".join(raw.get("sub_teams") or []),
            detail.get("title", ""),
            detail.get("description", ""),
            detail.get("responsibilities", ""),
            detail.get("qualifications", ""),
        ]
        return any(q_lower in (h or "").lower() for h in haystacks)
