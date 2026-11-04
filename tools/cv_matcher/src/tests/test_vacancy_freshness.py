import io,json,tempfile,threading,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src import source_runs
from src.tests.test_archive import job,record
from scripts import scrape_online

TEXT='Обязанности и требования к роли. '*10
def ids(n,start=1):return {f'hh_{i}' for i in range(start,start+n)}

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);path=Path(self.tmp.name)/'a.sqlite3'
        ApplicationStore(path);self.store=ArchiveStore(path)
    def add(self,*names):
        self.store.sync({'client_id':'client_12345','records':[record('vacancy',job(n)) for n in names]})
    def listing(self,identifier):
        return self.store.detail('vacancy',identifier)['listing']
    def events(self,identifier):
        with self.store.connect() as db:return [r[0] for r in db.execute('SELECT event FROM events WHERE entity_id=? ORDER BY id',(identifier,))]

class Listings(Fixture):
    def test_absent_from_complete_listing_is_gone_then_returns_with_events(self):
        self.add('hh_1','hh_2')
        self.store.record_listing('a','src','https://x.example/',{'hh_1','hh_2'},complete=True)
        self.assertEqual(self.listing('hh_1')['state'],'listed')
        self.store.record_listing('b','src','https://x.example/',{'hh_1'},complete=True)
        gone=self.listing('hh_2');self.assertEqual(gone['state'],'gone');self.assertIn('missing',self.events('hh_2'))
        self.assertEqual(self.store.detail('vacancy','hh_2')['availability'],'active')
        self.store.record_listing('c','src','https://x.example/',{'hh_1','hh_2'},complete=True)
        self.assertEqual(self.listing('hh_2')['state'],'listed');self.assertIn('returned',self.events('hh_2'))
    def test_partial_listing_never_marks_absence(self):
        self.add('hh_1','hh_2')
        self.store.record_listing('a','src','https://x.example/',{'hh_1','hh_2'},complete=True)
        self.store.record_listing('b','src','https://x.example/',{'hh_1'},complete=False)
        self.assertEqual(self.listing('hh_2')['state'],'listed')
    def test_listing_that_halves_is_treated_as_site_fault(self):
        names=sorted(ids(12));self.add(*names)
        self.store.record_listing('a','src','https://x.example/',set(names),complete=True)
        result=self.store.record_listing('b','src','https://x.example/',{'hh_1'},complete=True)
        self.assertTrue(result['suspicious']);self.assertFalse(result['complete']);self.assertEqual(self.listing('hh_2')['state'],'listed')
    def test_universe_marks_old_rows_absent_without_flooding_events(self):
        self.add('hh_1','hh_2')
        self.store.record_listing('a','src','https://x.example/',{'hh_1'},complete=True,universe={'hh_1','hh_2'})
        self.assertEqual(self.listing('hh_2')['state'],'gone');self.assertNotIn('missing',self.events('hh_2'))
    def test_unknown_ids_are_ignored_and_retry_is_idempotent(self):
        self.add('hh_1')
        self.assertEqual(self.store.record_listing('a','src','https://x.example/',{'hh_1','hh_404'},complete=True)['seen'],1)
        self.assertTrue(self.store.record_listing('a','src','https://x.example/',{'hh_1'},complete=True)['duplicate'])
    def test_filters_and_list_rows_show_latest_observation(self):
        self.add('hh_1','hh_2','hh_3')
        self.store.record_listing('a','src','https://x.example/',{'hh_1','hh_2'},complete=True)
        self.store.record_listing('b','src','https://x.example/',{'hh_1'},complete=True)
        self.assertEqual([r['id'] for r in self.store.entities('vacancy',status='listed')['items']],['hh_1'])
        self.assertEqual([r['id'] for r in self.store.entities('vacancy',status='gone')['items']],['hh_2'])
        rows={r['id']:r for r in self.store.entities('vacancy')['items']}
        self.assertEqual(rows['hh_2']['listing']['state'],'gone');self.assertIsNone(rows['hh_3']['listing'])
    def test_gone_in_one_scope_but_seen_later_in_another_counts_as_listed(self):
        self.add('hh_1')
        self.store.record_listing('a','one','https://x.example/1',set(),complete=True,universe={'hh_1'})
        self.store.record_listing('b','two','https://x.example/2',{'hh_1'},complete=True)
        self.assertEqual(self.listing('hh_1')['state'],'listed')
    def test_market_changes_counts_by_company(self):
        self.add('hh_1','hh_2')
        self.store.record_listing('a','src','https://x.example/',{'hh_1','hh_2'},complete=True)
        self.store.record_listing('b','src','https://x.example/',{'hh_1'},complete=True)
        data=self.store.market_changes(7);self.assertEqual(sum(r['missing'] for r in data['items']),1);self.assertEqual(sum(r['added'] for r in data['items']),2);self.assertIn('не доказывает',data['note'])

def board_row(n):
    return {'title':f'Role {n}','company':'Anthropic','description':TEXT,'description_quality':'full','link':f'https://job-boards.greenhouse.io/anthropic/jobs/{n}'}

