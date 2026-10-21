"""Deterministic fallback tests: temporary SQLite, no browser, network or model."""
import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from src.tests import test_workflow as fixtures
from src import hybrid_collection as hybrid, discovery, agent_tasks
from src.vacancy_intake import collect_one, status
from src.python_collection import persist
from src.tests.test_archive import record

URL='https://career.avito.com/vacancies/data-science/19450/'
def row(identifier='19450'):
 return {'id':'avito_'+identifier,'title':'Research Engineer','company':'Avito','link':URL.replace('19450',identifier),'description':'Research, distributed training and PyTorch. '*20,'description_quality':'full'}

class HybridCollectionTests(unittest.TestCase):
 def setUp(self):
  f=fixtures.WorkflowTests('runTest');f.setUp();self.addCleanup(f.doCleanups)
  self.store=f.store;self.archive=f.archive;self.f=f
 def mode(self,value):discovery.config(self.store,{**discovery.DEFAULT,'transport':value})
 def queue(self,mode):self.mode(mode);return collect_one(self.store,URL)['command_id']
 def chrome(self):return self.store.next_command('chrome-fixture',kinds=['discover','collect'])['command']
 def finish(self,cmd,result):return self.store.finish_command(cmd['id'],'chrome-fixture',result)
 def test_python_first_is_not_claimed_by_chrome_and_success_has_no_fallback(self):
  identifier=self.queue('python_first');self.assertIsNone(self.chrome())
  calls=[]
  hybrid.run_pending(self.store,self.archive,lambda p,stop:(calls.append(p) or {'rows':[{**row(),'skills':['PyTorch'],'employment_type':'full-time','raw_html':'<p>source</p>'}]}))
  current=hybrid.leaf(self.store,identifier)
  self.assertEqual(current['id'],identifier);self.assertEqual(current['state'],'complete');self.assertEqual(status(self.store,identifier)['result']['ids'],['avito_19450'])
  self.assertEqual(self.archive.detail('vacancy','avito_19450')['availability'],'active')
  self.assertFalse(hybrid.run_pending(self.store,self.archive,lambda *args:self.fail('Duplicate read')))
  self.assertEqual(len(calls),1)
 def test_python_failure_falls_back_to_chrome_once_with_new_receipt_id(self):
  identifier=self.queue('python_first')
  hybrid.run_pending(self.store,self.archive,lambda *args:{'rows':[],'reason':'timeout'})
  next=hybrid.fallback(self.store,identifier);self.assertNotEqual(next['id'],identifier);self.assertEqual(next['payload']['collection_transport'],'chrome')
  self.assertEqual(hybrid.fallback(self.store,identifier)['id'],next['id'])
  command=self.chrome();self.assertEqual(command['id'],next['id'])
  self.finish(command,{'state':'failed','ids':[],'note':'Unavailable'})
  self.assertEqual(hybrid.fallback(self.store,identifier)['id'],next['id']);self.assertIsNone(self.chrome())
  self.assertEqual(len(status(self.store,identifier)['result']['transport_history']),1)
 def test_chrome_failure_falls_back_to_python_and_partial_ids_are_preserved(self):
  self.mode('chrome_first')
  identifier=self.store.queue_command('discover',payload=hybrid.prepare({'source_url':'https://career.avito.com/vacancies/'},'chrome_first'));command=self.chrome()
  self.archive.sync({'client_id':'hybrid-test','records':[record('vacancy',row())]})
  self.finish(command,{'state':'complete','ids':['avito_19450'],'progress':{'failed':1}})
  hybrid.tick(self.store,self.archive,lambda *args:{'rows':[row('19451')]})
  command_leaf=hybrid.leaf(self.store,identifier);current={**command_leaf,'result':hybrid.merged_result(command_leaf),'transport':command_leaf['payload']['collection_transport']}
  self.assertEqual(current['state'],'complete');self.assertEqual(set(current['result']['ids']),{'avito_19450','avito_19451'})
  self.assertEqual(current['transport'],'python')
  self.assertTrue(self.finish(command,{'state':'complete','ids':['avito_19450'],'progress':{'failed':1}})['replayed'])
 def test_unverified_empty_is_not_success_or_evidence_of_closure(self):
  identifier=self.queue('python_first')
  self.archive.sync({'client_id':'hybrid-test','records':[record('vacancy',row())]})
  hybrid.run_pending(self.store,self.archive,lambda *args:{'rows':[]})
  self.assertEqual(hybrid.leaf(self.store,identifier)['state'],'queued')
  self.assertEqual(self.archive.detail('vacancy','avito_19450')['availability'],'unknown') # imported fixture did not prove activity
  verified={'id':'empty','state':'complete','payload':{},'result':{'ids':[],'verified_empty':True}}
  self.assertIsNone(hybrid.failure_reason(verified))
 def test_snippet_is_saved_for_review_and_cannot_satisfy_full_description(self):
  result=persist(self.archive,{'source_url':URL,'vacancy_id':'avito_19450'},{'rows':[{**row(),'description':'short','description_quality':'full'}]})
  self.assertEqual(result['state'],'needs_input');self.assertEqual(self.archive.detail('vacancy','avito_19450')['payload']['description_quality'],'snippet')
  self.assertNotEqual(self.archive.detail('vacancy','avito_19450')['availability'],'active')
 def test_cross_source_or_wrong_vacancy_records_cannot_enter_archive(self):
  response={'rows':[{**row(),'link':'https://evil.example/jobs/123'},row('19451')]}
  result=persist(self.archive,{'source_url':URL,'vacancy_id':'avito_19450'},response)
  self.assertEqual(result['ids'],[]);self.assertEqual(result['state'],'needs_input')
 def test_cancelled_or_paused_read_does_not_start_fallback(self):
  identifier=self.queue('python_first');task=agent_tasks.get(self.store,'browser:'+identifier)
  agent_tasks.control(self.store,task['id'],'cancel',task['revision'],actor='fixture')
  self.assertFalse(hybrid.run_pending(self.store,self.archive,lambda *a:self.fail('Cancelled task executed')))
  self.assertEqual(hybrid.leaf(self.store,identifier)['state'],'cancelled')
 def test_task_controls_follow_fallback_executor(self):
  identifier=self.queue('python_first');original=agent_tasks.get(self.store,'browser:'+identifier)
  hybrid.run_pending(self.store,self.archive,lambda *args:{'rows':[]})
  current=agent_tasks.get(self.store,original['id']);self.assertNotEqual(current['command_id'],identifier)
  with self.assertRaises(ValueError):agent_tasks.control(self.store,original['id'],'cancel',original['revision'],actor='fixture')
  agent_tasks.control(self.store,current['id'],'cancel',current['revision'],actor='fixture');self.assertIsNone(self.chrome())
 def test_hh_stays_in_authorized_chrome_and_google_meta_do_not_claim_chrome_support(self):
  self.assertEqual(hybrid.prepare({'source_url':'https://hh.ru/search/vacancy'},'python_first')['transport_order'],['chrome'])
  for url in ('https://www.google.com/about/careers/applications/jobs/results/','https://www.metacareers.com/jobs'):
   self.assertEqual(hybrid.prepare({'source_url':url},'chrome_first')['transport_order'],['python'])
   with self.assertRaises(ValueError):hybrid.prepare({'source_url':url},'chrome_only')
  with self.assertRaises(ValueError):discovery.config(self.store,{**discovery.DEFAULT,'transport':'unknown'})
 def test_python_cancellation_during_read_does_not_commit_returned_rows(self):
  identifier=self.queue('python_first')
  def runner(payload,stop):
   task=agent_tasks.get(self.store,'browser:'+identifier)
   agent_tasks.control(self.store,task['id'],'cancel',task['revision'],actor='fixture')
   return {'rows':[row()]}
  hybrid.run_pending(self.store,self.archive,runner)
  with self.assertRaises(ValueError):self.archive.detail('vacancy','avito_19450')
  self.assertIsNone(self.chrome())
 def test_discovery_checkpoint_follows_fallback_before_pausing(self):
  self.mode('python_first');run_id='hybrid-discovery'
  command_id=self.store.queue_command('discover',payload=hybrid.prepare({'source_url':'https://career.avito.com/vacancies/','run_id':run_id},'python_first'))
  p={'command_id':command_id,'sources':['https://career.avito.com/vacancies/'],'index':0,'ids':[],'config':discovery.config(self.store),'resume_id':self.f.cv['id'],'goal':'Research','warnings':[]}
  with self.store.connect() as db:db.execute('INSERT INTO discovery_runs VALUES(?,?,?,?,?,?)',(run_id,run_id,'collecting',json.dumps(p),None,time.time()))
  hybrid.run_pending(self.store,self.archive,lambda *args:{'rows':[]})
  current=discovery.advance(self.store,self.archive,run_id,Path(self.f.temp.name))
  self.assertNotEqual(current['payload']['command_id'],command_id)
  task=agent_tasks.get(self.store,'search:'+run_id);agent_tasks.control(self.store,task['id'],'pause',task['revision'],actor='fixture')
  self.assertIsNone(self.chrome())
 def test_lost_chrome_read_switches_to_python_after_expired_heartbeat(self):
  identifier=self.queue('chrome_first');self.chrome()
  with self.store.connect() as db:db.execute('UPDATE browser_commands SET updated=? WHERE id=?',(time.time()-400,identifier))
  hybrid.tick(self.store,self.archive,lambda *a:{'rows':[row()]})
  self.assertEqual(status(self.store,identifier)['state'],'complete');self.assertEqual(status(self.store,identifier)['transport'],'python')
 def test_python_health_does_not_report_its_queue_as_chrome_work(self):
  identifier=self.queue('python_first');health=self.store.browser_status()['workers']
  self.assertEqual(health['python_collection']['queued'],1);self.assertEqual(health['collection']['queued'],0)
 def test_default_legacy_queue_still_uses_chrome(self):
  identifier=collect_one(self.store,URL)['command_id'];self.assertEqual(self.chrome()['id'],identifier)

