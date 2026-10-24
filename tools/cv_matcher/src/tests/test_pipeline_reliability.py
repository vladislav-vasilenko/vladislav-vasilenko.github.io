import asyncio,json,time,unittest
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from src.tests import test_workflow as workflow_fixtures
from src.tests.test_recruiter import Operator
from src.tests.test_archive import record
from src.workflow_bot import WorkflowBot
from src.application_store import ApplicationStore
from src.runtime_health import GigaHealth,read_health,write_health
from src import discovery

class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  f=workflow_fixtures.WorkflowTests('runTest');f.setUp();self.addCleanup(f.doCleanups);self.f=f;self.s=f.store;self.archive=f.archive
  self.op=Operator();self.bot=WorkflowBot(self.s,self.op,42)
 def profile(self):
  self.archive.sync({'client_id':'pipeline-test','records':[record('profile',{'primary_id':self.f.cv['id'],'goal':'Generative models'},'profile')]})
 def complete_source(self,run,ids=None):
  cmd=self.s.next_command('read-worker',kinds=['discover','collect'])['command'];self.assertEqual(cmd['kind'],'discover')
  self.s.finish_command(cmd['id'],'read-worker',{'state':'complete','ids':ids or [self.f.jd['id']]})
 async def test_105_events_are_all_queued_and_restart_does_not_duplicate_delivery(self):
  with self.s.connect() as db:
   for n in range(105):self.s._event(db,self.f.id,'career_fill_failed',{'note':str(n)})
  await self.bot.enqueue_event_notifications()
  reopened=WorkflowBot(ApplicationStore(self.s.path),self.op,42)
  await reopened.enqueue_event_notifications()
  with self.s.connect() as db:
   self.assertEqual(db.execute("SELECT COUNT(*) FROM workflow_delivery WHERE key LIKE 'event:%' AND state='sent'").fetchone()[0],105)
  self.assertEqual(len(self.op.messages),105)
 async def test_page_enqueue_crash_rolls_back_and_retry_keeps_all_events(self):
  with self.s.connect() as db:
   for n in range(3):self.s._event(db,self.f.id,'career_fill_failed',{'note':str(n)})
  original=self.bot.enqueue;calls=0
  def interrupted(*args,**kwargs):
   nonlocal calls
   calls+=1
   if calls==2:raise RuntimeError('Simulated process crash')
   return original(*args,**kwargs)
  with patch.object(self.bot,'enqueue',side_effect=interrupted):
   with self.assertRaises(RuntimeError):await self.bot.enqueue_event_notifications()
  with self.s.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM workflow_delivery').fetchone()[0],0)
  await self.bot.enqueue_event_notifications();self.assertEqual(len(self.op.messages),3)
 async def test_company_job_cannot_make_hh_connected(self):
  with self.s.connect() as db:db.execute("INSERT INTO browser_commands VALUES('fixture',?,'career_fill','{}','running','fixture',?,?,NULL)",(self.f.id,time.time(),time.time()))
  self.s.setting('career_worker_last_seen',time.time());health=self.s.browser_status()
  self.assertFalse(health['connected']);self.assertEqual(health['running'],0);self.assertTrue(health['workers']['career']['connected'])
 async def test_giga_health_reconnects_with_backoff_and_requires_identity_rpc(self):
  client=SimpleNamespace(is_connected=Mock(return_value=False),connect=AsyncMock(side_effect=OSError('secret')),get_me=AsyncMock())
  h=GigaHealth(self.s,client,42);self.assertFalse(await h.check(force=True));self.assertFalse(await h.check());self.assertEqual(client.connect.await_count,1)
  self.assertFalse(read_health(self.s,'giga')['connected']);self.assertNotIn('secret',self.s.setting('runtime:giga'))
  client.is_connected.return_value=True;client.get_me.return_value=SimpleNamespace(id=42,bot=False)
  self.assertTrue(await h.check(force=True));self.assertTrue(read_health(self.s,'giga')['connected'])
  client.get_me.side_effect=TimeoutError();self.assertFalse(await h.check(force=True));self.assertFalse(read_health(self.s,'giga')['connected'])
 async def test_stale_or_wrong_user_session_is_not_connected(self):
  write_health(self.s,'giga','connected',verified=True)
  saved=json.loads(self.s.setting('runtime:giga'));saved['checked_at']=time.time()-121;self.s.setting('runtime:giga',json.dumps(saved));self.assertFalse(read_health(self.s,'giga')['connected'])
  client=SimpleNamespace(is_connected=lambda:True,get_me=AsyncMock(return_value=SimpleNamespace(id=7,bot=False)))
  self.assertFalse(await GigaHealth(self.s,client,42).check(force=True));self.assertEqual(read_health(self.s,'giga')['state'],'unauthorized')
 async def test_schedule_starts_discovery_even_without_saved_ranking(self):
  self.profile();await self.bot.begin_digest('new-discovery')
  pending=json.loads(self.s.setting('pending_digest'));run=discovery.read(self.s,pending['discovery_id'])
  self.assertEqual(run['state'],'waiting_chrome');self.assertFalse(run['payload']['config']['allow_api'])
  cmd=self.s.next_command('read-worker',kinds=['discover','collect'])['command'];self.assertEqual(cmd['kind'],'discover');self.assertIn('resume=',cmd['payload']['source_url']);self.assertTrue(cmd['payload']['refresh_cv'])
  self.assertEqual(discovery.start(self.s,self.archive,'new-discovery')['id'],run['id'])
 async def test_collect_then_recalculate_uses_updated_cv_and_explicit_cost_mode(self):
  self.profile();discovery.config(self.s,{**discovery.DEFAULT,'allow_api':True})
  run=discovery.start(self.s,self.archive,'api-approved');self.complete_source(run)
  captured=[]
  def rank(payload,*args,**kwargs):captured.append(payload);return {'ranked_count':len(payload['vacancies']),'api_requests':1}
  result=discovery.advance(self.s,self.archive,run['id'],self.f.temp.name,ranker=rank)
  self.assertEqual(result['state'],'complete');self.assertTrue(captured[0]['allow_api']);self.assertEqual(captured[0]['resume_id'],self.f.cv['id'])
  discovery.advance(self.s,self.archive,run['id'],self.f.temp.name,ranker=rank);self.assertEqual(len(captured),1)
 async def test_offline_missing_embeddings_never_calls_api(self):
  self.profile();run=discovery.start(self.s,self.archive,'cache-only');self.complete_source(run)
  with patch('src.extension_ranking.OpenAIBackend.embed_documents',side_effect=ValueError('missing cache')) as embed:
   result=discovery.advance(self.s,self.archive,run['id'],self.f.temp.name)
  self.assertEqual(result['state'],'needs_embeddings');self.assertEqual(result['result']['api_requests'],0);self.assertEqual(result['result']['missing_embeddings'],1)
 async def test_source_sequence_and_changed_context_prevent_paid_ranking(self):
  self.profile();discovery.config(self.s,{**discovery.DEFAULT,'sources':['https://hh.ru/search/vacancy?text=ML','https://career.avito.com/vacancies/?direction=data-science']})
  run=discovery.start(self.s,self.archive,'two-sources');self.complete_source(run)
  next_run=discovery.advance(self.s,self.archive,run['id'],self.f.temp.name);self.assertEqual(next_run['state'],'collecting')
  self.complete_source(next_run)
  self.archive.sync({'client_id':'pipeline-test','records':[record('profile',{'primary_id':self.f.cv['id'],'goal':'changed'},'profile')]})
  rank=Mock();result=discovery.advance(self.s,self.archive,run['id'],self.f.temp.name,ranker=rank);self.assertEqual(result['state'],'needs_input');rank.assert_not_called()
 async def test_latest_missed_slot_is_caught_up_once_after_restart(self):
  from zoneinfo import ZoneInfo
  from src.career_notifications import config
  config(self.s,{'mode':'discovery'})
  with patch.object(self.bot,'begin_digest',new_callable=AsyncMock) as begin:
   await self.bot.tick(datetime(2026,10,17,10,30,tzinfo=ZoneInfo('Europe/Moscow')))
   self.assertEqual(begin.await_count,1);self.assertIn('T10:00:00+03:00',begin.call_args.args[0])
 async def test_expense_permission_is_frozen_for_existing_run(self):
  self.profile();run=discovery.start(self.s,self.archive,'frozen-offline')
  discovery.config(self.s,{**discovery.DEFAULT,'allow_api':True})
  self.assertFalse(discovery.read(self.s,run['id'])['payload']['config']['allow_api'])
 async def test_tbank_profile_is_saved_and_frozen_in_source_command(self):
  self.profile();discovery.config(self.s,{**discovery.DEFAULT,'sources':['https://www.tbank.ru/career/vacancies/all/moscow/'],'tbank_filters':['IT-разработка','Машинное обучение']})
  run=discovery.start(self.s,self.archive,'tbank-filters');command=self.s.next_command('collector',kinds=['discover','collect'])['command']
  self.assertEqual(command['payload']['options']['tbank_filters'],['IT-разработка','Машинное обучение']);self.assertFalse(command['payload']['options'].get('allow_api',False))
  discovery.config(self.s,{**discovery.DEFAULT,'tbank_filters':['Senior']})
  self.assertEqual(discovery.read(self.s,run['id'])['payload']['config']['tbank_filters'],['IT-разработка','Машинное обучение'])
 async def test_collect_queue_heartbeat_cannot_mark_hh_connected(self):
  self.s.next_command('collect-worker',kinds=['discover','collect']);h=self.s.browser_status()
  self.assertFalse(h['connected']);self.assertTrue(h['workers']['collection']['connected'])
 async def test_interrupted_ranking_is_never_retried(self):
  self.profile();run=discovery.start(self.s,self.archive,'crash')
  with self.s.connect() as db:db.execute("UPDATE discovery_runs SET state='ranking',updated=? WHERE id=?",(time.time()-301,run['id']))
  rank=Mock();result=discovery.advance(self.s,self.archive,run['id'],self.f.temp.name,ranker=rank);self.assertEqual(result['state'],'needs_input');rank.assert_not_called()
 async def test_multiple_sources_do_not_drop_jobs_above_ranker_batch_limit(self):
  self.profile();run=discovery.start(self.s,self.archive,'more-than-200');ids=['hh_'+str(n) for n in range(205)]
  self.complete_source(run,ids);original=self.archive.detail
  def detail(kind,jid):
   if kind=='resume':return original(kind,jid)
   return {'availability':'active','payload':{**self.f.jd,'id':jid,'link':'https://hh.ru/vacancy/'+jid[3:]}}
  sizes=[]
  def rank(payload,*args,**kwargs):sizes.append(len(payload['vacancies']));return {'ranked_count':len(payload['vacancies']),'api_requests':0}
  with patch.object(self.archive,'detail',side_effect=detail):result=discovery.advance(self.s,self.archive,run['id'],self.f.temp.name,ranker=rank)
  self.assertEqual(sizes,[200,5]);self.assertEqual(result['result']['ranked_count'],205)

