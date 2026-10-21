"""No network: free promotion policy, persistence, one-time claims and ownership."""
import asyncio,json,time,unittest
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from src.tests import test_workflow as fixtures
from src.tests.test_recruiter import Operator,update
from src.application_store import ApplicationStore
from src.application_workflow import packed
from src import resume_bump as bump
from src.workflow_bot import WorkflowBot

class ResumeBumpTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.WorkflowTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups);self.s=self.f.store;self.rid=self.f.cv['id']
 def enable(self):return bump.configure(self.s,{'enabled':True,'resume_ids':[self.rid]},bump.status(self.s)['revision'],True)
 def command(self):
  bump.tick(self.s);return self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command']
 def test_default_off_explicit_selection_and_confirmation(self):
  self.assertFalse(bump.status(self.s)['enabled']);bump.tick(self.s)
  with self.s.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM browser_commands WHERE kind='resume_bump'").fetchone()[0],0)
  for value,confirmed in [({'enabled':True,'resume_ids':[]},True),({'enabled':True,'resume_ids':[self.rid]},False),({'enabled':True,'resume_ids':['f'*38]},True)]:
   with self.assertRaises(ValueError):bump.configure(self.s,value,0,confirmed)
  self.enable()
  with self.assertRaises(ValueError):bump.configure(self.s,{'enabled':False,'resume_ids':[self.rid]},0)
 def test_offline_queue_is_durable_atomic_and_old_extensions_cannot_claim(self):
  self.enable()
  with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:bump.tick(ApplicationStore(self.s.path)),range(4)))
  self.assertEqual(bump.status(self.s)['resumes'][0]['state'],'queued');self.assertFalse(bump.status(self.s)['worker_ready'])
  self.assertIsNone(self.s.next_command('old-worker')['command'])
  self.assertIsNone(self.s.next_command('unversioned-worker',kinds=['resume_bump'])['command'])
  cmd=ApplicationStore(self.s.path).next_command('new-worker',kinds=['resume_bump'],resume_bump_version=1)['command'];self.assertEqual(cmd['payload']['resume_id'],self.rid)
  self.assertTrue(bump.status(self.s)['worker_ready'])
 def test_single_claim_cooldown_success_and_idempotent_receipt(self):
  self.enable();cmd=self.command()
  with self.assertRaises(ValueError):bump.claim(self.s,cmd['id'],'other-worker')
  with self.assertRaises(ValueError):bump.finish(self.s,cmd['id'],'bump-worker',{'outcome':'raised','evidence':'fake'})
  bump.claim(self.s,cmd['id'],'bump-worker')
  with self.assertRaises(ValueError):bump.claim(self.s,cmd['id'],'bump-worker')
  result={'state':'complete','outcome':'raised','resume_id':self.rid,'source_url':'https://hh.ru/applicant/profile/me','evidence':'Кнопка HH стала недоступна.','note':'Поднято.'}
  self.s.finish_command(cmd['id'],'bump-worker',result);self.assertTrue(self.s.finish_command(cmd['id'],'bump-worker',result)['replayed'])
  saved=bump.status(self.s)['resumes'][0];self.assertAlmostEqual(saved['next_at']-saved['last_success'],14400)
  bump.tick(self.s,now=saved['last_success']+14399);self.assertIsNone(self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command'])
  bump.tick(self.s,now=saved['next_at']+1);self.assertIsNotNone(self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command'])
  self.assertEqual(len([r for r in self.s.deliveries() if r['key'].startswith('resume-bump:')]),1)
 def test_claimed_crash_never_requeues_even_after_restart_and_manual_retry_needs_check(self):
  self.enable();cmd=self.command();bump.claim(self.s,cmd['id'],'bump-worker');bump.tick(ApplicationStore(self.s.path),now=time.time()+301)
  row=bump.status(self.s)['resumes'][0];self.assertTrue(row['blocked']);self.assertIsNone(self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command'])
  bump.tick(self.s);self.assertEqual(len([r for r in self.s.deliveries() if r['key'].startswith('resume-bump:')]),1)
  with self.assertRaises(ValueError):bump.retry(self.s,self.rid,False)
  bump.retry(self.s,self.rid,True);self.assertIsNotNone(self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command'])
 def test_disabling_revokes_pending_claim_and_never_changes_resume_visibility(self):
  self.enable();cmd=self.command();before=self.f.archive.detail('resume',self.rid)['payload']
  bump.configure(self.s,{'enabled':False,'resume_ids':[self.rid]},1)
  with self.assertRaises(ValueError):bump.claim(self.s,cmd['id'],'bump-worker')
  self.assertEqual(self.f.archive.detail('resume',self.rid)['payload'],before)
 def test_hidden_and_unknown_results_block_retries_cooldown_checks_do_not_claim(self):
  self.enable();cmd=self.command();self.s.finish_command(cmd['id'],'bump-worker',{'state':'complete','outcome':'cooldown'})
  self.assertFalse(bump.status(self.s)['resumes'][0]['blocked'])
  with self.s.connect() as db:self.s.setting_in(db,'hh-resume-bump:'+self.rid,'{}')
  cmd=self.command();self.s.finish_command(cmd['id'],'bump-worker',{'state':'needs_input','outcome':'not_visible','note':'Скрыто.'})
  self.assertTrue(bump.status(self.s)['resumes'][0]['blocked']);bump.tick(self.s,now=time.time()+20000)
  self.assertIsNone(self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command'])
 def test_task_cancel_stops_future_schedule_for_that_resume(self):
  self.enable();bump.tick(self.s)
  with self.s.connect() as db:identifier=db.execute("SELECT id FROM browser_commands WHERE kind='resume_bump'").fetchone()[0]
  from src.agent_tasks import get,control
  task=get(self.s,'browser:'+identifier);self.assertEqual(task['actions'],['cancel']);control(self.s,task['id'],'cancel',task['revision'],actor='owner')
  bump.tick(self.s);self.assertTrue(bump.status(self.s)['resumes'][0]['blocked']);self.assertIsNone(self.s.next_command('bump-worker',kinds=['resume_bump'],resume_bump_version=1)['command'])
 def test_http_auth_cookie_cannot_claim_and_origin_is_checked(self):
  from resume_import_server import create_app
  with TestClient(create_app('fixture',archive_path=self.s.path)) as client:
   self.assertEqual(client.post('/archive/workflow',json={'op':'resume_bump'}).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   self.assertEqual(client.post('/archive/workflow',json={'op':'resume_bump_claim','command_id':'x','worker_id':'bump-worker'},headers={'Origin':'http://127.0.0.1:8788'}).status_code,403)
   response=client.post('/archive/workflow',json={'op':'resume_bump_save','config':{'enabled':True,'resume_ids':[self.rid]},'revision':0,'confirmed':True},headers={'Origin':'https://evil.example'})
   self.assertEqual(response.status_code,401)
   response=client.post('/archive/workflow',json={'op':'resume_bump_save','config':{'enabled':True,'resume_ids':[self.rid]},'revision':0,'confirmed':True},headers={'Origin':'http://127.0.0.1:8788'})
   self.assertEqual(response.status_code,200,response.text)
 def test_telegram_button_binds_cv_owner_revision_and_expiry(self):
  async def run():
   from src.tests.test_archive import record,CLIENT
   self.f.archive.sync({'client_id':CLIENT,'records':[record('profile',{'primary_id':self.rid,'goal':''},'profile')]})
   op=Operator();bot=WorkflowBot(self.s,op,42);await bot.resume_bump_menu();buttons=[b for row in op.messages[-1][1] for b in row];enable=next(b[1] for b in buttons if b[1].startswith('w:bumpon:'))
   await bot.update(update(callback=enable,owner=99));self.assertFalse(bump.status(self.s)['enabled'])
   await bot.update(update(callback=enable));self.assertTrue(bump.status(self.s)['enabled'])
   revision=bump.status(self.s)['revision'];await bot.update(update(callback=enable));self.assertEqual(bump.status(self.s)['revision'],revision)
  asyncio.run(run())
