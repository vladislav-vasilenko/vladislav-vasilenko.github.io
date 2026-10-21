import json
import tempfile
import unittest
from pathlib import Path
from src.board_import import extract_html, load_board_export, identity

class BoardImportTests(unittest.TestCase):
    def test_avito_preserves_long_description_excludes_application_and_related_jobs(self):
        desc = 'Training transformer ' * 350
        html = f'<h1>Research Engineer</h1><section class="vacancies-detail__description">{desc}</section><form>private@email.ru<input value="secret"></form><div>Related jobs</div>'
        rows = extract_html(html,'https://career.avito.com/vacancies/data-science/19450/')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['description'],desc.strip())
        self.assertNotIn('secret',rows[0]['description'])
        self.assertNotIn('Related',rows[0]['description'])
        self.assertEqual(rows[0]['description_quality'],'full')

    def test_ozon_mixed_listing_urls_and_query_ids(self):
        html = '<a href="https://ozon.tech/vacancies/136375417/">Base models</a><a href="/fintech/vacancy?id=123">Bank</a><a href="/vacancy/python/">Python filter</a>'
        rows=extract_html(html,'https://career.ozon.ru/vacancy/?query=ML')
        self.assertEqual({r['id'] for r in rows},{'ozon_136375417','ozon_123'})
        self.assertEqual(identity('https://ozon.tech/vacancies/136375417-name/')['id'],'ozon_136375417')

    def test_schema_requires_review_and_main_is_never_accepted_as_full(self):
        desc='Transformer training ' * 15
        schema=json.dumps({'@graph':[{'@type':'JobPosting','title':'Research','description':desc}]})
        rows=extract_html(f'<script type="application/ld+json">{schema}</script>', 'https://example.com/jobs/1')
        self.assertEqual(rows[0]['description_quality'],'needs_review')
        self.assertEqual(extract_html('<h1>Research</h1><main>'+desc+'</main>','https://example.com/jobs/1'),[])

    def test_import_rejects_snippets_and_review_pending(self):
        base={'id':'ozon_123','title':'Research','link':'https://ozon.tech/vacancies/123/','description':'training '*50}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'export.json'
            p.write_text(json.dumps([{**base,'description_quality':'snippet'},{**base,'id':'ozon_124','link':'https://ozon.tech/vacancies/124/','description_quality':'needs_review'},{**base,'description_quality':'full'}]))
            rows,rejected=load_board_export(p)
        self.assertEqual(len(rows),1); self.assertEqual(len(rejected),2)

if __name__=='__main__': unittest.main()
