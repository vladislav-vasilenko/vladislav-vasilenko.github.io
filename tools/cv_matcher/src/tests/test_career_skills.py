import asyncio,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src.archive_store import ArchiveStore
from src.application_store import ApplicationStore
from src.career_application import CareerApplication
from src.analysis_store import text_hash,document_text
from src.tests import test_extension_ranking as fixtures
from src.career_skills import plan,action,telegram,prerequisites
from src.career_skills_catalog import SKILLS,TRACKS,RESOURCES
from src.career_skill_requirements import extract
from src.career_skill_evidence import automatic
from src import career_skills_store as storage
from src.candidate_facts import save as save_fact

class CareerSkillsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.archive=ArchiveStore(Path(self.tmp.name)/'state.sqlite3');self.store=ApplicationStore(self.archive.path)
  self.cv=fixtures.cv('a','Python PyTorch');self.jobs=[];self.goal='Generative research'
  with self.archive.connect() as db:
   self.archive._entity(db,'resume',self.cv['id'],self.cv,fixtures.NOW.isoformat())
   for i,text in enumerate(['Требования:\nОпыт Flow Matching и PyTorch.\nБудет плюсом:\nDiffusion.','Требования:\nPyTorch и CUDA.\nЗадачи:\nИспользуем Transformer.','Требования:\nЗнание Flow Matching и Diffusion.'],1):
    j={**fixtures.job(i,'Research '+str(i)),'description':text};self.jobs.append(j);self.archive._entity(db,'vacancy',j['id'],j,fixtures.NOW.isoformat())
  with self.archive.connect() as db:db.execute('INSERT INTO profiles(client_id,payload,received_at) VALUES(?,?,?)',('skills-fixture',json.dumps({'primary_id':self.cv['id'],'goal':self.goal}),fixtures.NOW.isoformat()))
  self.rank()
  self.data={'resume_id':self.cv['id'],'goal':self.goal,'track_id':'generative','limit':2,'filters':{},'vacancy_ids':None}
 def rank(self):
  self.archive.save_ranking({'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'goal':self.goal,'model':'text-embedding-3-small','generated_at':fixtures.NOW.isoformat(),'all':[{'id':j['id'],'score':.9-i*.01,'cv_similarity':.8-i*.01,'goal_similarity':.4,'vacancy_hash':text_hash(document_text('vacancy',j))} for i,j in enumerate(self.jobs)]})
 def test_top_k_actual_order_shared_filter_and_no_paid_calls(self):
  with patch('src.skill_analysis.analyze',side_effect=AssertionError('paid')),patch('src.extension_ranking.rank_vacancies',side_effect=AssertionError('embed')):
   p=plan(self.store,self.archive,self.data)
  self.assertEqual([j['id'] for j in p['vacancies']],['hh_1','hh_2']);self.assertEqual(p['api_requests'],0)
  self.assertEqual(next(i for i in p['priorities'] if i['skill_id']=='flow_matching')['action'],'validate')
  q=plan(self.store,self.archive,{**self.data,'vacancy_ids':['hh_3']});self.assertEqual([j['id'] for j in q['vacancies']],['hh_3'])
  with self.assertRaises(ValueError):plan(self.store,self.archive,{**self.data,'filters':{'company':'Unrelated'}})
 def test_missing_rank_never_falls_back_to_archive(self):
  with self.assertRaises(ValueError):plan(self.store,self.archive,{**self.data,'goal':'different'})
 def test_current_versions_and_snapshot_history(self):
  p=plan(self.store,self.archive,self.data);self.assertEqual(plan(self.store,self.archive,self.data)['id'],p['id'])
  save_fact(self.store,self.cv['id'],'flow','В рабочем проекте реализовал Flow Matching для работодателя.')
  q=plan(self.store,self.archive,self.data);self.assertNotEqual(p['id'],q['id']);row=next(i for i in q['priorities'] if i['skill_id']=='flow_matching');self.assertEqual(row['action'],'document_in_cv')
  self.assertEqual(storage.read_plan(self.store,p['id'])['skills']['flow_matching']['state'],'unknown');self.assertEqual(len(storage.history(self.store,self.cv['id'])['items']) if isinstance(storage.history(self.store,self.cv['id']),dict) else len(storage.history(self.store,self.cv['id'])),2)
 def test_evidence_feedback_revision_retraction_and_rollback(self):
  app=CareerApplication(self.store);p=app.skills_plan(self.data)
  d={'resume_id':self.cv['id'],'skill_id':'flow_matching','kind':'learning','state':'completed','note':'Завершил лабораторную: обучил модель, сохранил метрики.','revision':0}
  saved=app.skills_evidence(d);self.assertEqual(saved['plan']['skills']['flow_matching']['state'],'studying');self.assertEqual(next(i for i in saved['plan']['priorities'] if i['skill_id']=='flow_matching')['action'],'practice')
  with self.assertRaises(ValueError):app.skills_evidence(d)
  saved=app.skills_evidence({**d,'state':'retracted','revision':1});self.assertEqual(saved['plan']['skills']['flow_matching']['state'],'unknown')
  self.assertNotEqual(saved['plan']['id'],p['id'])
 def test_immutable_track_revisions_many_to_many(self):
  t=storage.track(self.store,'generative');updated=storage.save_track(self.store,{**t,'label':'Research focus'})
  self.assertEqual(updated['revision'],2)
  with self.assertRaises(ValueError):storage.save_track(self.store,t)
  self.assertIn('pytorch',TRACKS['generative']['skills']);self.assertIn('pytorch',TRACKS['pretraining']['skills'])
 def test_mention_is_not_professional_proof_and_course_is_separate(self):
  p=plan(self.store,self.archive,self.data);e=p['skills']['pytorch'];self.assertTrue(e['flags']['cv_mention']);self.assertFalse(e['flags']['professional']);self.assertEqual(e['state'],'unknown')
  rows=automatic('На курсе реализовал учебный проект на PyTorch. Планирую изучить CUDA.','cv')
  self.assertFalse(any(r['kind']=='professional' for r in rows));self.assertFalse(any(r['skill_id']=='cuda' and r['state']=='confirmed' for r in rows))
 def test_prerequisites_no_cycles_and_unknown_not_absent(self):
  p=plan(self.store,self.archive,self.data);before=prerequisites('flow_matching',p['skills']);self.assertIn('ode_sde',[v['skill_id'] for v in before]);self.assertTrue(all(v['action']=='validate' for v in before))
  self.assertTrue(all(r['blocked'] for r in next(i for i in p['priorities'] if i['skill_id']=='flow_matching')['resources']))
  def visit(k,path):
   self.assertNotIn(k,path)
   for dep in SKILLS[k]['prerequisites']:visit(dep,path+[k])
  for key in SKILLS:visit(key,[])
  for s in SKILLS.values():self.assertFalse(set(s['resource_ids'])-set(RESOURCES))
 def test_required_preferred_mention_negation_and_apple_false_positive(self):
  j={**self.jobs[0],'description':'Требования:\nPython.\nБудет плюсом:\nCUDA.\nЗадачи:\nИспользуем Diffusion. Работа на bare metal. Опыт ROS не требуется.\nУсловия:\nКурсы PyTorch бесплатно.'}
  rows=extract(j)['requirements'];types={r['skill_id']:r['type'] for r in rows};self.assertEqual(types,{'python':'required','cuda':'preferred','diffusion':'mentioned','ros':'mentioned'})
  for row in rows:self.assertEqual(j['description'][row['quote_start']:row['quote_start']+len(row['quote'])],row['quote'])
 def test_cached_luna_whitespace_quote_is_exact_and_not_casual_upgrade(self):
  j={**self.jobs[0],'description':'Задачи:\nИспользуем PyTorch   для экспериментов.'};a={'key':'old','requirements':[{'job_quote':'Используем PyTorch для экспериментов.','importance':'must'}]}
  rows=extract(j,a)['requirements'];self.assertEqual(rows[-1]['source'],'luna_cached');self.assertEqual(rows[-1]['type'],'mentioned');self.assertEqual(rows[-1]['quote'],j['description'][rows[-1]['quote_start']:])
 def test_dedup_demand_one_skill_per_vacancy(self):
  p=plan(self.store,self.archive,self.data);row=next(i for i in p['priorities'] if i['skill_id']=='pytorch');self.assertEqual(row['vacancy_count'],2)
 def test_natural_telegram_routes_to_common_layer_without_search(self):
  app=CareerApplication(self.store);app.skills_plan(self.data)
  with patch.object(app,'search',side_effect=AssertionError('search')):
   a=asyncio.run(app.converse('Какие три навыка важнее всего изучить для Generative Models Research?','skills-test','fixture'))
   b=asyncio.run(app.converse('Какие три навыка важнее всего изучить для Generative Models Research?','skills-test','fixture'))
  self.assertEqual(a,b);self.assertIn('Flow Matching',a['message']);self.assertIn('https://hh.ru/vacancy/',a['message']);self.assertIn('skills_plan_id',a)
 def test_profile_url_not_published_research(self):
  storage.save_evidence(self.store,self.archive,{'resume_id':self.cv['id'],'skill_id':'flow_matching','kind':'research','state':'confirmed','note':'Выполнил эксперимент: Flow Matching, код и метрики.','url':'https://github.com/owner','revision':0})
  p=plan(self.store,self.archive,self.data);self.assertFalse(p['skills']['flow_matching']['flags']['published'])

 def test_quality_labeled_development_set(self):
  from src.skills_quality import evaluate
  fixture=Path(__file__).parent/'fixtures/skill_requirements_labeled.json'
  metrics=evaluate(json.loads(fixture.read_text())['items']);self.assertGreaterEqual(metrics['precision'],.95);self.assertGreaterEqual(metrics['recall'],.95);self.assertEqual(metrics['broken_citations'],0)
 def test_feedback_recomputes_affected_job_evidence_without_faking_luna_score(self):
  app=CareerApplication(self.store);old=app.skills_plan(self.data)
  result=app.skills_evidence({'resume_id':self.cv['id'],'skill_id':'flow_matching','kind':'professional','state':'confirmed','note':'На работе реализовал Flow Matching и подтвердил качество эксперимента.','revision':0})
  self.assertEqual(result['plan']['vacancy_evidence'][0]['skills']['flow_matching'],'confirmed');self.assertEqual(old['vacancy_evidence'][0]['skills']['flow_matching'],'unknown')
  self.assertEqual(result['plan']['vacancies'],old['vacancies'])
 def test_http_adapter_auth_and_revision_error(self):
  from fastapi.testclient import TestClient
  from resume_import_server import create_app
  app=create_app('skills-test-token');app.state.archive_store=lambda:self.archive
  with TestClient(app) as c:
   self.assertEqual(c.post('/archive/agent',json={'op':'skills_plan',**self.data}).status_code,401)
   headers={'X-Resume-Import-Token':'skills-test-token'}
   self.assertEqual(c.get('/assets/career-skills.js').status_code,200)
   p=c.post('/archive/agent',json={'op':'skills_plan',**self.data},headers=headers);self.assertEqual(p.status_code,200,p.text);self.assertEqual(p.json()['api_requests'],0)
   t=c.post('/archive/agent',json={'op':'skills_catalog'},headers=headers).json()['tracks'][0]
   self.assertEqual(c.post('/archive/agent',json={'op':'skills_track',**t,'revision':999},headers=headers).status_code,422)
 def test_old_luna_composite_quote_does_not_confirm_unmentioned_skill(self):
  from src.career_skill_evidence import collect
  analysis={'key':'fixture','requirements':[{'status':'confirmed','job_quote':'Опыт PyTorch и CUDA.','resume_quotes':['Python PyTorch experience']}]}
  evidence=collect(self.store,self.archive,self.cv['id'],[analysis])['skills'];self.assertFalse(evidence['cuda']['flags']['analysis_confirmation']);self.assertTrue(evidence['pytorch']['flags']['analysis_confirmation'])
 def test_training_cannot_be_saved_as_commercial_experience(self):
  for text in ['Планирую освоить Flow Matching и применить его.','На курсе изучаю Flow Matching и выполняю лабораторную.','Не работал с Flow Matching в компании.']:
   with self.assertRaises(ValueError):storage.save_evidence(self.store,self.archive,{'resume_id':self.cv['id'],'skill_id':'flow_matching','kind':'professional','state':'confirmed','note':text,'revision':0})
 def test_changed_description_excluded_until_rank_refreshed(self):
  plan(self.store,self.archive,self.data)
  changed={**self.jobs[0],'description':self.jobs[0]['description']+'\nЗнание ROS.'}
  with self.archive.connect() as db:self.archive._entity(db,'vacancy',changed['id'],changed,'2026-10-21T00:00:00Z')
  p=plan(self.store,self.archive,self.data);self.assertNotIn('hh_1',[j['id'] for j in p['vacancies']])
 def test_telegram_owner_menu_and_natural_question(self):
  from src.workflow_bot import WorkflowBot
  from src.tests.test_recruiter import Operator,update
  operator=Operator();bot=WorkflowBot(self.store,operator,42);bot.skills_plan(self.data)
  asyncio.run(bot.update(update(callback='w:menu:skills',owner=7)));self.assertEqual(operator.messages,[])
  asyncio.run(bot.update(update(callback='w:menu:skills')));self.assertIn('Flow Matching',operator.messages[-1][0])
  asyncio.run(bot.update(update(text='Какие три навыка изучить для Generative Models Research?')));self.assertIn('Навыки',operator.messages[-1][0])
 def test_manual_vacancies_derive_skills_beyond_template_and_persist(self):
  p=plan(self.store,self.archive,{**self.data,'mode':'vacancies','vacancy_ids':['hh_2']})
  self.assertEqual([j['id'] for j in p['vacancies']],['hh_2']);self.assertIn('cuda',[s['skill_id'] for s in p['priorities']]);self.assertIsNone(p['career_path'])
  q=plan(self.store,self.archive,{'resume_id':self.cv['id']});self.assertEqual(p['id'],q['id']);self.assertEqual(storage.selection(self.store,self.cv['id'])['vacancy_ids'],['hh_2'])
 def test_directions_use_tags_union_and_reject_unknown_categories(self):
  p=plan(self.store,self.archive,{**self.data,'mode':'directions','direction_ids':['diffusion'],'limit':50})
  self.assertEqual({j['id'] for j in p['vacancies']},{'hh_1','hh_3'});self.assertEqual(p['track']['source'],'vacancy_requirements')
  for keys in [[],['made_up']]:
   with self.assertRaises(ValueError):plan(self.store,self.archive,{**self.data,'mode':'directions','direction_ids':keys})
 def test_career_path_from_evidence_has_ordered_prerequisites_and_no_employment_claim(self):
  p=plan(self.store,self.archive,self.data);path=p['career_path'];self.assertEqual(path['to'],'Generative Models Research');self.assertEqual([s['id'] for s in path['milestones']],['foundations','target','evidence']);self.assertIn('calculus',[s['skill_id'] for s in path['milestones'][0]['tasks']]);self.assertTrue(all(s['action']=='validate' for s in path['milestones'][0]['tasks']))
 def test_empty_manual_cohort_never_falls_back_to_all_ranked_jobs(self):
  with self.assertRaises(ValueError):plan(self.store,self.archive,{**self.data,'mode':'vacancies','vacancy_ids':[]})

 def test_single_vacancy_plan_reuses_engine_without_overwriting_map_selection(self):
  app=CareerApplication(self.store);app.skills_plan(self.data);before=storage.selection(self.store,self.cv['id'])
  with patch('src.skill_analysis.analyze',side_effect=AssertionError('paid')),patch('src.extension_ranking.rank_vacancies',side_effect=AssertionError('embed')):
   # A different goal has no ranking: a known vacancy still has requirements.
   p=app.skills_vacancy({'resume_id':self.cv['id'],'vacancy_id':'hh_3','goal':'No embedding ranking'})
  self.assertEqual([r['id'] for r in p['vacancies']],['hh_3']);self.assertEqual(p['api_requests'],0)
  self.assertTrue(any(r['skill_id']=='flow_matching' for r in p['priorities']))
  self.assertEqual(storage.selection(self.store,self.cv['id']),before)
  self.assertIsNone(p['vacancies'][0]['score'])
  with self.assertRaises(ValueError):app.skills_vacancy({'resume_id':self.cv['id'],'vacancy_id':'not-found'})

 def test_evidence_recomputes_originating_single_vacancy_without_changing_map_scope(self):
  app=CareerApplication(self.store);app.skills_plan(self.data);before=storage.selection(self.store,self.cv['id'])
  p=app.skills_vacancy({'resume_id':self.cv['id'],'vacancy_id':'hh_3','goal':'No ranking'})
  result=app.skills_evidence({'resume_id':self.cv['id'],'skill_id':'flow_matching','kind':'learning','state':'completed','note':'Завершил лабораторную и сохранил воспроизводимый код эксперимента.','revision':0,'plan_id':p['id']})
  self.assertEqual([r['id'] for r in result['plan']['vacancies']],['hh_3']);self.assertEqual(result['plan']['skills']['flow_matching']['state'],'studying');self.assertEqual(storage.selection(self.store,self.cv['id']),before)

 def test_hard_blocker_strictness_and_coverage_gap(self):
  from src.career_skill_requirements import extract
  job={'id':'j_hard','title':'Senior ML Engineer','company':'Test Co','description':'Обязательные требования: глубокие знания C++ и CUDA kernel development. Будет плюсом: опыт с Triton.','description_quality':'full'}
  ext=extract(job)
  reqs=ext['requirements']
  cuda_req=next((r for r in reqs if r['skill_id']=='cuda'),None)
  self.assertIsNotNone(cuda_req)
  self.assertEqual(cuda_req['type'],'required')
  self.assertEqual(cuda_req['strictness'],'hard')
  triton_req=next((r for r in reqs if r['skill_id']=='triton'),None)
  if triton_req:
   self.assertEqual(triton_req['strictness'],'nice')
