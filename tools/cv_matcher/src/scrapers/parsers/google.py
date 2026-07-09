"""Google Careers SSR payload parser."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, Optional, Set


# Wiz data field indices discovered via SSR payload analysis.
F_ID = 0
F_TITLE = 1
F_RESPONSIBILITIES = 3
F_QUALIFICATIONS = 4
F_LOCATIONS = 9
F_DESCRIPTION = 10
F_TIMESTAMPS = 12
TOTAL_IDX = 2
PAGE_SIZE = 20


def google_html_to_text(s: str) -> str:
    """Strip HTML tags and decode entities from Google Careers fields."""
    if not s:
        return ""
    s = unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>|</li>|</div>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def safe_html_field(record: list, idx: int) -> str:
    """Extract an HTML string from a Wiz field."""
    if len(record) <= idx:
        return ""
    field = record[idx]
    if isinstance(field, list) and len(field) > 1 and isinstance(field[1], str):
        return field[1]
    if isinstance(field, str):
        return field
    return ""


def extract_wiz_data(html: str) -> Optional[list]:
    """Extract the AF_initDataCallback data payload containing job records."""
    pattern = r"AF_initDataCallback\([^)]*?data:\s*(\[[\s\S]*?)\}\);\s*</script>"
    for block in re.findall(pattern, html):
        depth = 0
        end = 0
        for ci, ch in enumerate(block):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = ci + 1
                    break
        if end == 0:
            continue
        try:
            data = json.loads(block[:end])
        except json.JSONDecodeError:
            continue
        if (
            isinstance(data, list)
            and len(data) >= 3
            and isinstance(data[0], list)
            and len(data[0]) > 0
            and isinstance(data[0][0], list)
            and len(data[0][0]) > 1
        ):
            return data
    return None


def parse_wiz_record(
    record: list,
    *,
    query: str,
    existing_ids: Set[str],
    id_prefix: str,
    company_name: str,
    detail_url_tpl: str,
) -> Optional[Dict[str, Any]]:
    """Parse a single Google Careers Wiz record into a vacancy dict."""
    if not isinstance(record, list) or len(record) < 11:
        return None

    vid = str(record[F_ID])
    jid = f"{id_prefix}_{vid}"
    if jid in existing_ids:
        return None

    title = record[F_TITLE] or "Google Vacancy"
    desc = google_html_to_text(safe_html_field(record, F_DESCRIPTION))
    resp = google_html_to_text(safe_html_field(record, F_RESPONSIBILITIES))
    quals = google_html_to_text(safe_html_field(record, F_QUALIFICATIONS))

    blocks = []
    if desc:
        blocks.append(desc)
    if resp:
        blocks.append("Responsibilities:\n" + resp)
    if quals:
        blocks.append("Qualifications:\n" + quals)

    full_desc = "\n\n".join(blocks)
    if not full_desc or len(full_desc) < 30:
        return None

    locations = []
    raw_locs = record[F_LOCATIONS] if len(record) > F_LOCATIONS else []
    if isinstance(raw_locs, list):
        for loc in raw_locs:
            if isinstance(loc, list) and len(loc) > 0 and loc[0]:
                loc_name = str(loc[0])
                if loc_name not in locations:
                    locations.append(loc_name)

    pub_date = "Recently"
    if len(record) > F_TIMESTAMPS and isinstance(record[F_TIMESTAMPS], list):
        try:
            ts = record[F_TIMESTAMPS][0]
            if ts:
                pub_date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pass

    return {
        "id": jid,
        "title": title,
        "company": company_name,
        "pub_date": pub_date,
        "description": full_desc[:5000],
        "link": detail_url_tpl.format(job_id=vid),
        "locations": locations,
        "compensation": "",
        "origin_query": query,
    }

