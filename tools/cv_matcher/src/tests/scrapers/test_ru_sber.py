"""Live smoke test for Sber scraper.

Run:
    uv run python -m src.tests.scrapers.test_ru_sber --headed
    uv run python -m src.tests.scrapers.test_ru_sber --query PyTorch --limit 500 --headed
"""

from __future__ import annotations

import sys

from src.scrapers.ru_sber import SberScraper
from src.tests.scrapers.common import build_parser, run_live_scraper


def main() -> int:
    parser = build_parser("Sber", default_limit=500, default_query="PyTorch")
    args = parser.parse_args()
    return run_live_scraper(
        SberScraper,
        site="Sber",
        expected_prefix="sber",
        expected_hosts=("rabota.sber.ru",),
        args=args,
        stealth=True,
    )


if __name__ == "__main__":
    sys.exit(main())
