"""No OpenAI calls: export -> manual paste -> validated, versioned local rendering."""
import copy,json,unittest
from unittest.mock import patch
from datetime import timedelta
from fastapi.testclient import TestClient
from src.tests import test_skill_analysis as fixtures
from src.external_analysis import export_review,import_review
from src.skill_analysis import analyze,cached,context,EXTERNAL_MODEL
from src.skill_history import detail,history
from resume_import_server import create_app

class ExternalAnalysisTests(unittest.TestCase):
    setUp=fixtures.SkillAnalysisTests.setUp
    def packet(self):return export_review(self.store,self.cv['id'],self.job['id'],self.goal)
    def answer(self,packet,raw=None):return json.dumps({'export_id':packet['export_id'],'analysis':self.raw if raw is None else raw},ensure_ascii=False)
    def test_round_trip_is_local_idempotent_and_reused_by_paid_button(self):
        p=self.packet();self.assertIn('JSON SCHEMA',p['prompt']);self.assertIn(self.cv_parts['R1'],p['prompt']);self.assertIn(self.jd_parts['J1'],p['prompt'])
        with patch('openai.OpenAI',side_effect=AssertionError('No API')):
            report=import_review(self.store,p['export_id'],self.answer(p));again=import_review(self.store,p['export_id'],'```json\n'+self.answer(p)+'\n```')
            self.assertEqual(report['api_requests'],0);self.assertTrue(again['cached']);self.assertEqual(history(self.store)['total'],1)
            reused=analyze(self.store,self.cv['id'],self.job['id'],self.goal,now=__import__('src.tests.test_extension_ranking',fromlist=['NOW']).NOW)
        self.assertEqual(reused['key'],report['key']);self.assertEqual(reused['model'],EXTERNAL_MODEL);self.assertEqual(report['metrics']['overall']['percent'],67)
        self.assertEqual(detail(self.store,report['key'])['sources']['resume']['text'],context(self.store,self.cv['id'],self.job['id'],self.goal)['cv_text'])
    def test_changed_sources_keep_exported_versions_and_do_not_become_current(self):
        p=self.packet();before=context(self.store,self.cv['id'],self.job['id'],self.goal)
        from src.tests.test_extension_ranking import NOW
        with self.store.connect() as db:self.store._entity(db,'vacancy',self.job['id'],{**self.job,'description':self.job['description']+' NEW REQUIREMENT'},(NOW+timedelta(hours=1)).isoformat())
        report=import_review(self.store,p['export_id'],self.answer(p));saved=detail(self.store,report['key'])
        self.assertEqual(saved['sources']['vacancy']['text'],before['jd_text']);self.assertEqual(saved['sources']['vacancy']['version_id'],before['vacancy_version_id']);self.assertFalse(saved['sources']['vacancy']['matches_current'])
        self.assertIsNone(cached(self.store,context(self.store,self.cv['id'],self.job['id'],self.goal)))
    def test_forged_citations_wrong_envelope_and_invalid_shapes_never_save(self):
        p=self.packet()
        invalid=[]
        for field,value in [('job_quote','This quote does not occur in the vacancy'),('resume_passage_ids',['R999']),('status','excellent'),('explanation',{'html':'bad'})]:
            raw=copy.deepcopy(self.raw);raw['requirements'][0][field]=value;invalid.append(self.answer(p,raw))
        invalid.extend([self.answer({**p,'export_id':'f'*64}),'{not json}',json.dumps({'export_id':p['export_id'],'analysis':[]}),json.dumps({'export_id':p['export_id'],'analysis':{**self.raw,'metrics':{'percent':100}}})])
        for answer in invalid:
            with self.assertRaises(ValueError):import_review(self.store,p['export_id'],answer)
        self.assertEqual(history(self.store)['total'],0)
    def test_authenticated_same_origin_routes_cannot_call_a_model(self):
        with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
            body={'op':'export','resume_id':self.cv['id'],'vacancy_id':self.job['id'],'goal':self.goal}
            self.assertEqual(client.post('/archive/skill-external',json=body).status_code,401)
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            self.assertEqual(client.post('/archive/skill-external',json=body,headers={'Origin':'https://evil.example'}).status_code,401)
            h={'Origin':'http://127.0.0.1:8788'}
            with patch('src.skill_analysis.analyze',side_effect=AssertionError('No paid calls')):
                r=client.post('/archive/skill-external',json=body,headers=h);self.assertEqual(r.status_code,200);p=r.json()
                imported=client.post('/archive/skill-external',json={'op':'import','export_id':p['export_id'],'answer':self.answer(p)},headers=h);self.assertEqual(imported.status_code,200)
                self.assertEqual(client.get('/archive/skill-history').json()['total'],1)
                backup=client.get('/archive/export').json()['tables'];self.assertEqual(len(backup['external_analysis_requests']),1)
