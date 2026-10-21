"""No network: approval, CRM, persisted observations, drafting and scheduled selection."""
import json,tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from fastapi.testclient import TestClient
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src.resume_source import content_hash
from src.application_workflow import packed,hashed,CRM_STAGES
from src.application_conversation import discuss
from src.workflow_bot import WorkflowBot
from src.analysis_store import text_hash,document_text
from src.tests.test_archive import cv,job,record,CLIENT
from src.tests.test_recruiter import Operator,update

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'state.sqlite3';self.store=ApplicationStore(self.path);self.archive=ArchiveStore(self.path)
  at=datetime.now(timezone.utc).isoformat();self.cv=cv(text='Обучал Transformer на PyTorch. Воспроизводимые эксперименты с SFT. '*6,at=at);self.cv['content_hash']=content_hash(self.cv);self.jd=job(at=at);self.sync(self.cv,self.jd)
  self.app=self.store.create({'resume_id':self.cv['id'],'bundle':{'resumes':[self.cv]},'vacancy':self.jd,'channel':'hh','goal':'Generative models'})
  self.id=self.app['id'];self.store.save_letter(self.id,'Обучал Transformer на PyTorch. Хочу развивать генеративные модели.',0)
 def sync(self,cv,job):self.archive.sync({'client_id':CLIENT,'records':[record('resume',cv),record('vacancy',job)]})
 def form(self,**extra):return {'state':'form','selected_resume_id':self.cv['id'],'fingerprint':'before','submit_label':'Отправить','fields':[{'id':'f0','label':'Сопроводительное письмо','purpose':'cover','type':'textarea','required':False,'value':self.store.workflow(self.id)['workflow']['draft'],'options':[]}],**extra}
 def approve(self):
  self.store.prepared(self.id,self.form());intent=self.store.intent(self.id);return self.store.approve(self.id,intent['intent_hash'],confirmed=True)
 def execute(self):
  approval=self.approve();command=self.store.next_command('worker-1')['command'];self.assertEqual(command['id'],approval['command_id']);intent=self.store.claim_approval(command['id'],'worker-1','before');return command,intent
 def test_permission_exact_content_single_use_and_edit_revokes(self):
  a=self.approve();self.store.save_letter(self.id,'Новое письмо.',1)
  self.assertIsNone(self.store.next_command('worker-1')['command'])
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT status FROM application_approvals WHERE id=?',(a['approval_id'],)).fetchone()[0],'revoked')
  command,intent=self.execute()
  with self.assertRaises(ValueError):self.store.claim_approval(command['id'],'worker-1','before')
  with self.assertRaises(ValueError):self.store.save_letter(self.id,'Во время отправки',2)
 def test_journey_is_shared_read_only_and_tracks_attention(self):
  from src.journey import overview
  before=overview(self.store);self.assertEqual(before['cv'],None);self.assertEqual(before['items'][0]['next'],'Подготовить форму HH')
  self.store.prepared(self.id,self.form());after=overview(self.store);self.assertEqual(after['items'][0]['next'],'Проверить ответы и разрешить действие');self.assertTrue(after['items'][0]['needs_attention'])
  from resume_import_server import create_app
  with TestClient(create_app('fixture',archive_path=self.path)) as client:
   self.assertEqual(client.get('/archive/journey').status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   self.assertEqual(client.get('/archive/journey').status_code,200)
 def test_browser_errors_are_explained_instead_of_forwarding_raw_javascript(self):
  from src.workflow_bot import browser_note
  note=browser_note("Cannot read properties of null (reading 'state')");self.assertIn('Не удалось прочитать форму HH',note);self.assertNotIn('Cannot read',note)
  self.assertEqual(browser_note('Вакансия закрыта.'),'Вакансия закрыта.')
 def test_worker_status_reports_real_contact_and_expires_without_changing_application(self):
  self.assertFalse(self.store.browser_status()['connected'])
  self.assertIsNone(self.store.next_command('worker-1')['command']);self.assertTrue(self.store.browser_status()['connected'])
  self.store.setting('hh_worker_last_seen',time.time()-400);self.assertFalse(self.store.browser_status()['connected'])
  self.assertEqual(self.store.get(self.id)['status'],'queued')
 def test_closed_changed_cv_and_changed_job_block_approval(self):
  self.store.prepared(self.id,self.form());intent=self.store.intent(self.id)
  with self.assertRaises(ValueError):self.store.approve(self.id,intent['intent_hash'],confirmed=False)
  for kind,change in [('vacancy',{'archived':True}),('resume',{'content_hash':'changed'}),('vacancy',{'description':'Новые требования'})]:
   original=self.archive.detail(kind,self.cv['id'] if kind=='resume' else 'hh_1')['payload'];altered={**original,**change}
   with self.store.connect() as db:db.execute('UPDATE entities SET payload=? WHERE kind=?',(packed(altered),kind))
   with self.assertRaises(ValueError):self.store.approve(self.id,intent['intent_hash'],confirmed=True)
   with self.store.connect() as db:db.execute('UPDATE entities SET payload=? WHERE kind=?',(packed(original),kind))
 def test_expired_permission_or_different_worker_never_claims(self):
  a=self.approve();self.store.next_command('worker-1')
  with self.assertRaises(ValueError):self.store.claim_approval(a['command_id'],'worker-2','before')
  with self.assertRaises(ValueError):self.store.claim_approval(a['command_id'],'worker-1','changed')
  with self.store.connect() as db:db.execute('UPDATE application_approvals SET expires=?',(time.time()-1,))
  with self.assertRaises(ValueError):self.store.claim_approval(a['command_id'],'worker-1','before')
 def test_next_question_requires_new_exact_approval(self):
  command,_=self.execute();next_form=self.form(fingerprint='next',submit_label='Продолжить',fields=[{'id':'q1','label':'Зарплата?','type':'text','required':True,'value':'','options':[]}])
  self.store.prepared(self.id,next_form,command_id=command['id']);self.store.finish_command(command['id'],'worker-1',{'state':'needs_input'})
  with self.assertRaises(ValueError):self.store.intent(self.id)
  new=self.store.intent(self.id,{'q1':'По договорённости'});a=self.store.approve(self.id,new['intent_hash'],{'q1':'По договорённости'},confirmed=True)
  self.assertNotEqual(command['id'],a['command_id'])
 def test_success_requires_vacancy_bound_proof_and_is_stored(self):
  command,_=self.execute()
  with self.assertRaises(ValueError):self.store.finish_command(command['id'],'worker-1',{'state':'submitted','source_url':'https://hh.ru/vacancy/2','evidence':'Отклик отправлен'})
  self.store.finish_command(command['id'],'worker-1',{'state':'submitted','source_url':self.jd['link'],'evidence':'Отклик отправлен'})
  self.assertEqual(self.store.get(self.id)['status'],'submitted');self.assertEqual(self.store.hh_inbox()['items'][0]['status'],'submitted')
  self.assertTrue(self.store.finish_command(command['id'],'worker-1',{'state':'submitted','source_url':self.jd['link'],'evidence':'Отклик отправлен'})['replayed'])
  with self.assertRaises(ValueError):self.store.finish_command(command['id'],'worker-2',{'state':'submitted','source_url':self.jd['link'],'evidence':'Отклик отправлен'})
 def test_failure_after_claim_is_uncertain_no_auto_retry_and_explicit_recovery(self):
  command,_=self.execute();self.store.finish_command(command['id'],'worker-1',{'state':'failed','note':'network'})
  self.assertEqual(self.store.workflow(self.id)['workflow']['state'],'uncertain');self.assertIsNone(self.store.next_command('worker-1')['command'])
  with self.assertRaises(ValueError):self.store.recover_unsent(self.id,False)
  self.store.recover_unsent(self.id,True);self.assertIsNone(self.store.workflow(self.id)['workflow']['form'])
 def test_observations_dedup_messages_no_absence_inference_and_unbound_chat(self):
  snap={'source_url':'https://hh.ru/applicant/negotiations','observed_at':datetime.now(timezone.utc).isoformat(),'records':[{'vacancy_id':'hh_1','status':'viewed','thread_id':'thread:12','messages':[{'id':'a','text':'Здравствуйте','direction':'incoming'}]}]}
  self.store.hh_sync(snap);self.assertEqual(self.store.hh_sync(snap)['messages_added'],0)
  self.store.hh_sync({**snap,'records':[]});self.assertEqual(self.store.get(self.id)['status'],'viewed')
  self.store.hh_sync({**snap,'records':[{'thread_id':'unbound-2','messages':[{'text':'Чат без вакансии'}]}]});self.assertEqual(len(self.store.hh_inbox()['unbound_threads']),1)
  with self.assertRaises(ValueError):self.store.bind_thread('unbound-2',self.id,False)
  self.store.bind_thread('unbound-2',self.id,True);self.assertEqual(len(self.store.workflow(self.id)['hh_messages']),2)
  with self.assertRaises(ValueError):self.store.hh_sync({**snap,'records':[{'vacancy_id':'hh_2','status':'viewed','thread_id':'thread:12'}]})
 def test_crm_history_survives_hh_sync_and_offer_invalidates_pending_send(self):
  a=self.approve();self.store.set_crm(self.id,'stage_1','Техническое интервью назначено')
  self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':'hh_1','status':'invited'}]})
  self.assertEqual(self.store.workflow(self.id)['crm']['stage'],'stage_1');self.assertEqual(self.store.get(self.id)['status'],'invited')
  self.store.set_crm(self.id,'offer','Оффер получен');self.assertEqual(ApplicationStore(self.path).workflow(self.id)['crm']['stage'],'offer')
  events=[e for e in self.store.workflow(self.id)['events'] if e['type']=='crm_stage'];self.assertEqual(len(events),2);self.assertEqual(events[0]['payload']['before'],'stage_1')
  with self.assertRaises(ValueError):self.store.set_crm(self.id,'hired-by-model')
 def test_drafting_idempotent_records_versions_and_preserves_manual_edit(self):
  client=MagicMock();client.responses.create.return_value=SimpleNamespace(status='completed',output_text=packed({'reply':'Сократил письмо.','draft_text':'Обучал Transformer на PyTorch.','needs_user':False,'missing':[],'evidence':['R1']}))
  # Obtain actual passage ID instead of assuming segment numbering.
  from src.cover_letter import source_passages
  passage=next(iter(source_passages(self.app['context']['resume_text'],'R')));data=json.loads(client.responses.create.return_value.output_text);data['evidence']=[passage];client.responses.create.return_value.output_text=packed(data)
  first=discuss(self.store,self.id,'Сократи письмо.','request-id-001',client_factory=lambda:client);second=discuss(self.store,self.id,'Сократи письмо.','request-id-001',client_factory=lambda:client)
  self.assertTrue(first['draft_applied']);self.assertTrue(second['cached']);self.assertEqual(client.responses.create.call_count,1);self.assertEqual(len(self.store.workflow(self.id)['draft_versions']),2)
  self.assertFalse(client.responses.create.call_args.kwargs['store'])
 def test_inline_reads_current_crm_letter_without_model_and_rejects_changed_cv_or_goal(self):
  from src.hh_inline import run
  params={'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'vacancy_id':self.jd['id'],'goal':'Generative models','action':'cover_read'}
  first=run(self.archive,params,Path(self.temp.name))['result'];self.assertEqual(first['text'],self.store.workflow(self.id)['workflow']['draft']);self.assertEqual(first['api_requests'],0);self.assertEqual(first['source'],'crm')
  self.assertIsNone(run(self.archive,{**params,'goal':'Another goal'},Path(self.temp.name))['result'])
  newer={**self.cv,'title':'Changed CV'};newer['content_hash']=content_hash(newer);self.sync(newer,self.jd)
  self.assertIsNone(run(self.archive,{**params,'resume_hash':newer['content_hash']},Path(self.temp.name))['result'])
 def test_generation_error_never_exposes_key_or_sdk_message(self):
  client=MagicMock();error=Exception('sk-secret-sensitive');error.status_code=401;client.responses.create.side_effect=error
  with self.assertRaisesRegex(ValueError,'401') as raised:discuss(self.store,self.id,'Составь письмо.','request-auth-error',client_factory=lambda:client)
  self.assertNotIn('sk-secret',str(raised.exception));self.assertIn('OPENAI_API_KEY',str(raised.exception))
 def test_renewed_cv_preserves_previous_letter_context_and_revokes_approval(self):
  self.approve();updated={**self.cv,'title':'Updated Research CV'};updated['content_hash']=content_hash(updated)
  self.sync(updated,self.jd);new=self.store.renew_context(self.id,updated,self.jd,'Generative models')
  self.assertNotEqual(new['id'],self.id);self.assertEqual(new['context']['resume_title'],'Updated Research CV');self.assertEqual(new['workflow']['draft'],'')
  old=self.store.workflow(self.id);self.assertEqual(old['status'],'superseded');self.assertEqual(old['context']['resume_title'],self.cv['title']);self.assertEqual(len(old['draft_versions']),1)
  with self.assertRaises(ValueError):self.store.intent(self.id)
  self.assertIsNone(self.store.next_command('worker-1')['command'])
 def test_cookie_can_edit_crm_but_not_impersonate_browser_worker(self):
  from resume_import_server import create_app
  app=create_app('fixture-code');app.state.archive_store=lambda:self.archive
  with TestClient(app) as c:
   self.assertEqual(c.get('/archive/workflow').status_code,401)
   c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture-code'})
   h={'Origin':'http://127.0.0.1:8788'}
   self.assertEqual(c.post('/archive/workflow',json={'op':'crm','app_id':self.id,'stage':'recruiter'},headers=h).status_code,200)
   self.assertEqual(c.post('/archive/workflow',json={'op':'next','worker_id':'worker-1'},headers=h).status_code,403)
   self.assertEqual(c.post('/archive/workflow',json={'op':'crm','app_id':self.id,'stage':'offer'},headers={'Origin':'https://example.com'}).status_code,401)

class WorkflowBotTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=ApplicationStore(Path(self.temp.name)/'state.sqlite3');self.operator=Operator();self.bot=WorkflowBot(self.store,self.operator,42)
 async def test_owner_only_and_crm_commands_do_not_invoke_model(self):
  await self.bot.update(update(text='/today',owner=99));self.assertEqual(self.operator.messages,[])
  await self.bot.update(update(text='/start'));self.assertIn('10:00',self.operator.messages[-1][0]);self.assertEqual(self.store.setting('pending_digest'),None)
 async def test_schedule_is_moscow_twice_daily_and_deduplicated_on_restart(self):
  at=datetime(2026,10,16,10,0,tzinfo=self.bot.zone)
  await self.bot.tick(at);n=len(self.operator.messages);await WorkflowBot(self.store,self.operator,42).tick(at+timedelta(minutes=1));self.assertEqual(len(self.operator.messages),n)
  await self.bot.tick(at.replace(hour=19));self.assertEqual(len(self.operator.messages),n+1)
  await self.bot.tick(at.replace(hour=22));self.assertEqual(len(self.operator.messages),n+1)
 async def test_selector_requires_current_cv_job_goal_rank_and_fresh_active_detail(self):
  at=datetime.now(timezone.utc);c=cv(text='Transformer PyTorch training. '*8,at=at.isoformat());c['content_hash']=content_hash(c);j=job(at=at.isoformat());archive=self.bot.archive
  archive.sync({'client_id':CLIENT,'records':[record('resume',c),record('vacancy',j),record('profile',{'primary_id':c['id'],'goal':'DiT'},'profile')]})
  run={'resume_id':c['id'],'resume_hash':c['content_hash'],'goal':'DiT','model':'text-embedding-3-small','generated_at':at.isoformat(),'all':[{'id':j['id'],'score':.8,'vacancy_hash':text_hash(document_text('vacancy',j))}]}
  with self.store.connect() as db:db.execute('INSERT INTO ranking_runs VALUES(?,?,?,?,?)',('run1',c['id'],run['model'],at.isoformat(),packed(run)))
  self.assertEqual(len(self.bot.candidates(now=at,fresh=True)),1)
  for change in [{'archived':True},{'collected_at':(at-timedelta(hours=1)).isoformat()},{'description':'JD changed'},{'source_page':'https://hh.ru/search/vacancy'}]:
   with self.store.connect() as db:db.execute("UPDATE entities SET payload=? WHERE kind='vacancy'",(packed({**j,**change}),))
   self.assertEqual(self.bot.candidates(now=at,fresh=True),[])
  with self.store.connect() as db:db.execute("UPDATE entities SET payload=? WHERE kind='vacancy'",(packed(j),))
  self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':'hh_1','status':'submitted'}]});self.assertEqual(self.bot.candidates(now=at,fresh=True),[])
 async def test_telegram_crm_buttons_are_owner_only_and_keep_transition_history(self):
  stamp=datetime.now(timezone.utc).isoformat();c=cv(text='Transformer PyTorch training. '*8,at=stamp);c['content_hash']=content_hash(c);j=job(at=stamp)
  self.bot.archive.sync({'client_id':CLIENT,'records':[record('resume',c),record('vacancy',j)]})
  a=self.store.create({'bundle':{'resumes':[c]},'resume_id':c['id'],'vacancy':j,'channel':'hh'})
  await self.bot.update(update(callback=f'w:stages:{a["id"]}'));self.assertEqual({row[0][1].split('@')[-1] for row in self.operator.messages[-1][1][:-1]},set(CRM_STAGES))
  await self.bot.update(update(callback=f'w:stage:{a["id"]}@offer',owner=99));self.assertEqual(self.store.workflow(a['id'])['crm']['stage'],'preparing')
  for stage in ('recruiter','stage_1','stage_2','stage_3','offer'):
   await self.bot.update(update(callback=f'w:stage:{a["id"]}@{stage}'));self.assertEqual(self.store.workflow(a['id'])['crm']['stage'],stage)
  history=[e for e in self.store.workflow(a['id'])['events'] if e['type']=='crm_stage'];self.assertEqual(len(history),5);self.assertEqual(history[0]['payload']['actor'],'telegram_user')

 async def test_unconnected_chrome_timeout_does_not_claim_vacancies_are_closed(self):
  command=self.store.queue_command('refresh',payload={'ids':['hh_1']})
  self.store.setting('pending_digest',packed({'key':'manual-test','command':command,'started':time.time()-601,'ids':['hh_1']}))
  await self.bot.finish_digest()
  self.assertIn('Chrome не начал',self.operator.messages[-1][0]);self.assertIn('не означает, что они закрыты',self.operator.messages[-1][0])
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT state FROM browser_commands WHERE id=?',(command,)).fetchone()[0],'cancelled')
  self.assertEqual(self.store.hh_inbox()['items'],[])
 async def test_status_explains_exact_chrome_setup_and_authorized_userbot(self):
  from src.runtime_health import write_health
  write_health(self.store,'giga','connected',verified=True)
  self.bot.giga_ready=True;await self.bot.update(update(text='/status'))
  message=self.operator.messages[-1][0];self.assertIn('Telethon/Giga: на связи (RPC подтверждён)',message);self.assertIn('chrome://extensions',message);self.assertIn('5. Отклик',message)
