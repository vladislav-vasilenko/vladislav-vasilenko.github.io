"""Yandex Jobs API parser helpers."""

from __future__ import annotations

import re
from typing import Dict, List


YANDEX_NAME_ALIASES = {
    "Плюс Фантех": "Плюс и Фантех",
}


def strip_html(s: str) -> str:
    """Remove inline HTML tags from a Yandex description block."""
    if not s:
        return s
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</?(?:p|div|li|ul|ol)[^>]*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def fetch_detail(page, slug: str) -> Dict[str, str]:
    """Pull full description blocks from the Yandex detail endpoint."""
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
        "description": strip_html(d.get("description") or ""),
        "duties": strip_html(d.get("duties") or ""),
        "key_qualifications": strip_html(d.get("key_qualifications") or ""),
        "additional_requirements": strip_html(d.get("additional_requirements") or ""),
        "conditions": strip_html(d.get("conditions") or ""),
        "our_team": strip_html(d.get("our_team") or ""),
        "tech_stack": strip_html(d.get("tech_stack") or ""),
    }


def compose_description(short_summary: str, profession: str, detail: Dict[str, str]) -> str:
    """Combine listing and detail data into one searchable description block."""
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


def normalize_name(s: str) -> str:
    if not s:
        return s
    if "\\u" in s:
        s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    cleaned = re.sub(r"\s+", " ", s).strip()
    return YANDEX_NAME_ALIASES.get(cleaned, cleaned)

