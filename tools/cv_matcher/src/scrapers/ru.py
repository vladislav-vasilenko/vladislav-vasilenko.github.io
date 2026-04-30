"""Russian job site scrapers."""

import json
import random
import re
import time
from typing import List, Dict, Any, Set
from urllib.parse import quote, urlparse, parse_qs
from playwright.sync_api import Page, TimeoutError as PWTimeout

from ._base import BaseScraper, _scroll_until_stable, _safe_text, _first_non_empty_text, _extract_date


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


# ---------------------------------------------------------------------------
# Yandex
# ---------------------------------------------------------------------------
# Yandex API returns group/service names with NBSP and minor variants (e.g.
# "Плюс Фантех" vs "Плюс и Фантех") — normalise to merge.
_YANDEX_NAME_ALIASES = {
    "Плюс Фантех": "Плюс и Фантех",
}


def _strip_html(s: str) -> str:
    """Remove inline HTML tags from a Yandex description block."""
    if not s:
        return s
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</?(?:p|div|li|ul|ol)[^>]*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def fetch_yandex_detail(page, slug: str) -> Dict[str, str]:
    """Pull full description blocks from the Yandex detail endpoint.

    Returns a dict with raw section strings (HTML stripped). Caller composes
    the final `description` text. Returns empty dict on failure.
    """
    if not slug:
        return {}
    url = f"https://yandex.ru/jobs/api/publications/{slug}"
    try:
        resp = page.request.get(url, timeout=20000)
        if not resp.ok:
            return {}
        d = resp.json()
    except Exception:
        return {}
    return {
        "description": _strip_html(d.get("description") or ""),
        "duties": _strip_html(d.get("duties") or ""),
        "key_qualifications": _strip_html(d.get("key_qualifications") or ""),
        "additional_requirements": _strip_html(d.get("additional_requirements") or ""),
        "conditions": _strip_html(d.get("conditions") or ""),
        "our_team": _strip_html(d.get("our_team") or ""),
        "tech_stack": _strip_html(d.get("tech_stack") or ""),
    }


def compose_yandex_description(short_summary: str, profession: str, detail: Dict[str, str]) -> str:
    """Combine listing+detail data into one searchable description block."""
    parts: List[str] = []
    if short_summary:
        parts.append(short_summary)
    if detail.get("description") and detail["description"] != short_summary:
        parts.append(detail["description"])
    if detail.get("our_team"):
        parts.append(f"Наша команда:\n{detail['our_team']}")
    if detail.get("duties"):
        parts.append(f"Обязанности:\n{detail['duties']}")
    if detail.get("key_qualifications"):
        parts.append(f"Требования:\n{detail['key_qualifications']}")
    if detail.get("additional_requirements"):
        parts.append(f"Будет плюсом:\n{detail['additional_requirements']}")
    if detail.get("conditions"):
        parts.append(f"Условия:\n{detail['conditions']}")
    if detail.get("tech_stack"):
        parts.append(f"Стек: {detail['tech_stack']}")
    if profession:
        parts.append(f"Профессия: {profession}")
    return "\n\n".join(parts)


def _normalize_yandex_name(s: str) -> str:
    if not s:
        return s
    # Yandex API occasionally returns literal `\uXXXX` escape sequences
    # (6 ASCII chars) instead of the real codepoint — decode those first.
    if "\\u" in s:
        s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    cleaned = re.sub(r"\s+", " ", s).strip()
    return _YANDEX_NAME_ALIASES.get(cleaned, cleaned)


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


