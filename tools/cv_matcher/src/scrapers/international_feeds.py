"""API/feed based international scrapers."""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Set

from ._base import BaseScraper, UA

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
