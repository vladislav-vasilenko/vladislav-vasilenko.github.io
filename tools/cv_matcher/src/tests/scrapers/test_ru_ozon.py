"""Live smoke test for Ozon scraper.

Run:
    uv run python -m src.tests.scrapers.test_ru_ozon
    uv run python -m src.tests.scrapers.test_ru_ozon --query PyTorch --limit 500
"""

from __future__ import annotations

import sys

from src.scrapers.ru_ozon import OzonScraper
from src.tests.scrapers.common import build_parser, run_live_scraper


def main() -> int:
    parser = build_parser("Ozon", default_limit=500, default_query="PyTorch")
    args = parser.parse_args()
    return run_live_scraper(
        OzonScraper,
        site="Ozon",
        expected_prefix="ozon",
        expected_hosts=("career.ozon.ru",),
        args=args,
    )


if __name__ == "__main__":
    sys.exit(main())

