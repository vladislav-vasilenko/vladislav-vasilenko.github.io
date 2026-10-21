"""Owner journey, bounded menus, questionnaire drafts and exact reapproval; zero network."""
import json,unittest
from unittest.mock import patch
from src.tests import test_workflow as fixtures
from src.tests.test_recruiter import Operator,update
from src.workflow_bot import WorkflowBot
from src.application_store import ApplicationStore

class TelegramFlowTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  f=fixtures.WorkflowTests();f.setUp();self.addCleanup(f.doCleanups);self.f=f;self.store=f.store;self.op=Operator();self.bot=WorkflowBot(f.store,self.op,42)
 def buttons(self):return [button for row in self.op.messages[-1][1] or [] for button in row]
 async def press(self,prefix):
  callback=next(data for _,data in self.buttons() if data.startswith(prefix));await self.bot.update(update(callback=callback));return callback
 async def prepare(self):
  await self.bot.update(update(callback='w:prepare:'+self.f.id));cmd=self.store.next_command('worker-1')['command']
  form=self.f.form(fields=[self.f.form()['fields'][0],{'id':'about','label':'Расскажите о себе','type':'textarea','required':True,'value':'','options':[]},{'id':'format','label':'Формат работы','type':'select','required':True,'value':'','options':[{'value':'remote','text':'Удалённо'},{'value':'office','text':'Офис'}]}])
  self.store.prepared(self.f.id,form,command_id=cmd['id']);self.store.finish_command(cmd['id'],'worker-1',{'state':'complete'});return form
 async def answer_about(self,text='Проверенный опыт PyTorch из CV.'):
  await self.bot.form_fields(self.f.id);await self.press('w:field:');await self.press('w:fedit:');await self.bot.update(update(text=text))
 async def test_manual_letter_questions_reopen_database_and_exact_approval(self):
  self.store.save_letter(self.f.id,'',1);await self.bot.show(self.f.id)
  self.assertFalse(any('prepare' in data for _,data in self.buttons()))
  await self.press('w:edit:');await self.bot.update(update(text='Мой проверенный текст письма.'))
  self.assertEqual(self.store.workflow(self.f.id)['workflow']['draft'],'Мой проверенный текст письма.')
  form=await self.prepare();await self.bot.preview(self.f.id)
  self.assertFalse(any(data.startswith('w:approve:') for _,data in self.buttons()))
  await self.answer_about();about_ref=self.op.messages[-1][1][1][0][1];await self.bot.update(update(callback=about_ref));await self.press('w:fchoice:')
  reopened=ApplicationStore(self.store.path);answers=reopened.form_answers(self.f.id)['values'];self.assertEqual(answers['format'],'remote');self.assertIn('PyTorch',answers['about']);self.assertEqual(len(reopened.field_history(self.f.id)),2)
  await self.bot.preview(self.f.id);await self.press('w:approve:');cmd=self.store.next_command('worker-1')['command'];intent=self.store.claim_approval(cmd['id'],'worker-1',form['fingerprint'])
  self.assertEqual(intent['answers'],answers);self.assertEqual(intent['form_snapshot']['fields'][1]['label'],'Расскажите о себе')
  self.assertEqual(cmd['kind'],'execute')
 async def test_old_approval_button_revoked_when_answer_changes(self):
  form=await self.prepare();self.store.save_field_answer(self.f.id,'about','Первый ответ',form['fingerprint'],0);self.store.save_field_answer(self.f.id,'format','remote',form['fingerprint'],0)
  await self.bot.preview(self.f.id);old=next(data for _,data in self.buttons() if data.startswith('w:approve:'))
  self.store.save_field_answer(self.f.id,'about','Новая редакция',form['fingerprint'],1)
  await self.bot.update(update(callback=old));self.assertIn('изменился',self.op.messages[-1][0])
  with self.store.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_commands WHERE kind='execute'").fetchone()[0],0)
 async def test_offline_question_prompt_contains_cv_jd_goal_and_returns_to_same_field(self):
  await self.prepare();await self.bot.form_fields(self.f.id);await self.press('w:field:');await self.press('w:foffline:')
  prompt=self.op.messages[-2][0];self.assertIn('Generative models',prompt);self.assertIn('Расскажите о себе',prompt);self.assertIn('Transformer',prompt)
  await self.bot.update(update(text='Ответ из ChatGPT, проверенный мной.'));self.assertEqual(self.store.form_answers(self.f.id)['values']['about'],'Ответ из ChatGPT, проверенный мной.')
 async def test_api_suggestion_is_never_submitted_or_saved_as_final_without_user(self):
  await self.prepare();await self.bot.form_fields(self.f.id);await self.press('w:field:')
  result={'answer':'Предложение модели','missing':[],'needs_user':False,'review_note':'Проверьте факты.'}
  with patch('src.recruiter_answers.draft_answer',return_value=result) as model:await self.press('w:fapi:')
  self.assertEqual(len(self.store.field_suggestions(self.f.id)),1);self.assertEqual(model.call_count,1);self.assertEqual(self.store.form_answers(self.f.id)['values']['about'],'')
  await self.bot.update(update(text='Моя отредактированная версия.'));self.assertEqual(self.store.form_answers(self.f.id)['values']['about'],'Моя отредактированная версия.')
 async def test_sent_case_hides_preparation_and_crm_is_a_separate_menu(self):
  self.store.hh_sync({'source_url':self.f.jd['link'],'records':[{'vacancy_id':self.f.jd['id'],'status':'invited'}]});await self.bot.show(self.f.id)
  callbacks=[data for _,data in self.buttons()];self.assertFalse(any('prepare' in data or 'preview' in data or 'stages' in data for data in callbacks));self.assertTrue(any('plan:' in data for data in callbacks))
  await self.press('w:plan:');self.assertTrue(any('stages:' in data for _,data in self.buttons()))
 async def test_cancel_and_stale_form_have_navigation_and_no_cross_vacancy_write(self):
  form=await self.prepare();await self.bot.form_fields(self.f.id);await self.press('w:field:');await self.press('w:fedit:')
  await self.bot.update(update(text='/cancel'));self.assertFalse(self.store.setting('workflow_waiting'));self.assertTrue(self.buttons())
  self.store.save_letter(self.f.id,'Письмо изменилось.',1)
  with self.assertRaises(ValueError):self.store.save_field_answer(self.f.id,'about','Старый ответ',form['fingerprint'],0)
 async def test_primary_menu_has_skills_entry_and_callback_payloads_fit_telegram(self):
  await self.bot.main_menu();self.assertEqual(len(self.buttons()),4)
  await self.bot.show(self.f.id)
  for _,rows in self.op.messages:
   for row in rows or []:
    for _,data in row:self.assertLessEqual(len(data.encode()),64)
