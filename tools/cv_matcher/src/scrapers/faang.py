"""FAANG scraper compatibility exports."""

from .google_careers import GoogleCareersScraper, _google_html_to_text  # noqa: F401
from .meta_careers import (  # noqa: F401
    MetaCareersScraper,
    MetaVacancy,
    _build_full_description,
    _meta_html_to_text,
    _meta_parse_detail,
)
