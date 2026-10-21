"""Telegram-to-browser integration with temporary SQLite and fake external IO.

Uses actual intent, search, ranking, Luna validation, drafting, Chrome wfPrepare,
CRM and approval validation. No live Telegram, paid model or recruiter submission.
"""
import json,time,unittest,subprocess
from pathlib import Path
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import Mock,patch
from src.tests import test_career_agent as fixtures
from src.tests.test_archive import job,record
from src.tests.test_recruiter import Operator,update
from src.tests.test_extension_ranking import FakeBackend
from src.career_application import CareerApplication
from src.workflow_bot import WorkflowBot
from src.application_store import ApplicationStore
from src.application_workflow import packed,hashed
from src.application_preparation import advance as prepare
from src.extension_ranking import rank_vacancies
from src.skill_analysis import analyze,context,cached
from src.application_conversation import discuss
from src import discovery

ROOT=Path(__file__).resolve().parents[2]
QUERY='Найди новые вакансии за последние семь дней в Яндексе, Сбере, Ozon и Авито. Интересуют LLM Pretraining, Post-training, Diffusion и Deep Learning Research. Выбери десять наиболее подходящих.'

class MilestoneTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  await fixtures.CareerAgentTests.asyncSetUp(self)
  self.f.jd={**self.f.jd,'description':self.f.jd['description']*5}
  self.archive.sync({'client_id':'milestone-fixture','records':[record('vacancy',self.f.jd)]})
  # Replace the untouched fixture case context; no submitted application exists.
  with self.store.connect() as db:
   ctx=json.loads(db.execute('SELECT context FROM applications WHERE id=?',(self.f.id,)).fetchone()[0]);ctx['vacancy']['description']=self.f.jd['description'];db.execute('UPDATE applications SET context=? WHERE id=?',(packed(ctx),self.f.id))
 def bot(self):return WorkflowBot(ApplicationStore(self.store.path),Operator(),42)
 def rank(self,payload,path,archive):return rank_vacancies(payload,path,archive=archive,backend_factory=FakeBackend)
 def clients(self,app):
  ctx=context(self.archive,app['context']['resume_id'],app['context']['vacancy']['id'],app['context']['goal'])
  from src.cover_letter import source_passages
  quote=next(iter(source_passages(ctx['jd_text'],'J').values()))[:80]
  raw={'requirements':[{'requirement':'Практическая разработка моделей','dimension':'engineering','importance':'must','status':'confirmed','job_passage_id':'J1','job_quote':quote,'resume_passage_ids':['R1'],'explanation':'В CV описана работа с PyTorch; масштабы нужно уточнить.','action':'Уточнить задачи.'}],'goal_alignment':'Исследовательская работа близка цели.','recommendation':'apply','recommendation_reason':'Есть подтверждённый опыт.','questions':[],'limitations':['Анализ только текстов.']}
  luna=Mock();luna.responses.create.return_value=SimpleNamespace(status='completed',output_text=packed(raw),usage=SimpleNamespace(input_tokens=10,output_tokens=10))
  editor=Mock();editor.responses.create.return_value=SimpleNamespace(status='completed',output_text=packed({'reply':'Письмо готово к проверке.','draft_text':'Работал с PyTorch и Transformer. Хочу развивать генеративные модели.','needs_user':False,'missing':[],'evidence':['R1']}))
  return luna,editor
 async def test_exact_user_query_persists_four_sources_period_and_topics_across_restart(self):
  bot=self.bot();await bot.update(update(text=QUERY))
  pending=json.loads(self.store.setting('pending_digest'));run=discovery.read(self.store,pending['discovery_id']);scope=run['payload']['scope']
  self.assertEqual(set(scope['companies']),{'yandex','sber','ozon','avito'});self.assertEqual(scope['since_days'],7);self.assertEqual(scope['limit'],10);self.assertEqual(len(scope['topics']),4);self.assertEqual(len(run['payload']['sources']),4)
  self.assertEqual(run['state'],'waiting_chrome');self.assertFalse(run['payload']['config']['allow_api'])
  await self.bot().update(update(text=QUERY));self.assertEqual(len(self.service.tasks()),1)
  with self.assertRaisesRegex(ValueError,'другими условиями'):await self.service.search('new-scope',{'companies':['tbank']})
 async def test_telegram_search_luna_draft_real_browser_worker_then_human_review_no_submit(self):
  bot=self.bot();await bot.update(update(text='найди вакансии'))
  run_id=json.loads(self.store.setting('pending_digest'))['discovery_id'];command=self.store.next_command('fixture-reader',kinds=['discover'])['command']
  self.store.finish_command(command['id'],'fixture-reader',{'state':'complete','ids':[self.f.jd['id']],'coverage':'complete'})
  result=discovery.advance(self.store,self.archive,run_id,self.f.temp.name,ranker=self.rank);self.assertEqual(result['state'],'complete',result)
  await bot.finish_digest();refs=json.loads(self.store.setting('last-recommendations'))['refs'];ref=refs[0]
  why=json.loads(self.store.setting('recommendation:'+ref))['explanation'];self.assertIsNotNone(why['qualification_fit']['semantic_similarity']);self.assertIn('не доля',why['qualification_fit']['meaning'])
  await bot.update(update(callback='w:pick:'+ref));app=self.store.workflow(self.f.id);luna,editor=self.clients(app)
  await bot.update(update(callback='w:pstart:'+self.f.id+'@'+str(app['workflow']['revision'])));await bot.update(update(callback='w:pstart:'+self.f.id+'@'+str(app['workflow']['revision'])))
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM application_preparations').fetchone()[0],1)
  result=prepare(CareerApplication(ApplicationStore(self.store.path)),analyzer=lambda a,r,j,g:analyze(a,r,j,g,client_factory=lambda:luna),drafter=lambda s,i,m,q,model:discuss(s,i,m,q,model,client_factory=lambda:editor))
  self.assertEqual(result['state'],'waiting_chrome',result);self.assertEqual(luna.responses.create.call_count,1);self.assertEqual(editor.responses.create.call_count,1)
  command=self.store.next_command('e2e-reader')['command'];self.assertEqual(command['kind'],'prepare')
  bridge=subprocess.run(['node',str(ROOT/'hh-research-extension/fixtures/preparation-bridge.mjs')],input=packed(command),text=True,capture_output=True,check=True)
  browser=json.loads(bridge.stdout);self.assertEqual(browser['filled'],1);self.assertEqual(browser['submitted'],0)
  self.store.prepared(self.f.id,browser['snapshot'],command_id=command['id']);self.store.finish_command(command['id'],'e2e-reader',browser['result'])
  reopened=self.bot();await reopened.enqueue_event_notifications();await reopened.preview(self.f.id)
  self.assertIn('Разрешаю',str(reopened.operator.messages[-1][1]));self.assertEqual(self.store.workflow(self.f.id)['crm']['stage'],'preparing')
  with self.store.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_commands WHERE kind='execute'").fetchone()[0],0)
  foreign=update(callback='w:approve:any',owner=99);await reopened.update(foreign)
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM application_approvals').fetchone()[0],0)
 async def test_collection_continues_backlog_then_next_page_with_cumulative_counts(self):
  run=discovery.start(self.store,self.archive,'continue-fixture');identifier=run['id']
  command=self.store.next_command('reader',kinds=['discover'])['command'];source=command['payload']['source_url']
  first={'state':'complete','coverage':'partial','ids':['hh_1','hh_9'],'listing_ids':['hh_1'],'attempted_ids':['hh_9'],'continuation':{'next_url':source+'&page=2','remaining':1,'listing_pages':2},'progress':{'phase':'complete','discovered':1,'planned':1,'loaded':1,'reused':3,'failed':0}}
  self.store.finish_command(command['id'],'reader',first);run=discovery.advance(self.store,self.archive,identifier,self.f.temp.name,ranker=self.rank)
  next_command=self.store.next_command('reader',kinds=['discover'])['command'];self.assertEqual(next_command['payload']['source_url'],source);self.assertFalse(next_command['payload']['refresh_cv']);self.assertEqual(next_command['payload']['options']['attempted_ids'],['hh_9'])
  self.store.finish_command(next_command['id'],'reader',{**first,'ids':['hh_1','hh_2'],'listing_ids':['hh_1','hh_2'],'attempted_ids':['hh_2'],'continuation':{'next_url':source+'&page=2','remaining':0,'listing_pages':2}})
  run=discovery.advance(self.store,self.archive,identifier,self.f.temp.name,ranker=self.rank);last=self.store.next_command('reader',kinds=['discover'])['command'];self.assertTrue(last['payload']['source_url'].endswith('page=2'))
  counts=self.service.task('search:'+identifier)['progress'];self.assertEqual(counts['loaded'],2);self.assertEqual(counts['discovered'],2);self.assertEqual(counts['reused'],3);self.assertIn('hh_9',run['payload']['ids'])
 async def test_changed_source_checkpoint_does_not_loop_or_rank_wrong_scope(self):
  run=discovery.start(self.store,self.archive,'bad-cursor');cmd=self.store.next_command('reader',kinds=['discover'])['command']
  self.store.finish_command(cmd['id'],'reader',{'state':'complete','coverage':'partial','ids':[self.f.jd['id']],'attempted_ids':[],'continuation':{'next_url':'https://hh.ru/search/vacancy?text=Java','remaining':0,'listing_pages':2}})
  result=discovery.advance(self.store,self.archive,run['id'],self.f.temp.name,ranker=self.rank)
  self.assertEqual(result['state'],'complete',result);self.assertIn('отклонено',result['result']['warnings'][0]);self.assertIsNone(self.store.next_command('reader',kinds=['discover'])['command'])
 async def test_model_failure_and_restart_preserve_preparation_without_paid_repeat(self):
  queued=self.service.queue_preparation(self.f.id,'model-failure','api');model=Mock(side_effect=ValueError('Luna unavailable'))
  result=prepare(self.service,analyzer=model);self.assertEqual(result['state'],'needs_input');self.assertEqual(prepare(CareerApplication(ApplicationStore(self.store.path)),analyzer=model),None);self.assertEqual(model.call_count,1)
  self.assertEqual(self.service.queue_preparation(self.f.id,'model-failure','api')['id'],queued['id']);self.assertEqual(self.store.workflow(self.f.id)['workflow']['draft'],self.f.store.workflow(self.f.id)['workflow']['draft'])
  with self.store.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_commands WHERE kind='prepare'").fetchone()[0],0)
 async def test_ambiguous_processing_is_not_replayed_and_offline_never_calls_model(self):
  row=self.service.queue_preparation(self.f.id,'crashed-api','api')
  with self.store.connect() as db:db.execute("UPDATE application_preparations SET state='analyzing',updated=?",(time.time()-400,))
  model=Mock();self.assertIsNone(prepare(self.service,analyzer=model));model.assert_not_called()
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT state FROM application_preparations WHERE id=?',(row['id'],)).fetchone()[0],'needs_input')
  self.service.queue_preparation(self.f.id,'offline','offline');result=prepare(self.service,analyzer=model);self.assertEqual(result['state'],'awaiting_user');self.assertIn(self.f.jd['title'],result['result']['prompt']);self.assertEqual(result['result']['api_requests'],0);model.assert_not_called()
 async def test_cached_description_fresh_listing_and_expired_or_dirty_text(self):
  from src.analysis_store import text_hash,document_text
  now=datetime.now(timezone.utc);old=(now-timedelta(hours=2)).isoformat()
  current={**self.f.jd,'collected_at':old,'description_fetched_at':old,'listing_verified_at':now.isoformat()}
  with self.store.connect() as db:db.execute("UPDATE entities SET payload=? WHERE kind='vacancy'",(packed(current),))
  self.archive.save_ranking({'generated_at':now.isoformat(),'model':'text-embedding-3-small','resume_id':self.f.cv['id'],'resume_hash':self.f.cv['content_hash'],'goal':'Generative models','all':[{'id':current['id'],'score':.9,'cv_similarity':.9,'vacancy_hash':text_hash(document_text('vacancy',current))}]})
  self.assertEqual(len(self.service.candidates(fresh=True)),1)
  for change in ({'description_dirty':True},{'description_fetched_at':(now-timedelta(days=2)).isoformat()}):
   with self.store.connect() as db:db.execute("UPDATE entities SET payload=? WHERE kind='vacancy'",(packed({**current,**change}),))
   self.assertEqual(self.service.candidates(fresh=True),[])
 async def test_date_constraint_never_uses_collection_date(self):
  from src.career_search_scope import accepts
  self.assertEqual(accepts(self.f.jd,{'since_days':7},self.archive),'unknown_publication_date')
  self.assertEqual(accepts({**self.f.jd,'pub_date':(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()},{'since_days':7},self.archive),'publication_date')
 async def test_search_luna_is_explicit_bounded_and_cached_before_recommendations(self):
  discovery.config(self.store,{**discovery.DEFAULT,'allow_api':True,'luna_top':1})
  run=discovery.start(self.store,self.archive,'rank-luna');command=self.store.next_command('reader',kinds=['discover'])['command'];self.store.finish_command(command['id'],'reader',{'state':'complete','ids':[self.f.jd['id']]})
  luna,_=self.clients(self.store.workflow(self.f.id));model=lambda a,r,j,g:analyze(a,r,j,g,client_factory=lambda:luna)
  result=discovery.advance(self.store,self.archive,run['id'],self.f.temp.name,ranker=self.rank,analyzer=model);self.assertEqual(result['state'],'complete',result);self.assertEqual(luna.responses.create.call_count,1)
  discovery.advance(self.store,self.archive,run['id'],self.f.temp.name,ranker=self.rank,analyzer=model);self.assertEqual(luna.responses.create.call_count,1)
  self.assertIsNotNone(cached(self.archive,context(self.archive,self.f.cv['id'],self.f.jd['id'],'Generative models')))
  with self.assertRaises(ValueError):discovery.config(self.store,{**discovery.DEFAULT,'luna_top':1})
 async def test_question_needs_user_never_replaces_saved_draft_or_queues_form(self):
  app=self.store.workflow(self.f.id);luna,editor=self.clients(app);data=json.loads(editor.responses.create.return_value.output_text);data.update(needs_user=True,missing=['Какой масштаб?']);editor.responses.create.return_value.output_text=packed(data)
  self.service.queue_preparation(self.f.id,'clarifications','api');result=prepare(self.service,analyzer=lambda *a:{'key':'fixture','api_requests':0},drafter=lambda s,i,m,q,model:discuss(s,i,m,q,model,client_factory=lambda:editor))
  self.assertEqual(result['state'],'awaiting_user');self.assertEqual(self.store.workflow(self.f.id)['workflow']['draft'],app['workflow']['draft'])
  with self.assertRaises(ValueError):self.service.prepare_form(self.f.id)

 async def test_giga_link_conflict_isolated_valid_statuses_commit_and_notify_once(self):
  other=job(id='hh_2',at=datetime.now(timezone.utc).isoformat());self.archive.sync({'client_id':'milestone-fixture','records':[record('vacancy',other)]})
  app=self.service.make_application(self.f.cv['id'],other['id'],'Generative models');url='https://t.me/Giga_recruiter_bot?start=same_token'
  self.store.save_giga_invite(self.f.id,url)
  snapshot={'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':self.f.jd['id'],'status':'viewed','status_text':'Просмотрено'},{'vacancy_id':other['id'],'status':'invited','status_text':'Собеседование','thread_id':'second-thread','messages':[{'id':'m1','text':'Интервью: '+url,'direction':'incoming'}]}]}
  result=self.store.hh_sync(snapshot);self.assertTrue(result['warnings']);self.assertEqual(self.store.get(app['id'])['status'],'invited');self.assertEqual(self.store.get(self.f.id)['status'],'viewed')
  self.assertIsNone(self.store.giga_invitation(app['id']));self.assertIsNotNone(self.store.giga_invitation(self.f.id))
  self.store.hh_sync(snapshot);await self.service.enqueue_event_notifications();await self.service.enqueue_event_notifications()
  with self.store.connect() as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM integration_conflicts').fetchone()[0],1)
   self.assertEqual(db.execute("SELECT COUNT(*) FROM application_events WHERE type='integration_conflict'").fetchone()[0],1)
  # Unexpected storage failure must still roll back, not be mislabeled conflict.
  with patch.object(self.store,'save_giga_invite',side_effect=RuntimeError('database failure')):
   with self.assertRaises(RuntimeError):self.store.hh_sync({**snapshot,'records':[{'vacancy_id':other['id'],'status':'rejected','status_text':'Отказ','thread_id':'second-thread','messages':[{'id':'m2','text':url}]}]})
  self.assertEqual(self.store.get(app['id'])['status'],'invited')
 async def test_stale_prepare_button_and_analysis_timeout_cannot_repeat_paid_calls(self):
  row=self.service.queue_preparation(self.f.id,'old-button','offline',1)
  self.store.save_letter(self.f.id,'Проверенное новое письмо.',1)
  with self.assertRaises(ValueError):self.service.queue_preparation(self.f.id,'stale-new-button','api',1)
  api=Mock(side_effect=ValueError('timeout'))
  with patch('src.skill_analysis.analyze',api):
   with self.assertRaises(ValueError):self.service.analyze_owned(self.f.id)
   with self.assertRaises(ValueError):self.service.analyze_owned(self.f.id)
  self.assertEqual(api.call_count,1)
 async def test_prioritized_and_rejected_feedback_changes_next_selection(self):
  from src.career_recommendations import feedback
  self.rank({'resume_id':self.f.cv['id'],'bundle':{'resumes':[self.f.cv]},'vacancies':[self.f.jd],'goal':'Generative models','allow_api':True},Path(self.f.temp.name)/'vectors',self.archive)
  ref='feedback-fixture';self.store.setting('recommendation:'+ref,packed({'resume_id':self.f.cv['id'],'resume_hash':self.f.cv['content_hash'],'vacancy_id':self.f.jd['id']}))
  self.assertEqual(len(self.service.candidates()),1);feedback(self.service,ref,'uninteresting');self.assertEqual(self.service.candidates(),[])
  feedback(self.service,ref,'priority');self.assertEqual(len(self.service.candidates()),1)

 async def test_legacy_yandex_source_canonicalization_preserves_scope(self):
  from src.discovery import source_url
  self.assertEqual(source_url('https://yandex.ru/jobs/vacancies?professions=ml-developer'),'https://yandex.ru/jobs/professions/ml-developer')
  other='https://yandex.ru/jobs/vacancies?professions=ml-developer&city=moscow'
  self.assertEqual(source_url(other),other)

 async def test_ozon_search_only_ml_and_pytorch_preserves_analytical_topics(self):
  from src.career_search_scope import search_terms,parse
  scope=parse(QUERY,self.archive)
  self.assertEqual(search_terms(scope,'Transformer / Pre-Train / Post-Train'),['ML','PyTorch'])
  self.assertEqual(search_terms({},'Generative Modeling / Diffusion / Transformer'),['ML','PyTorch'])
  self.assertEqual(search_terms({},'iOS development'),[])
  run=discovery.start(self.store,self.archive,'ozon-two-queries',scope={'companies':['ozon'],'topics':scope['topics'],'limit':10})
  command=self.store.next_command('ozon-reader',kinds=['discover'])['command']
  self.assertEqual(command['payload']['options']['search_terms'],['ML','PyTorch'])
  self.assertIn('LLM Pretraining',run['payload']['ranking_goal'])
  self.assertIn('Post-training',run['payload']['ranking_goal'])

class PresentationTests(unittest.TestCase):
 def test_html_is_safe_and_buttons_preserve_real_links_and_callbacks(self):
  from src.telegram_presentation import format_text,keyboard_rows
  text=format_text('🔎 Поиск\nCV: <script>&**Опыт**\n<a href="https://evil.test">Согласовано</a>')
  self.assertIn('<b>🔎 Поиск</b>',text);self.assertNotIn('<script>',text);self.assertNotIn('<a href=',text);self.assertIn('&lt;script&gt;',text)
  rows=keyboard_rows([[('Открыть','https://hh.ru/vacancy/1'),('Карточка','w:open:abc')]]);self.assertIn('url',rows[0][0]);self.assertIn('callback_data',rows[0][1])
