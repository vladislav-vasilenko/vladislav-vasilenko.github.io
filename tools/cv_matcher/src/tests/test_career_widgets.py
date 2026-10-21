"""Employer overlays share exact-version caches and never create HH sending tasks."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from src.tests import test_skill_analysis as fixtures
from src.hh_badges import lookup
from src.hh_inline import run
from src.application_store import ApplicationStore
from src.board_import import identity,extract_html

URLS={
 'avito':'https://career.avito.com/vacancies/data-science/19450/',
 'ozon':'https://ozon.tech/vacancies/ab7e6be8-15d7-4bb8-aaa1-0e9c1bf7f555-data-scientist/',
 'yandex':'https://yandex.ru/jobs/vacancies/mlrazrabotchik-49380',
 'tbank':'https://www.tbank.ru/career/it/vacancy/moscow/ml-engineer/0d772642-b21e-4529-a234-5e93b00210be/',
}
class CareerWidgetTests(unittest.TestCase):
    setUp=fixtures.SkillAnalysisTests.setUp
    def params(self,provider):
        url=URLS[provider];job={**self.job,**identity(url)}
        with self.store.connect() as db:self.store._entity(db,'vacancy',job['id'],job,fixtures.NOW.isoformat())
        return {'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'vacancy_id':job['id'],'goal':self.goal}
    def test_every_board_imports_a_review_and_paid_button_reuses_it_without_api(self):
        for provider in URLS:
            with self.subTest(provider=provider):
                p=self.params(provider);packet=run(self.store,{**p,'action':'analysis_export'},Path(self.tmp.name))['result']
                answer=json.dumps({'export_id':packet['export_id'],'analysis':self.raw})
                saved=run(self.store,{**p,'action':'analysis_import','export_id':packet['export_id'],'answer':answer},Path(self.tmp.name))['result']
                with patch('openai.OpenAI',side_effect=AssertionError('No API')):
                    again=run(self.store,{**p,'action':'analysis'},Path(self.tmp.name))['result']
                    self.assertEqual(again['key'],saved['key']);self.assertEqual(again['api_requests'],0)
                item=lookup(self.store,{**p,'provider':provider,'ids':[p['vacancy_id']]})['items'][0]
                self.assertEqual(item['analysis_key'],saved['key']);self.assertEqual(item['coverage'],saved['metrics']['overall']['percent']);self.assertTrue(item['recommendation_reason'])
                with self.assertRaises(ValueError):lookup(self.store,{**p,'provider':provider,'ids':['hh_1']})
    def test_career_letter_is_versioned_and_cannot_be_sent_to_hh_queue(self):
        p=self.params('tbank');root=Path(self.tmp.name)
        packet=run(self.store,{**p,'action':'cover_export'},root)['result']
        args={**p,'action':'cover_save','text':'Моё проверенное письмо.','revision':0,'resume_hash_at_export':packet['context']['resume_hash'],'vacancy_hash_at_export':packet['vacancy_hash']}
        saved=run(self.store,args,root)['result'];apps=ApplicationStore(self.store.path)
        self.assertEqual(apps.get(saved['application_id'])['context']['channel'],'career')
        restored=run(self.store,{**p,'action':'cover_read'},root)['result']
        self.assertEqual(restored['text'],args['text']);self.assertEqual(restored['revision'],1)
        for kind in ('prepare','execute'):
            with self.assertRaisesRegex(ValueError,'HH'):apps.queue_command(kind,saved['application_id'])
        with self.assertRaisesRegex(ValueError,'HH'):apps.intent(saved['application_id'])
        with self.assertRaises(ValueError):run(self.store,{**args,'revision':1,'resume_hash_at_export':'changed'},root)
    def test_live_listing_fixtures_have_titles_not_apply_labels_or_badges(self):
        directory=Path(__file__).resolve().parents[2]/'hh-research-extension/fixtures/boards'
        for provider in URLS:
            listing=URLS[provider].split('/vacanc')[0]+('/jobs/vacancies' if provider=='yandex' else '/vacancies/')
            rows=extract_html((directory/(provider+'-listing.html')).read_text(),listing)
            self.assertGreaterEqual(len(rows),2,provider)
            for row in rows:self.assertNotEqual(row['title'],'Откликнуться');self.assertNotIn('Middle',row['title'])
        rows=extract_html((directory/'avito-detail.html').read_text(),URLS['avito'])
        self.assertEqual(rows[0]['description_quality'],'full');self.assertIn('pre-training',rows[0]['description'])
        self.assertNotIn('agree-resume-validity',rows[0]['description'])
    def test_tbank_back_office_urls_share_the_same_stable_identity_contract(self):
        url='https://www.tbank.ru/career/back-office/vacancy/moscow/legal/f58f31d5-475a-41fb-9f07-30e957d7f152/'
        self.assertEqual(identity(url)['id'],'tbank_f58f31d5-475a-41fb-9f07-30e957d7f152')