class ParserReuseTests(unittest.TestCase):
 def test_ozon_respects_explicit_tech_url_and_yandex_profession_is_preserved(self):
  from src.scrapers.ru_ozon import OzonScraper
  page=Mock();page.eval_on_selector_all.return_value=[]
  url='https://ozon.tech/vacancies/?search=PyTorch';OzonScraper(archive_path=False)._scrape(page,url,set())
  self.assertEqual(page.goto.call_args.args[0],url)
  from src.scrapers.ru_yandex import YandexScraper
  response=Mock(ok=True);response.json.return_value={'results':[]}
  page.request.get.return_value=response
  with patch('src.scrapers.ru_yandex.time.sleep'):
   YandexScraper(archive_path=False)._scrape(page,'https://yandex.ru/jobs/professions/ml-developer',set())
  self.assertIn('professions=ml-developer',page.request.get.call_args.args[0])
 def test_google_structured_text_is_not_truncated(self):
  from src.scrapers.parsers import google as parser
  sample=[None]*max(30,parser.F_LOCATIONS+1,parser.F_TIMESTAMPS+1)
  sample[parser.F_ID]='123';sample[parser.F_TITLE]='Research';sample[parser.F_DESCRIPTION]='<p>'+('Research '*900)+'</p>'
  result=parser.parse_wiz_record(sample,query='ML',existing_ids=set(),id_prefix='goog',company_name='Google',detail_url_tpl='https://www.google.com/about/careers/applications/jobs/results/{job_id}')
  self.assertGreater(len(result['description']),5000);self.assertEqual(result['description_quality'],'full')
