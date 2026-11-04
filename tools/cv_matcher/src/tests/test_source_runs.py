import asyncio,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src import source_runs
from src.python_collection import collect
from src.scrapers.ru_sber import SberScraper
from src.board_import import identity

TEXT='Обязанности и требования к роли. '*10
def row(number,quality='full',source='sber'):
    link=f'https://rabota.sber.ru/search/{number}' if source=='sber' else f'https://yandex.ru/jobs/vacancies/role-{number}'
    return {'title':f'Role {number}','company':'Сбер','description':TEXT,'description_quality':quality,'link':link,'locations':['Москва']}
def publication(number,**extra):
    return {'internalId':number,'title':f'ML role {number}','company':'ПАО Сбербанк','introduction':'Команда ML.','duties':'*   обучать модели\n*   запускать эксперименты '+'x'*80,'requirements':'*   Python\n*   PyTorch '+'y'*80,'conditions':'• офис','city':'г Москва','publicationDate':'2026-10-26T06:59:33.000Z','salary_min':None,'salary_max':None,'specialization':'ИТ',**extra}

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);path=Path(self.tmp.name)/'a.sqlite3'
        ApplicationStore(path);self.archive=ArchiveStore(path);self.runner=source_runs.Runner(self.archive)
    def run_id(self,source='sber'):
        self.runner.start([source])
        with self.archive.connect() as db:return db.execute('SELECT id FROM source_runs WHERE source=? ORDER BY created DESC',(source,)).fetchone()[0]
    def last(self,source='sber'):
        return next(i['last'] for i in self.runner.status()['items'] if i['source']==source)

class Runs(Fixture):
    def test_saves_each_query_and_a_repeat_only_asks_for_what_is_missing(self):
        seen=[]
        def executor(payload,stopped):
            seen.append(payload['known_ids']);return {'rows':[row(1001),row(1002,'needs_review')],'report':{'listed':50,'errors':0}}
        with patch.object(source_runs,'SOURCES',{'sber':{**source_runs.SOURCES['sber'],'queries':source_runs.SOURCES['sber']['queries'][:2]}}):
            state=source_runs.run_one(self.archive,self.run_id(),'sber',threading.Event(),executor)
        self.assertEqual(state,'complete');self.assertEqual(seen,[[],['sber_1001']])
        progress=self.last()['progress'];self.assertEqual(progress['new'],2);self.assertEqual(progress['updated'],2);self.assertEqual(progress['listed'],100);self.assertEqual(progress['done'],2)
        self.assertEqual(self.archive.detail('vacancy','sber_1001')['payload']['collector'],'python')
    def test_empty_listing_is_failure_and_errors_are_partial(self):
        state=source_runs.run_one(self.archive,self.run_id(),'yandex',threading.Event(),lambda p,s:{'rows':[],'report':{'listed':0,'errors':0}})
        self.assertEqual(state,'failed')
        state=source_runs.run_one(self.archive,self.run_id(),'yandex',threading.Event(),lambda p,s:{'rows':[row(7,source='yandex')],'report':{'listed':5,'errors':1}})
        self.assertEqual(state,'partial')
    def test_timeout_reason_is_reported_without_losing_earlier_rows(self):
        answers=iter([{'rows':[row(1001)],'report':{'listed':9,'errors':0}},{'rows':[],'reason':'python_timeout'}])
        with patch.object(source_runs,'SOURCES',{'sber':{**source_runs.SOURCES['sber'],'queries':source_runs.SOURCES['sber']['queries'][:2]}}):
            state=source_runs.run_one(self.archive,self.run_id(),'sber',threading.Event(),lambda p,s:next(answers))
        self.assertEqual(state,'partial');self.assertEqual(self.last()['progress']['reasons'],['python_timeout']);self.assertTrue(self.archive.detail('vacancy','sber_1001'))
    def test_stop_ends_before_next_query(self):
        stop=threading.Event();calls=[]
        def executor(payload,stopped):
            calls.append(1);stop.set();return {'rows':[row(1001)],'report':{'listed':1,'errors':0}}
        self.assertEqual(source_runs.run_one(self.archive,self.run_id(),'sber',stop,executor),'stopped');self.assertEqual(len(calls),1)
    def test_same_source_is_not_started_twice_and_unknown_is_refused(self):
        self.assertEqual(self.runner.start(['sber'])['started'],['sber']);self.assertEqual(self.runner.start(['sber','yandex'])['started'],['yandex'])
        with self.assertRaises(ValueError):self.runner.start(['hh'])
    def test_queue_runs_in_order_and_restart_marks_leftovers_interrupted(self):
        order=[]
        def executor(payload,stopped):order.append(payload['source_key']);return {'rows':[],'report':{'listed':1,'errors':0}}
        self.runner.executor=executor
        with patch.object(source_runs,'SOURCES',{'yandex':source_runs.SOURCES['yandex'],'sber':{**source_runs.SOURCES['sber'],'queries':source_runs.SOURCES['sber']['queries'][:1]}}):
            self.runner.start(['yandex','sber']);asyncio.run(self.runner._drain())
            self.assertEqual(self.last('yandex')['state'],'complete');self.assertEqual(self.last('sber')['state'],'complete')
        self.assertEqual(order[0],'yandex')
        self.runner.start(['sber']);source_runs.Runner(self.archive);self.assertEqual(self.last()['state'],'interrupted')

