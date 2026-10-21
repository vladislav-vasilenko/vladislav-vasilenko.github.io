"""Company transfer is a separate approved disclosure, never proof of application."""
import json,time,unittest
from copy import deepcopy
from src.tests import test_company_questionnaires as company_fixtures
from src.career_questionnaires import capture
from src.tests.test_recruiter import Operator,update
from src.workflow_bot import WorkflowBot

class CareerTransferTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  await company_fixtures.CompanyFormTests.asyncSetUp(self)
  self.job.update(source_page=self.job['link'],archived=False);self.f.sync(self.f.cv,self.job)
  self.snapshot['adapter_version']='career-fields-v1'
  self.snapshot['fields'] += [{'id':'f3','type':'checkbox','label':'Согласие на кадровый резерв','value':False,'manual_only':True},{'id':'f4','type':'email','label':'E-mail','value':''}]
  self.snapshot['fingerprint']=json.dumps(['avito',self.job['id'],self.snapshot['fields']],ensure_ascii=False,separators=(',',':'))
  capture(self.s,self.a['id'],self.snapshot);self.s.save_letter(self.a['id'],'Мой проверенный сопроводительный текст.',0)
  self.s.save_field_answer(self.a['id'],'f0','Исследовательский опыт из CV.',self.snapshot['fingerprint'],0)
  self.s.save_field_answer(self.a['id'],'f4','candidate@example.test',self.snapshot['fingerprint'],0)
 def approval(self):
  intent=self.s.career_fill_intent(self.a['id']);approval=self.s.approve_career_fill(self.a['id'],intent['intent_hash'],True)
  return intent,approval
 def claim(self):
  intent,approval=self.approval();cmd=self.s.next_command('career-worker',kinds=['career_fill'],app_ids=[self.a['id']])['command'];self.assertEqual(cmd['id'],approval['command_id'])
  self.assertEqual(self.s.claim_career_fill(cmd['id'],'career-worker',intent['form_fingerprint']),intent)
  return intent,cmd
 async def test_telegram_preview_approval_and_receipt_preserve_unsent_status(self):
  op=Operator();bot=WorkflowBot(self.s,op,42);await bot.preview(self.a['id'])
  self.assertTrue(any('candidate@example.test' in text for text,_ in op.messages))
  callback=next(b[1] for _,rows in op.messages for row in rows or [] for b in row if 'w:cfill_approve:' in b[1])
  await bot.update(update(callback=callback));cmd=self.s.next_command('career-worker',kinds=['career_fill'],app_ids=[self.a['id']])['command'];self.assertIsNotNone(cmd)
  intent=self.s.claim_career_fill(cmd['id'],'career-worker',self.snapshot['fingerprint'])
  result={'state':'fields_filled','source_url':self.job['link'],'values':intent['answers'],'note':'Тексты перенесены. Отклик ещё не отправлен.'}
  self.s.finish_career_fill(cmd['id'],'career-worker',result);self.assertTrue(self.s.finish_career_fill(cmd['id'],'career-worker',result)['replayed'])
  a=self.s.workflow(self.a['id']);self.assertEqual(a['status'],'queued');self.assertEqual(a['crm']['stage'],'preparing');self.assertEqual(a['workflow']['state'],'fields_filled');self.assertIsNone(a['workflow']['form']);self.assertTrue(a['field_history'])
  await bot.tick();self.assertTrue(any('Отклик ещё не отправлен' in text for text,_ in op.messages))
 async def test_receipt_status_is_read_only_bound_to_application_and_hides_contact_values(self):
  intent,cmd=self.claim()
  status=self.s.career_fill_status(self.a['id'],cmd['id']);self.assertEqual(status['state'],'running')
  with self.assertRaises(ValueError):self.s.career_fill_status('other-app',cmd['id'])
  result={'state':'fields_filled','source_url':self.job['link'],'values':intent['answers'],'note':'Готово.'}
  self.s.finish_career_fill(cmd['id'],'career-worker',result)
  status=self.s.career_fill_status(self.a['id'],cmd['id']);self.assertEqual(status['state'],'complete');self.assertEqual(status['result_state'],'fields_filled');self.assertNotIn('values',status);self.assertNotIn('candidate@example.test',json.dumps(status))
 async def test_old_preview_cannot_override_new_answers(self):
  intent,_=self.approval();self.s.save_field_answer(self.a['id'],'f0','Новая редакция',self.snapshot['fingerprint'],1)
  with self.assertRaises(ValueError):self.s.approve_career_fill(self.a['id'],intent['intent_hash'],True)
  self.assertIsNone(self.s.next_command('career-worker',kinds=['career_fill'],app_ids=[self.a['id']])['command'])
 async def test_transfer_has_no_file_consent_or_blank_field_values(self):
  self.s.save_field_answer(self.a['id'],'f3',True,self.snapshot['fingerprint'],0)
  intent=self.s.career_fill_intent(self.a['id']);self.assertEqual(set(intent['answers']),{'f0','f1','f4'});self.assertIn('Согласие на кадровый резерв',intent['manual_fields'])
  with self.assertRaises(ValueError):self.s.approve_career_fill(self.a['id'],intent['intent_hash'],False)
  with self.assertRaises(ValueError):self.s.intent(self.a['id'])
 async def test_workers_cannot_take_other_channel_or_unbound_job(self):
  intent,approval=self.approval();self.assertIsNone(self.s.next_command('hh-worker')['command'])
  self.assertIsNone(self.s.next_command('career-worker',kinds=['career_fill'],app_ids=['other'])['command'])
  for kinds,ids in [(['career_fill'],None),(['career_fill','execute'],[self.a['id']])]:
   with self.assertRaises(ValueError):self.s.next_command('worker',kinds=kinds,app_ids=ids)
 async def test_claim_once_expiry_worker_and_current_cv_checks(self):
  intent,approval=self.approval();self.s.next_command('career-worker',kinds=['career_fill'],app_ids=[self.a['id']])
  for worker,fp in [('other-worker',intent['form_fingerprint']),('career-worker','changed')]:
   with self.assertRaises(ValueError):self.s.claim_career_fill(approval['command_id'],worker,fp)
  with self.s.connect() as db:db.execute('UPDATE application_approvals SET expires=? WHERE id=?',(time.time()-1,approval['approval_id']))
  with self.assertRaises(ValueError):self.s.claim_career_fill(approval['command_id'],'career-worker',intent['form_fingerprint'])
 async def test_claim_blocks_edits_and_never_accepts_submission_receipt(self):
  intent,cmd=self.claim()
  with self.assertRaises(ValueError):self.s.claim_career_fill(cmd['id'],'career-worker',intent['form_fingerprint'])
  with self.assertRaises(ValueError):self.s.save_letter(self.a['id'],'Changed',1)
  for result in [{'state':'submitted'},{'state':'fields_filled','source_url':'https://evil.example','values':intent['answers']},{'state':'fields_filled','source_url':self.job['link'],'values':{'f0':'Wrong'}}]:
   with self.assertRaises(ValueError):self.s.finish_career_fill(cmd['id'],'career-worker',result)
  self.assertEqual(self.s.get(self.a['id'])['status'],'queued')
 async def test_crash_does_not_requeue_disclosure_and_new_capture_survives_late_receipt(self):
  intent,cmd=self.claim()
  with self.s.connect() as db:db.execute('UPDATE browser_commands SET updated=? WHERE id=?',(time.time()-400,cmd['id']))
  self.assertIsNone(self.s.next_command('career-worker',kinds=['career_fill'],app_ids=[self.a['id']])['command'])
  new=deepcopy(self.snapshot);new['fields'][0]['label']='Новый вопрос';new['fingerprint']=json.dumps(['avito',self.job['id'],new['fields']],ensure_ascii=False,separators=(',',':'));capture(self.s,self.a['id'],new)
  self.s.finish_career_fill(cmd['id'],'career-worker',{'state':'fields_filled','source_url':self.job['link'],'values':intent['answers']})
  self.assertEqual(self.s.workflow(self.a['id'])['workflow']['form']['fingerprint'],new['fingerprint'])
 async def test_closed_or_changed_cv_prevents_disclosure(self):
  intent=self.s.career_fill_intent(self.a['id'])
  with self.s.connect() as db:
   row=db.execute("SELECT payload FROM entities WHERE kind='resume' AND id=?",(self.f.cv['id'],)).fetchone();cv=json.loads(row[0]);cv['content_hash']='changed';db.execute("UPDATE entities SET payload=? WHERE kind='resume' AND id=?",(json.dumps(cv),self.f.cv['id']))
  with self.assertRaises(ValueError):self.s.approve_career_fill(self.a['id'],intent['intent_hash'],True)

 async def test_chrome_dictionary_order_does_not_change_form_version(self):
  snapshot=deepcopy(self.snapshot);snapshot['fields']=[dict(sorted(f.items())) for f in snapshot['fields']]
  capture(self.s,self.a['id'],snapshot)
  self.assertEqual(self.s.workflow(self.a['id'])['workflow']['form']['fingerprint'],self.snapshot['fingerprint'])
  snapshot['fields'][0]['label']='Другой вопрос'
  with self.assertRaises(ValueError):capture(self.s,self.a['id'],snapshot)

 async def test_web_preview_owner_approval_and_extension_only_execution(self):
  from fastapi.testclient import TestClient
  from resume_import_server import create_app
  from unittest.mock import patch
  with TestClient(create_app('fixture',archive_path=self.s.path)) as client:
   self.assertEqual(client.post('/archive/workflow',json={'op':'career_fill_intent','app_id':self.a['id']}).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
   client.headers['Origin']='http://127.0.0.1:8788'
   with patch('src.recruiter_answers.draft_answer') as model:
    response=client.post('/archive/workflow',json={'op':'answer','app_id':self.a['id'],'question':'Invent email','field_id':'f4','fingerprint':self.snapshot['fingerprint'],'revision':1})
    self.assertEqual(response.status_code,422);model.assert_not_called()
   intent=client.post('/archive/workflow',json={'op':'career_fill_intent','app_id':self.a['id']}).json()
   approval={'op':'career_fill_approve','app_id':self.a['id'],'intent_hash':intent['intent_hash'],'confirmed':True}
   self.assertEqual(client.post('/archive/workflow',json={**approval,'confirmed':False}).status_code,422)
   self.assertEqual(client.post('/archive/workflow',json=approval).status_code,200)
   poll={'op':'next','worker_id':'career-worker','kinds':['career_fill'],'app_ids':[self.a['id']]}
   self.assertEqual(client.post('/archive/workflow',json=poll).status_code,403)
   command=client.post('/archive/workflow',json=poll,headers={'X-Resume-Import-Token':'fixture'}).json()['command']
   claim={'op':'career_fill_claim','command_id':command['id'],'worker_id':'career-worker','fingerprint':self.snapshot['fingerprint']}
   self.assertEqual(client.post('/archive/workflow',json=claim).status_code,403)
   self.assertEqual(client.post('/archive/workflow',json=claim,headers={'X-Resume-Import-Token':'fixture'}).status_code,200)
