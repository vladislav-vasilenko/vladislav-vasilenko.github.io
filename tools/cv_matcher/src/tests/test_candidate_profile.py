import json,unittest
from src.tests import test_career_field_transfer as fixtures
from src.candidate_profile import read,save,field_key,import_saved_contacts
from src.career_questionnaires import capture
from src.application_store import ApplicationStore
from src.workflow_bot import WorkflowBot
from src.tests.test_recruiter import Operator,update

class CandidateProfileTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):await fixtures.CareerTransferTests.asyncSetUp(self)
 def new_form(self,native_email=''):
  # A new source version simulates the same standard fields on another board.
  form={**self.snapshot,'fields':[{'id':'name','label':'Имя*','type':'text','value':''},{'id':'mail','label':'E-mail*','type':'email','value':native_email},{'id':'consent','label':'Имя согласия','type':'checkbox','value':False,'manual_only':True},{'id':'motivation','label':'О себе','type':'textarea','purpose':'about','value':''}]}
  form['fingerprint']=json.dumps(['avito',self.job['id'],form['fields']],ensure_ascii=False,separators=(',',':'));capture(self.s,self.a['id'],form);return form
 async def test_defaults_reuse_profile_without_overwriting_native_or_per_application_values(self):
  save(self.s,{'first_name':'Владислав','email':'owner@example.test'},{'first_name':0,'email':0})
  form=self.new_form();answers=self.s.form_answers(self.a['id']);self.assertEqual(answers['values']['name'],'Владислав');self.assertEqual(answers['values']['mail'],'owner@example.test');self.assertEqual(answers['values']['motivation'],'');self.assertFalse(answers['values']['consent']);self.assertEqual(answers['from_profile']['mail'],'email')
  self.s.save_field_answer(self.a['id'],'mail','special@example.test',form['fingerprint'],0);self.assertEqual(self.s.form_answers(self.a['id'])['values']['mail'],'special@example.test')
  self.new_form('existing@example.test');self.assertEqual(self.s.form_answers(self.a['id'])['values']['mail'],'existing@example.test')
 async def test_resume_link_uses_selected_cv_not_global_profile_and_is_not_generated(self):
  with self.s.connect() as db:
   context=json.loads(db.execute('SELECT context FROM applications WHERE id=?',(self.a['id'],)).fetchone()[0]);context['resume_url']='https://hh.ru/resume/selected-cv'
   db.execute('UPDATE applications SET context=? WHERE id=?',(json.dumps(context),self.a['id']))
  form={**self.snapshot,'fields':[{'id':'cv_link','label':'Ссылка на резюме','type':'text','purpose':'resume_url','value':''}]};form['fingerprint']=json.dumps(['avito',self.job['id'],form['fields']],ensure_ascii=False,separators=(',',':'));capture(self.s,self.a['id'],form)
  answers=self.s.form_answers(self.a['id']);self.assertEqual(answers['values']['cv_link'],context['resume_url']);self.assertTrue(answers['from_resume']['cv_link']);self.assertNotIn('cv_link',answers['from_profile'])
  intent=self.s.career_fill_intent(self.a['id']);self.assertEqual(intent['answers']['cv_link'],context['resume_url'])
  with self.assertRaises(ValueError):self.s.answerable_field(self.a['id'],'cv_link',form['fingerprint'],0)
  self.s.save_field_answer(self.a['id'],'cv_link','https://example.test/my-cv',form['fingerprint'],0)
  self.assertEqual(self.s.career_fill_intent(self.a['id'])['answers']['cv_link'],'https://example.test/my-cv')
 async def test_resume_default_preserves_native_url_and_rejects_credentials_or_non_web_sources(self):
  from src.candidate_profile import defaults
  f={'id':'cv','type':'url','purpose':'resume_url','value':''}
  with self.s.connect() as db:
   for url in ('file:///private/cv.pdf','javascript:alert(1)','https://user:pass@example.test/cv'):
    self.assertNotIn('cv',defaults(db,[f],{'resume_url':url}))
   self.assertNotIn('cv',defaults(db,[{**f,'value':'https://example.test/already'}],{'resume_url':'https://hh.ru/resume/selected'}))
 async def test_profile_versions_reopen_optimistic_edit_validation_and_clear(self):
  save(self.s,{'phone':'+7 999 111-22-33'},{'phone':0})
  with self.assertRaises(ValueError):save(self.s,{'phone':'+7 999 222-33-44'},{'phone':0})
  for values in [{'email':'invented'},{'phone':'call me'},{'consent':'yes'}]:
   with self.assertRaises(ValueError):save(self.s,values,{next(iter(values)):0})
  self.assertEqual(read(ApplicationStore(self.s.path))['values']['phone'],'+7 999 111-22-33')
  save(self.s,{'phone':''},{'phone':1});self.assertEqual(read(self.s)['values']['phone'],'')
  with self.s.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM candidate_profile_versions WHERE field='phone'").fetchone()[0],2)
 async def test_profile_edit_revokes_queued_transfer_and_does_not_enter_model_context(self):
  save(self.s,{'email':'owner@example.test'},{'email':0});self.new_form();intent=self.s.career_fill_intent(self.a['id']);self.assertEqual(intent['answers']['mail'],'owner@example.test')
  self.s.approve_career_fill(self.a['id'],intent['intent_hash'],True);save(self.s,{'email':'changed@example.test'},{'email':1})
  self.assertIsNone(self.s.next_command('career-worker',kinds=['career_fill'],app_ids=[self.a['id']])['command'])
  with self.assertRaises(ValueError):self.s.approve_career_fill(self.a['id'],intent['intent_hash'],True)
  from src.candidate_facts import answer_context
  self.assertNotIn('changed@example.test',json.dumps(answer_context(self.s,self.a['context'])))
 async def test_manual_saved_contacts_migrate_but_model_proposals_and_consents_do_not(self):
  fields=import_saved_contacts(self.s);self.assertEqual(fields,['email']);self.assertEqual(read(self.s)['values']['email'],'candidate@example.test');self.assertEqual(import_saved_contacts(self.s),[])
  for f,key in [({'label':'Номер телефона*','type':'text'},'phone'),({'label':'First name','type':'text'},'first_name'),({'label':'E-mail*','type':'email'},'email'),({'label':'Имя','type':'checkbox'},None),({'label':'О себе','type':'textarea','purpose':'about'},None)]:self.assertEqual(field_key(f),key)
 async def test_telegram_profile_edit_is_owner_only_and_preserves_revision(self):
  op=Operator();bot=WorkflowBot(self.s,op,42);await bot.profile_menu(self.a['id']);data=next(b[1] for row in op.messages[-1][1] for b in row if b[1].startswith('w:pedit:'))
  await bot.update(update(callback=data,owner=99));self.assertFalse(self.s.setting('workflow_waiting'))
  await bot.update(update(callback=data));await bot.update(update(text='Владислав'));self.assertEqual(read(self.s)['values']['first_name'],'Владислав');self.assertFalse(self.s.setting('workflow_waiting'))

 async def test_phone_mask_changes_format_but_never_number(self):
  from src.candidate_profile import same_value
  field={'label':'Номер телефона*','type':'text'}
  self.assertTrue(same_value(field,'+79991112233','+7 (999) 111-22-33'))
  self.assertFalse(same_value(field,'+79991112233','+7 (999) 111-22-34'))
  self.assertFalse(same_value({'label':'О себе','type':'textarea'},'123456789','123 456 789'))

 async def test_field_history_keeps_its_cv_context_after_form_is_consumed(self):
  from copy import deepcopy
  from src.resume_source import content_hash
  job={**self.job,'id':'avito_20000','link':'https://career.avito.com/vacancies/data-science/20000/'}
  payload={'resume_id':self.f.cv['id'],'bundle':{'resumes':[self.f.cv]},'vacancy':job,'channel':'career'};a=self.s.create(payload)
  form={**self.snapshot,'vacancy_id':job['id'],'source_url':job['link']};form['fingerprint']=json.dumps(['avito',job['id'],form['fields']],ensure_ascii=False,separators=(',',':'));capture(self.s,a['id'],form)
  self.s.save_field_answer(a['id'],'f0','Ответ относится к исходному CV.',form['fingerprint'],0)
  with self.s.connect() as db:db.execute("UPDATE application_workflow SET form=NULL,state='fields_filled' WHERE app_id=?",(a['id'],))
  cv=deepcopy(self.f.cv);cv['sections'][0]['text']+=' Новый опыт.';cv['content_hash']=content_hash(cv)
  with self.assertRaises(ValueError):self.s.create({**payload,'bundle':{'resumes':[cv]}})

 async def test_tbank_combined_name_and_mail_use_saved_facts_without_inventing_or_overwriting(self):
  from src.candidate_profile import defaults
  save(self.s,{'first_name':'Владислав','last_name':'Василенко','email':'owner@example.test'},{'first_name':0,'last_name':0,'email':0})
  fields=[{'id':'name','label':'Фамилия и имя','type':'text','value':''},{'id':'mail','label':'Почта','type':'text','value':''}]
  with self.s.connect() as db:
   d=defaults(db,fields);self.assertEqual(d['name']['value'],'Василенко Владислав');self.assertEqual(d['mail']['value'],'owner@example.test')
   fields[0]['value']='Уже введено';self.assertNotIn('name',defaults(db,fields))

 async def test_links_and_exact_tbank_city_are_factual_defaults_and_revision_guarded(self):
  from src.candidate_profile import defaults
  values={'city':'Москва','telegram_url':'https://t.me/vsvladis','portfolio_url':'https://github.com/vladislav-vasilenko'}
  save(self.s,values,{k:0 for k in values})
  fields=[{'id':'city','label':'Город','type':'text','control':'tbank_city','value':''},{'id':'social','label':'Вконтакте, Телеграм и другие','type':'text','value':''},{'id':'portfolio','label':'Ссылка на портфолио','type':'url','value':''}]
  with self.s.connect() as db:
   d=defaults(db,fields);self.assertEqual(d['city']['value'],'Россия, г Москва');self.assertEqual(d['social']['value'],values['telegram_url']);self.assertEqual(d['portfolio']['value'],values['portfolio_url'])
   fields[1]['value']='https://example.test/existing';self.assertNotIn('social',defaults(db,fields))
  for value in ('javascript:alert(1)','https://user:pass@example.test/','https://example.test/a b'):
   with self.assertRaises(ValueError):save(self.s,{'portfolio_url':value},{'portfolio_url':1})

 async def test_tbank_v2_city_is_in_exact_transfer_preview_and_other_boards_cannot_claim_its_control(self):
  values={'city':'Москва'};save(self.s,values,{'city':0})
  uid='0d772642-b21e-4529-a234-5e93b00210be';link='https://www.tbank.ru/career/it/vacancy/moscow/ml/'+uid+'/'
  job={**self.job,'id':'tbank_'+uid,'link':link,'source_page':link};self.f.sync(self.f.cv,job)
  app=self.s.create({'resume_id':self.f.cv['id'],'bundle':{'resumes':[self.f.cv]},'vacancy':job,'channel':'career'})
  fields=[{'id':'city','label':'Город','type':'text','value':'','control':'tbank_city','manual_only':False,'purpose':'contact'}]
  form={**self.snapshot,'adapter_version':'career-fields-v2','provider':'tbank','vacancy_id':job['id'],'source_url':link,'fields':fields};form['fingerprint']=json.dumps(['tbank',job['id'],fields],ensure_ascii=False,separators=(',',':'))
  capture(self.s,app['id'],form);intent=self.s.career_fill_intent(app['id']);self.assertEqual(intent['answers']['city'],'Россия, г Москва')
  bad={**self.snapshot,'adapter_version':'career-fields-v2','fields':fields};bad['fingerprint']=json.dumps(['avito',self.job['id'],fields],ensure_ascii=False,separators=(',',':'))
  with self.assertRaisesRegex(ValueError,'контрол'):capture(self.s,self.a['id'],bad)
