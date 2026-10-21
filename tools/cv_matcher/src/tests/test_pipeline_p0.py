"""Crash/restart and cross-channel contract tests; no live external requests."""
import json,time,unittest
from unittest.mock import patch
from src.tests import test_workflow as workflow_fixtures
from src.tests import test_recruiter as recruiter_fixtures
from src.tests.test_recruiter import update
from src.application_store import ApplicationStore
from src.workflow_bot import WorkflowBot
from src.delivery_store import DeliveryRejected

class DeliveryTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=workflow_fixtures.WorkflowBotTests.asyncSetUp
 async def test_ambiguous_failure_requires_explicit_reconciliation_then_delivers_once(self):
  async def fail(*a):raise TimeoutError('secret must not be persisted')
  self.bot.enqueue('followup:fixture','Проверить ответ')
  with patch.object(self.operator,'send',side_effect=fail):await self.bot.flush_deliveries()
  fresh=WorkflowBot(ApplicationStore(self.store.path),self.operator,42);await fresh.flush_deliveries()
  row=self.store.deliveries()[0];self.assertEqual(row['state'],'uncertain');self.assertNotIn('secret',row['last_error']);self.assertEqual(self.operator.messages,[])
  with self.assertRaises(ValueError):self.store.resolve_delivery(row['key'],row['revision'],'retry')
  self.store.resolve_delivery(row['key'],row['revision'],'retry',True)
  await fresh.flush_deliveries();await fresh.flush_deliveries();self.assertEqual(len(self.operator.messages),1)
 async def test_rejection_retries_after_backoff_without_manual_guessing(self):
  self.bot.enqueue('known-rejection','Проверить')
  with patch.object(self.operator,'send',side_effect=DeliveryRejected('denied')):await self.bot.flush_deliveries()
  self.assertEqual(self.store.deliveries()[0]['state'],'pending')
  await self.bot.flush_deliveries();self.assertEqual(self.operator.messages,[])
  with self.store.connect() as db:db.execute('UPDATE workflow_delivery SET next_attempt=0')
  await self.bot.flush_deliveries();self.assertEqual(len(self.operator.messages),1)
 async def test_crash_lease_legacy_migration_and_obsolete_resolution(self):
  self.bot.enqueue('lease','Текст');claim=self.store.claim_delivery_send('lease');self.assertIsNone(self.store.claim_delivery_send('lease'))
  with self.store.connect() as db:
   db.execute('UPDATE workflow_delivery SET lease_until=0')
   db.execute("INSERT INTO workflow_delivery(key,state,created_at) VALUES('legacy','claimed','2026-10-16')")
  reopened=ApplicationStore(self.store.path);rows={r['key']:r for r in reopened.deliveries()}
  self.assertEqual(rows['lease']['state'],'uncertain');self.assertEqual(rows['legacy']['state'],'uncertain')
  reopened.finish_delivery('lease',claim['lease_token'],message_ids=[99])
  with self.assertRaises(ValueError):reopened.resolve_delivery('lease',rows['lease']['revision'],'retry',True)
  with reopened.connect() as db:self.assertEqual(json.loads(db.execute("SELECT message_ids FROM workflow_delivery WHERE key='lease'").fetchone()[0]),[99])
 async def test_pending_payload_survives_restart_without_source_reconstruction(self):
  self.bot.enqueue('event:fixture','Важное сообщение',[[('Открыть','w:open:fixture')]])
  bot=WorkflowBot(ApplicationStore(self.store.path),self.operator,42);await bot.flush_deliveries()
  self.assertEqual(self.operator.messages,[('Важное сообщение',[[['Открыть','w:open:fixture']]])]);self.assertEqual(self.store.deliveries(),[])
 async def test_partial_long_notice_never_resends_confirmed_first_part(self):
  self.bot.enqueue('long-notice','A'*3600)
  calls=[]
  async def send(text,keyboard=None):
   calls.append(text)
   if len(calls)==2:raise TimeoutError()
   return [123]
  with patch.object(self.operator,'send',side_effect=send):await self.bot.flush_deliveries()
  self.assertEqual(len(calls),2);row=self.store.deliveries()[0];self.assertEqual(row['key'],'long-notice:part:1')
  self.store.resolve_delivery(row['key'],row['revision'],'retry',True)
  await self.bot.flush_deliveries();self.assertEqual(self.operator.messages,[('A'*100,None)])

