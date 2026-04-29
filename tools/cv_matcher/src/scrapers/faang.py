"""FAANG scrapers (iter 1: Google + Meta; Amazon/Netflix/Apple — TODO)."""

import json
import re
import random
import time
from typing import List, Dict, Any, Set, Optional
from urllib.parse import quote
from html import unescape
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


class MetaCareersScraper(BaseScraper):
    """metacareers.com — full-board scraper.

    Approach (works around Meta's anti-bot + Relay/SSR quirks):
      1. Navigate to https://www.metacareers.com/jobs and intercept the
         GraphQL response that returns ``job_search_with_featured_jobs.all_jobs``.
         A single response carries all ~552 active vacancies (the UI's
         ``?page=N`` is a client-side slice of the same payload).
      2. For each vacancy, fetch the detail HTML and parse the JSON-LD
         ``JobPosting`` block embedded in the SSR markup. Avoids waiting for
         React hydration.

    When ``query`` is empty, returns the full board. When set, filters by
    case-insensitive substring against title/description/teams.
    """

    company_name = "Meta"
    id_prefix = "meta"
    stealth = True

    listing_url = "https://www.metacareers.com/jobs"
    paginated_url_tpl = "https://www.metacareers.com/jobsearch?source=cp_chatbot&page={page}"
    detail_url_tpl = "https://www.metacareers.com/jobs/{job_id}/"

    # Per-job navigation budget. Detail pages render in ~1–2s with images blocked.
    detail_timeout_ms = 30000
    inter_request_pause_ms = (250, 800)

    # Hard cap on how many `?page=N` walks we'll try as fallback if the single
    # GraphQL response is incomplete. Each page navigation costs ~3s.
    pagination_fallback_limit = 60

    def _capture_listing(self, page: Page) -> List[Dict[str, Any]]:
        """Capture the listing.

        Primary path: navigate to /jobs and intercept the GraphQL response — a
        single payload contains all ~552 active vacancies, so the UI's
        ``?page=N`` paging is a no-op.

        Fallback: if that response doesn't materialise (or returns far fewer
        jobs than the page header advertises), walk ``?page=N`` URLs until we
        either catch the full payload or exhaust ``pagination_fallback_limit``.
        """
        captured: List[Dict[str, Any]] = []

        def on_response(resp):
            if "graphql" not in resp.url.lower():
                return
            try:
                body = resp.text()
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
                    break

        page.on("response", on_response)
        try:
            page.goto(self.listing_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            # Wait up to 15s for the listing payload to land.
            for _ in range(30):
                if captured:
                    break
                page.wait_for_timeout(500)

            by_id = self._dedup_by_id(captured)
            expected = self._read_total_from_pagination(page)
            # Trigger fallback only on a *significant* shortfall (<90% of expected).
            # Meta's "Page X of Y" rounds up — last page is partial, so 553 unique
            # vs 560 (=56*10) is normal and shouldn't kick off a 60-page walk.
            if expected and len(by_id) < int(expected * 0.9):
                print(
                    f"  ⚠️ Meta: GraphQL gave {len(by_id)} jobs, page header says ~{expected}. "
                    "Falling back to page-by-page walk."
                )
                self._walk_pagination(page, captured, expected)
                by_id = self._dedup_by_id(captured)
            elif expected:
                print(
                    f"  Meta: pagination indicator ~{expected}, GraphQL captured {len(by_id)} unique — within tolerance."
                )
            return list(by_id.values())
        finally:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass

    @staticmethod
    def _dedup_by_id(jobs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for j in jobs:
            jid = str(j.get("id") or "")
            if jid and jid not in out:
                out[jid] = j
        return out

    @staticmethod
    def _read_total_from_pagination(page: Page) -> Optional[int]:
        """Parse 'Page X of Y' from the listing UI; multiply by 10 jobs/page.

        Returns ``None`` if the indicator is absent (e.g. site redesign).
        """
        try:
            html = page.content()
        except Exception:
            return None
        m = re.search(r"Page\s+\d+\s+of\s+(\d+)", html)
        if not m:
            return None
        try:
            pages = int(m.group(1))
            # Meta paginates 10/page; round up for the tail.
            return pages * 10
        except ValueError:
            return None

    def _walk_pagination(
        self, page: Page, sink: List[Dict[str, Any]], expected: int,
    ) -> None:
        """Walk ``?page=N`` until ``sink`` reaches ``expected``, plateaus, or is capped.

        The on-response listener keeps appending into ``sink``. We stop early
        if three consecutive pages add zero new jobs (Meta's pagination loops
        the same payload).
        """
        last_unique = len(self._dedup_by_id(sink))
        plateau = 0
        for n in range(1, self.pagination_fallback_limit + 1):
            try:
                url = self.paginated_url_tpl.format(page=n)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
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

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        # Block heavy resources on the listing page too — speeds up cold start.
        def block_heavy(route):
            t = route.request.resource_type
            if t in ("image", "media", "font"):
                route.abort()
            else:
                route.continue_()

        try:
            page.route("**/*", block_heavy)
        except Exception:
            pass

        raw_jobs = self._capture_listing(page)
        print(f"  Meta: {len(raw_jobs)} вакансий получено из GraphQL")
        self._emit("listing_captured", company=self.company_name, count=len(raw_jobs))

        if not raw_jobs:
            return []

        q_lower = (query or "").strip().lower()
        results: List[Dict[str, Any]] = []
        cap = self.limit if self.limit and self.limit > 0 else len(raw_jobs)

        for i, raw in enumerate(raw_jobs):
            if len(results) >= cap:
                break
            vid = str(raw.get("id") or "")
            if not vid:
                continue
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue

            job_url = self.detail_url_tpl.format(job_id=vid)
            detail: Dict[str, Any] = {}
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=self.detail_timeout_ms)
                # Hand the SSR HTML straight to the parser; no hydration wait needed.
                html = page.content()
                detail = _meta_parse_detail(html)
                # Some pages take an extra tick for ld+json to be in DOM; one short retry.
                if not detail.get("description"):
                    page.wait_for_timeout(800)
                    detail = _meta_parse_detail(page.content())
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
                continue

            if not self._matches_query(raw, detail, q_lower):
                continue

            title = detail.get("title") or raw.get("title") or "Meta Vacancy"
            full_desc = _build_full_description(detail) or raw.get("title", "")

            vacancy = {
                "id": jid,
                "title": title,
                "company": self.company_name,
                "locations": list(raw.get("locations") or []),
                "teams": list(raw.get("teams") or []),
                "sub_teams": list(raw.get("sub_teams") or []),
                "compensation": detail.get("compensation", ""),
                "description": full_desc,
                "link": job_url,
                "pub_date": detail.get("date_posted") or "Recently",
                "origin_query": query or "",
            }
            results.append(vacancy)
            self._emit(
                "vacancy",
                id=jid,
                title=title,
                company=self.company_name,
                link=job_url,
                locations=vacancy["locations"],
                teams=vacancy["teams"],
                compensation=vacancy["compensation"],
            )

            if (i + 1) % 25 == 0:
                print(f"  … {len(results)}/{len(raw_jobs)} обработано")

            # gentle jitter — keeps us under any per-IP rate trap
            lo, hi = self.inter_request_pause_ms
            time.sleep(random.uniform(lo, hi) / 1000.0)

        print(f"  Meta: ✓ {len(results)} вакансий собрано")
        return results
