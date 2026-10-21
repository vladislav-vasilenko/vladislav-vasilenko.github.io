import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from src.board_import import identity,extract_html
from src.collection_contract import normalize_browser_rows,archive_browser_rows,read_browser_board
from src.archive_store import ArchiveStore

class CollectionContractTests(unittest.TestCase):
    def test_known_url_identities_match_chrome_registry_and_drop_listing_directories(self):
        samples=[('https://career.avito.com/vacancies/data-science/19450/','avito_19450'),('https://ozon.tech/vacancies/12345/','ozon_12345'),('https://yandex.ru/jobs/vacancies/ml-engineer-20372','yandex_20372'),('https://rabota.sber.ru/search/ml-engineer-12345','sber_12345'),('https://www.tbank.ru/career/it/vacancy/moscow/ml-engineer/0d772642-b21e-4529-a234-5e93b00210be/','tbank_0d772642-b21e-4529-a234-5e93b00210be')]
        for url,expected in samples:self.assertEqual(identity(url)['id'],expected)
        for url in ('https://yandex.ru/jobs/vacancies','https://rabota.sber.ru/search/','https://www.tbank.ru/career/vacancies/it/'):self.assertIsNone(identity(url))
    def test_python_and_chrome_share_one_archived_entity_and_do_not_truncate_description(self):
        row={'id':'legacy_tinkoff_id','link':'https://www.tbank.ru/career/it/vacancy/moscow/ml/0d772642-b21e-4529-a234-5e93b00210be/','title':'ML Engineer','company':'T-Bank','description':'Transformer training '*700,'description_quality':'full'}
        rows=normalize_browser_rows([row]);self.assertEqual(rows[0]['collector'],'playwright');self.assertGreater(len(rows[0]['description']),10000)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.sqlite3';archive_browser_rows(rows,path);archive_browser_rows([{**rows[0],'collector':'chrome_extension'}],path)
            store=ArchiveStore(path);self.assertEqual(store.summary()['vacancies'],1);self.assertEqual(store.summary()['versions'],1)
    def test_tbank_sber_fallback_retains_focused_sections_and_never_promotes_unreviewed_text(self):
        text='Обучение Transformer, распределённые эксперименты, Python и CUDA. '*10
        html='<h1>Research ML</h1><section><h2>Требования</h2><p>'+text+'</p></section><form>PRIVATE</form><aside>Related roles</aside>'
        for url in ('https://www.tbank.ru/career/it/vacancy/moscow/ml/0d772642-b21e-4529-a234-5e93b00210be/','https://rabota.sber.ru/search/ml-engineer-12345'):
            row=extract_html(html,url)[0];self.assertEqual(row['description_quality'],'needs_review');self.assertNotIn('PRIVATE',row['description']);self.assertNotIn('Related',row['description'])
    def test_yandex_current_dom_extracts_required_body_without_forms_or_recommendations(self):
        text='Исследовать ML-модели. '*40
        row=extract_html('<h1>Research ML</h1><div class="Vacancy_vacancyBody__abc">'+text+'<form>PRIVATE</form></div><aside>Recommended</aside>','https://yandex.ru/jobs/vacancies/research-12345')[0]
        self.assertEqual(row['description_quality'],'full');self.assertNotIn('PRIVATE',row['description']);self.assertNotIn('Recommended',row['description'])
    def test_missing_quality_does_not_become_full_and_shared_js_is_loaded_without_return_newline_bug(self):
        page=Mock();page.evaluate.return_value={'vacancies':[]};read_browser_board(page);script=page.evaluate.call_args.args[0];self.assertIn('return (\n',script);self.assertIn('JobBoardAdapters',script)
        row=normalize_browser_rows([{'link':'https://ozon.tech/vacancies/12345/','title':'ML','description':'long '*100}])[0];self.assertEqual(row['description_quality'],'needs_review')
    def test_review_confirmation_requires_exact_current_description_and_never_promotes_a_snippet(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ArchiveStore(Path(tmp)/'state.sqlite3');row={'id':'sber_12345','title':'ML','link':'https://rabota.sber.ru/search/ml-engineer-12345','description':'Research training '*30,'description_quality':'needs_review'}
            with store.connect() as db:store._entity(db,'vacancy',row['id'],row,'2026-10-15T12:00:00Z')
            detail=store.detail('vacancy',row['id'])
            with self.assertRaises(ValueError):store.confirm_description(row['id'],'outdated-hash')
            store.confirm_description(row['id'],detail['content_hash']);self.assertEqual(store.detail('vacancy',row['id'])['payload']['description_quality'],'full');self.assertEqual(len(store.detail('vacancy',row['id'])['versions']),2)
            snippet={**row,'id':'sber_12346','link':'https://rabota.sber.ru/search/ml-engineer-12346','description_quality':'snippet'}
            with store.connect() as db:store._entity(db,'vacancy',snippet['id'],snippet,'2026-10-15T12:00:00Z')
            with self.assertRaises(ValueError):store.confirm_description(snippet['id'],store.detail('vacancy',snippet['id'])['content_hash'])

if __name__=='__main__':unittest.main()
