import json,unittest
from unittest.mock import Mock
from types import SimpleNamespace
from src.tests import test_workflow as fixtures
from src import linkedin_workspace as li,linkedin_chat_analysis as advice
from src.linkedin_messages import messages,merge
URL='https://www.linkedin.com/messaging/thread/2-example==/'
ACCOUNT='https://www.linkedin.com/in/owner/'
class ChatAdviceTests(unittest.TestCase):
 sync=fixtures.WorkflowTests.sync
 def setUp(self):
  fixtures.WorkflowTests.setUp(self);li.configure(self.archive,{'profile_url':ACCOUNT,'own_profile':True})
  with self.archive.connect() as db:
   li._put_snapshot(db,ACCOUNT,'profile.read',{'title':'Owner','url':ACCOUNT})
   li._record(db,ACCOUNT,'threads',URL,{'id':URL,'url':URL,'name':'Recruiter','read_quality':'loaded','history_coverage':'message_limit','text':'Private transcript person@example.com','messages':[{'id':'1','sender':'Owner','text':'I build Python systems.','sent_label':'Today'},{'id':'2','sender':'Recruiter','text':'We would like to schedule a technical interview.','sent_label':'Today'}]})
 def prepare(self,goal='Research Engineer'):
  return advice.prepare(self.archive,{'thread_ids':[URL],'resume_id':self.cv['id'],'goal':goal,'model':'luna'})
 def output(self,key):
  return {'context_key':key,'summary':'Диалог стоит продолжить.','threads':[{'thread_ref':'T1','priority':'high','goal_fit':'aligned','employer_interest':'strong','stage_signal':'early','rationale':'Есть приглашение к интервью.','evidence':[{'message_ref':'T1_M2','quote':'schedule a technical interview'}],'next_action':'Уточнить роль и время.','draft_reply':'Спасибо! Какой фокус у роли?','questions':['Какая команда?']}],'limitations':['Доступна часть истории.']}
 def test_manual_prompt_and_import_never_call_api_and_do_not_export_private_metadata(self):
  p=self.prepare();ctx=advice.context(self.archive,p['context_key']);prompt=advice.prompt(ctx)
  self.assertNotIn(URL,prompt);self.assertNotIn('person@example.com',prompt);self.assertIn('candidate',prompt);self.assertIn('message_limit',prompt)
  client=Mock();result=advice.run(self.archive,p['context_key'],raw=self.output(p['context_key']),client_factory=lambda:client);self.assertEqual(result['api_requests'],0);client.assert_not_called()
  self.assertNotIn('Private transcript',json.dumps(self.archive.restore()))
 def test_exact_quotes_and_speaker_attribution_are_required(self):
  p=self.prepare();ctx=advice.context(self.archive,p['context_key']);bad=self.output(p['context_key']);bad['threads'][0]['evidence'][0]['quote']='An offer for one million dollars.'
  with self.assertRaises(ValueError):advice.validate(bad,ctx)
  bad=self.output(p['context_key']);bad['threads'][0]['evidence']=[{'message_ref':'T1_M1','quote':'I build Python systems.'}]
  with self.assertRaises(ValueError):advice.validate(bad,ctx)
 def test_api_is_explicit_single_call_and_reuses_cached_results(self):
  p=self.prepare();client=Mock();client.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(self.output(p['context_key'])))
  with self.assertRaises(ValueError):advice.run(self.archive,p['context_key'],client_factory=lambda:client)
  client.responses.create.assert_not_called();advice.run(self.archive,p['context_key'],confirmed=True,client_factory=lambda:client);result=advice.run(self.archive,p['context_key'],confirmed=True,client_factory=lambda:client)
  self.assertEqual(client.responses.create.call_count,1);self.assertTrue(result['cached']);self.assertFalse(client.responses.create.call_args.kwargs['store'])
 def test_changed_messages_block_paid_run(self):
  p=self.prepare();client=Mock()
  with self.archive.connect() as db:
   value=json.loads(db.execute("SELECT payload FROM linkedin_records WHERE kind='threads'").fetchone()[0]);value['messages'][1]['text']='Updated message';li._record(db,ACCOUNT,'threads',URL,value)
  with self.assertRaises(ValueError):advice.run(self.archive,p['context_key'],confirmed=True,client_factory=lambda:client)
  client.responses.create.assert_not_called()
 def test_message_merge_keeps_new_older_history_and_safe_links(self):
  old=[{'id':'2','text':'middle'},{'id':'3','text':'recent'}];incoming=[{'id':'1','text':'older'},{'id':'2','text':'updated'}]
  self.assertEqual([m['id'] for m in merge(old,incoming)],['1','2','3'])
  with self.assertRaises(ValueError):messages([{'id':'x','text':'hello','attachments':[{'url':'javascript:alert(1)'}]}])
