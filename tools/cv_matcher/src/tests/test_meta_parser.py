"""Snapshot tests for Meta parser helpers.

These run *without* a browser — they exercise the parser logic against saved
HTML fixtures, so a Meta site redesign that breaks parsing fails CI here
instead of producing silent empty rows in production.

Run:
    uv run python -m src.tests.test_meta_parser
    pytest src/tests/test_meta_parser.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from src.scrapers.faang import (  # noqa: E402
    MetaVacancy,
    _build_full_description,
    _meta_html_to_text,
    _meta_parse_detail,
)

FIXTURES = Path(__file__).parent / "fixtures" / "meta"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_detail_with_comp() -> None:
    """Real Meta detail page (Product Manager) — full extraction."""
    html = _load_fixture("job_with_comp.html")
    parsed = _meta_parse_detail(html)

    assert parsed["title"] == "Product Manager", f"title: {parsed['title']!r}"
    assert "Meta Product Managers" in parsed["description"]
    assert len(parsed["responsibilities"]) > 200, "responsibilities too short"
    assert len(parsed["qualifications"]) > 200, "qualifications too short"

    # Compensation must match Meta's documented format.
    assert re.match(
        r"^\$[\d,]+/year to \$[\d,]+/year",
        parsed["compensation"],
    ), f"unexpected comp format: {parsed['compensation']!r}"
    # Date is ISO 8601 with timezone.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", parsed["date_posted"]), parsed["date_posted"]
    print(f"  ✓ with_comp: comp={parsed['compensation']!r}")


def test_parse_detail_no_comp_synthetic() -> None:
    """Strip comp markers from the with-comp fixture and re-parse — parser
    should succeed without compensation, returning empty string."""
    html = _load_fixture("job_with_comp.html")
    # Remove both the rendered span and the JSON-form min/max fields so
    # neither extractor finds anything.
    stripped = re.sub(r"\$[\d,]+(?:\.\d+)?\s*/\s*(?:year|hour|month)[^<\n]*", "[REDACTED]", html)
    stripped = re.sub(r'"compensation_amount_minimum"\s*:\s*"[^"]*"', '"compensation_amount_minimum":""', stripped)
    stripped = re.sub(r'"compensation_amount_maximum"\s*:\s*"[^"]*"', '"compensation_amount_maximum":""', stripped)

    parsed = _meta_parse_detail(stripped)
    assert parsed["title"] == "Product Manager"
    assert len(parsed["description"]) > 50
    assert parsed["compensation"] == "", f"expected empty comp, got {parsed['compensation']!r}"
    print("  ✓ no_comp: empty compensation, other fields intact")


def test_html_to_text_decodes_entities() -> None:
    """HTML entities + common tags must round-trip into clean text."""
    raw = "First line.<br/>Second line.&nbsp;With&nbsp;nbsp.</p><li>Bullet</li>"
    out = _meta_html_to_text(raw)
    assert "First line." in out
    assert "Second line." in out
    assert "<" not in out and ">" not in out
    assert "&nbsp;" not in out
    print("  ✓ html_to_text: tags stripped, entities decoded")


def test_build_full_description_concat_order() -> None:
    """Sections must be assembled in fixed order: desc → resp → qual → comp."""
    parts = {
        "description": "Lead role.",
        "responsibilities": "Ship features.",
        "qualifications": "5+ years.",
        "compensation": "$100,000/year",
    }
    out = _build_full_description(parts)
    # Each section header followed by content
    desc_idx = out.index("Lead role.")
    resp_idx = out.index("Responsibilities:")
    qual_idx = out.index("Qualifications:")
    comp_idx = out.index("$100,000/year")
    assert desc_idx < resp_idx < qual_idx < comp_idx, "section order broken"
    print("  ✓ full_description: ordering preserved")


def test_pydantic_model_rejects_short_description() -> None:
    """MetaVacancy must reject descriptions <50 chars (parser drift detector)."""
    try:
        MetaVacancy(
            id="meta_123456",
            title="Engineer",
            description="too short",
            link="https://www.metacareers.com/jobs/123456/",
        )
    except ValidationError:
        print("  ✓ pydantic: short description rejected")
        return
    raise AssertionError("MetaVacancy should have rejected short description")


def test_pydantic_model_rejects_bad_link() -> None:
    """Link pattern guards against detail-URL drift."""
    try:
        MetaVacancy(
            id="meta_123456",
            title="Engineer",
            description="x" * 100,
            link="https://example.com/jobs/123456/",
        )
    except ValidationError:
        print("  ✓ pydantic: bad link rejected")
        return
    raise AssertionError("MetaVacancy should have rejected bad link")


def test_pydantic_model_accepts_real_extraction() -> None:
    """End-to-end: parse fixture → build description → validate."""
    html = _load_fixture("job_with_comp.html")
    parsed = _meta_parse_detail(html)
    full_desc = _build_full_description(parsed)
    vac = MetaVacancy(
        id="meta_1238249364564427",
        title=parsed["title"],
        locations=["Los Angeles, CA"],
        teams=["Product Management"],
        sub_teams=["Product Strategy"],
        compensation=parsed["compensation"],
        description=full_desc,
        link="https://www.metacareers.com/jobs/1238249364564427/",
        pub_date=parsed["date_posted"],
    )
    dumped = vac.model_dump()
    assert dumped["company"] == "Meta"
    assert dumped["compensation"].startswith("$")
    assert len(dumped["description"]) > 200
    print("  ✓ pydantic: real extraction validates")


def test_listing_sample_shape() -> None:
    """The listing JSON snapshot has the field shape our scraper depends on."""
    jobs = json.loads(_load_fixture("listing_sample.json"))
    assert isinstance(jobs, list) and jobs
    for j in jobs:
        for k in ("id", "title", "locations", "teams"):
            assert k in j, f"listing entry missing key {k!r}: {j}"
        assert isinstance(j["locations"], list)
        assert isinstance(j["teams"], list)
    print(f"  ✓ listing_sample: {len(jobs)} entries, all fields present")


import unittest
from src.scrapers.parsers.meta import parse_meta_graphql, parse_meta_rendered_detail

class CurrentMetaContracts(unittest.TestCase):
    def test_current_and_legacy_listing_keep_all_locations(self):
        for name in ('job_search_with_featured_jobs_v2', 'job_search_with_featured_jobs'):
            body = json.dumps({'data': {name: {'all_jobs': [{'id': '123', 'title': 'Research Engineer', 'locations': ['Paris, France', 'London, UK'], 'teams': ['AI']}]}}})
            result = parse_meta_graphql(body)
            self.assertEqual(result[0]['locations'], ['Paris, France', 'London, UK'])
            self.assertTrue(result[0]['locations_complete'])
        self.assertEqual(parse_meta_graphql('{"data":{"unrelated_query":[]}}'), [])

    def test_unlimited_detail_collection_has_no_500_cap_and_skips_existing(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from src.scrapers.meta_careers import MetaCareersScraper
        scraper=MetaCareersScraper(limit=0)
        raw=[{'id':str(i)} for i in range(1,1103)]
        async def detail(context,row,*args):return {'id':'meta_'+row['id'],'title':'Engineer','link':'https://www.metacareers.com/profile/job_details/'+row['id']+'/','locations':['London'],'teams':[],'compensation':''}
        with patch.object(scraper,'_fetch_one_async',side_effect=detail),patch('builtins.print'):
            result=asyncio.run(scraper._fetch_details_async(None,raw,'',{'meta_1'}))
        self.assertEqual(len(result),1101)
        self.assertNotIn('meta_1',{r['id'] for r in result})

    def test_rendered_detail_requires_job_sections_and_excludes_footer(self):
        html = '<h1>Research Engineer</h1><div><div>Train generative models and evaluate reproducible scientific experiments.</div><div><h2>Research Engineer Responsibilities</h2><ul><li>Build experiments and reusable code.</li></ul></div><div><h2>Minimum Qualifications</h2><ul><li>Experience with PyTorch and research.</li></ul></div><div><h2>About Meta</h2>Company boilerplate</div></div><footer>Footer not JD</footer>'
        result = parse_meta_rendered_detail(html)
        self.assertIn('generative', result['description'])
        self.assertIn('PyTorch', result['qualifications'])
        self.assertNotIn('boilerplate', result['description'])
        self.assertFalse(parse_meta_rendered_detail('<h1>Careers at Meta</h1><p>Company introduction only.</p>')['description'])


TESTS = [
    test_parse_detail_with_comp,
    test_parse_detail_no_comp_synthetic,
    test_html_to_text_decodes_entities,
    test_build_full_description_concat_order,
    test_pydantic_model_rejects_short_description,
    test_pydantic_model_rejects_bad_link,
    test_pydantic_model_accepts_real_extraction,
    test_listing_sample_shape,
]


def main() -> int:
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
