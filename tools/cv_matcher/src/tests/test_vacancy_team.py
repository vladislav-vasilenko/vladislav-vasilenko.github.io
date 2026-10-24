import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore
from src import vacancy_team as team,linkedin_workspace as li

class TeamTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.archive=ArchiveStore(Path(t.name)/'state.sqlite')
  with self.archive.connect() as db:self.archive._entity(db,'vacancy','hh_1',{'id':'hh_1','title':'Research Engineer','company':'Lab','link':'https://hh.ru/vacancy/1','description':'Role','description_quality':'snippet'},'2026-10-24T00:00:00Z')
  self.data={'vacancy_id':'hh_1','name':'Kandinsky Lab'};self.data.update(team.bind(self.archive,self.data))
 def test_huggingface_members_are_not_invented_stream_assignments_and_remain_private(self):
  response=Mock(status_code=200);response.json.return_value=[{'user':'researcher','fullname':'Researcher','isPro':True}]
  with patch('requests.get',return_value=response) as get:
   team.collect_huggingface(self.archive,{**self.data,'organization':'kandinskylab'});self.assertFalse(get.call_args.kwargs['allow_redirects'])
  state=team.view(self.archive,self.data);self.assertEqual(len(state['streams']),11);person=state['teams'][0]['members'][0]
  self.assertEqual(person['relationship'],'organization_member');self.assertEqual(person['streams'],[]);self.assertEqual(person['observed_role'],'');self.assertEqual(person['badges'],['PRO'])
  self.assertNotIn('researcher',json.dumps(self.archive.restore()))
  values={**self.data,'person_id':person['id'],'revision':person['revision'],'role':'Research Engineer','streams':['VAE / KVAE','Metrics & Evaluation (Benchmarking)'],'status':'hypothesis','evidence_url':'https://huggingface.co/kandinskylab/KVAE-Audio','evidence_quote':'A candidate lead for manual verification.'}
  team.annotate(self.archive,values)
  with self.assertRaises(ValueError):team.annotate(self.archive,values)
  person=team.view(self.archive,self.data)['teams'][0]['members'][0];self.assertEqual(len(person['streams']),2);self.assertTrue(all(s['status']=='hypothesis' for s in person['streams']))
  with self.archive.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM network_events').fetchone()[0],2)
 def test_linkedin_capture_is_tied_to_the_selected_vacancy_and_source(self):
  li.configure(self.archive,{'profile_url':'https://www.linkedin.com/in/owner/','own_profile':True})
  li.enqueue(self.archive,{**self.data,'action':'team.read','url':'https://www.linkedin.com/jobs/view/123/'})
  command=li.claim(self.archive,{'worker_id':'linkedin-team-test-worker'})['command'];self.assertEqual(command['kind'],'linkedin.team.read')
  li.result(self.archive,{'id':command['id'],'worker_id':command['worker_id'],'outcome':{'state':'completed','message':'Observed hiring team','data':{'items':[{'url':'https://www.linkedin.com/in/person/','name':'Person','role':'Hiring manager','relationship':'job_poster','evidence_quote':'Person, Hiring manager, Job poster'}]}}})
  person=team.view(self.archive,self.data)['teams'][0]['members'][0];self.assertEqual(person['evidence_url'],'https://www.linkedin.com/jobs/view/123/');self.assertEqual(person['streams'],[])
  with self.assertRaises(ValueError):li.enqueue(self.archive,{**self.data,'vacancy_id':'missing','action':'team.read','url':'https://www.linkedin.com/jobs/view/123/'})
 def test_team_api_auth_and_stream_validation(self):
  app=create_app('test-local-token',archive_path=self.archive.path)
  with TestClient(app) as client:
   self.assertEqual(client.post('/archive/vacancy-team',json={'op':'view',**self.data}).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'test-local-token'})
   self.assertEqual(client.post('/archive/vacancy-team',json={'op':'view',**self.data},headers={'Origin':'http://127.0.0.1:8788'}).status_code,200)
   self.assertEqual(client.post('/archive/vacancy-team',json={'op':'view',**self.data},headers={'Origin':'https://evil.test'}).status_code,401)
  with self.assertRaises(ValueError):team.annotate(self.archive,{**self.data,'streams':['Invented assignment']})
