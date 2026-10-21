"""Progress counters, owner-message edit semantics and restart/rate-limit behavior."""
import json,time,unittest
from unittest.mock import AsyncMock,Mock
from src.tests import test_career_agent as fixtures
from src.career_application import CareerApplication
from src.workflow_bot import WorkflowBot
from src.application_store import ApplicationStore
from src.agent_progress import report,text,EditRetry
from telegram_recruiter import OperatorBot

class ProgressTests(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=fixtures.CareerAgentTests.asyncSetUp
 async def start(self):
  task=await self.service.search('progress-fixture');command=self.store.next_command('progress-reader',kinds=['discover','collect'])['command'];return task,command
 def counters(self,**values):return {'phase':'descriptions','discovered':50,'planned':20,'loaded':3,'reused':25,'failed':2,'skipped_closed':5,'archived':0,'review':0,'pages':1,**values}
 async def test_progress_validates_worker_and_sequence_and_preserves_real_counters(self):
  task,command=await self.start();progress=self.counters()
  with self.assertRaises(ValueError):report(self.store,command['id'],'wrong-reader',1,progress)
  for value in (-1,True,'5',100001):
   with self.assertRaises(ValueError):report(self.store,command['id'],'progress-reader',1,self.counters(loaded=value))
  report(self.store,command['id'],'progress-reader',2,progress)
  self.assertTrue(report(self.store,command['id'],'progress-reader',1,self.counters(loaded=0))['ignored'])
  saved=self.service.task(task['id']);self.assertEqual(saved['progress']['loaded'],3);self.assertEqual(saved['progress']['failed'],2);self.assertTrue(saved['progress']['planned_complete'])
  message=text(saved);self.assertIn('Прочитано полных описаний: 3',message);self.assertIn('Не удалось прочитать: 2',message);self.assertIn('свежего кэша: 25',message)
 async def test_unknown_totals_are_not_reported_as_zero_and_sources_aggregate_without_old_retries(self):
  task,command=await self.start();message=text(self.service.task(task['id']));self.assertIn('уточняется',message);self.assertIn('Прочитано полных описаний: ожидаем данные',message)
  report(self.store,command['id'],'progress-reader',1,self.counters(phase='listing',planned=None))
  self.assertFalse(self.service.task(task['id'])['progress']['planned_complete'])
  with self.store.connect() as db:
   run=json.loads(db.execute('SELECT payload FROM discovery_runs WHERE id=?',(task['id'][7:],)).fetchone()[0]);run['sources'].append('https://career.avito.com/vacancies/');db.execute('UPDATE discovery_runs SET payload=? WHERE id=?',(json.dumps(run),task['id'][7:]))
  report(self.store,command['id'],'progress-reader',2,self.counters())
  saved=self.service.task(task['id']);self.assertFalse(saved['progress']['planned_complete']);self.assertIn('не менее 20',text(saved))
 async def test_edit_reuses_delivery_message_id_throttles_and_survives_restart_without_send(self):
  task,command=await self.start();report(self.store,command['id'],'progress-reader',1,self.counters())
  with self.store.connect() as db:db.execute("UPDATE workflow_delivery SET state='sent',message_ids='[1234]' WHERE key LIKE '%:progress'")
  operator=Mock();operator.edit=AsyncMock(return_value=True);operator.send=AsyncMock();bot=WorkflowBot(self.store,operator,42)
  await bot.refresh_progress();self.assertEqual(operator.edit.await_count,1);self.assertEqual(operator.edit.call_args.args[0],1234);operator.send.assert_not_called()
  report(self.store,command['id'],'progress-reader',2,self.counters(loaded=4));await bot.refresh_progress();self.assertEqual(operator.edit.await_count,1)
  key='telegram-progress:'+task['id'][7:];saved=json.loads(self.store.setting(key));saved['next_at']=0;self.store.setting(key,json.dumps(saved))
  reopened=WorkflowBot(ApplicationStore(self.store.path),operator,42);await reopened.refresh_progress();self.assertEqual(operator.edit.await_count,2);self.assertIn('описаний: 4',operator.edit.call_args.args[1])
  saved=json.loads(self.store.setting(key));saved['next_at']=0;self.store.setting(key,json.dumps(saved));await reopened.refresh_progress();self.assertEqual(operator.edit.await_count,2)
 async def test_deleted_progress_is_not_resent_and_flood_wait_is_respected(self):
  task,command=await self.start()
  with self.store.connect() as db:db.execute("UPDATE workflow_delivery SET state='sent',message_ids='[4321]' WHERE key LIKE '%:progress'")
  operator=Mock();operator.edit=AsyncMock(side_effect=EditRetry(120));operator.send=AsyncMock();bot=WorkflowBot(self.store,operator,42);key='telegram-progress:'+task['id'][7:]
  await bot.refresh_progress();self.assertGreater(json.loads(self.store.setting(key))['next_at'],time.time()+110);await bot.refresh_progress();self.assertEqual(operator.edit.await_count,1)
  self.store.setting(key,'{}');operator.edit.side_effect=None;operator.edit.return_value=False;await bot.refresh_progress();self.assertTrue(json.loads(self.store.setting(key))['disabled']);await bot.refresh_progress();self.assertEqual(operator.edit.await_count,2);operator.send.assert_not_called()
 async def test_sleep_state_is_rendered_in_same_progress_message_and_old_owner_cannot_report(self):
  task,command=await self.start();self.store.finish_command(command['id'],'progress-reader',{'state':'complete','ids':[]})
  with self.assertRaises(ValueError):report(self.store,command['id'],'progress-reader',1,self.counters())
  with self.store.connect() as db:db.execute("UPDATE discovery_runs SET state='waiting_chrome' WHERE id=?",(task['id'][7:],))
  self.assertIn('Ждём Chrome',text(self.service.task(task['id'])))
 async def test_operator_edits_exact_owner_message_and_handles_not_modified_429_and_deleted(self):
  bot=OperatorBot('fixture-not-real-token',42);self.addAsyncCleanup(bot.http.aclose)
  for data,expected in [({'ok':True},True),({'ok':False,'description':'Bad Request: message is not modified'},True),({'ok':False,'description':'Bad Request: message to edit not found'},False)]:
   bot.http.post=AsyncMock(return_value=Mock(json=lambda:data));self.assertEqual(await bot.edit(123,'Прогресс'),expected)
   args=bot.http.post.call_args;self.assertEqual(args.kwargs['json']['chat_id'],42);self.assertEqual(args.kwargs['json']['message_id'],123);self.assertTrue(args.args[0].endswith('/editMessageText'))
  bot.http.post=AsyncMock(return_value=Mock(json=lambda:{'ok':False,'parameters':{'retry_after':77}}))
  with self.assertRaises(EditRetry) as error:await bot.edit(123,'Прогресс')
  self.assertEqual(error.exception.after,77)