class IntakeTests(unittest.TestCase):
 def setUp(self):
  self.f=workflow_fixtures.WorkflowTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
 def test_paste_yandex_job_enables_career_letter_without_ranking_or_embeddings(self):
  from src.vacancy_intake import import_text
  r=import_text(self.f.archive,{'url':'https://yandex.ru/jobs/vacancies/research-12345','title':'ML Research Engineer','company':'Yandex','text':'Обучать Transformer, разрабатывать модели на PyTorch. '*8,'confirmed_full':True})
  j=self.f.archive.detail('vacancy',r['vacancy_id']);self.assertEqual(j['payload']['description_quality'],'full');self.assertEqual(j['availability'],'unknown')
  a=self.f.store.create({'resume_id':self.f.cv['id'],'bundle':{'resumes':[self.f.cv]},'vacancy':j['payload'],'channel':'career'})
  self.assertEqual(a['context']['channel'],'career');self.assertEqual(r['api_requests'],0)
 def test_import_confirmation_and_collection_allowlist(self):
  from src.vacancy_intake import import_text,collect_one
  for url in ['http://127.0.0.1/private','https://127.0.0.1/x','https://evil.test/vacancies/1','https://user:pass@hh.ru/vacancy/1']:
   with self.assertRaises(ValueError):collect_one(self.f.store,url)
  with self.assertRaises(ValueError):import_text(self.f.archive,{'url':'https://hh.ru/vacancy/7','title':'Research','text':'PyTorch '*40,'confirmed_full':False})
  cmd=collect_one(self.f.store,'https://yandex.ru/jobs/vacancies/research-12345');self.assertTrue(cmd['command_id'])
 def test_tbank_service_identity_matches_browser_capture_and_is_accepted_by_archive(self):
  from src.vacancy_intake import import_text
  r=import_text(self.f.archive,{'url':'https://tbank.ru/career/service/vacancy/moscow/predstavitel/89f9888b-8a3e-4905-84c4-9c08a2f6c771/','title':'Представитель','text':'Доставляйте продукты банка и рассказывайте об их преимуществах. '*4,'confirmed_full':True})
  self.assertEqual(r['vacancy_id'],'tbank_89f9888b-8a3e-4905-84c4-9c08a2f6c771')
 def test_web_import_company_make_and_mock_letter_generation(self):
  from fastapi.testclient import TestClient
  from resume_import_server import create_app
  from src.application_conversation import discuss
  from unittest.mock import MagicMock
  fake=MagicMock();fake.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps({'reply':'Письмо готово.','draft_text':'Обучал Transformer на PyTorch. Хочу развивать генеративные модели в вашей команде.','needs_user':False,'missing':[],'evidence':['R1']}))
  with TestClient(create_app('fixture',archive_path=self.f.path)) as client:
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   headers={'Origin':'http://127.0.0.1:8788'}
   imported=client.post('/archive/workflow',json={'op':'vacancy_import','url':'https://yandex.ru/jobs/vacancies/ml-12345','title':'ML Research','company':'Yandex','text':'Обучать Transformer и разрабатывать генеративные модели на PyTorch. '*7,'confirmed_full':True},headers=headers);self.assertEqual(imported.status_code,200,imported.text)
   made=client.post('/archive/workflow',json={'op':'make','resume_id':self.f.cv['id'],'vacancy_id':imported.json()['vacancy_id'],'goal':'Generative models'},headers=headers);self.assertEqual(made.status_code,200,made.text);identifier=made.json()['id']
   with patch('src.application_conversation.discuss',side_effect=lambda s,a,m,r,model:discuss(s,a,m,r,model,client_factory=lambda:fake)):
    drafted=client.post('/archive/workflow',json={'op':'chat','app_id':identifier,'message':'Составь короткое сопроводительное письмо.','request_id':'mock-request-letter','model':'luna'},headers=headers)
   self.assertEqual(drafted.status_code,200,drafted.text);self.assertTrue(drafted.json()['draft_applied']);self.assertEqual(fake.responses.create.call_count,1)
   with self.f.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM ranking_runs').fetchone()[0],0)
