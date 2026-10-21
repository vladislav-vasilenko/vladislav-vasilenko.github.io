import json,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.tests import test_telegram_ranking as fixtures
from src.manual_applications import set_mark,listing
from src.career_analytics import snapshot
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from resume_import_server import create_app

class ManualApplicationsTests(unittest.IsolatedAsyncioTestCase):
 def reopen(self):return self.service.__class__(ApplicationStore(self.store.path))
 async def asyncSetUp(self):await fixtures.TelegramRankingTests.asyncSetUp(self)
 async def test_mark_survives_restart_excludes_only_this_source_and_undo_restores(self):
  jid=self.jobs[0]['id'];before=[c['job']['id'] for c in self.service.candidates()]
  mark=set_mark(self.archive,jid,True,0);self.assertFalse(mark['site_confirmed']);self.assertEqual(mark['source'],'user')
  self.assertEqual(mark,set_mark(self.archive,jid,True,0))
  restored=ArchiveStore(self.archive.path);row=restored.detail('vacancy',jid);self.assertTrue(row['manual_application']['marked'])
  self.assertEqual([c['job']['id'] for c in self.reopen().candidates()],[v for v in before if v!=jid])
  self.assertEqual(next(r for r in snapshot(restored)['rows'] if r['id']==jid)['stage'],'applied')
  set_mark(restored,jid,False,mark['revision']);self.assertEqual([c['job']['id'] for c in self.reopen().candidates()],before)
  with self.archive.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM hh_observations WHERE vacancy_id=?",(jid,)).fetchone()[0],0)
 async def test_undo_does_not_erase_actual_site_confirmation(self):
  jid=self.jobs[0]['id'];mark=set_mark(self.archive,jid,True,0)
  self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':jid,'status':'submitted'}]})
  set_mark(self.archive,jid,False,mark['revision']);self.assertNotIn(jid,[c['job']['id'] for c in self.service.candidates()])
 async def test_no_cv_or_full_description_needed_and_no_model_or_browser_action(self):
  from src.tests.test_archive import job,record
  jd=job('hh_999',text='short');jd['description_quality']='snippet';self.archive.sync({'client_id':'manual-test','records':[record('vacancy',jd)]})
  with self.store.connect() as db:before=db.execute('SELECT COUNT(*) FROM browser_commands').fetchone()[0]
  with patch('openai.OpenAI',side_effect=AssertionError('No model')):set_mark(self.archive,jd['id'],True,0)
  self.assertEqual(listing(self.store)[0]['vacancy_id'],jd['id'])
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_commands').fetchone()[0],before)
 async def test_revision_and_new_preparation_guard(self):
  jid=self.jobs[0]['id'];mark=set_mark(self.archive,jid,True,0)
  with self.assertRaises(ValueError):set_mark(self.archive,jid,False,0)
  with self.assertRaisesRegex(ValueError,'уже отмечен'):self.service.make_application(self.f.cv['id'],jid,'Generative models')
  set_mark(self.archive,jid,False,mark['revision'])
 async def test_authenticated_route_and_common_crm_listing(self):
  jid=self.jobs[0]['id'];body={'op':'manual_application','vacancy_id':jid,'marked':True,'revision':0}
  with TestClient(create_app('fixture',archive_path=self.store.path)) as c:
   self.assertEqual(c.post('/archive/workflow',json=body).status_code,401);c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   self.assertEqual(c.post('/archive/workflow',json=body,headers={'Origin':'https://evil.example'}).status_code,401)
   r=c.post('/archive/workflow',json=body,headers={'Origin':'http://127.0.0.1:8788'});self.assertEqual(r.status_code,200,r.text)
   self.assertEqual(c.get('/archive/workflow').json()['manual_marks'][0]['vacancy_id'],jid)
   self.assertTrue(c.get('/archive/entities?kind=vacancy&limit=200').json()['items'][0].get('manual_application') is not None)
 async def test_running_browser_write_is_not_overridden_and_queued_write_is_revoked(self):
  command=self.store.queue_command('execute',self.f.id)
  with self.store.connect() as db:db.execute("UPDATE browser_commands SET state='running' WHERE id=?",(command,))
  with self.assertRaisesRegex(ValueError,'выполняется'):set_mark(self.archive,self.f.jd['id'],True,0)
  with self.store.connect() as db:db.execute("UPDATE browser_commands SET state='queued' WHERE id=?",(command,))
  set_mark(self.archive,self.f.jd['id'],True,0)
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT state FROM browser_commands WHERE id=?',(command,)).fetchone()[0],'cancelled')
  with self.assertRaisesRegex(ValueError,'уже отмечен'):self.store.validate_current(self.f.id,active=True)
