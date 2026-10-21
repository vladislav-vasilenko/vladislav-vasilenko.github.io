import unittest,json
from datetime import datetime,timezone,timedelta
from src.tests import test_career_agent as fixtures
from src.tests.test_archive import job,record
from src.tests.test_recruiter import Operator,update
from src.analysis_store import text_hash,document_text
from src.application_workflow import packed
from src.workflow_bot import WorkflowBot

class TelegramRankingTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  await fixtures.CareerAgentTests.asyncSetUp(self)
  at=datetime.now(timezone.utc).isoformat();old=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
  self.jobs=[job('hh_'+str(i),company='Company '+str(i),at=old,text='Practical research '+str(i)+' '+('PyTorch '*30)) for i in range(101,117)]
  self.archive.sync({'client_id':'ranking-parity','records':[record('vacancy',j) for j in self.jobs]})
  self.archive.save_ranking({'resume_id':self.f.cv['id'],'resume_hash':self.f.cv['content_hash'],'goal':'Generative models','model':'text-embedding-3-small','generated_at':at,'all':[{'id':j['id'],'score':.9-i*.04,'cv_similarity':.85-i*.04,'vacancy_hash':text_hash(document_text('vacancy',j))} for i,j in enumerate(self.jobs)]})
  self.bot=WorkflowBot(self.store,Operator(),42)
 async def test_top_comes_from_full_web_ranking_excludes_applied_not_old_or_previously_notified(self):
  self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':'hh_101','status':'invited'},{'vacancy_id':'hh_102','status':'rejected'}]})
  self.store.enqueue_delivery('job:'+datetime.now(self.service.zone).date().isoformat()+':hh_103','already seen')
  web=self.archive.entities('vacancy',status='full',resume_id=self.f.cv['id'],goal='Generative models',ranked_only=True,exclude_closed=True,all_items=True)['items']
  expected=[r['id'] for r in web if r['id'] not in ('hh_101','hh_102')]
  self.assertEqual([c['job']['id'] for c in self.service.candidates()],expected)
  self.assertIn('hh_116',expected)  # Low score has no hidden .45 cutoff.
  await self.bot.update(update(callback='w:menu:top'))
  refs=json.loads(self.store.setting('last-selection'))['refs'];self.assertEqual(len(refs),10)
  ids=[json.loads(self.store.setting('recommendation:'+ref))['vacancy_id'] for ref in refs]
  self.assertEqual(ids,expected[:10]);self.assertIn('Подробный разбор',str(self.bot.operator.messages))
 async def test_global_top_is_not_limited_to_ids_in_last_crawl_and_repeat_digest_is_idempotent(self):
  from src import discovery
  await self.service.search('global-top')
  run_id=json.loads(self.store.setting('pending_digest'))['discovery_id']
  with self.store.connect() as db:db.execute("UPDATE discovery_runs SET state='complete',result=? WHERE id=?",(packed({'ids':['hh_116'],'ranked_count':1}),run_id))
  await self.service.finish_digest()
  refs=json.loads(self.store.setting('last-recommendations'))['refs']
  self.assertEqual(len(refs),10);self.assertEqual(json.loads(self.store.setting('recommendation:'+refs[0]))['vacancy_id'],'hh_101')
  with self.store.connect() as db:before=db.execute('SELECT COUNT(*) FROM workflow_delivery').fetchone()[0]
  await self.service.finish_digest()
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM workflow_delivery').fetchone()[0],before)
 async def test_full_ranking_page_uses_same_order_and_count_as_web(self):
  await self.bot.update(update(callback='w:rank:0'));text,keyboard=self.bot.operator.messages[-1]
  self.assertIn('из 16',text);self.assertIn('w:rank:5',str(keyboard))
  await self.bot.update(update(callback='w:rank:5'));self.assertIn('6.',self.bot.operator.messages[-1][0])
