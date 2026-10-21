import json,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.tests import test_web_ranking_modes as fixtures
from src.company_catalog import read,save,validate
from src.company_filter import company_key
from src.extension_ranking import rank_vacancies
from src.tests.test_extension_ranking import FakeBackend
from resume_import_server import create_app

class CompanyCatalogTests(unittest.TestCase):
 setUp=fixtures.WebRankingTests.setUp
 def test_editable_tiers_persist_and_longer_team_alias_wins(self):
  before=read(self.archive);catalog=before['companies'];by_id={c['id']:c for c in catalog}
  self.assertEqual(company_key('МТС AI',catalog),'mws');self.assertEqual(company_key('СберМегаМаркет',catalog),'megamarket')
  by_id['sber']['tier']='second';by_id['sber']['label']='Мой Сбер';by_id['sber']['boards'][0]['description_selector']='.custom-jd'
  saved=save(self.archive,{'revision':before['revision'],'companies':catalog})
  self.assertNotEqual(saved['revision'],before['revision']);self.assertEqual(next(c for c in saved['companies'] if c['id']=='sber')['tier'],'second')
  self.assertEqual(next(c for c in read(self.archive)['companies'] if c['id']=='sber')['boards'][0]['status'],'custom')
  with self.assertRaisesRegex(ValueError,'другом окне'):save(self.archive,{'revision':before['revision'],'companies':catalog})
  with self.archive.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM company_catalog_history').fetchone()[0],2)
 def test_multi_selection_filters_before_pagination_and_none_means_zero(self):
  result=self.archive.entities('vacancy',companies=['sber','yandex'],exclude_closed=True,limit=1)
  self.assertEqual(result['total'],3);self.assertEqual(len(result['items']),1)
  self.assertEqual(self.archive.entities('vacancy',companies=[])['total'],0)
  self.assertEqual(self.archive.entities('vacancy',companies=['missing'])['total'],0)
 def test_authenticated_settings_and_multi_rank_share_the_same_catalog(self):
  requests=[]
  def runner(packet,cache):requests.append(packet);return rank_vacancies(packet,self.root/'vectors',archive=self.archive,backend_factory=FakeBackend)
  with TestClient(create_app('fixture',ranker=runner,archive_path=self.path)) as c:
   self.assertEqual(c.get('/archive/company-settings').status_code,401)
   c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   data=c.get('/archive/company-settings').json();self.assertIn('adapters',data)
   h={'Origin':'http://127.0.0.1:8788'}
   self.assertEqual(c.post('/archive/company-settings',json=data,headers={'Origin':'https://evil.example'}).status_code,401)
   self.assertEqual(c.post('/archive/company-settings',json=data,headers=h).status_code,200)
   companies=c.get('/archive/companies').json()['items'];self.assertEqual(next(i for i in companies if i['id']=='alfa')['tier'],'second')
   self.assertEqual(c.get('/archive/entities',params={'companies':'[]'}).json()['total'],0)
   self.assertEqual(c.get('/archive/entities',params={'companies':'bad'}).status_code,422)
   body={'resume_id':self.cv['id'],'companies':['sber','yandex'],'allow_api':True,'goal':'ML'}
   response=c.post('/archive/rank',json=body,headers=h);self.assertEqual(response.status_code,200,response.text)
   self.assertEqual({j['id'] for j in requests[-1]['vacancies']},{'hh_1','hh_2','hh_3'})
   before=len(FakeBackend.calls);response=c.post('/archive/rank',json={**body,'allow_api':False},headers=h)
   self.assertEqual(response.status_code,200);self.assertEqual(response.json()['api_requests'],0);self.assertEqual(len(FakeBackend.calls),before)
   response=c.post('/archive/rank',json={**body,'companies':[]},headers=h);self.assertEqual(len(FakeBackend.calls),before)
   backup=c.get('/archive/export').json()['tables'];self.assertIn('company_catalog_history',backup)
 def test_catalog_rejects_invalid_urls_or_tiers_and_lists_missing_adapters_honestly(self):
  data=read(self.archive);company=data['companies'][0];company['boards']=[{'url':'https://jobs.example.org/jobs','description_selector':'.jd'}]
  saved=save(self.archive,data);board=saved['companies'][0]['boards'][0];self.assertEqual(board['status'],'custom');self.assertIsNone(board['adapter_id'])
  for url in ['javascript:alert(1)','http://example.org/jobs','https://user:secret@example.org/jobs']:
   company['boards'][0]['url']=url
   with self.assertRaises(ValueError):validate(data['companies'])
