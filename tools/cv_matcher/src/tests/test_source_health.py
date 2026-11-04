import io,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from src.archive_store import ArchiveStore
from src.scrapers._base import BaseScraper
from src.tests.test_archive import job,record
from scripts import check_scrape_health,scrape_online

class ArchiveEvents(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'archive.sqlite3';self.store=ArchiveStore(self.path)
    def sync(self,*records):
        result=self.store.sync({'client_id':'client_12345','records':list(records)});self.assertFalse(result['rejected']);return result
    def events(self,identifier='hh_1'):
        with self.store.connect() as db:return [r[0] for r in db.execute('SELECT event FROM events WHERE entity_id=? ORDER BY id',(identifier,))]
    def test_first_confirmation_is_not_reopening(self):
        self.sync(record('vacancy',job(description_quality='snippet',source_page='https://hh.ru/search/vacancy')))
        self.sync(record('vacancy',job(at='2026-10-14T13:00:00Z')))
        self.assertIn('confirmed_active',self.events());self.assertNotIn('reopened',self.events())
        self.assertNotIn('confirmed_active',[r['event'] for r in self.store.timeline()['items']])
    def test_migration_relabels_only_events_without_earlier_closure_and_runs_once(self):
        with self.store.connect() as db:
            db.execute("DELETE FROM archive_meta WHERE key='migration:confirmed-active-events'")
            for entity,event in (('false','reopened'),('real','closed'),('real','reopened')):
                db.execute("INSERT INTO events(kind,entity_id,event,at,details) VALUES('vacancy',?,?,'2026-10-14T10:00:00+00:00','{}')",(entity,event))
        ArchiveStore(self.path)
        self.assertEqual(self.events('false'),['confirmed_active']);self.assertEqual(self.events('real'),['closed','reopened'])
        with self.store.connect() as db:db.execute("INSERT INTO events(kind,entity_id,event,at,details) VALUES('vacancy','later','reopened','2026-10-15T10:00:00+00:00','{}')")
        ArchiveStore(self.path);self.assertEqual(self.events('later'),['reopened'])
    def test_newest_vacancy_comes_first_after_older_one_is_resynced(self):
        self.sync(record('vacancy',job('hh_1')));self.sync(record('vacancy',job('hh_2')))
        self.sync(record('vacancy',job('hh_1',text='Обновлённый текст',at='2026-10-14T13:00:00Z')))
        self.assertEqual([r['id'] for r in self.store.entities('vacancy')['items']],['hh_2','hh_1'])

class BrokenScraper(BaseScraper):
    def _scrape(self,page,query,existing_ids):raise RuntimeError('layout changed')

class ScraperReports(unittest.TestCase):
    def test_base_scraper_records_failure_and_keeps_empty_result(self):
        scraper=BrokenScraper(archive_path=False);events=[];scraper.event_sink=events.append
        with patch('src.scrapers._base.sync_playwright') as runtime,patch('src.scrapers._base._launch_browser'):
            runtime.return_value.__enter__.return_value=Mock()
            self.assertEqual(scraper.fetch_jobs('ML'),[])
        self.assertEqual(scraper.report['errors'],1);self.assertEqual(scraper.report['coverage'],'partial')
        self.assertTrue(any(e['type']=='error' for e in events))
    def run_source(self,report,empty_is_error=True):
        scraper=Mock(report=report,empty_listing_is_error=empty_is_error);scraper.fetch_jobs.return_value=[]
        saved={}
        def save(by_id,stats,now):saved.update(json.loads(json.dumps(stats)))
        with patch('sys.argv',['scrape_online','--scrapers','yandex']),patch.object(scrape_online,'_source_plan',return_value=[('yandex',Mock(return_value=scraper),['q'])]),patch.object(scrape_online,'_load_existing',return_value={}),patch.object(scrape_online,'_save',side_effect=save):
            self.assertEqual(scrape_online.main(),0)
        return saved['yandex']
    def test_empty_listing_fails_source_even_with_no_exception(self):
        self.assertTrue(self.run_source({'listed':0,'errors':0})['failed'])
    def test_listing_with_only_known_rows_is_healthy(self):
        result=self.run_source({'listed':120,'errors':0});self.assertFalse(result['failed']);self.assertEqual(result['new'],0)
    def test_adapter_can_opt_out_of_empty_listing_rule_but_not_of_errors(self):
        self.assertFalse(self.run_source({'listed':0,'errors':0},False)['failed'])
        self.assertTrue(self.run_source({'listed':0,'errors':2},False)['failed'])
    def test_health_check_fails_only_for_failed_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'export.json'
            def run(stats):
                path.write_text(json.dumps({'stats_last_run':stats}));out=io.StringIO();return check_scrape_health.check(path,out),out.getvalue()
            code,text=run({'meta':{'listed':0,'errors':1,'failed':True},'google':{'listed':9,'errors':0,'failed':False}});self.assertEqual(code,1);self.assertIn('::error::meta',text)
            code,text=run({'google':{'listed':9,'errors':2,'failed':False}});self.assertEqual(code,0);self.assertIn('::warning::google',text)
            self.assertEqual(run({})[0],1)

class SavedResults(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        from src.application_store import ApplicationStore
        ApplicationStore(Path(self.tmp.name)/'archive.sqlite3')
        self.store=ArchiveStore(Path(self.tmp.name)/'archive.sqlite3')
        self.store.sync({'client_id':'client_12345','records':[record('vacancy',job('hh_1',text='PyTorch diffusion research '*12)),record('vacancy',job('hh_2',text='Backend Python service '*12))]})
    def test_results_match_direct_computation_and_changed_text_is_recomputed(self):
        from src import vacancy_derived as derived
        from src.career_analytics import classify,snapshot,history_part
        self.assertFalse(derived.status(self.store)['rows_ready'])
        derived.warm(self.store,pause=0);state=derived.status(self.store)
        self.assertTrue(state['rows_ready']);self.assertTrue(state['history_ready']);self.assertEqual(set(state['missing'].values()),{0})
        detail=self.store.detail('vacancy','hh_1')
        rows={r['id']:r for r in snapshot(self.store)['rows']}
        self.assertEqual(rows['hh_1']['tags'],classify(detail['payload'])['tags'])
        self.sync_change();rows={r['id']:r for r in snapshot(self.store)['rows']}
        self.assertEqual(rows['hh_1']['tags'],classify(self.store.detail('vacancy','hh_1')['payload'])['tags']);self.assertIn('diffusion',rows['hh_1']['tags'])
        self.assertEqual(len(history_part(self.store)['history'][-1]['ids']),len(rows and snapshot(self.store)['history'][-1]['ids']))
    def sync_change(self):
        self.store.sync({'client_id':'client_12345','records':[record('vacancy',job('hh_1',text='Diffusion and flow matching models '*12,at='2026-10-14T13:00:00Z'))]})
    def test_rule_change_invalidates_saved_results(self):
        from src import vacancy_derived as derived
        derived.warm(self.store,pause=0)
        with patch.object(derived,'engine',lambda family:'new-rules'):
            self.assertFalse(derived.status(self.store)['rows_ready'])
            with self.store.connect() as db:self.assertEqual(derived.heads(db,'taxonomy'),{})
    def test_payload_callers_read_real_text_not_saved_facts(self):
        from src import vacancy_derived as derived
        derived.warm(self.store,pause=0)
        with self.store.connect() as db:db.execute("UPDATE entities SET payload=json_set(payload,'$.description_quality','snippet') WHERE id='hh_1'")
        self.assertEqual(self.store.entities('vacancy',status='full',all_items=True,include_payload=True)['total'],1)
    def test_routes_require_login_and_return_each_part(self):
        from fastapi.testclient import TestClient
        from resume_import_server import create_app
        client=TestClient(create_app('fixture-token-fixture-token',archive_path=self.store.path))
        self.assertEqual(client.get('/archive/analytics/status').status_code,401)
        client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture-token-fixture-token'})
        self.assertIn('missing',client.get('/archive/analytics/status').json())
        rows=client.get('/archive/analytics?history=false&evidence=false').json()
        self.assertEqual(rows['history'],[]);self.assertNotIn('classification_evidence',rows['rows'][0])
        self.assertIn('history',client.get('/archive/analytics/history').json())
        self.assertIn('hh_1',client.get('/archive/analytics/evidence?ids=hh_1').json()['items'])
        self.assertEqual(client.get('/assets/busy.js').status_code,200)
