import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src.career_analytics import snapshot,classify
from src.tests.test_archive import cv,job,record,CLIENT
from src.analysis_store import text_hash,document_text
from src.resume_source import matching_text,content_hash
from resume_import_server import create_app

class CareerAnalyticsTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.path=Path(t.name)/'state.sqlite3';ApplicationStore(self.path);self.store=ArchiveStore(self.path)
  self.cv=cv(text='Изучаю MIT 6.S184 Flow Matching and Diffusion Models. GitHub: https://github.com/example/research',at='2026-08-01T00:00:00Z');self.cv['content_hash']=content_hash(self.cv)
  self.jd=job(text='Pre-training diffusion models with flow-matching, CUDA kernels and Apple MLX / MPS / Metal.',at='2026-08-01T00:00:00Z')
  with patch('src.archive_store.now_iso',return_value='2026-08-01T00:00:00+00:00'):self.store.sync({'client_id':CLIENT,'records':[record('resume',self.cv),record('vacancy',self.jd),record('profile',{'primary_id':self.cv['id'],'goal':'Flow Matching'},'profile')]})
 def test_tags_preserve_flow_diffusion_cuda_and_apple_when_primary_is_pretraining(self):
  classified=classify(self.jd);self.assertEqual(classified['primary'],'pretraining')
  self.assertTrue({'diffusion','cuda','apple'}<=set(classified['tags']))
  for spelling in ('Flow Matching','flow-matching','FlowMatching','диффузионные модели'):
   self.assertIn('diffusion',classify({'title':spelling})['tags'])
 def test_bare_metal_platform_job_is_not_apple_metal_or_mps(self):
  text='Опыт проектирования горизонтально масштабируемых, отказоустойчивых data-intensive систем на bare-metal/VM-инфраструктуре и/или в Kubernetes; Python FastAPI Airflow HTC/HPC S3.'
  self.assertNotIn('apple',classify({'title':'Lead data platform developer','description':text})['tags'])
  for phrase in ('bare metal','bare-metal','bare–metal','bare—metal','bare  metal'):
   self.assertNotIn('apple',classify({'description':phrase+' VM infrastructure'})['tags'])
  self.assertNotIn('apple',classify({'description':'NVIDIA CUDA MPS Multi-Process Service'})['tags'])
  self.assertNotIn('apple',classify({'description':'bare-metal NVIDIA CUDA MPS Multi-Process Service'})['tags'])
  self.assertNotIn('apple',classify({'description':'Выдаём ноутбук на Apple Silicon для работы с документацией'})['tags'])
  for phrase in ('MLX','Metal Performance Shaders','PyTorch device mps','Metal compute shaders','Apple Metal','Обучение моделей на Apple Silicon'):
   result=classify({'description':phrase});self.assertIn('apple',result['tags'],phrase);self.assertEqual(result['evidence'][0]['quote'],phrase)
 def test_platform_qa_and_company_boilerplate_are_not_ml_research_or_apple(self):
  lead={'title':'Lead data platform developer','description':'Основные задачи: Разрабатывать платформу данных для потребностей исследователей. Требования: Python FastAPI, bare-metal/VM Kubernetes.'}
  qa={'title':'Auto QA Python (Hadoop, Spark)','description':'Занимаемся исследовательской работой и публикуем статьи. Что нужно делать: Автоматизировать тестирование Hadoop Spark на bare metal, VM и Kubernetes. Мы ждем, что вы: Python Pytest. Условия: Ноутбук Apple Silicon с Metal.'}
  for value in (lead,qa):
   result=classify(value);self.assertNotIn('apple',result['tags']);self.assertNotIn('research',result['tags'])
 def test_scientific_imaging_metal_conductor_is_a_material_not_an_apple_framework(self):
  result=classify({'title':'Senior Computer Vision Engineer (Scientific Imaging)','description':'The first task is to find a thin, dense metal conductor inside the composite. Requirements: Python NumPy OpenCV. Nice to have: Small-dataset deep learning: segmentation, transfer learning.'})
  self.assertNotIn('apple',result['tags']);self.assertIn('research',result['tags'])
 def test_missing_evaluations_are_null_study_is_evidence_not_a_skill_score(self):
  result=snapshot(self.store,now=datetime(2026,10,19,tzinfo=timezone.utc));row=result['rows'][0]
  self.assertIsNone(row['fit']);self.assertIsNone(row['alignment']);self.assertIsNone(row['salary']);self.assertEqual(row['stage'],'none');self.assertEqual(result['api_requests'],0)
  self.assertIn('MIT',result['skills']['learning_evidence'][0]);self.assertEqual(result['skills']['github_links'],['https://github.com/example/research'])
 def test_version_bound_analysis_and_learning_rubric_not_embedding(self):
  req={'status':'studying','importance':'must','dimension':'research','resume_quotes':['Изучаю курс']}
  with self.store.connect() as db:db.execute('INSERT INTO skill_analyses VALUES(?,?,?,?,?,?,?,?,?)',('key',self.cv['id'],self.jd['id'],text_hash(matching_text(self.cv)),text_hash(document_text('vacancy',self.jd)),'Flow Matching','fixture','2026-08-01',json.dumps({'key':'key','requirements':[req]})))
  result=snapshot(self.store);self.assertEqual(result['rows'][0]['fit'],25);self.assertEqual(result['skills']['analyses'],1)
  with self.store.connect() as db:
   head=json.loads(db.execute("SELECT payload FROM entities WHERE kind='resume'").fetchone()[0]);head['sections'][0]['text']+=' New project';db.execute("UPDATE entities SET payload=? WHERE kind='resume'",(json.dumps(head),))
  self.assertIsNone(snapshot(self.store)['rows'][0]['fit'])
 def test_history_uses_received_versions_and_only_explicit_closure_not_missing(self):
  changed={**self.jd,'description':'RAG applications','collected_at':'2026-10-01T00:00:00Z'}
  with patch('src.archive_store.now_iso',return_value='2026-10-01T00:00:00+00:00'):self.store.sync({'client_id':CLIENT,'records':[record('vacancy',changed)]})
  with self.store.connect() as db:db.execute("INSERT INTO events(kind,entity_id,event,at,details) VALUES('vacancy',?,'missing','2026-09-01T00:00:00+00:00','{}')",(self.jd['id'],))
  result=snapshot(self.store,now=datetime(2026,10,19,tzinfo=timezone.utc));hist={p['month']:p for p in result['history']}
  self.assertEqual(hist['2026-08']['ids']['pretraining'],[self.jd['id']]);self.assertEqual(hist['2026-09']['ids']['pretraining'],[self.jd['id']]);self.assertEqual(hist['2026-10']['ids']['rag'],[self.jd['id']])
  with self.store.connect() as db:db.execute("INSERT INTO events(kind,entity_id,event,at,details) VALUES('vacancy',?,'closed','2026-09-20T00:00:00+00:00','{}')",(self.jd['id'],))
  after=snapshot(self.store,now=datetime(2026,10,19,tzinfo=timezone.utc));self.assertFalse(any(self.jd['id'] in ids for ids in after['history'][1]['ids'].values()))
 def test_authenticated_read_only_route_and_static_assets(self):
  with TestClient(create_app('fixture',archive_path=self.path)) as c:
   self.assertEqual(c.get('/archive/analytics').status_code,401);c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   with patch('openai.OpenAI',side_effect=AssertionError('No API in analytics')):
    response=c.get('/archive/analytics');self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['api_requests'],0)
   self.assertEqual(c.get('/assets/career-analytics.js').status_code,200);self.assertEqual(c.get('/assets/career-charts.js').status_code,200);self.assertEqual(c.get('/assets/career-analytics.css').status_code,200)
   self.assertEqual(c.get('/archive/analytics?model=unknown').status_code,422)
 def test_work_format_and_region_classification_in_snapshot(self):
  remote_job=job(id='hh_1001',text='Удалённая работа для ML инженера. Локация: Санкт-Петербург.',at='2026-08-01T00:00:00Z',locations=['Санкт-Петербург'])
  hybrid_job=job(id='hh_1002',text='Гибридный формат, офис в Москве.',at='2026-08-01T00:00:00Z',locations=['Москва'])
  with patch('src.archive_store.now_iso',return_value='2026-08-01T00:00:00+00:00'):
   self.store.sync({'client_id':CLIENT,'records':[record('vacancy',remote_job),record('vacancy',hybrid_job)]})
  result=snapshot(self.store,now=datetime(2026,10,19,tzinfo=timezone.utc))
  rows_by_id={r['id']:r for r in result['rows']}
  self.assertEqual(rows_by_id[remote_job['id']]['work_format'],'remote')
  self.assertEqual(rows_by_id[remote_job['id']]['region'],'spb')
  self.assertEqual(rows_by_id[hybrid_job['id']]['work_format'],'hybrid')
  self.assertEqual(rows_by_id[hybrid_job['id']]['region'],'moscow')
