import json,unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from src.tests import test_workflow as fixtures
from src.tests.test_archive import job,record,CLIENT
from src.resume_review import prepare,passages,run,AREAS,prompt
from src.analysis_store import text_hash,document_text
from src.application_workflow import packed

class ResumeReviewTests(unittest.TestCase):
 setUp=fixtures.WorkflowTests.setUp
 sync=fixtures.WorkflowTests.sync
 def output(self,ctx):
  cv,_=passages(ctx);key=next(iter(cv))
  return {'context_key':ctx['key'],'summary':'Подтверждения и план развития.','dimensions':[{'area':area,'status':'partial','comment':'Есть подтверждение в CV; масштаб требует уточнения.','evidence':[{'resume_passage_id':key,'quote':cv[key][:100]}],'next_steps':['Проверить метрики эксперимента.']} for area in AREAS],'projects':[{'title':'Исследовательский эксперимент','why':'Поддерживает карьерную цель.','deliverable':'Репозиторий с baseline, метрикой и абляцией.','job_passage_ids':[],'job_quotes':[]}],'questions':['Какие проекты были коммерческими?'],'limitations':['Нет достаточного числа вакансий.']}
 def test_no_api_import_caches_with_exact_sources_and_rejects_fabricated_evidence(self):
  result=prepare(self.archive,self.cv['id'],'DiT');ctx=result['context'];self.assertEqual(len(ctx['jobs']),0)
  bad=self.output(ctx);bad['dimensions'][0]['evidence'][0]['quote']='Работал в вымышленной компании больше двадцати лет.'
  with self.assertRaises(ValueError):run(self.archive,ctx['key'],raw=bad)
  imported=run(self.archive,ctx['key'],raw=self.output(ctx));self.assertEqual(imported['api_requests'],0)
  client=MagicMock();cached=run(self.archive,ctx['key'],client_factory=lambda:client);self.assertTrue(cached['cached']);client.assert_not_called()
  with self.archive.connect() as db:saved=json.loads(db.execute('SELECT payload FROM resume_review_contexts').fetchone()[0])
  self.assertEqual(saved['resume_version_id'],ctx['resume_version_id']);self.assertEqual(saved['resume_text'],ctx['resume_text'])
 def test_top_ten_use_only_current_cv_goal_and_job_hashes(self):
  jobs=[job('hh_'+str(i),at=self.jd['collected_at']) for i in range(1,13)]
  self.archive.sync({'client_id':CLIENT,'records':[record('vacancy',j) for j in jobs]})
  rank={'resume_id':self.cv['id'],'resume_hash':self.cv['content_hash'],'goal':'DiT','model':'text-embedding-3-small','generated_at':self.jd['collected_at'],'all':[{'id':j['id'],'score':1-i*.01,'vacancy_hash':text_hash(document_text('vacancy',j))} for i,j in enumerate(jobs)]}
  with self.archive.connect() as db:db.execute('INSERT INTO ranking_runs VALUES(?,?,?,?,?)',('r',self.cv['id'],rank['model'],rank['generated_at'],packed(rank)))
  ctx=prepare(self.archive,self.cv['id'],'DiT')['context'];self.assertEqual(len(ctx['jobs']),10);self.assertEqual(ctx['jobs'][0]['id'],'hh_1');self.assertIn('R1',prompt(ctx));self.assertEqual(prepare(self.archive,self.cv['id'],'Другие цели')['context']['jobs'],[])
  altered={**self.cv,'title':'New CV'}
  from src.resume_source import content_hash
  altered['content_hash']=content_hash(altered);self.sync(altered,self.jd)
  with self.assertRaises(ValueError):run(self.archive,ctx['key'],raw=self.output(ctx))
 def test_paid_generation_is_cached_and_invalid_response_never_causes_second_charge(self):
  ctx=prepare(self.archive,self.cv['id'],'DiT')['context'];client=MagicMock();client.responses.create.return_value=SimpleNamespace(status='completed',output_text=packed(self.output(ctx)))
  first=run(self.archive,ctx['key'],client_factory=lambda:client);second=run(self.archive,ctx['key'],client_factory=lambda:client);self.assertEqual(client.responses.create.call_count,1);self.assertTrue(second['cached']);self.assertFalse(client.responses.create.call_args.kwargs['store'])
  ctx=prepare(self.archive,self.cv['id'],'Another goal')['context'];client.responses.create.return_value=SimpleNamespace(status='completed',output_text='{}')
  for i in range(2):
   with self.assertRaises(ValueError):run(self.archive,ctx['key'],client_factory=lambda:client)
  self.assertEqual(client.responses.create.call_count,2)
 def test_user_experience_is_versioned_separately_and_invalidates_review_context(self):
  from src.resume_supplements import save,read
  before=prepare(self.archive,self.cv['id'],'DiT')['context']
  value={'key':'rambler','company':'Рамблер ДС','role':'Инженер-разработчик iOS','start':'2016-04-07','end':'2016-09-08','description':'Разработал раздел новостей на VIPER с кэшированием в Core Data.'}
  save(self.archive,self.cv['id'],value);save(self.archive,self.cv['id'],value)
  self.assertEqual(len(read(self.archive,self.cv['id'])),1)
  after=prepare(self.archive,self.cv['id'],'DiT')['context'];self.assertNotEqual(before['key'],after['key']);self.assertEqual(before['resume_hash'],after['resume_hash']);self.assertTrue(any(k.startswith('U') for k in passages(after)[0]))
  self.assertNotIn('Рамблер',self.archive.detail('resume',self.cv['id'])['text'])
  with self.assertRaises(ValueError):run(self.archive,after['key'],raw=self.output(before))
 def test_cookie_routes_reject_import_null_without_ever_calling_api(self):
  from fastapi.testclient import TestClient
  from resume_import_server import create_app
  from unittest.mock import patch
  app=create_app('fixture',archive_path=self.path)
  with TestClient(app) as client:
   self.assertEqual(client.post('/archive/resume-review',json={'op':'prepare','resume_id':self.cv['id']}).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   data=client.post('/archive/resume-review',headers={'Origin':'http://127.0.0.1:8788'},json={'op':'prepare','resume_id':self.cv['id']}).json()
   self.assertIn('context',data)
   with patch('src.resume_review.run') as generate:
    response=client.post('/archive/resume-review',headers={'Origin':'http://127.0.0.1:8788'},json={'op':'import','context_key':data['context']['key'],'analysis':None})
    self.assertEqual(response.status_code,422);generate.assert_not_called()
   self.assertEqual(client.post('/archive/resume-review',headers={'Origin':'https://evil.example'},json={'op':'generate','context_key':data['context']['key']}).status_code,401)
