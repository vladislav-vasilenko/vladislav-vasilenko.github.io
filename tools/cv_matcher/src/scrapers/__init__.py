"""Scraper package — re-exports all scrapers plus SCRAPER_REGISTRY / SOURCE_GROUPS."""

from ._base import (  # noqa: F401
    BaseScraper, UA,
    _launch_browser, _scroll_until_stable,
    _safe_text, _first_non_empty_text, _extract_date,
)
from .ru import (  # noqa: F401
    YandexScraper, TinkoffScraper, AvitoScraper, VKScraper, X5RetailScraper,
    WildberriesTechScraper, MTSScraper, AlfaScraper,
    SberScraper, HHScraper, OzonScraper,
)
from .international import (  # noqa: F401
    RemoteOKScraper, WeWorkRemotelyScraper, HackerNewsHiringScraper,
    LinkedInScraper, IndeedScraper, WelcomeJungleScraper, WellfoundScraper,
    _strip_html,
)
from .faang import GoogleCareersScraper, MetaCareersScraper  # noqa: F401

SCRAPER_REGISTRY = {
    # RU
    "yandex":      YandexScraper,
    "tinkoff":     TinkoffScraper,
    "avito":       AvitoScraper,
    "vk":          VKScraper,
    "x5":          X5RetailScraper,
    "hh":          HHScraper,
    "ozon":        OzonScraper,
    "sber":        SberScraper,
    "wildberries": WildberriesTechScraper,
    "mts":         MTSScraper,
    "alfa":        AlfaScraper,
    # International
    "remoteok":    RemoteOKScraper,
    "wwr":         WeWorkRemotelyScraper,
    "hn":          HackerNewsHiringScraper,
    "linkedin":    LinkedInScraper,
    "indeed":      IndeedScraper,
    "wttj":        WelcomeJungleScraper,
    "wellfound":   WellfoundScraper,
    # FAANG
    "google":      GoogleCareersScraper,
    "meta":        MetaCareersScraper,
}

SOURCE_GROUPS: dict = {
    "ru": ["yandex", "hh", "ozon", "avito", "tinkoff", "vk", "x5", "wildberries", "mts", "alfa"],
    "international": ["remoteok", "wwr", "hn", "linkedin", "indeed", "wttj", "wellfound"],
    "faang": ["google", "meta"],
}
SOURCE_GROUPS["all"] = SOURCE_GROUPS["ru"] + SOURCE_GROUPS["international"] + SOURCE_GROUPS["faang"]
