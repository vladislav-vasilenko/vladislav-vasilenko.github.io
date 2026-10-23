"""Import extension JSON or extract public HTML without scraping forms/navigation."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs, parse_qsl, urlencode
from bs4 import BeautifulSoup


def identity(link, base=""):
    url = urlsplit(urljoin(base, link))
    if url.scheme != "https":
        return None
    host, path = url.hostname, url.path
    match = None
    prefix = "board"
    if host in ('linkedin.com','www.linkedin.com'):
        if url.netloc not in ('linkedin.com','www.linkedin.com'): return None
        from .linkedin_workspace import linkedin_url
        try: canonical = linkedin_url(url.geturl(), 'job')
        except ValueError: return None
        return {'id':'linkedin_'+canonical.rstrip('/').split('/')[-1], 'link':canonical}
    if host == "career.avito.com":
        match, prefix = re.fullmatch(r"/vacancies/[^/]+/(\d+)/?", path), "avito"
    elif host == "ozon.tech":
        match, prefix = re.fullmatch(r"/vacancies/([\da-f-]{36}|\d+)(?:-[^/]*)?/?", path), "ozon"
    elif host == "career.ozon.ru":
        rid = parse_qs(url.query).get("id", [None])[0]
        match = re.search(r"-(\d+)/?$", path)
        if rid and "/vacancy" in path:
            return {"id": f"ozon_{rid}", "link": urlunsplit(url._replace(fragment=""))}
        prefix = "ozon"
    elif host == "hh.ru" or (host or "").endswith(".hh.ru"):
        match, prefix = re.fullmatch(r"/vacancy/(\d+)/?", path), "hh"
    elif host=='www.metacareers.com':
        match,prefix=re.fullmatch(r'/(?:jobs|profile/job_details)/(\d+)/?',path),'meta'
    elif host in ('yandex.ru','yandex.com'):
        match,prefix=re.fullmatch(r'/jobs/vacancies/(?:[^/]+-)?(\d+)/?',path),'yandex'
    elif host in ('tbank.ru','www.tbank.ru'):
        match,prefix=re.fullmatch(r'/career/(?:(?:it|back-office|service)/)?vacancy/(?:[^/]+/)*([a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12})/?',path,re.I),'tbank'
    elif host=='rabota.sber.ru':
        match,prefix=re.fullmatch(r'/search/(?:[^/]*-)?(\d{4,})/?',path),'sber'
    else:
        params = [(k,v) for k,v in parse_qsl(url.query, keep_blank_values=True) if not re.match(r"^(utm_|hhtm|__rr|abt_)",k)]
        canonical = urlunsplit(url._replace(path=path.rstrip("/") or "/", query=urlencode(sorted(params)), fragment=""))
        return {"id": "board_" + hashlib.sha256(canonical.encode()).hexdigest()[:24], "link": canonical}
    if not match:
        return None
    return {"id": f"{prefix}_{match[1].lower() if prefix=='tbank' else match[1]}", "link": urlunsplit(url._replace(fragment=""))}


def extract_html(html, url, recipe=None):
    recipe = recipe or {}
    soup = BeautifulSoup(html, "html.parser")
    host = urlsplit(url).hostname
    company = recipe.get("company") or {"career.avito.com": "Avito", "ozon.tech": "Ozon", "career.ozon.ru": "Ozon",'yandex.ru':'Yandex','yandex.com':'Yandex','tbank.ru':'T-Bank','www.tbank.ru':'T-Bank','rabota.sber.ru':'Sber'}.get(host, host)
    base = {"company": company, "source": "public_html", "source_page": url,
            "collected_at": datetime.now(timezone.utc).isoformat(), "pub_date": ""}
    selectors = {"career.avito.com": ".vacancies-detail__description", "ozon.tech": '[class*="descriptionHtml"]', "career.ozon.ru": '[class*="_description_"]', "hh.ru": '[data-qa="vacancy-description"]','yandex.ru':'[class*="Vacancy_vacancyBody__"]','yandex.com':'[class*="Vacancy_vacancyBody__"]'}
    selector = recipe.get("description_selector") or selectors.get(host)
    title = soup.select_one(recipe.get("title_selector", "h1"))
    own = identity(url)
    for element in soup.select("form,script:not([type='application/ld+json']),style,nav,footer,input,textarea,select,button"):
        element.decompose()
    if selector and title and own:
        desc = "\n\n".join(n.get_text(" ", strip=True) for n in soup.select(selector))
        if len(desc) > 150:
            return [{**base, **own, "title": title.get_text(" ", strip=True), "description": desc,
                     "description_quality": "needs_review" if recipe.get("description_selector") else "full",
                     "extraction_method": "html_selector", "extraction_selector": selector}]
    jobs = []
    def walk(obj):
        if isinstance(obj, list):
            for item in obj: walk(item)
        elif isinstance(obj, dict):
            types = obj.get("@type", [])
            if (types == "JobPosting" or "JobPosting" in types) and obj.get("title") and obj.get("description"):
                job = identity(obj.get("url", url), url)
                if job:
                    jobs.append({**base, **job, "title": obj["title"], "description": BeautifulSoup(obj["description"], "html.parser").get_text(" ", strip=True),
                                 "description_quality": "needs_review", "extraction_method": "schema_jobposting"})
            for value in obj.values():
                if isinstance(value, (list, dict)): walk(value)
    for node in soup.select('script[type="application/ld+json"]'):
        try: walk(json.loads(node.string or node.get_text()))
        except (TypeError, ValueError): pass
    if jobs: return jobs
    if host in ('tbank.ru','www.tbank.ru','rabota.sber.ru') and own and title:
        sections=[]
        for heading in soup.select('h2,h3'):
            if not re.search(r'описание|обязанност|требован|задач|мы жд[её]м|предстоит|заниматься',heading.get_text(' ',strip=True),re.I):continue
            block=heading.parent
            for _ in range(4):
                if not block or block.name in ('body','main','form') or len(block.select('h2,h3'))>3:break
                text=block.get_text(' ',strip=True)
                if len(text)>=150:
                    if text not in sections:sections.append(text)
                    break
                block=block.parent
        if sections:return [{**base,**own,'title':title.get_text(' ',strip=True),'description':'\n\n'.join(sections),'description_quality':'needs_review','extraction_method':'semantic_sections'}]
    rows = {}
    for a in soup.select(recipe.get("link_selector", "a[href]")):
        if a.find_parent(["nav","footer","form"]): continue
        job = identity(a.get("href", ""), url)
        heading=a.select_one('h1,h2,h3,h4,[class*="vacancyTitle"]')
        if not heading and host in ('tbank.ru','www.tbank.ru'):
            card=a.find_parent(attrs={'role':'button'});heading=card.select_one('h1,h2,h3') if card else None
        name = (heading or a).get_text(" ", strip=True)
        if not job or not name: continue
        if job["id"].startswith("board_") and not recipe.get("link_selector") and not re.search(r"/(vacanc(?:y|ies)|jobs?|positions?|careers?|openings?)/.+", urlsplit(job["link"]).path): continue
        rows[job["id"]] = {**base, **job, "title": name, "description": "", "description_quality": "snippet", "extraction_method": "listing_link"}
    return list(rows.values())


def load_board_export(path, *, full_only=True):
    payload = json.loads(__import__("pathlib").Path(path).read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("vacancies", [])
    accepted, rejected = {}, []
    for row in rows:
        if not isinstance(row, dict):
            rejected.append({"id": None, "reason": "invalid_record"}); continue
        valid = identity(row.get("link", ""))
        if not valid or not row.get("title") or not row.get("id"):
            rejected.append({"id": row.get("id"), "reason": "invalid_record"}); continue
        if full_only and (row.get("description_quality") != "full" or len(row.get("description", "")) < 150):
            rejected.append({"id": row["id"], "reason": "full_description_required"}); continue
        # Canonical URLs across Ozon IDs/slugs map to one employer vacancy.
        key = valid["id"]
        accepted[key] = {**row, "id": key}
    return list(accepted.values()), rejected
