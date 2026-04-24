"""Base scraper class and shared browser utilities."""

import os
import re
import random
from typing import List, Dict, Any, Optional, Set, Callable
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PWTimeout  # noqa: F401


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


class BaseScraper:
    """Shared lifecycle: open browser, run `_scrape`, close browser.

    Subclasses implement `_scrape(page, query, existing_ids)` which returns
    the list of vacancy dicts. The base class handles Playwright setup so
    browser startup errors are uniform across sites.

    `storage_state_path` points to a Playwright storage_state JSON exported
    from an authenticated browser (cookies + localStorage). Used for sites
    that gate job search behind login (LinkedIn, Wellfound, …). Generate via:
        playwright codegen --save-storage=linkedin_state.json https://linkedin.com
    """

    company_name: str = "Unknown"
    id_prefix: str = "x"
    headless: bool = True
    storage_state_path: Optional[str] = None
    event_sink: Optional[Callable[[Dict[str, Any]], None]] = None

    def __init__(self, limit: int = 20, headless: bool = True,
                 storage_state_path: Optional[str] = None,
                 event_sink: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.limit = limit
        self.headless = headless
        if storage_state_path:
            self.storage_state_path = storage_state_path
        if event_sink is not None:
            self.event_sink = event_sink

    def _emit(self, event_type: str, **data: Any) -> None:
        """Push a live event through the optional event_sink (no-op if unset)."""
        if self.event_sink is None:
            return
        try:
            payload = {"type": event_type, "source": self.id_prefix, **data}
            self.event_sink(payload)
        except Exception as e:
            print(f"  ⚠️ event_sink error: {e}")

    def _context_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"user_agent": UA}
        if self.storage_state_path and os.path.exists(self.storage_state_path):
            kwargs["storage_state"] = self.storage_state_path
            print(f"  🔐 {self.company_name}: использую storage_state → {self.storage_state_path}")
        elif self.storage_state_path:
            print(f"  ⚠️ {self.company_name}: storage_state '{self.storage_state_path}' не найден — иду без авторизации")
        return kwargs

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        if existing_ids is None:
            existing_ids = set()
        print(f"🔍 {self.company_name}: запрос '{query}' (limit={self.limit}, headless={self.headless})")
        self._emit("source_start", company=self.company_name, query=query, limit=self.limit)
        try:
            with sync_playwright() as p:
                browser = _launch_browser(p, headless=self.headless)
                context = browser.new_context(**self._context_kwargs())
                page = context.new_page()
                try:
                    result = self._scrape(page, query, existing_ids)
                    self._emit("source_done", company=self.company_name, query=query, count=len(result))
                    return result
                finally:
                    browser.close()
        except Exception as e:
            print(f"❌ {self.company_name}: ошибка — {e}")
            self._emit("error", company=self.company_name, query=query, message=str(e))
            return []

    def _scrape(self, page: Page, query: str, existing_ids: Set[str]) -> List[Dict[str, Any]]:
        raise NotImplementedError
