"""Batch contracts use a disposable SQLite file and never call a provider."""
import asyncio,json,time,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.tests import test_skill_analysis as fixtures
from src.tests.test_extension_ranking import job,NOW
from src.application_store import ApplicationStore
from src.career_application import CareerApplication
from src.analysis_store import text_hash,document_text
from src.external_analysis import export_review,import_review
from src import luna_batch as batch
from resume_import_server import create_app

class LunaBatchTests(unittest.TestCase):
 def setUp(self):
  fixtures.SkillAnalysisTests.setUp(self);self.app=CareerApplication(ApplicationStore(self.store.path));self.jobs=[self.job]
  for n in range(2,56):
   j=job(n,'PyTorch Transformer')
   with self.store.connect() as db:self.store._entity(db,'vacancy',j['id'],j,NOW.isoformat())
   self.jobs.append(j)
  self.store.save_ranking({'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'goal':self.goal,'model':'text-embedding-3-small','generated_at':NOW.isoformat(),'all':[{'id':j['id'],'score':.99-n*.005,'cv_similarity':.99-n*.005,'goal_similarity':.4,'vacancy_hash':text_hash(document_text('vacancy',j))} for n,j in enumerate(self.jobs)]})
 def plan(self,limit=50,**kwargs):return batch.preview(self.app.store,self.store,{'resume_id':self.cv['id'],'goal':self.goal,'limit':limit,**kwargs})
 def start(self,limit=1):
  p=self.plan(limit);return batch.start(self.app.store,self.store,p['id'])
 def step(self):asyncio.run(batch.advance(self.app))
 def test_preview_top50_same_rank_and_filters_no_api_or_browser_work(self):
  with patch('openai.OpenAI',side_effect=AssertionError('No paid request')):
   p=self.plan();self.assertEqual(len(p['items']),50);self.assertEqual([i['id'] for i in p['items']],[j['id'] for j in self.jobs[:50]])
   with self.assertRaises(ValueError):self.plan(filters={'company':'No such company'})
   e=batch.export_prompt(self.app.store,self.store,p['id']);self.assertEqual(e['count'],50);self.assertIn('results',e['prompt']);self.assertIn(self.cv_parts['R1'],e['prompt']);self.assertEqual(e['api_requests'],0)
  self.assertEqual(self.app.tasks(),[])
  with self.store.connect() as db:
   for table in ('applications','browser_commands'):self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
 def test_start_is_idempotent_and_expired_or_changed_data_cannot_start(self):
  t=self.start();again=batch.start(self.app.store,self.store,t['id']);self.assertEqual(t,again)
  p=self.plan()
  with self.store.connect() as db:db.execute('UPDATE analysis_batches SET created=? WHERE id=?',(time.time()-901,p['id']))
  with self.assertRaisesRegex(ValueError,'15 минут'):batch.start(self.app.store,self.store,p['id'])
  p=self.plan()
  with self.store.connect() as db:
   jd={**self.job,'description':self.job['description']+' EDIT'};self.store._entity(db,'vacancy',jd['id'],jd,NOW.isoformat())
  with self.assertRaisesRegex(ValueError,'изменились'):batch.start(self.app.store,self.store,p['id'])
 def test_cached_import_is_reused_and_foreign_or_invalid_results_are_rejected(self):
  p=self.plan(1);batch.export_prompt(self.app.store,self.store,p['id']);saved=batch.read(self.app.store,p['id'])['payload'];eid=saved['exports'][0];answer=json.dumps({'results':[{'export_id':eid,'analysis':self.raw}]})
  result=batch.import_results(self.app.store,self.store,p['id'],answer);self.assertEqual(result['imported'],1);self.assertEqual(result['errors'],[])
  self.assertEqual(batch.import_results(self.app.store,self.store,p['id'],answer)['imported'],1)
  self.assertEqual(self.plan(1)['summary']['api_needed'],0)
  t=batch.start(self.app.store,self.store,p['id'])
  with patch.object(self.app,'analyze_context',side_effect=AssertionError('Cache must avoid API')):self.step();self.step()
  t=batch.task(self.app.store,t['id']);self.assertEqual(t['state'],'complete');self.assertEqual(t['progress']['cached'],1);self.assertEqual(t['progress']['api_requests'],0)
  bad=batch.import_results(self.app.store,self.store,p['id'],json.dumps({'results':[{'export_id':'f'*64,'analysis':self.raw}]}));self.assertEqual(bad['imported'],0);self.assertEqual(len(bad['errors']),1)
 def test_pause_cancel_revision_and_restart_preserve_progress(self):
  t=self.start(2)
  def run(*_):
   live=batch.task(self.app.store,t['id']);batch.control(self.app.store,t['id'],'pause',live['revision']);return {'key':'mock','api_requests':1}
  with patch.object(self.app,'analyze_context',side_effect=run) as model:self.step();self.assertEqual(model.call_count,1)
  self.app=CareerApplication(ApplicationStore(self.store.path));live=self.app.task(t['id']);self.assertEqual(live['state'],'paused');self.assertEqual(live['progress']['done'],1)
  with self.assertRaises(ValueError):self.app.control_task(t['id'],'resume',t['revision'])
  live=self.app.control_task(t['id'],'resume',live['revision'])
  with patch.object(self.app,'analyze_context',return_value={'key':'mock2','api_requests':1}) as model:self.step();self.step();self.assertEqual(model.call_count,1)
  self.assertEqual(self.app.task(t['id'])['progress']['done'],2)
 def test_failed_and_crashed_attempts_never_replay(self):
  t=self.start(2)
  with patch.object(self.app,'analyze_context',side_effect=ValueError('provider failed')) as model:self.step();self.step();self.assertEqual(model.call_count,1)
  t=self.app.task(t['id']);self.assertEqual(t['state'],'needs_input');self.app.control_task(t['id'],'resume',t['revision'])
  with patch.object(self.app,'analyze_context',return_value={'key':'next','api_requests':1}) as model:self.step();self.step();self.assertEqual(model.call_count,1)
  t=self.start(1);p=batch.read(self.app.store,t['id'])['payload'];p['items'][0]['state']='started'
  with self.store.connect() as db:db.execute("UPDATE analysis_batches SET state='running',updated=?,payload=? WHERE id=?",(time.time()-601,json.dumps(p),t['id']))
  with patch.object(self.app,'analyze_context',side_effect=AssertionError('Do not replay')):self.step()
  self.assertEqual(self.app.task(t['id'])['state'],'needs_input');self.assertEqual(self.app.task(t['id'])['progress']['failed'],1)
 def test_closed_or_changed_job_before_step_never_calls_model(self):
  t=self.start()
  with self.store.connect() as db:db.execute("UPDATE entities SET availability='closed' WHERE kind='vacancy' AND id=?",(self.job['id'],))
  with patch.object(self.app,'analyze_context',side_effect=AssertionError('Closed')):self.step()
  self.assertEqual(self.app.task(t['id'])['state'],'needs_input')
 def test_authenticated_routes_and_diagnostics(self):
  with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
   body={'op':'preview','resume_id':self.cv['id'],'goal':self.goal,'limit':1}
   self.assertEqual(client.post('/archive/analytics-batch',json=body).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   self.assertEqual(client.post('/archive/analytics-batch',json=body,headers={'Origin':'https://evil.example'}).status_code,401)
   headers={'Origin':'http://127.0.0.1:8788'}
   with patch('src.skill_analysis.analyze',side_effect=AssertionError('No paid request')):
    r=client.post('/archive/analytics-batch',json=body,headers=headers);self.assertEqual(r.status_code,200,r.text);p=r.json();self.assertTrue(r.headers.get('X-Career-Request-Id'))
    self.assertEqual(client.get('/archive/analytics-batch/'+p['id']).status_code,200)
    self.assertEqual(client.post('/archive/analytics-batch',json={'op':'export','plan_id':p['id']},headers=headers).status_code,200)
    self.assertEqual(client.post('/archive/analytics-batch',json={'op':'bad'},headers=headers).status_code,422)