class Runs(Fixture):
    def run_board(self,rows,seen,coverage='listing_exhausted'):
        runner=source_runs.Runner(self.store);runner.start(['anthropic'])
        with self.store.connect() as db:run=db.execute("SELECT id FROM source_runs ORDER BY rowid DESC").fetchone()[0]
        state=source_runs.run_one(self.store,run,'anthropic',threading.Event(),lambda p,s:{'rows':rows,'report':{'listed':len(seen),'errors':0,'coverage':coverage},'seen_ids':seen})
        return state,self.store.entities('vacancy',status='gone')['total']
    def test_board_run_marks_old_rows_gone_only_when_listing_was_whole(self):
        from src.board_import import identity
        first=[identity(board_row(n)['link'])['id'] for n in (1,2)]
        self.assertEqual(self.run_board([board_row(1),board_row(2)],first)[1],0)
        self.assertEqual(self.run_board([],first[:1],'limited')[1],0)
        self.assertEqual(self.run_board([],first[:1])[1],1)
        self.assertEqual(self.store.detail('vacancy',first[1])['recheck_source'],'anthropic')
    def test_source_for_picks_the_right_listing(self):
        google='https://www.google.com/about/careers/applications/jobs/results/1-role'
        self.assertEqual(source_runs.source_for({'link':google,'company':'DeepMind'}),'deepmind')
        self.assertEqual(source_runs.source_for({'link':google,'company':'Google'}),'google')
        self.assertEqual(source_runs.source_for({'link':'https://jobs.ashbyhq.com/openai/x','company':'OpenAI'}),'openai')
        self.assertEqual(source_runs.source_for({'link':'https://rabota.sber.ru/search/1','company':'ПАО Сбербанк'}),'sber')
        self.assertIsNone(source_runs.source_for({'link':'https://hh.ru/vacancy/1','company':'X'}))
        self.assertIsNone(source_runs.source_for({'link':'https://careers.tencent.com/x','company':'Tencent'}))
    def test_only_sources_that_can_speak_for_a_row_claim_it(self):
        self.assertEqual(source_runs.universe(self.store,'sber'),set())

class Daily(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'out.json'
    def old(self,days):return (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    def test_prune_uses_last_seen_and_keeps_live_old_rows(self):
        self.path.write_text(json.dumps({'vacancies':[{'id':'live','first_seen':self.old(90),'last_seen':self.old(1)},{'id':'stale','first_seen':self.old(90),'last_seen':self.old(40)},{'first_seen':self.old(1)}]}))
        with patch.object(scrape_online,'OUTPUT',self.path):self.assertEqual(set(scrape_online._load_existing()),{'live'})
    def test_corrupt_file_fails_instead_of_erasing_history(self):
        self.path.write_text('{broken')
        with patch.object(scrape_online,'OUTPUT',self.path),self.assertRaises(ValueError):scrape_online._load_existing()
    def test_known_rows_seen_again_get_fresh_last_seen_and_worst_coverage_wins(self):
        old=self.old(5);saved={'known':{'id':'known','first_seen':old,'last_seen':old},'away':{'id':'away','first_seen':old,'last_seen':old}}
        scraper=Mock(seen_ids={'known'},empty_listing_is_error=True);scraper.fetch_jobs.return_value=[]
        reports=iter([{'listed':3,'errors':0,'coverage':'limited'},{'listed':3,'errors':0,'coverage':'listing_exhausted'}])
        def fetch(*a,**k):scraper.report=next(reports);return []
        scraper.fetch_jobs.side_effect=fetch;captured={}
        def save(by_id,stats,now):captured.update(rows=json.loads(json.dumps(by_id)),stats=json.loads(json.dumps(stats)),now=now)
        with patch('sys.argv',['s','--scrapers','google']),patch.object(scrape_online,'_source_plan',return_value=[('google',Mock(return_value=scraper),['a','b'])]),patch.object(scrape_online,'_load_existing',return_value=saved),patch.object(scrape_online,'_save',side_effect=save):
            self.assertEqual(scrape_online.main(),0)
        self.assertEqual(captured['rows']['known']['last_seen'],captured['now']);self.assertEqual(captured['rows']['away']['last_seen'],old);self.assertEqual(captured['stats']['google']['coverage'],'limited')

class Import(Fixture):
    def test_export_listing_marks_absent_only_for_whole_sources(self):
        from src.github_collection_import import record_listings
        from src.board_import import identity
        for n in (1,2):
            link=f'https://www.metacareers.com/jobs/{n}';self.store.sync({'client_id':'client_12345','records':[record('vacancy',{**job(identity(link)['id']),'link':link,'source_page':link})]})
        payload={'stats_last_run':{'meta':{'errors':0,'coverage':'limited'}}}
        record_listings(self.store,'r1',payload,{'meta':{'meta_1'}});self.assertEqual(self.listing('meta_1')['state'],'listed');self.assertIsNone(self.listing('meta_2'))
        payload={'stats_last_run':{'meta':{'errors':0,'coverage':'listing_exhausted'}}}
        record_listings(self.store,'r2',payload,{'meta':{'meta_1'}});self.assertEqual(self.listing('meta_2')['state'],'gone')

class Catalog(Fixture):
    def test_labs_get_their_own_filter_entries_even_with_a_saved_catalog(self):
        from src.company_catalog import raw_catalog,required_companies,defaults,AI_LABS
        from src.company_filter import company_key
        catalog=raw_catalog(self.store)
        self.assertEqual(company_key('OpenAI',catalog),'openai');self.assertEqual(company_key('xAI / SpaceXSI',catalog),'xai');self.assertEqual(company_key('DeepMind',catalog),'deepmind')
        saved=[r for r in defaults() if r['id'] in ('yandex',)]
        self.assertTrue({lab[0] for lab in AI_LABS}<={r['id'] for r in required_companies(saved)})
    def test_every_board_source_has_a_catalog_entry(self):
        from src.company_catalog import AI_LABS
        from src.scrapers.ats import BOARDS
        self.assertFalse(set(BOARDS)-{lab[0] for lab in AI_LABS})

