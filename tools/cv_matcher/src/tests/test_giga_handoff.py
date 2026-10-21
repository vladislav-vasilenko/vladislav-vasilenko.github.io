"""HH invitation provenance and owner-reviewed start; no network or model calls."""
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from src.tests import test_workflow as fixtures
from src.tests.test_recruiter import Operator,User,update
from src.recruiter_controller import RecruiterController
from src.giga_handoff import invitation_url

LINK='https://telegram.me/Giga_recruiter_bot?start=fixture_job_token'
class HandoffTests(unittest.TestCase):
 setUp=fixtures.WorkflowTests.setUp
 sync=fixtures.WorkflowTests.sync
 def invite(self,vid=None):
  return self.store.hh_sync({'source_url':'https://hh.ru/chat/123','records':[{'vacancy_id':vid or self.jd['id'],'thread_id':'thread:123','status':'unknown','messages':[{'id':'m1','text':'Пройдите интервью: '+LINK,'links':[LINK]}]}]})
 def test_strict_link_and_snapshot_idempotent_with_unknown_status_preserved(self):
  self.invite();self.invite();a=self.store.workflow(self.id)
  self.assertEqual(a['status'],'queued');self.assertEqual(len(a['hh_messages']),1);self.assertEqual(a['giga_invitation']['source_thread'],'thread:123')
  self.assertEqual(len([e for e in a['events'] if e['type']=='giga_invite']),1)
  for url in ['https://evil.example/Giga_recruiter_bot?start=a','https://t.me/Giga_recruiter_bot?start=a&start=b','https://t.me/Giga_recruiter_bot?start=a&other=b','http://t.me/Giga_recruiter_bot?start=a','https://t.me/other?start=a']:
   with self.assertRaises(ValueError):invitation_url(url)
 def test_start_once_shared_case_and_new_question_watermark(self):
  self.invite();self.store.hh_sync({'source_url':self.jd['link'],'records':[{'vacancy_id':self.jd['id'],'status':'invited'}]})
  child=self.store.start_screening(self.id,True);cid=child['id'];self.store.activate(cid);preview=self.store.giga_start_preview(cid)
  self.assertFalse(self.store.giga_question_current(cid,10,'old'))
  with self.assertRaises(ValueError):self.store.claim_giga_start(cid,'changed',None)
  run=self.store.claim_giga_start(cid,preview['token'],{'id':10,'fingerprint':'old'})
  self.assertEqual(run['start_param'],'fixture_job_token');self.assertGreater(run['nonce'],0)
  self.assertFalse(self.store.giga_question_current(cid,10,'old'));self.assertFalse(self.store.giga_question_current(cid,9,'edit'))
  self.assertTrue(self.store.giga_question_current(cid,11,'new'));self.assertTrue(self.store.giga_question_current(cid,10,'edited'))
  self.store.finish_giga_start(run['invite_id'],False)
  with self.assertRaises(ValueError):self.store.claim_giga_start(cid,preview['token'],None)
  self.assertEqual(self.store.giga_invitation(self.id)['start_state'],'uncertain')
  self.store.setting('giga_current_invite','other-interview')
  self.assertFalse(self.store.giga_question_current(cid,999,'new-but-another-job'))
 def test_chat_queue_rejects_external_or_non_chat_target(self):
  self.store.queue_command('sync',payload={'source_url':'https://hh.ru/chat/123'})
  for url in ['https://evil.example/chat/123','https://hh.ru/vacancy/1','https://hh.ru/chat/123?redirect=evil']:
   with self.assertRaises(ValueError):self.store.queue_command('sync',payload={'source_url':url})

class ControllerHandoffTests(unittest.IsolatedAsyncioTestCase):
 async def test_review_start_then_only_fresh_questions_and_exact_answer_send(self):
  f=HandoffTests();f.setUp();self.addCleanup(f.doCleanups);s=f.store;f.invite()
  s.hh_sync({'source_url':f.jd['link'],'records':[{'vacancy_id':f.jd['id'],'status':'invited'}]})
  child=s.start_screening(f.id,True);cid=child['id'];s.activate(cid);op=Operator();user=User();user.start=AsyncMock()
  c=RecruiterController(s,op,user,42,Path(f.temp.name)/'cache')
  await c.receive(1,user.current['text'],[]);self.assertEqual(len(op.messages),0)
  await c.update(update(text='/start_recruiter'));self.assertEqual(user.start.await_count,0)
  callback=op.messages[-1][1][0][0][1]
  await c.update(update(callback=callback,owner=99));self.assertEqual(user.start.await_count,0)
  await c.update(update(callback=callback));self.assertEqual(user.start.await_count,1);self.assertEqual(user.start.call_args.args[0],'fixture_job_token')
  await c.update(update(callback=callback));self.assertEqual(user.start.await_count,1)
  await c.update(update(text='/question'))
  with s.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],0)
  user.current={'id':2,'text':'Расскажите о PyTorch','buttons':[]};await c.receive(2,user.current['text'],[])
  with s.connect() as db:tid=db.execute('SELECT id FROM turns').fetchone()[0]
  await c.update(update(callback='own:'+tid));await c.update(update(text='Мой проверенный ответ.'))
  self.assertEqual(user.sent,[]);await c.update(update(callback=f'send:{tid}:'+c.draft_token('Мой проверенный ответ.')))
  self.assertEqual(user.sent,[('Мой проверенный ответ.',2)])
 async def test_transport_uses_telethon_start_request_with_persisted_nonce(self):
  from telegram_recruiter import UserTransport
  client=AsyncMock();entity=object()
  from unittest.mock import patch
  with patch('telethon.tl.functions.messages.StartBotRequest') as request:
   await UserTransport(client,entity).start('fixture_job_token',123)
   request.assert_called_once_with(bot=entity,peer=entity,start_param='fixture_job_token',random_id=123)
   client.assert_awaited_once_with(request.return_value)