class Routes(Fixture):
    def test_requires_login_and_exposes_status(self):
        from fastapi.testclient import TestClient
        from resume_import_server import create_app
        client=TestClient(create_app('fixture-token-fixture-token',archive_path=self.archive.path))
        self.assertEqual(client.get('/archive/source-runs').status_code,401)
        client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture-token-fixture-token'})
        data=client.get('/archive/source-runs').json();self.assertEqual([i['source'] for i in data['items']][:2],['yandex','sber']);self.assertIn('deepmind',[i['source'] for i in data['items'] if i['fast']])
        self.assertEqual(client.post('/archive/source-runs',json={'op':'start','sources':['hh']},headers={'origin':'http://127.0.0.1:8788'}).status_code,422)
        self.assertEqual(client.post('/archive/source-runs',json={'op':'start','sources':['sber']},headers={'origin':'https://evil.example'}).status_code,401)
        self.assertEqual(client.get('/assets/source-runs.js').status_code,200)

class Response:
    ok=True;status=200
    def __init__(self,data):self.data=data
    def json(self):return self.data
class Request:
    def __init__(self,pages,fail=False):self.pages=list(pages);self.urls=[];self.fail=fail
    def get(self,url,timeout=0):
        self.urls.append(url)
        if self.fail:raise RuntimeError('blocked')
        return Response({'data':self.pages.pop(0),'success':True})
class Page:
    def __init__(self,request):self.request=request
    def goto(self,*a,**k):pass

class SberAPI(unittest.TestCase):
    def scraper(self,limit=10):return SberScraper(limit=limit,archive_path=False)
    def test_list_pages_become_clean_full_rows_with_valid_identity(self):
        request=Request([{'vacancies':[publication(1001),publication(1002)],'total':3},{'vacancies':[publication(1003)],'total':3}])
        s=self.scraper();s.api_page_size=2
        with patch('time.sleep'):rows=s._scrape(Page(request),'ML',{'sber_1002'})
        self.assertEqual([r['id'] for r in rows],['sber_1001','sber_1003']);self.assertEqual(s.report['listed'],3)
        self.assertEqual(rows[0]['description_quality'],'full');self.assertIn('Обязанности:\n- обучать',rows[0]['description']);self.assertNotIn('Вакансии',rows[0]['description'])
        self.assertEqual(identity(rows[0]['link'])['id'],'sber_1001');self.assertIn('searchString=ML',request.urls[0]);self.assertIn('skip=2',request.urls[1])
    def test_missing_sections_need_review_and_unrelated_rows_are_dropped(self):
        s=self.scraper()
        self.assertEqual(s._publication(publication(1,requirements=''),'','',set())['description_quality'],'needs_review')
        self.assertIsNone(s._publication(publication(2),'Diffusion','diffusion',set()))
    def test_failure_after_first_page_is_counted(self):
        class Flaky(Request):
            def get(self,url,timeout=0):
                if self.pages:return super().get(url)
                raise RuntimeError('blocked')
        s=self.scraper();s.api_page_size=1
        with patch('time.sleep'):rows=s._scrape(Page(Flaky([{'vacancies':[publication(1001)],'total':5}])),'',set())
        self.assertEqual(len(rows),1);self.assertEqual(s.report['errors'],1);self.assertEqual(s.report['coverage'],'partial')
    def test_a_hung_request_is_retried_once(self):
        class Hangs(Request):
            def get(self,url,timeout=0):
                self.urls.append(url)
                if len(self.urls)==1:raise TimeoutError('hung')
                return Response({'data':self.pages.pop(0)})
        s=self.scraper();request=Hangs([{'vacancies':[publication(1001)],'total':1}])
        with patch('time.sleep'):rows=s._scrape(Page(request),'',set())
        self.assertEqual(len(rows),1);self.assertEqual(len(request.urls),2);self.assertEqual(s.report['errors'],0)
    def test_a_refusal_is_not_retried_and_is_reported(self):
        class Refused(Request):
            def get(self,url,timeout=0):
                self.urls.append(url);r=Response({});r.ok=False;r.status=403;return r
        s=self.scraper();request=Refused([])
        self.assertEqual(s._scrape(Page(request),'',set()),[]);self.assertEqual(len(request.urls),1);self.assertEqual(s.report['errors'],1);self.assertEqual(s.report['listed'],0)
    def test_collect_passes_known_ids_and_returns_report(self):
        calls={}
        class Fake:
            def __init__(self,**k):self.report={'listed':4,'errors':0};calls['limit']=k['limit']
            def fetch_jobs(self,search,existing_ids):calls.update(search=search,known=existing_ids);return []
        with patch.dict('src.scrapers.SCRAPER_REGISTRY',{'sber':Fake}):
            result=collect({'source_key':'sber','query':'ML','known_ids':['sber_1'],'options':{'details':500,'source_run':True}})
        self.assertEqual(calls,{'limit':500,'search':'ML','known':{'sber_1'}});self.assertEqual(result['report']['listed'],4)

