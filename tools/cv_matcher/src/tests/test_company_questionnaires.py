import json,unittest
from copy import deepcopy
from src.tests import test_workflow as fixtures
from src.career_questionnaires import capture
from src.workflow_bot import WorkflowBot
from src.tests.test_recruiter import Operator

class CompanyFormTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  f=fixtures.WorkflowTests();f.setUp();self.addCleanup(f.doCleanups);self.f=f;self.s=f.store
  self.job={**f.jd,'id':'avito_19450','link':'https://career.avito.com/vacancies/data-science/19450/','company':'Avito'};f.sync(f.cv,self.job)
  self.a=self.s.create({'resume_id':f.cv['id'],'bundle':{'resumes':[f.cv]},'vacancy':self.job,'channel':'career','goal':'Generative models'})
  fields=[{'id':'f0','label':'О себе','type':'textarea','purpose':'about','required':True,'value':''},{'id':'f1','label':'Сопроводительное письмо','type':'textarea','purpose':'cover','value':''},{'id':'f2','label':'Резюме PDF','type':'file','manual_only':True,'value':''}]
  self.snapshot={'state':'questionnaire','provider':'avito','vacancy_id':self.job['id'],'source_url':self.job['link'],'fields':fields,'execution_supported':False,'fingerprint':json.dumps(['avito',self.job['id'],fields],ensure_ascii=False,separators=(',',':'))}
 async def test_questions_share_bot_web_history_but_never_enable_unverified_company_submit(self):
  a=capture(self.s,self.a['id'],self.snapshot);capture(self.s,self.a['id'],self.snapshot)
  op_notice=Operator();await WorkflowBot(self.s,op_notice,42).tick()
  notices=[text for text,_ in op_notice.messages if 'Анкета работодателя сохранена' in text];self.assertEqual(len(notices),1)
  self.assertEqual(a['workflow']['form']['fields'][0]['label'],'О себе')
  self.s.save_field_answer(a['id'],'f0','Мой опыт из CV',self.snapshot['fingerprint'],0)
  self.assertEqual(self.s.workflow(a['id'])['field_history'][0]['value'],'Мой опыт из CV')
  self.s.save_letter(a['id'],'Проверенное письмо.',0);a=self.s.workflow(a['id']);self.assertIsNotNone(a['workflow']['form']);self.assertEqual(a['form_answers']['values']['f1'],'Проверенное письмо.')
  with self.assertRaises(ValueError):self.s.intent(a['id'])
  with self.assertRaises(ValueError):self.s.queue_command('prepare',a['id'])
  with self.assertRaises(ValueError):self.s.save_field_answer(a['id'],'f2','/private/file.pdf',self.snapshot['fingerprint'],0)
  op=Operator();bot=WorkflowBot(self.s,op,42);await bot.show(a['id']);buttons=[b for row in op.messages[-1][1] for b in row]
  self.assertTrue(any('w:fields:' in b[1] for b in buttons));self.assertFalse(any('w:prepare:' in b[1] or 'w:approve:' in b[1] for b in buttons))
 async def test_wrong_vacancy_domain_and_changed_schema_are_rejected(self):
  for change in [{'source_url':'https://evil.example/vacancies/data-science/19450/'},{'source_url':'https://career.avito.com/vacancies/data-science/123/'},{'provider':'yandex'},{'execution_supported':True},{'fingerprint':'wrong'}]:
   with self.assertRaises(ValueError):capture(self.s,self.a['id'],{**self.snapshot,**change})
 async def test_draft_edits_optimistic_revisions_and_source_versions_survive_reopen(self):
  capture(self.s,self.a['id'],self.snapshot);self.s.save_field_answer(self.a['id'],'f0','Первая версия',self.snapshot['fingerprint'],0)
  with self.assertRaises(ValueError):self.s.save_field_answer(self.a['id'],'f0','Устаревшая версия',self.snapshot['fingerprint'],0)
  self.s.save_field_answer(self.a['id'],'f0','Вторая версия',self.snapshot['fingerprint'],1)
  from src.application_store import ApplicationStore
  s=ApplicationStore(self.s.path);history=s.field_history(self.a['id']);self.assertEqual([v['value'] for v in history],['Вторая версия','Первая версия']);self.assertTrue(all(v['question']=='О себе' for v in history))
