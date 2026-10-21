import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from fastapi.testclient import TestClient
from src.tests.test_archive import cv,job,record,CLIENT
from src.archive_store import ArchiveStore
from src.application_store import ApplicationStore
from src.resume_source import content_hash
from src.extension_ranking import rank_vacancies
from src.tests.test_extension_ranking import FakeBackend
from resume_import_server import create_app

class WebRankingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.path=self.root/'state.sqlite3';ApplicationStore(self.path);self.archive=ArchiveStore(self.path)
  at=datetime.now(timezone.utc).isoformat();self.cv=cv(text='PyTorch Transformer. '*15,at=at);self.cv['content_hash']=content_hash(self.cv)
  self.jobs=[job('hh_1',text='PyTorch Transformer duties. '*15,company='Сбер. AI',at=at),job('hh_2',text='Swift work. '*20,company='SberTech',at=at),job('hh_3',text='PyTorch Transformer duties. '*15,company='Yandex',at=at),job('hh_4',text='Closed role. '*20,company='Sber',archived=True,at=at)]
  self.archive.sync({'client_id':CLIENT,'records':[record('resume',self.cv),*[record('vacancy',j) for j in self.jobs]]});FakeBackend.calls=[]
 def test_company_filter_uses_group_aliases_not_text_search_and_applies_before_pagination(self):
  result=self.archive.entities('vacancy',company='sber',limit=1,exclude_closed=True);self.assertEqual(result['total'],2);self.assertEqual(len(result['items']),1)
  self.assertEqual(self.archive.entities('vacancy',company='yandex')['total'],1);self.assertEqual(self.archive.entities('vacancy',company='missing')['total'],0)
 def test_web_rank_uses_one_cv_selected_company_and_caches_repeat_without_backend(self):
  requests=[]
  def runner(packet,cache):
   requests.append(packet);return rank_vacancies(packet,self.root/'vectors',archive=self.archive,backend_factory=FakeBackend)
  with TestClient(create_app('fixture',ranker=runner,archive_path=self.path)) as c:
   self.assertEqual(c.post('/archive/rank',json={}).status_code,401);c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   data={'resume_id':self.cv['id'],'company':'sber','goal':'DiT','model':'text-embedding-3-small'};h={'Origin':'http://127.0.0.1:8788'}
   response=c.post('/archive/rank',json=data,headers=h);self.assertEqual(response.status_code,200,response.text)
   self.assertEqual({j['id'] for j in requests[0]['vacancies']},{'hh_1','hh_2'});self.assertEqual(len(requests[0]['bundle']['resumes']),1)
   before=len(FakeBackend.calls);again=c.post('/archive/rank',json={**data,'allow_api':False},headers=h);self.assertEqual(again.status_code,200);self.assertEqual(again.json()['api_requests'],0);self.assertEqual(len(FakeBackend.calls),before)
   rows=c.get('/archive/entities',params={'kind':'vacancy','company':'sber','resume_id':self.cv['id'],'goal':'DiT','ranked_only':True}).json();self.assertEqual(rows['total'],2)
   self.assertEqual(c.get('/archive/entities',params={'kind':'vacancy','resume_id':self.cv['id'],'goal':'other','ranked_only':True}).json()['total'],0)
 def test_cache_only_uses_existing_vectors_without_key_and_never_falls_back_for_new_text(self):
  vector=[1.0]+[0.0]*1535;client=MagicMock()
  client.embeddings.create.side_effect=lambda **kw:SimpleNamespace(data=[SimpleNamespace(index=i,embedding=vector) for i in range(len(kw['input']))],usage=SimpleNamespace(total_tokens=10))
  packet={'resume_id':self.cv['id'],'bundle':{'resumes':[self.cv]},'vacancies':[self.jobs[0]],'goal':'','model':'text-embedding-3-small'}
  with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture'}),patch('openai.OpenAI',return_value=client):first=rank_vacancies(packet,self.root/'vectors',archive=self.archive)
  self.assertGreater(first['api_requests'],0)
  with self.archive.connect() as db:db.execute('DELETE FROM ranking_runs')
  with patch.dict('os.environ',{},clear=True),patch('openai.OpenAI',side_effect=AssertionError('Must not construct paid client')):
   result=rank_vacancies({**packet,'allow_api':False},self.root/'vectors',archive=self.archive);self.assertEqual(result['api_requests'],0);self.assertEqual(result['ranked_count'],1)
   with self.assertRaisesRegex(ValueError,'не хватает готовых векторов'):rank_vacancies({**packet,'goal':'New DiT goal','allow_api':False},self.root/'vectors',archive=self.archive)
   with self.assertRaises(ValueError):rank_vacancies({**packet,'allow_api':'false'},self.root/'vectors',archive=self.archive)
