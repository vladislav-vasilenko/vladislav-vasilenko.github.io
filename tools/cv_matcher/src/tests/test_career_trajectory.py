import copy,json,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src import career_trajectory as trajectory
from src.tests.test_archive import cv,job,record
from src.career_skill_evidence import collect
from src.career_skills import plan,save_evidence
from resume_import_server import create_app

class TrajectoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'state.sqlite3';self.store=ApplicationStore(self.path);self.archive=ArchiveStore(self.path)
 def draft(self):return trajectory.defaults(self.store,'generative')
 def evidence(self,kind='project',skills=None,**extra):
  return trajectory.save_evidence(self.store,{'kind':kind,'skill_ids':skills or ['flow_matching'],'note':'Реализован воспроизводимый эксперимент с кодом, метриками и анализом результатов.','reviewed':True,**extra})
 def test_goal_and_multi_step_path_work_without_any_resume_and_survive_reload(self):
  first=trajectory.save(self.store,self.archive,self.draft());self.assertEqual(first['resumes'],[]);self.assertEqual(first['path']['total'],3)
  self.assertEqual([s['state'] for s in first['path']['stages']],['ready','blocked','blocked'])
  self.assertEqual(trajectory.overview(ApplicationStore(self.path),self.archive)['path']['id'],first['path']['id'])
 def test_conflicting_edit_rejected_and_history_kept(self):
  path=trajectory.save(self.store,self.archive,self.draft())['path'];second=trajectory.save(self.store,self.archive,{**path,'goal':'Новая роль'})['path']
  with self.assertRaisesRegex(ValueError,'другой вкладке'):trajectory.save(self.store,self.archive,path)
  with self.store.connect() as db:count=db.execute("SELECT COUNT(*) FROM archive_meta WHERE key LIKE '%trajectory-version:%'").fetchone()[0]
  self.assertEqual(count,2);self.assertEqual(second['revision'],2)
 def test_cycles_forward_dependencies_and_missing_evidence_rejected(self):
  for mutate in ('cycle','forward','unknown'):
   value=self.draft()
   if mutate=='cycle':value['stages'][0]['after']=['practice']
   if mutate=='forward':value['stages'][0]['after']=['project']
   if mutate=='unknown':value['stages'][0]['criteria'][0]['evidence_ids']=['fake']
   with self.assertRaises(ValueError):trajectory.save(self.store,self.archive,value)
 def test_learning_does_not_complete_practical_skill_and_retraction_reopens_path(self):
  draft=self.draft();draft['stages']=draft['stages'][:1];draft['stages'][0]['criteria']=draft['stages'][0]['criteria'][:1];c=draft['stages'][0]['criteria'][0]
  learned=self.evidence('learning',c['skill_ids']);c['evidence_ids']=[learned['id']]
  value=trajectory.save(self.store,self.archive,draft);self.assertFalse(value['path']['stages'][0]['criteria'][0]['met'])
  project=self.evidence('project',c['skill_ids']);path=value['path'];path['stages'][0]['criteria'][0]['evidence_ids']=[project['id']]
  value=trajectory.save(self.store,self.archive,path);self.assertEqual(value['path']['completed'],1)
  trajectory.save_evidence(self.store,{**project,'state':'retracted','reviewed':True})
  self.assertEqual(trajectory.overview(self.store,self.archive)['path']['completed'],0)
 def test_any_alternatives_and_all_criteria_follow_predecessors(self):
  path=self.draft();keys=list({k for s in path['stages'] for c in s['criteria'] for k in c['skill_ids']});e=self.evidence(skills=keys)
  path['stages'][1]['criteria'][0]['evidence_ids']=[e['id']]
  value=trajectory.save(self.store,self.archive,path)['path'];self.assertEqual(value['stages'][1]['state'],'blocked');self.assertEqual(value['stages'][1]['met'],1)
  for c in value['stages'][0]['criteria']:c['evidence_ids']=[e['id']]
  value=trajectory.save(self.store,self.archive,value)['path'];self.assertEqual(value['completed'],2)
 def test_shared_evidence_updates_skill_engine_without_changing_cv(self):
  resume=cv();self.archive.sync({'client_id':'trajectory-fixture','records':[record('resume',resume)]});before=self.archive.detail('resume',resume['id'])['version_id']
  e=self.evidence();result=collect(self.store,self.archive,resume['id'],[])
  self.assertTrue(result['skills']['flow_matching']['flags']['project']);self.assertIn((e['id'],1),result['versions']['trajectory'])
  self.assertEqual(self.archive.detail('resume',resume['id'])['version_id'],before)
 def test_stage_jobs_do_not_require_cv_similarity_or_embeddings_and_cv_is_selected_later(self):
  resume=cv(text='Работал Python backend инженером.');self.archive.sync({'client_id':'trajectory-fixture','records':[record('resume',resume),record('vacancy',job(text='Требования:\nПрактический опыт Flow Matching и диффузионных моделей.'))]})
  path=self.draft();path['stages'][0]['criteria'][0]['skill_ids']=['flow_matching'];value=trajectory.save(self.store,self.archive,path)['path']
  detail=trajectory.stage_detail(self.store,self.archive,value['id'],'practice');self.assertEqual(detail['matched_total'],1);self.assertEqual(detail['api_requests'],0);self.assertEqual(detail['resumes'][0]['id'],resume['id'])
  result=plan(self.store,self.archive,{'resume_id':resume['id'],'mode':'vacancies','vacancy_ids':['hh_1'],'trajectory_id':value['id'],'stage_id':'practice','filters':{},'limit':10})
  self.assertEqual(len(result['vacancies']),1);self.assertEqual(result['api_requests'],0)
 def test_completed_course_requires_owner_review_and_cannot_impersonate_professional_work(self):
  with self.assertRaises(ValueError):self.evidence(reviewed=False)
  with self.assertRaises(ValueError):self.evidence(note='Планирую изучить Flow Matching и сделать проект.')
  with self.assertRaises(ValueError):self.evidence(kind='professional',note='Прошёл курс и изучаю Flow Matching на лекциях.')
 def test_authenticated_routes_and_foreign_origin_cannot_edit(self):
  app=create_app('fixture',archive_path=self.path)
  with TestClient(app) as client:
   body={'op':'trajectory_save','path':self.draft()};self.assertEqual(client.post('/archive/agent',json=body).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   self.assertEqual(client.post('/archive/agent',json=body,headers={'Origin':'https://example.org'}).status_code,401)
   response=client.post('/archive/agent',json=body,headers={'Origin':'http://127.0.0.1:8788'});self.assertEqual(response.status_code,200);self.assertEqual(response.json()['api_requests'],0)

 def test_vacancy_draft_compares_all_cv_keeps_versions_and_never_learns_unknown(self):
  first=cv(text='Упомянут Python и Flow Matching.');second={**cv(text='Реализовал Flow Matching в production для работодателя.'),'id':'b'*38,'source_url':'https://hh.ru/resume/'+'b'*38}
  vacancy=job(text='Требования:\nПрактический опыт Flow Matching и Python.\nБудет преимуществом:\nTriton.');self.archive.sync({'client_id':'trajectory-fixture','records':[record('resume',first),record('resume',second),record('vacancy',vacancy)]})
  draft=trajectory.vacancy_draft(self.store,self.archive,'hh_1');self.assertEqual(len(draft['basis']['resumes']),2)
  self.assertTrue(all(r['action']=='validate' for r in draft['proposal']['requirements']));self.assertTrue(draft['proposal']['preferred'])
  keys={k for st in draft['stages'] for c in st['criteria'] for k in c['skill_ids']};self.assertNotIn('triton',keys)
  self.assertEqual(trajectory.overview(self.store,self.archive)['paths'],[])
  saved=trajectory.save(self.store,self.archive,draft)['path'];self.assertEqual(saved['basis'],draft['basis'])
 def test_explicit_gaps_create_learning_then_practice_but_negated_and_mentions_do_not(self):
  self.archive.sync({'client_id':'trajectory-fixture','records':[record('resume',cv(text='Нет опыта Flow Matching.')),record('vacancy',job(text='Требования:\nНужен опыт Flow Matching.\nЗадачи:\nИспользуем Triton.'))]})
  draft=trajectory.vacancy_draft(self.store,self.archive,'hh_1');self.assertEqual(draft['proposal']['requirements'][0]['action'],'learn')
  self.assertEqual([s['id'] for s in draft['stages']],['learn_1','practice_1','application'])
  self.assertEqual(draft['stages'][1]['after'],['learn_1']);self.assertEqual(draft['stages'][1]['criteria'][0]['kind'],'skill')
 def test_preferred_only_vacancy_cannot_create_mandatory_milestones(self):
  self.archive.sync({'client_id':'trajectory-fixture','records':[record('vacancy',job(text='Будет преимуществом:\nPython и Flow Matching.'))]})
  with self.assertRaisesRegex(ValueError,'обязательные'):trajectory.vacancy_draft(self.store,self.archive,'hh_1')
 def test_stage_plan_feedback_preserves_trajectory_context(self):
  resume=cv();self.archive.sync({'client_id':'trajectory-fixture','records':[record('resume',resume),record('vacancy',job(text='Требования:\nПрактический опыт Flow Matching.'))]})
  path=trajectory.save(self.store,self.archive,self.draft())['path'];source=plan(self.store,self.archive,{'resume_id':resume['id'],'mode':'vacancies','vacancy_ids':['hh_1'],'trajectory_id':path['id'],'stage_id':'practice','limit':10})
  updated=save_evidence(self.store,self.archive,{'resume_id':resume['id'],'skill_id':'flow_matching','kind':'project','state':'confirmed','note':'Реализован Flow Matching в самостоятельном проекте с метриками и кодом.','url':'','revision':0,'plan_id':source['id']})
  self.assertIsNotNone(updated['plan']);self.assertEqual(updated['plan']['trajectory_id'],path['id']);self.assertEqual(updated['plan']['stage_id'],'practice')

 def test_flattened_dom_requirements_do_not_inherit_preferred_section(self):
  from src.career_skill_requirements import extract
  text='Будет преимуществом: опыт Triton. Обязанности Разрабатывать генеративные модели. Технологический стек Основной стек: Python. Требования Опыт Flow Matching. Хорошую математическую базу: линейная алгебра. Условия спортзал и обучение PyTorch.'
  source=job(text=text);rows=extract(source)['requirements'];types={r['skill_id']:r['type'] for r in rows}
  self.assertEqual(types['triton'],'preferred');self.assertEqual(types['python'],'mentioned');self.assertEqual(types['flow_matching'],'required');self.assertNotIn('pytorch',types)
  for row in rows:self.assertEqual(text[row['quote_start']:row['quote_start']+len(row['quote'])],row['quote'])
  self.archive.sync({'client_id':'trajectory-fixture','records':[record('vacancy',source)]})
  draft=trajectory.vacancy_draft(self.store,self.archive,'hh_1');self.assertTrue(draft['proposal']['requirements']);self.assertEqual(draft['track_id'],'generative')