class Sources(Fixture):
    def test_every_source_has_a_scraper_and_foreign_hosts_are_not_saved(self):
        from src.scrapers import SCRAPER_REGISTRY
        from src.python_collection import persist
        self.assertFalse(set(source_runs.SOURCES)-set(SCRAPER_REGISTRY))
        rows=[{'title':'Role','description':TEXT,'description_quality':'full','link':'https://job-boards.greenhouse.io/anthropic/jobs/1'},{'title':'Foreign','description':TEXT,'description_quality':'full','link':'https://evil.example/jobs/2'}]
        result=persist(self.archive,{'allowed_hosts':source_runs.SOURCES['anthropic']['hosts'],'adapter_id':'anthropic'},{'rows':rows})
        self.assertEqual(len(result['ids']),1);self.assertEqual(self.archive.entities('vacancy')['total'],1)
        self.assertEqual(SCRAPER_REGISTRY['xai'].board,'xai');self.assertEqual(SCRAPER_REGISTRY['xai'].company_name,source_runs.SOURCES['xai']['label'])
    def test_limited_batches_repeat_until_nothing_new_and_save_each_round(self):
        batches=iter([[1,2],[3],[]])
        def executor(payload,stopped):
            rows=[{**row(n,source='yandex')} for n in next(batches)];return {'rows':rows,'report':{'listed':9,'errors':0,'coverage':'limited'}}
        with patch.dict(source_runs.SOURCES,{'yandex':{**source_runs.SOURCES['yandex'],'rounds':5}}):
            self.assertEqual(source_runs.run_one(self.archive,self.run_id('yandex'),'yandex',threading.Event(),executor),'complete')
        self.assertEqual(self.last('yandex')['progress']['new'],3)
    def test_google_rows_are_skipped_by_scraper_id_and_deepmind_relabels_google_rows(self):
        link='https://www.google.com/about/careers/applications/jobs/results/12345-role'
        self.archive.sync({'client_id':'client_12345','records':[]})
        from src.python_collection import persist
        persist(self.archive,{'allowed_hosts':{'www.google.com'},'adapter_id':'google'},{'rows':[{'title':'Role','company':'Google','description':TEXT,'description_quality':'full','link':link}]})
        _,google=source_runs._known(self.archive,source_runs.SOURCES['google'],'google');self.assertEqual(google,{'goog_12345'})
        _,deepmind=source_runs._known(self.archive,source_runs.SOURCES['deepmind'],'deepmind');self.assertEqual(deepmind,set())

class BoardAPIs(unittest.TestCase):
    def test_greenhouse_rows_are_clean_and_known_ones_skipped(self):
        from src.scrapers.ats import AnthropicScraper
        s=AnthropicScraper(limit=10,archive_path=False)
        jobs=[{'absolute_url':f'https://job-boards.greenhouse.io/anthropic/jobs/{n}','title':f'Role {n}','content':'&lt;p&gt;'+'Build models. '*20+'&lt;/p&gt;','location':{'name':'SF | Seattle'},'departments':[{'name':'Research'}],'first_published':'2026-10-01T00:00:00-04:00'} for n in (1,2)]
        with patch.object(s,'_get',return_value={'jobs':jobs}):first=s.fetch_jobs('');known={first[0]['id']}
        self.assertEqual(first[0]['locations'],['SF','Seattle']);self.assertNotIn('<p>',first[0]['description']);self.assertEqual(first[0]['description_quality'],'full')
        with patch.object(s,'_get',return_value={'jobs':jobs}):second=s.fetch_jobs('',existing_ids=known)
        self.assertEqual(len(second),1);self.assertEqual(s.report['listed'],2);self.assertEqual(s.report['coverage'],'listing_exhausted')
    def test_ashby_skips_unlisted_and_network_failure_raises(self):
        import requests
        from src.scrapers.ats import OpenAIScraper
        s=OpenAIScraper(limit=10,archive_path=False)
        jobs=[{'jobUrl':'https://jobs.ashbyhq.com/openai/a','title':'Listed','descriptionPlain':'Research work. '*20,'location':'SF','isListed':True},{'jobUrl':'https://jobs.ashbyhq.com/openai/b','title':'Hidden','descriptionPlain':'x','isListed':False}]
        with patch.object(s,'_get',return_value={'jobs':jobs}):self.assertEqual([r['title'] for r in s.fetch_jobs('')],['Listed'])
        with patch.object(s,'_get',side_effect=requests.ConnectionError()),self.assertRaises(RuntimeError):s.fetch_jobs('')

