"""Meta Careers parser helpers."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Dict, List

from pydantic import BaseModel, Field


RE_META_LD = re.compile(
    r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL,
)
RE_META_COMP_MIN = re.compile(
    r'"compensation_amount_minimum"\s*:\s*"\$([0-9,.]+)\\?/\s*(year|hour|month)"',
    re.IGNORECASE,
)
RE_META_COMP_MAX = re.compile(
    r'"compensation_amount_maximum"\s*:\s*"\$([0-9,.]+)\\?/\s*(year|hour|month)"',
    re.IGNORECASE,
)
RE_META_COMP_SPAN = re.compile(
    r"\$[\d,]+(?:\.\d+)?\s*/\s*(?:year|hour|month)[^<\n]*",
    re.IGNORECASE,
)


def meta_html_to_text(s: str) -> str:
    """Strip HTML tags and decode entities from Meta Careers fields."""
    s = unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace(" ", " ")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def parse_meta_detail(html: str) -> Dict[str, Any]:
    """Extract stable job-detail fields from a Meta SSR detail page."""
    out: Dict[str, Any] = {
        "title": "",
        "description": "",
        "responsibilities": "",
        "qualifications": "",
        "compensation": "",
        "date_posted": "",
    }

    for raw in RE_META_LD.findall(html):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if "title" not in obj or "description" not in obj:
            continue
        out["title"] = obj.get("title", "")
        out["description"] = meta_html_to_text(obj.get("description", ""))
        out["responsibilities"] = meta_html_to_text(obj.get("responsibilities", ""))
        out["qualifications"] = meta_html_to_text(obj.get("qualifications", ""))
        out["date_posted"] = obj.get("datePosted", "")
        break

    span = RE_META_COMP_SPAN.search(html)
    if span:
        out["compensation"] = span.group().strip()
    else:
        m_min = RE_META_COMP_MIN.search(html)
        m_max = RE_META_COMP_MAX.search(html)
        if m_min and m_max:
            unit = m_min.group(2)
            out["compensation"] = f"${m_min.group(1)}/{unit} to ${m_max.group(1)}/{unit}"
        elif m_min:
            out["compensation"] = f"${m_min.group(1)}/{m_min.group(2)}"
    return out


def build_full_description(parts: Dict[str, Any]) -> str:
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
    """Validated Meta job record; catches parser/schema drift before storage."""

    id: str = Field(min_length=5)
    title: str = Field(min_length=1)
    company: str = "Meta"
    locations: List[str] = Field(default_factory=list)
    teams: List[str] = Field(default_factory=list)
    sub_teams: List[str] = Field(default_factory=list)
    compensation: str = ""
    description: str = Field(min_length=50)
    link: str = Field(pattern=r"^https://www\.metacareers\.com/(?:jobs|profile/job_details)/\d+/?$")
    pub_date: str = "Recently"
    origin_query: str = ""



def parse_meta_listing(html: str) -> List[Dict[str, Any]]:
    """Read public rendered cards across old /jobs and current /profile routes."""
    from bs4 import BeautifulSoup
    from urllib.parse import urlsplit
    soup=BeautifulSoup(html,'html.parser');found={}
    for a in soup.select('a[href]'):
        u=urlsplit(a.get('href',''))
        if u.netloc and u.netloc!='www.metacareers.com':continue
        m=re.fullmatch(r'/(?:jobs|profile/job_details)/(\d+)/?',u.path)
        if not m:continue
        heading=a.select_one('h2,h3,h4');title=(heading or a).get_text(' ',strip=True)
        if not title or title.lower() in ('apply','apply now','view job'):continue
        found[m[1]]={'id':m[1],'title':title[:500],'locations':[],'teams':[],'sub_teams':[],'url':'https://www.metacareers.com'+u.path}
    return list(found.values())


def parse_meta_rendered_detail(html: str) -> Dict[str, Any]:
    """Fallback for the current public React detail page; excludes site footer."""
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser');out={'title':'','description':'','responsibilities':'','qualifications':'','compensation':'','date_posted':''}
    h=soup.find('h1')
    if h:out['title']=h.get_text(' ',strip=True)
    for heading in soup.find_all(['h2','h3']):
        label=heading.get_text(' ',strip=True)
        if not re.search(r'Responsibilities$|^(Minimum|Preferred) Qualifications$',label,re.I):continue
        block=heading.parent
        for _ in range(3):
            if block is None:break
            if len(block.get_text(' ',strip=True))>len(label)+30:break
            block=block.parent
        if block is None:continue
        body=block.get_text('\n',strip=True)
        if re.search('Responsibilities$',label,re.I):
            out['responsibilities']=body
            intro=[]
            for sibling in block.previous_siblings:
                if getattr(sibling,'name',None) and sibling.find(['h1','h2','h3']):break
                if getattr(sibling,'get_text',None):
                    value=sibling.get_text('\n',strip=True)
                    if len(value)>50:intro.append(value)
            out['description']='\n\n'.join(reversed(intro))
        else:out['qualifications']+='\n\n'+body
    out['qualifications']=out['qualifications'].strip()
    if not out['description'] and out['responsibilities']:out['description']=out['responsibilities'];out['responsibilities']=''
    # A general page with a title is never accepted as a complete job.
    if not out['title'] or not out['qualifications']:out['description']=''
    return out


def parse_meta_graphql(body: str) -> List[Dict[str, Any]]:
    """Both observed public listing contracts, including October 2026 v2."""
    found={}
    for line in body.splitlines():
        line=line.strip().removeprefix('for (;;);').strip()
        try:obj=json.loads(line)
        except ValueError:continue
        if not isinstance(obj,dict):continue
        data=obj.get('data') or {}
        for name in ('job_search_with_featured_jobs_v2','job_search_with_featured_jobs'):
            container=data.get(name) or {}
            for item in container.get('all_jobs') or []:
                if not isinstance(item,dict) or not re.fullmatch(r'\d{1,25}',str(item.get('id',''))) or not isinstance(item.get('title'),str):continue
                locations=item.get('locations') or []
                if not isinstance(locations,list) or any(not isinstance(x,str) for x in locations):continue
                found[str(item['id'])]={**item,'id':str(item['id']),'locations':locations,'locations_complete':True}
    return list(found.values())
