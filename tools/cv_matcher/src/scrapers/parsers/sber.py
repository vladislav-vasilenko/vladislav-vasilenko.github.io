"""Helpers for Sber's public publications API."""

from __future__ import annotations

import re
from typing import Any, Dict


SBER_PUBLICATIONS_URL = "https://rabota.sber.ru/public/app-candidate-public-api-gateway/api/v1/publications"
SBER_API_VERSION = "sber-public-api-v1"


def _sber_text(value: Any) -> str:
    return re.sub(r"(?m)^\s*\*\s+", "- ", str(value or "")).strip()


def compose_sber_publication(item: Dict[str, Any]) -> str:
    """Build vacancy text from the structured fields of the public publications API."""
    parts = [_sber_text(item.get("introduction"))]
    for heading, key in (("Обязанности", "duties"), ("Требования", "requirements"), ("Условия", "conditions")):
        text = _sber_text(item.get(key))
        if text:
            parts.append(f"{heading}:\n{text}")
    return "\n\n".join(part for part in parts if part)


def sber_compensation(item: Dict[str, Any]) -> str:
    low, high = item.get("salary_min"), item.get("salary_max")
    if low and high:
        return f"{low}–{high}"
    return str(low or high or "")
