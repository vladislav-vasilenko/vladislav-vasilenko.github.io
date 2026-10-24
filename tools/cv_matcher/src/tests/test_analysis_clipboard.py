import unittest,json
from src.tests import test_workflow as fixtures
from src import linkedin_workspace as li,vacancy_export
from src.career_skills_store import put

class ClipboardTests(unittest.TestCase):
 sync=fixtures.WorkflowTests.sync
 def setUp(self):
  fixtures.WorkflowTests.setUp(self)
  with self.archive.connect() as db:
   put(db,'trajectory-active','test-route');put(db,'trajectory:test-route',{'id':'test-route','label':'SELECTED CAREER TRACK','stages':[],'track_id':'generative_models','revision':1})
 def test_contact_context_contains_exact_selected_cv_track_and_goal_only_when_checked(self):
  meta=li.contacts_context(self.archive,{'resume_id':self.cv['id'],'metadata_only':True});self.assertEqual(meta['resume']['id'],self.cv['id']);self.assertNotIn('sections',meta['resume'])
  full=li.contacts_context(self.archive,{'resume_id':self.cv['id']});self.assertEqual(full['resume']['sections'],self.archive.detail('resume',self.cv['id'])['payload']['sections']);self.assertEqual(full['trajectory']['label'],'SELECTED CAREER TRACK')
  omitted=li.contacts_context(self.archive,{'include_resume':False,'include_trajectory':False,'include_goal':False,'include_team_coverage':False});self.assertEqual(omitted,{})
  for key in ('include_resume','include_trajectory','include_goal'):
   with self.assertRaises(ValueError):li.contacts_context(self.archive,{key:'false'})
 def test_vacancy_export_respects_explicit_ids_and_context_checkboxes_without_model_calls(self):
  data=vacancy_export.prepare(self.archive,{'scope':'selected','ids':['hh_1'],'filters':{'resume_id':self.cv['id'],'model':'text-embedding-3-small'},'instruction':'MY CUSTOM QUESTION','include_resume':True,'include_trajectory':True,'include_goal':True})
  self.assertEqual(data['count'],1);self.assertEqual(data['api_requests'],0);self.assertIn('MY CUSTOM QUESTION',data['prompt']);self.assertIn('SELECTED CAREER TRACK',data['prompt']);self.assertIn('"sections"',data['prompt'])
  stripped=vacancy_export.prepare(self.archive,{'scope':'filtered','filters':{'resume_id':self.cv['id']},'include_resume':False,'include_trajectory':False,'include_goal':False})
  body=json.loads(stripped['prompt'].split('Контекст и вакансии:\n',1)[1]);self.assertNotIn('resume',body);self.assertNotIn('trajectory',body);self.assertNotIn('goal',body)
  with self.assertRaises(ValueError):vacancy_export.prepare(self.archive,{'scope':'selected','ids':['missing'],'filters':{'resume_id':self.cv['id']}})
 def test_linkedin_export_reads_private_selection_instead_of_main_archive_and_counts_entire_prompt(self):
  account='https://www.linkedin.com/in/owner/';li.configure(self.archive,{'profile_url':account,'own_profile':True})
  with self.archive.connect() as db:
   for index in (10,11):li._record(db,account,'jobs','linkedin_'+str(index),{'id':'linkedin_'+str(index),'link':'https://www.linkedin.com/jobs/view/'+str(index)+'/','title':'LinkedIn role '+str(index),'description':'Detailed requirements. '*90,'description_quality':'full','linkedin_signals':{'applicants_label':'Over 100 applicants'},'apply':{'kind':'external','url':'https://boards.greenhouse.io/example/jobs/'+str(index)}})
   li._record(db,'https://www.linkedin.com/in/other/','jobs','linkedin_99',{'id':'linkedin_99','title':'OTHER ACCOUNT'})
  query={'dataset':'linkedin','account':account,'scope':'selected','ids':['linkedin_10'],'filters':{'resume_id':self.cv['id']},'include_resume':False,'include_trajectory':False,'include_goal':False,'description_mode':'full'}
  result=vacancy_export.prepare(self.archive,query);self.assertEqual(result['count'],1);self.assertEqual(result['characters'],len(result['prompt']));self.assertGreater(result['estimated_tokens'],0);self.assertIn('greenhouse.io',result['prompt']);self.assertIn('Over 100 applicants',result['prompt']);self.assertNotIn('OTHER ACCOUNT',result['prompt']);self.assertNotIn('"resume"',result['prompt']);self.assertEqual(result['api_requests'],0)
  self.assertEqual(vacancy_export.prepare(self.archive,{**query,'scope':'archive'})['count'],2)
  with self.assertRaises(ValueError):vacancy_export.prepare(self.archive,{**query,'account':'https://www.linkedin.com/in/other/'})
