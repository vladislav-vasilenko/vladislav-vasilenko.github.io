import unittest
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
from src.tests import test_career_field_transfer as transfer
from src.application_readiness import read,open_career

class ApplicationReadinessTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):await transfer.CareerTransferTests.asyncSetUp(self)
 async def test_stale_activity_keeps_preparation_available_but_transfer_requires_refresh(self):
  self.job['availability_checked_at']=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat();self.f.sync(self.f.cv,self.job)
  ready=read(self.s,self.a['id']);self.assertTrue(ready['can_prepare']);self.assertFalse(ready['activity_fresh']);self.assertEqual(ready['issues'][0]['code'],'activity')
  intent=self.s.career_fill_intent(self.a['id'])
  with self.assertRaisesRegex(ValueError,'свежая проверка'):self.s.approve_career_fill(self.a['id'],intent['intent_hash'],True)
  self.assertEqual(self.s.workflow(self.a['id'])['workflow']['draft'],'Мой проверенный сопроводительный текст.')
 async def test_open_form_is_deduplicated_and_separate_from_approved_field_transfer(self):
  a=open_career(self.s,self.a['id']);b=open_career(self.s,self.a['id']);self.assertEqual(a,b)
  self.assertIsNone(self.s.next_command('legacy-hh-worker')['command'])
  cmd=self.s.next_command('career-open-worker',kinds=['career_open'])['command'];self.assertEqual(cmd['app_id'],self.a['id']);self.assertEqual(cmd['payload']['url'],self.snapshot['source_url'])
  before=self.s.workflow(self.a['id'])['workflow']['draft'];self.s.finish_command(cmd['id'],'career-open-worker',{'state':'complete','note':'Only read'})
  after=self.s.workflow(self.a['id']);self.assertEqual(after['workflow']['draft'],before);self.assertEqual(after['status'],'queued');self.assertFalse(after['approvals'])
  self.assertFalse(self.s.browser_status()['auto_sync']['worker_ready'])
 async def test_closed_vacancy_blocks_form_open_and_owner_cannot_submit_browser_snapshot(self):
  self.job['archived']=True;self.f.sync(self.f.cv,self.job)
  with self.assertRaisesRegex(ValueError,'закрыта'):open_career(self.s,self.a['id'])
  from resume_import_server import create_app
  with TestClient(create_app('fixture',archive_path=self.s.path)) as client:
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   response=client.post('/archive/workflow',json={'op':'career_form_for_application','app_id':self.a['id'],'snapshot':self.snapshot},headers={'Origin':'http://127.0.0.1:8788'})
   self.assertEqual(response.status_code,403)

 async def test_company_health_is_independent_from_hh_and_assets_are_served(self):
  import time
  from resume_import_server import create_app
  self.s.setting('hh_worker_last_seen',str(time.time()))
  ready=read(self.s,self.a['id']);self.assertFalse(ready['browser']['connected'])
  self.s.next_command('company-worker',kinds=['career_open'])
  ready=read(self.s,self.a['id']);self.assertTrue(ready['browser']['connected'])
  with TestClient(create_app('fixture',archive_path=self.s.path)) as client:
   html=client.get('/').text
   for name in ('workflow-core','workflow-letter','workflow-career'):
    response=client.get('/assets/'+name+'.js');self.assertEqual(response.status_code,200)
    self.assertIn(name,html);self.assertNotIn('text/html',response.headers['content-type'])
