"""Russian scraper compatibility exports."""

from .ru_boards import HHScraper  # noqa: F401
from .ru_companies import (  # noqa: F401
    AlfaScraper,
    AvitoScraper,
    MTSScraper,
    OzonScraper,
    TinkoffScraper,
    VKScraper,
    WildberriesTechScraper,
    X5RetailScraper,
)
from .ru_sber import SberScraper  # noqa: F401
from .ru_yandex import (  # noqa: F401
    YandexScraper,
    _normalize_yandex_name,
    _strip_html,
    compose_yandex_description,
    fetch_yandex_detail,
)
