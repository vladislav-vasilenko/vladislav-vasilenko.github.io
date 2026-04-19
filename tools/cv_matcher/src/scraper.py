"""Job site scrapers built on Playwright.

Each scraper exposes `fetch_jobs(query, existing_ids)` and returns a list of
vacancy dicts with: id, title, company, pub_date, description, link, origin_query.
"""

import re
from typing import List, Dict, Any, Optional, Set
from urllib.parse import quote, urlparse, parse_qs
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PWTimeout


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _launch_browser(p, headless: bool = True) -> Browser:
    """Launch Chromium with Mac-stable flags, falling back to bundled chromium."""
    common_args = [
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-software-rasterizer",
    ]
    try:
        return p.chromium.launch(channel="chrome", headless=headless, args=common_args)
    except Exception as e:
        print(f"      ⚠️ Системный Chrome недоступен ({e}), используем bundled chromium")
        return p.chromium.launch(headless=headless, args=["--disable-gpu"])


def _scroll_until_stable(page: Page, max_attempts: int = 10, delay_ms: int = 1500,
                        show_more_re: Optional[re.Pattern] = None,
                        link_selector: Optional[str] = None,
                        target_count: int = 200) -> int:
    """Scroll page until link count stops growing. Returns final count."""
    last_count = 0
    stale_steps = 0
    for attempt in range(max_attempts):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(delay_ms)

        if show_more_re is not None:
            try:
                btn = page.get_by_role("button", name=show_more_re)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    page.wait_for_timeout(delay_ms)
            except Exception:
                pass

        if link_selector:
            count = page.locator(link_selector).count()
            print(f"    scroll #{attempt+1}: {count} ссылок")
            if count >= target_count:
                return count
            if count == last_count:
                stale_steps += 1
                if stale_steps >= 2:
                    return count
            else:
                stale_steps = 0
            last_count = count
    return last_count


def _safe_text(page: Page, selector: str, timeout: int = 3000) -> str:
    """Get inner_text or empty string; never throws."""
    try:
        loc = page.locator(selector).first
        if loc.count() > 0:
            return loc.inner_text(timeout=timeout).strip()
    except Exception:
        pass
    return ""


def _first_non_empty_text(page: Page, selectors: List[str]) -> str:
    for sel in selectors:
        txt = _safe_text(page, sel)
        if txt:
            return txt
    return ""


def _extract_date(text: str) -> str:
    """Find a Russian month date in free text."""
    months = ("января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря")
    m = re.search(rf"(\d{{1,2}}\s+(?:{months})(?:\s+\d{{4}})?)", text, re.IGNORECASE)
    return m.group(1) if m else "Недавно"


