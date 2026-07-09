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
    link: str = Field(pattern=r"^https://www\.metacareers\.com/jobs/\d+/?$")
    pub_date: str = "Recently"
    origin_query: str = ""