# ---------------------------------------------------------------------------
# Tinkoff / T-Bank
# ---------------------------------------------------------------------------
class TinkoffScraper(BaseScraper):
    company_name = "Т-Банк"
    id_prefix = "tinkoff"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = "https://www.tbank.ru/career/vacancies/it/"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        try:
            page.get_by_role("button", name=re.compile(r"Принять|OK", re.I)).first.click(timeout=1500)
        except Exception:
            pass

        try:
            search_box = page.locator("input[type='search'], input[placeholder*='Поиск']").first
            if search_box.count() > 0:
                search_box.fill(query)
                page.wait_for_timeout(2000)
        except Exception:
            pass

        link_selector = "a[href*='/career/it/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=15,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать ещё|Показать еще|Загрузить", re.I),
            link_selector=link_selector,
            target_count=self.limit * 3,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        seen, links = set(), []
        uuid_re = re.compile(r"/([0-9a-f\-]{32,})/?$", re.I)
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            if clean in seen or not uuid_re.search(clean):
                continue
            seen.add(clean)
            links.append(clean)
        print(f"  Т-Банк: {len(links)} ссылок")

        q_lower = query.lower()
        if q_lower:
            def score(u):
                slug = u.rstrip("/").split("/")[-2]
                return -slug.lower().count(q_lower[:3])
            links.sort(key=score)

        vacancies = []
        for job_url in links:
            if len(vacancies) >= self.limit:
                break
            uid = uuid_re.search(job_url).group(1)
            jid = f"{self.id_prefix}_{uid}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск: {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, ["h1", "[data-test*='title']"]) or "T-Bank Vacancy"
                body = _first_non_empty_text(page, [
                    "[data-test*='vacancy']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                if query and q_lower not in clean.lower() and q_lower not in title.lower():
                    continue
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Avito
# ---------------------------------------------------------------------------
class AvitoScraper(BaseScraper):
    company_name = "Avito"
    id_prefix = "avito"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://career.avito.com/vacancies/?q={quote(query)}&action=filter"
        page.goto(listing_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        link_selector = "a[href*='/vacancies/']"
        _scroll_until_stable(
            page,
            max_attempts=10,
            delay_ms=1500,
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancies/[^/]+/(\d+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            if not clean.startswith("http"):
                clean = f"https://career.avito.com{clean}"
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  Avito: {len(links)} ссылок")

        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск: {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, ["h1"]) or "Avito Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='Vacancy_description']",
                    "[class*='vacancy-description']",
                    "article",
                    "main",
                    "body",
                ])
                clean = " ".join(body.split())
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# VK
# ---------------------------------------------------------------------------
class VKScraper(BaseScraper):
    company_name = "VK"
    id_prefix = "vk"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = "https://team.vk.company/vacancy/"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        try:
            search_box = page.locator(
                "input[type='search'], input[placeholder*='Поиск'], input[placeholder*='Найти']"
            ).first
            if search_box.count() > 0:
                search_box.fill(query)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2500)
        except Exception:
            pass

        link_selector = "a[href*='/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/(\d+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  VK: {len(links)} ссылок")

        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск: {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, ["h1", "[class*='VacancyHeader']"]) or "VK Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='VacancyContent']",
                    "[class*='vacancy-content']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                if query and query.lower() not in clean.lower() and query.lower() not in title.lower():
                    continue
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# X5 Retail
# ---------------------------------------------------------------------------
class X5RetailScraper(BaseScraper):
    company_name = "X5 Retail"
    id_prefix = "x5"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://rabota.x5.ru/vacancies?search={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        link_selector = "a[href*='/vacancies/']"
        _scroll_until_stable(
            page,
            max_attempts=10,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Загрузить", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancies/([A-Za-z0-9\-]{8,})/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  X5: {len(links)} ссылок")

        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск: {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, [
                    "h1",
                    "[class*='vacancy-title' i]",
                    "[class*='VacancyTitle' i]",
                    "[class*='title' i]",
                ]) or "X5 Vacancy"
                title = title.split("зарплата")[0].strip() or title
                body = _first_non_empty_text(page, [
                    "[class*='VacancyContent']",
                    "[class*='vacancy-description']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Wildberries Tech
# ---------------------------------------------------------------------------
class WildberriesTechScraper(BaseScraper):
    """career.wb.ru — полнотекстовый поиск через URL-фильтр."""

    company_name = "Wildberries Tech"
    id_prefix = "wb"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://career.wb.ru/vacancies?search={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        link_selector = "a[href*='/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Загрузить|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/([A-Za-z0-9\-_]+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  Wildberries: {len(links)} ссылок")

        q_lower = query.lower()
        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1200)
                title = _first_non_empty_text(page, ["h1", "[class*='vacancy-title' i]"]) or "Wildberries Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='VacancyContent']",
                    "[class*='vacancy-description' i]",
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
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# МТС
# ---------------------------------------------------------------------------
class MTSScraper(BaseScraper):
    """job.mts.ru — публичная выдача вакансий с поиском по query-param."""

    company_name = "МТС"
    id_prefix = "mts"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://job.mts.ru/vacancy?search={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        link_selector = "a[href*='/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Загрузить|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/([A-Za-z0-9\-_]+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  МТС: {len(links)} ссылок")

        q_lower = query.lower()
        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1200)
                title = _first_non_empty_text(page, ["h1", "[class*='vacancy-header' i]"]) or "MTS Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='vacancy-content' i]",
                    "[class*='description' i]",
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
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Альфа-Банк
# ---------------------------------------------------------------------------
class AlfaScraper(BaseScraper):
    """jobs.alfabank.ru — основной карьерный портал Альфы."""

    company_name = "Альфа-Банк"
    id_prefix = "alfa"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        listing_url = f"https://jobs.alfabank.ru/vacancy?search={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        try:
            page.get_by_role("button", name=re.compile(r"Принять|Accept|OK", re.I)).first.click(timeout=1500)
        except Exception:
            pass

        link_selector = "a[href*='/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать|Загрузить|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/([A-Za-z0-9\-_]+)/?$")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  Альфа: {len(links)} ссылок")

        q_lower = query.lower()
        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1200)
                title = _first_non_empty_text(page, ["h1", "[class*='vacancy-title' i]"]) or "Alfa Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='vacancy-content' i]",
                    "[class*='description' i]",
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
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Сбер (stealth-enabled — requires stealth=True to pass anti-bot)
# ---------------------------------------------------------------------------
class SberScraper(BaseScraper):
    """rabota.sber.ru — карьерный портал Сбера. Без stealth upload падает в JS-challenge."""

    company_name = "Сбер"
    id_prefix = "sber"
    stealth = True  # requires stealth to bypass the JS challenge

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        import random
        listing_url = f"https://rabota.sber.ru/search/vacancy?text={quote(query)}"
        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        # human-like settle time — anti-bot checks timing of first interaction
        page.wait_for_timeout(3500 + int(random.random() * 1500))

        # sometimes a challenge page shows up — detect and bail early
        html_head = (page.content() or "").lower()[:2000]
        if "проверк" in html_head and ("человек" in html_head or "робот" in html_head):
            print("  ⚠️ Сбер: JS-challenge detected — requires storage_state or headed mode")
            return []

        link_selector = "a[href*='/vacancy/'], a[href*='/search/vacancy/']"
        _scroll_until_stable(
            page,
            max_attempts=10,
            delay_ms=1800,
            show_more_re=re.compile(r"Показать|Загрузить|Ещё|Еще", re.I),
            link_selector=link_selector,
            target_count=self.limit * 2,
        )

        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        id_re = re.compile(r"/vacancy/([A-Za-z0-9\-_]+)(?:/|$|\?)")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            m = id_re.search(clean)
            if not m or clean in seen:
                continue
            seen.add(clean)
            links.append((clean, m.group(1)))
        print(f"  Сбер: {len(links)} ссылок")

        q_lower = query.lower()
        vacancies = []
        for job_url, vid in links:
            if len(vacancies) >= self.limit:
                break
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                # jittered pacing — Sber rate-limits bursts
                page.wait_for_timeout(1500 + int(random.random() * 2000))
                title = _first_non_empty_text(page, [
                    "h1",
                    "[class*='vacancy-title' i]",
                    "[data-qa*='title']",
                ]) or "Sber Vacancy"
                body = _first_non_empty_text(page, [
                    "[class*='vacancy-description' i]",
                    "[data-qa*='description']",
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
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# HH.ru
# ---------------------------------------------------------------------------
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
class OzonScraper(BaseScraper):
    company_name = "Ozon"
    id_prefix = "ozon"

    def __init__(self, limit: int = 30, headless: bool = True, **kwargs):
        super().__init__(limit=limit, headless=headless, **kwargs)

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        url = f"https://career.ozon.ru/vacancies/?query={quote(query)}&city=Москва"
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        link_selector = 'a[href*="/vacancy/"]'
        hrefs = page.eval_on_selector_all(link_selector, "els => els.map(e => e.href)")
        seen, links = set(), []
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            if "/vacancy/" not in clean or clean in seen:
                continue
            seen.add(clean)
            links.append(clean)
        print(f"  Ozon: {len(links)} ссылок")
        vacancies = []
        for job_url in links:
            if len(vacancies) >= self.limit:
                break
            vid = job_url.rstrip("/").split("/")[-1]
            jid = f"{self.id_prefix}_{vid}"
            if jid in existing_ids:
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _safe_text(page, "h1") or "Ozon Vacancy"
                desc = _first_non_empty_text(page, [
                    'div[class*="vacancy-description"]',
                    'div[class*="VacancyDescription"]',
                    "main",
                    "body",
                ])
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": "Ozon",
                    "pub_date": "Recently",
                    "description": desc[:4000],
                    "link": job_url,
                    "origin_query": query,
                })
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
                print(f"    [Ozon] {title}")
            except Exception as e:
                print(f"    ⚠️ {job_url}: {e}")
        return vacancies