# ---------------------------------------------------------------------------
# Base scraper
# ---------------------------------------------------------------------------
class BaseScraper:
    """Shared lifecycle: open browser, run `_scrape`, close browser.

    Subclasses implement `_scrape(page, query, existing_ids)` which returns
    the list of vacancy dicts. The base class handles Playwright setup so
    browser startup errors are uniform across sites.
    """

    company_name: str = "Unknown"
    id_prefix: str = "x"
    headless: bool = True

    def __init__(self, limit: int = 20, headless: bool = True):
        self.limit = limit
        self.headless = headless

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        if existing_ids is None:
            existing_ids = set()
        print(f"🔍 {self.company_name}: запрос '{query}' (limit={self.limit}, headless={self.headless})")
        try:
            with sync_playwright() as p:
                browser = _launch_browser(p, headless=self.headless)
                context = browser.new_context(user_agent=UA)
                page = context.new_page()
                try:
                    return self._scrape(page, query, existing_ids)
                finally:
                    browser.close()
        except Exception as e:
            print(f"❌ {self.company_name}: ошибка — {e}")
            return []

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Yandex
# ---------------------------------------------------------------------------
class YandexScraper(BaseScraper):
    company_name = "Яндекс"
    id_prefix = "yandex"

    def __init__(self, limit: int = 50, headless: bool = True):
        super().__init__(limit=limit, headless=headless)

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        # `query` here is expected to be either a keyword or a full listing URL.
        if query.startswith("http"):
            listing_url = query
        else:
            listing_url = f"https://yandex.ru/jobs/vacancies?text={quote(query)}"

        parsed = urlparse(listing_url)
        professions = parse_qs(parsed.query).get("professions", [])
        origin_label = ", ".join(professions) if professions else query

        page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        link_selector = "a[href*='/jobs/vacancies/']"
        _scroll_until_stable(
            page,
            max_attempts=12,
            delay_ms=1500,
            show_more_re=re.compile(r"Показать ещё|Показать еще|Загрузить", re.I),
            link_selector=link_selector,
            target_count=self.limit,
        )

        hrefs = page.eval_on_selector_all(
            link_selector, "els => els.map(e => e.href)"
        )
        # Keep only detail-page links (have a slug + id). Filter listing root.
        job_links = []
        seen = set()
        for h in hrefs:
            clean = h.split("?")[0].rstrip("/")
            if clean in seen:
                continue
            if not re.search(r"/jobs/vacancies/[^/]+-\d+$", clean):
                continue
            seen.add(clean)
            job_links.append(clean)

        print(f"  Яндекс: {len(job_links)} ссылок на вакансии")
        vacancies = []
        for idx, job_url in enumerate(job_links[: self.limit]):
            slug = job_url.rstrip("/").split("/")[-1]
            jid = f"{self.id_prefix}_{slug}"
            if jid in existing_ids:
                print(f"  ⚡ Пропуск (кэш): {jid}")
                continue
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)
                title = _first_non_empty_text(page, [
                    "h1.lc-styled-text__text",
                    "main h1",
                    "h1",
                ]) or "Yandex Vacancy"
                body = _first_non_empty_text(page, ["main", "body"])
                clean = " ".join(body.split())
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": origin_label,
                })
                print(f"  [{idx+1}] {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


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

        # Dismiss cookie/consent if present
        try:
            page.get_by_role("button", name=re.compile(r"Принять|OK", re.I)).first.click(timeout=1500)
        except Exception:
            pass

        # Try client-side search so we don't fetch irrelevant vacancies.
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
            target_count=self.limit * 3,  # generous, we filter by query below
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

        # Rank links by query match from link text if we have it.
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
                # Skip if query doesn't appear (reduces off-topic noise).
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

        # VK has a search box — using it narrows results.
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
        # Rabota.x5.ru filters server-side via ?search= (the ?q= param is ignored).
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
                # Drop the trailing "зарплата ..." fragment some titles pick up.
                title = title.split("зарплата")[0].strip() or title
                body = _first_non_empty_text(page, [
                    "[class*='VacancyContent']",
                    "[class*='vacancy-description']",
                    "main",
                    "article",
                    "body",
                ])
                clean = " ".join(body.split())
                # Listing already filters server-side; no body-text filter needed.
                vacancies.append({
                    "id": jid,
                    "title": title,
                    "company": self.company_name,
                    "pub_date": _extract_date(clean),
                    "description": clean[:3500],
                    "link": job_url,
                    "origin_query": query,
                })
                print(f"  ✓ {title}")
            except Exception as e:
                print(f"  ⚠️ {job_url}: {e}")
        return vacancies


# ---------------------------------------------------------------------------
# Backwards-compatible scrapers (kept so cv_matcher.py imports don't break)
# ---------------------------------------------------------------------------
class SberScraper(BaseScraper):
    """Placeholder: rabota.sber.ru uses an anti-bot shield that requires JS
    challenge solving. Kept as no-op for now; previous implementation was broken.
    """

    company_name = "Сбер"
    id_prefix = "sber"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        print("  Сбер: скрейпер отключён (anti-bot shield). Используйте другие источники.")
        return []


class HHScraper(BaseScraper):
    company_name = "HH.ru"
    id_prefix = "hh"

    def __init__(self, limit: int = 50, headless: bool = True):
        super().__init__(limit=limit, headless=headless)

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
                try:
                    page.goto(job_url, wait_until="domcontentloaded", timeout=40000)
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
                    print(f"    [HH] {title} ({company})")
                    page.wait_for_timeout(800)
                except Exception as e:
                    print(f"    ⚠️ {job_url}: {e}")
            page_num += 1
        return vacancies


class OzonScraper(BaseScraper):
    company_name = "Ozon"
    id_prefix = "ozon"

    def __init__(self, limit: int = 30, headless: bool = True):
        super().__init__(limit=limit, headless=headless)

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
                print(f"    [Ozon] {title}")
            except Exception as e:
                print(f"    ⚠️ {job_url}: {e}")
        return vacancies


SCRAPER_REGISTRY = {
    "yandex": YandexScraper,
    "tinkoff": TinkoffScraper,
    "avito": AvitoScraper,
    "vk": VKScraper,
    "x5": X5RetailScraper,
    "hh": HHScraper,
    "ozon": OzonScraper,
    "sber": SberScraper,
}


if __name__ == "__main__":
    import sys, json
    args = sys.argv[1:]
    if not args:
        print("Usage: python scraper.py <site> [query] [--limit N] [--headed]")
        print(f"Sites: {', '.join(SCRAPER_REGISTRY)}")
        sys.exit(1)
    site = args[0]
    query = args[1] if len(args) > 1 and not args[1].startswith("--") else "ML"
    limit = 5
    headless = True
    for i, a in enumerate(args):
        if a == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if a == "--headed":
            headless = False
    cls = SCRAPER_REGISTRY[site]
    scraper = cls(limit=limit, headless=headless)
    jobs = scraper.fetch_jobs(query)
    print(f"\n=== {len(jobs)} вакансий ===")
    for j in jobs[:3]:
        print(json.dumps({k: v for k, v in j.items() if k != "description"}, ensure_ascii=False, indent=2))