class ChannelTests(unittest.TestCase):
 setUp=workflow_fixtures.WorkflowTests.setUp
 sync=workflow_fixtures.WorkflowTests.sync
 form=workflow_fixtures.WorkflowTests.form
 approve=workflow_fixtures.WorkflowTests.approve
 execute=workflow_fixtures.WorkflowTests.execute
 def link(self):
  self.store.hh_sync({'source_url':self.jd['link'],'records':[{'vacancy_id':self.jd['id'],'status':'invited','status_text':'Вас пригласили'}]})
  return self.store.start_screening(self.id,True)
 def test_hh_giga_share_case_plan_and_context_but_not_send_permission(self):
  with self.assertRaises(ValueError):self.store.start_screening(self.id,True)
  child=self.link();self.assertEqual(child['case_id'],self.id);self.assertEqual(child['context']['resume_hash'],self.app['context']['resume_hash']);self.assertEqual(len(child['channels']),2)
  self.assertEqual(self.store.start_screening(self.id,True)['id'],child['id'])
  self.store.activate(child['id']);self.store.receive(child['id'],5,'Спасибо, интервью завершено.',[])
  preview=self.store.screening_preview(child['id'])
  with self.assertRaises(ValueError):self.store.complete_screening(child['id'],preview['token'])
  self.store.complete_screening(child['id'],preview['token'],True)
  a=ApplicationStore(self.path).workflow(self.id);self.assertEqual(a['crm']['stage'],'ai_screened');self.assertEqual(a['crm']['work_status'],'waiting_invitation');self.assertEqual(self.store.get(child['id'])['status'],'completed');self.assertEqual(self.store.get(self.id)['status'],'invited')
  self.assertTrue(any(e['type']=='ai_screening_completed' for e in a['events']))
  with self.assertRaises(ValueError):self.store.queue_command('prepare',child['id'])
 def test_completion_stale_question_uncertain_send_and_later_crm_stage(self):
  child=self.link();cid=child['id'];self.store.activate(cid);turn,_=self.store.receive(cid,1,'Готово',[]);preview=self.store.screening_preview(cid)
  self.store.receive(cid,2,'Ещё вопрос',[])
  with self.assertRaises(ValueError):self.store.complete_screening(cid,preview['token'],True)
  new,_=self.store.receive(cid,3,'Ответ?',[]);self.store.claim_send(new['id']);self.store.finish_send(new['id'],False)
  with self.assertRaises(ValueError):self.store.screening_preview(cid)
  self.store.finish_send(new['id'],True);self.store.set_crm(cid,'stage_2');preview=self.store.screening_preview(cid);self.store.complete_screening(cid,preview['token'],True)
  self.assertEqual(self.store.workflow(self.id)['crm']['stage'],'stage_2')
 def test_late_hh_receipt_after_lease_expiry_and_replay_after_restart(self):
  cmd,_=self.execute()
  with self.store.connect() as db:db.execute('UPDATE browser_commands SET updated=0 WHERE id=?',(cmd['id'],))
  self.assertEqual(self.store.workflow(self.id)['workflow']['state'],'uncertain')
  result={'state':'submitted','source_url':self.jd['link'],'evidence':'Отклик отправлен'}
  self.store.finish_command(cmd['id'],'worker-1',result)
  self.assertTrue(ApplicationStore(self.path).finish_command(cmd['id'],'worker-1',result)['replayed'])
  with self.assertRaises(ValueError):self.store.finish_command(cmd['id'],'worker-1',{'state':'failed'})
  with self.store.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM application_events WHERE type='browser_result'").fetchone()[0],1)
 def test_late_receipt_after_manual_recovery_still_reconciles_actual_hh_success(self):
  cmd,_=self.execute()
  with self.store.connect() as db:db.execute('UPDATE browser_commands SET updated=0 WHERE id=?',(cmd['id'],))
  self.store.workflow(self.id);self.store.recover_unsent(self.id,True)
  self.store.finish_command(cmd['id'],'worker-1',{'state':'submitted','source_url':self.jd['link'],'evidence':'Вы откликнулись'})
  self.assertEqual(self.store.workflow(self.id)['crm']['stage'],'applied')
 def test_unknown_chat_observation_never_hides_last_confirmed_hh_status(self):
  self.store.hh_sync({'source_url':self.jd['link'],'records':[{'vacancy_id':self.jd['id'],'status':'invited'}]})
  self.store.hh_sync({'source_url':self.jd['link'],'records':[{'vacancy_id':self.jd['id'],'status':'unknown'}]})
  self.assertEqual(self.store.hh_inbox()['items'][0]['status'],'invited')

class CompletionControllerTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=recruiter_fixtures.ControllerTests.asyncSetUp
 send_callback=recruiter_fixtures.ControllerTests.send_callback
 async def test_done_requires_current_owner_confirmation(self):
  await self.controller.update(update(text='/done'));self.assertEqual(self.store.get(self.app['id'])['status'],'active')
  callback=self.operator.messages[-1][1][0][0][1]
  await self.controller.update(update(callback=callback,owner=99));self.assertEqual(self.store.get(self.app['id'])['status'],'active')
  await self.controller.update(update(callback=callback));self.assertEqual(self.store.workflow(self.app['id'])['crm']['stage'],'ai_screened');self.assertEqual(self.user.sent,[])
