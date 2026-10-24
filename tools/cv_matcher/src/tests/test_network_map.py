import json,unittest
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.tests import test_vacancy_team as fixtures
from src import network_map as graph,vacancy_team as team,linkedin_workspace as li

class NetworkMapTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.TeamTests('runTest');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.archive=self.fixture.archive;self.team_id=self.fixture.data['team_id']
  li.configure(self.archive,{'profile_url':'https://www.linkedin.com/in/owner/','own_profile':True})
  with self.archive.connect() as db:
   team.capture(db,{**self.fixture.data,'url':'https://huggingface.co/kandinskylab'},[{'url':'https://huggingface.co/researcher','name':'Researcher','relationship':'organization_member'}],'huggingface')
   self.archive._entity(db,'vacancy','hh_2',{'id':'hh_2','title':'Research Engineer GigaChat','company':'Lab 2','link':'https://hh.ru/vacancy/2','description':'Role','description_quality':'snippet'},'2026-10-24T00:00:00Z')
   url='https://www.linkedin.com/in/colleague/';li._record(db,'https://www.linkedin.com/in/owner/','contacts',url,{'id':url,'url':url,'name':'Colleague','headline':'ML Research Engineer'})
 def test_presets_filter_real_members_and_title_suggestions_do_not_create_membership(self):
  kandinsky=graph.view(self.archive,{'cluster':'kandinsky'});self.assertEqual(len(kandinsky['people']),1);self.assertEqual(kandinsky['people'][0]['streams'],[])
  gigachat=graph.view(self.archive,{'cluster':'gigachat'});self.assertEqual(len(gigachat['people']),0);self.assertEqual(gigachat['vacancies'][0]['id'],'hh_2');self.assertEqual(gigachat['edges'][0]['status'],'hypothesis')
  self.assertEqual(graph.view(self.archive,{'cluster':'aliceart'})['vacancies'],[])
 def test_explicit_job_contact_and_stream_links_remain_separate_and_have_evidence(self):
  values={'team_id':'preset:gigachat','vacancy_id':'hh_2','streams':['Post-training'],'evidence_url':'https://hh.ru/vacancy/2','evidence_quote':'Post-training experiments','status':'confirmed'}
  linked=graph.link_vacancy(self.archive,values);self.assertNotEqual(linked['team_id'],'preset:gigachat')
  graph.link_contact(self.archive,{'team_id':linked['team_id'],'url':'https://www.linkedin.com/in/colleague/','role':'Research Engineer','streams':['Post-training'],'status':'hypothesis','evidence_quote':'Needs verification','evidence_url':'https://www.linkedin.com/in/colleague/'})
  selected=graph.view(self.archive,{'cluster':'gigachat','stream':'Post-training'});self.assertEqual(len(selected['people']),1);self.assertTrue(any(edge['kind']=='vacancy_stream' for edge in selected['edges']));self.assertTrue(any(edge['kind']=='person_stream' and edge['status']=='hypothesis' for edge in selected['edges']))
  self.assertEqual(graph.view(self.archive,{'cluster':'kandinsky'})['people'][0]['source'],'huggingface')
  self.assertEqual(li.contacts(self.archive,{})['items'][0]['relevance']['category'],'team')
  with self.assertRaises(ValueError):graph.link_contact(self.archive,{'team_id':linked['team_id'],'url':'https://www.linkedin.com/in/colleague/','status':'confirmed','evidence_quote':'Changed without revision'})
  self.assertNotIn('Needs verification',json.dumps(self.archive.restore()))
 def test_graph_api_requires_local_authorization(self):
  with TestClient(create_app('fixture',archive_path=self.archive.path)) as client:
   self.assertEqual(client.post('/archive/network',json={'op':'view'}).status_code,401)
   result=client.post('/archive/network',json={'op':'view','cluster':'kandinsky'},headers={'X-Resume-Import-Token':'fixture'});self.assertEqual(result.status_code,200);self.assertEqual(len(result.json()['people']),1)
