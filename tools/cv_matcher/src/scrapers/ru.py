"""Russian job site scrapers."""

import re
from typing import List, Dict, Any, Set
from urllib.parse import quote, urlparse, parse_qs
from playwright.sync_api import Page, TimeoutError as PWTimeout

from ._base import BaseScraper, _scroll_until_stable, _safe_text, _first_non_empty_text, _extract_date


# ---------------------------------------------------------------------------
# Yandex
# ---------------------------------------------------------------------------
class YandexScraper(BaseScraper):
    company_name = "Яндекс"
    id_prefix = "yandex"

    def __init__(self, limit: int = 50, headless: bool = True, **kwargs):
        super().__init__(limit=limit, headless=headless, **kwargs)

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
                self._emit("vacancy", id=jid, title=title, company=self.company_name, link=job_url)
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
# Сбер (placeholder — anti-bot shield)
# ---------------------------------------------------------------------------
class SberScraper(BaseScraper):
    """Placeholder: rabota.sber.ru uses an anti-bot shield that requires JS
    challenge solving. Kept as no-op for now."""

    company_name = "Сбер"
    id_prefix = "sber"

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        print("  Сбер: скрейпер отключён (anti-bot shield). Используйте другие источники.")
        return []


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
                    self._emit("vacancy", id=jid, title=title, company=company or self.company_name, link=job_url)
                    print(f"    [HH] {title} ({company})")
                    page.wait_for_timeout(800)
                except Exception as e:
                    print(f"    ⚠️ {job_url}: {e}")
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
