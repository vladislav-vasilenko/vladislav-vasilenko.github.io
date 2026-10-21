"""Fault injection for durable description enrichment; no network or models."""
import json,time,unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from src.tests import test_workflow as fixtures
from src.tests.test_archive import record
from src.tests.test_hybrid_collection import row,URL
from src import collection_backfill as queue, hybrid_collection as hybrid
from src.python_collection import detail,persist
from src import hh_auto_sync


class BackfillTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.WorkflowTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.s=self.f.store;self.a=self.f.archive
 def add(self,identifier='19450',**extra):
  value={**row(identifier),'description':'Short listing','description_quality':'snippet',**extra}
  self.a.sync({'client_id':'backfill-test','records':[record('vacancy',value)]});return value['id']
 def start(self):return queue.start(self.s,mode='python_first')['run']['id']
 def test_duplicate_start_is_idempotent_and_window_is_bounded_per_source(self):
  for n in range(10):self.add(str(19450+n))
  with ThreadPoolExecutor(2) as pool:ids=list(pool.map(lambda _:self.start(),range(2)))
  self.assertEqual(ids[0],ids[1]);queue.tick(self.s,self.a)
  status=queue.status(self.s);self.assertEqual(status['total'],10);self.assertEqual(status['counts']['reading'],1)
  queue.tick(self.s,self.a);self.assertEqual(queue.status(self.s)['counts']['reading'],1)
 def test_real_receipt_reconciliation_completes_run_and_survives_new_store(self):
  self.add();identifier=self.start();queue.tick(self.s,self.a)
  hybrid.run_pending(self.s,self.a,lambda *a:{'rows':[row()]});queue.tick(self.s,self.a)
  from src.application_store import ApplicationStore
  result=queue.status(ApplicationStore(self.s.path),identifier)
  self.assertEqual(result['run']['state'],'complete');self.assertEqual(result['counts'],{'complete':1})
 def test_full_and_closed_are_skipped_but_missing_is_not_inferred_closed(self):
  self.add();self.add('19451',archived=True,source_page=URL.replace('19450','19451'))
  identifier=self.start();self.assertEqual(queue.status(self.s,identifier)['total'],1)
  queue.tick(self.s,self.a);hybrid.run_pending(self.s,self.a,lambda *a:{'rows':[]});queue.tick(self.s,self.a)
  self.assertNotEqual(self.a.detail('vacancy','avito_19450')['availability'],'closed')
 def test_pause_and_cancel_block_both_transports_even_after_fallback(self):
  self.add();identifier=self.start();queue.tick(self.s,self.a)
  queue.control(self.s,identifier,'pause');self.assertFalse(hybrid.run_pending(self.s,self.a,lambda *a:self.fail('Paused execution')))
  queue.control(self.s,identifier,'resume');hybrid.run_pending(self.s,self.a,lambda *a:{'rows':[]})
  queue.control(self.s,identifier,'pause');self.assertIsNone(self.s.next_command('chrome-fixture',kinds=['discover','collect'],collection_version=2)['command'])
  queue.control(self.s,identifier,'cancel');self.assertEqual(queue.status(self.s,identifier)['counts'],{'cancelled':1})
 def test_old_extension_cannot_claim_backfill_but_current_protocol_can(self):
  self.add('19450',id='hh_99',link='https://hh.ru/vacancy/99');self.start();queue.tick(self.s,self.a)
  self.assertIsNone(self.s.next_command('old-worker',kinds=['discover','collect'])['command'])
  self.assertTrue(queue.status(self.s)['chrome_requires_update'])
  command=self.s.next_command('new-worker',kinds=['discover','collect'],collection_version=2)['command']
  self.assertEqual(command['payload']['vacancy_id'],'hh_99');self.assertFalse(queue.status(self.s)['chrome_requires_update'])
 def test_transient_failure_is_delayed_and_never_retried_forever(self):
  self.add();identifier=queue.start(self.s,mode='python_only')['run']['id'];queue.tick(self.s,self.a)
  for attempt in range(1,4):
   hybrid.run_pending(self.s,self.a,lambda *a:{'rows':[],'reason':'http_timeout'});queue.tick(self.s,self.a)
   current=queue.status(self.s,identifier)
   if attempt<3:
    self.assertEqual(current['counts'],{'retry':1});self.assertFalse(hybrid.run_pending(self.s,self.a,lambda *a:self.fail('Backoff ignored')))
    queue.tick(self.s,self.a,now=time.time()+2000)
   else:self.assertEqual(current['run']['state'],'needs_input');self.assertEqual(current['issues'][0]['attempts'],3)
 def test_manual_full_import_wins_over_pending_enrichment(self):
  self.add();self.start();persist(self.a,{'source_url':URL,'vacancy_id':'avito_19450'},{'rows':[row()]})
  queue.tick(self.s,self.a);self.assertEqual(queue.status(self.s)['counts'],{'complete':1});self.assertFalse(hybrid.run_pending(self.s,self.a,lambda *a:self.fail('Already full')))
 def test_chrome_cannot_requeue_stale_python_command(self):
  self.add();self.start();queue.tick(self.s,self.a)
  def runner(payload,stop):
   with self.s.connect() as db:db.execute("UPDATE browser_commands SET updated=? WHERE state='running'",(time.time()-400,))
   self.s.next_command('other-worker')
   with self.s.connect() as db:self.assertEqual(db.execute("SELECT state FROM browser_commands WHERE kind='collect'").fetchone()[0],'running')
   return {'rows':[row()]}
  hybrid.run_pending(self.s,self.a,runner)
 def test_access_challenge_stops_entire_source_without_reading_remaining_links(self):
  for n in range(3):self.add(str(19450+n))
  queue.start(self.s,mode='python_only');queue.tick(self.s,self.a)
  hybrid.run_pending(self.s,self.a,lambda *a:{'rows':[],'reason':'access_required'});queue.tick(self.s,self.a)
  value=queue.status(self.s);self.assertEqual(value['counts'],{'needs_input':3});self.assertEqual(value['run']['state'],'needs_input')
  self.assertEqual(sum(r['attempts'] for r in value['issues']),1)
 def test_rate_limit_cools_down_source_instead_of_skipping_to_the_next_vacancy(self):
  self.add();self.add('19451');queue.start(self.s,mode='python_only');queue.tick(self.s,self.a)
  hybrid.run_pending(self.s,self.a,lambda *a:{'rows':[],'reason':'http_rate_limited'});queue.tick(self.s,self.a)
  value=queue.status(self.s);self.assertEqual(value['counts'],{'retry':1,'pending':1})
  self.assertFalse(hybrid.run_pending(self.s,self.a,lambda *a:self.fail('Source cooldown ignored')))
 def test_http_then_shared_playwright_adapter_and_no_repeat_after_success(self):
  with patch('src.python_collection.public_html',return_value=[]),patch('src.python_collection.playwright_detail',return_value={'rows':[row()]}) as browser:
   result=detail({'source_url':URL,'vacancy_id':'avito_19450'})
   self.assertEqual([a['transport'] for a in result['attempts']],['http','playwright_dom']);browser.assert_called_once()
  with patch('src.python_collection.public_html',return_value=[row()]),patch('src.python_collection.playwright_detail') as browser:
   self.assertEqual(len(detail({'source_url':URL})['attempts']),1);browser.assert_not_called()
 def test_access_denial_does_not_trigger_repeated_headless_reads(self):
  with patch('src.python_collection.public_html',side_effect=ValueError('403 access denied')),patch('src.python_collection.playwright_detail') as browser:
   result=detail({'source_url':URL});self.assertEqual(result['reason'],'access_required');browser.assert_not_called()
 def test_weak_read_preserves_existing_full_description_and_closed_status(self):
  persist(self.a,{'source_url':URL},{'rows':[{**row(),'archived':True,'source_page':URL}]})
  result=persist(self.a,{'source_url':URL},{'rows':[{**row(),'description':'short','description_quality':'snippet','archived':False}]})
  saved=self.a.detail('vacancy','avito_19450');self.assertEqual(saved['availability'],'closed');self.assertEqual(saved['payload']['description_quality'],'full')
 def test_enrichment_routes_authenticate_and_do_not_enable_paid_analysis(self):
  from resume_import_server import create_app
  from fastapi.testclient import TestClient
  self.add();client=TestClient(create_app('fixture',archive_path=self.s.path))
  self.assertEqual(client.post('/archive/workflow',json={'op':'collection_backfill_start'}).status_code,401)
  response=client.post('/archive/workflow',headers={'X-Resume-Import-Token':'fixture'},json={'op':'collection_backfill_start'})
  self.assertEqual(response.status_code,200);self.assertEqual(response.json()['total'],1)
  from src.discovery import config
  self.assertFalse(config(self.s)['allow_api'])
 def test_expired_automatic_sync_becomes_delayed_failure_and_collection_wins(self):
  self.s.next_command('hh-fixture',auto_sync=True);identifier=hh_auto_sync.tick(self.s)['command_id']
  command=self.s.next_command('hh-fixture',auto_sync=True)['command'];self.assertEqual(command['id'],identifier)
  with self.s.connect() as db:db.execute('UPDATE browser_commands SET updated=? WHERE id=?',(time.time()-200,identifier))
  result=hh_auto_sync.tick(self.s);self.assertEqual(result['state'],'backoff')
  with self.s.connect() as db:self.assertEqual(db.execute('SELECT state FROM browser_commands WHERE id=?',(identifier,)).fetchone()[0],'failed')
