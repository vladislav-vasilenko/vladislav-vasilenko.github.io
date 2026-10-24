import json,tempfile,unittest
from pathlib import Path
from src.archive_store import ArchiveStore
from src import linkedin_workspace as li,contact_relevance as relevance

ACCOUNT='https://www.linkedin.com/in/owner/'
PERSON='https://www.linkedin.com/in/person/'

class RelevanceTests(unittest.TestCase):
 def test_explanation_distinguishes_recruiters_adjacent_roles_and_missing_data(self):
  ctx={'hash':'fixture','current':['ML / AI'],'adjacent':['Разработка'],'members':set()}
  for headline,category in [('Talent Acquisition Specialist @Labelbox | AI','recruiter'),('Research Engineer | Diffusion models','focus'),('Senior Python Backend Developer','adjacent'),('Architect | Urban Design','review'),('','unknown')]:
   result=relevance.classify({'url':PERSON,'name':'ML Engineer','headline':headline},ctx);self.assertEqual(result['category'],category);self.assertEqual(result['evidence'],headline)
  ctx['members'].add(PERSON);result=relevance.classify({'url':PERSON,'headline':'IT Recruiter'},ctx);self.assertEqual(result['category'],'team');self.assertTrue(result['is_recruiter'])
 def test_review_plan_is_local_reversible_versioned_and_filtered_before_pagination(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);archive=ArchiveStore(Path(tmp.name)/'state.sqlite');li.configure(archive,{'profile_url':ACCOUNT,'own_profile':True})
  with archive.connect() as db:
   for i in range(45):
    url=PERSON.rstrip('/')+'-'+str(i)+'/';li._record(db,ACCOUNT,'contacts',url,{'id':url,'url':url,'name':'Contact '+str(i),'headline':'IT Recruiter' if i==44 else 'Unknown job'})
  recruiters=li.contacts(archive,{'category':'recruiter','limit':1});self.assertEqual(recruiters['total'],1);self.assertEqual(recruiters['items'][0]['id'],PERSON.rstrip('/')+'-44/')
  target=PERSON.rstrip('/')+'-1/';first=relevance.review(archive,{'id':target,'plan':'disconnect','note':'Review professional connection','revision':0});self.assertEqual(first['review']['execution'],'local_plan_only')
  self.assertEqual(li.contacts(archive,{'plan':'disconnect'})['total'],1)
  with self.assertRaises(ValueError):relevance.review(archive,{'id':target,'plan':'keep','revision':0})
  relevance.review(archive,{'id':target,'plan':'keep','revision':1});self.assertEqual(li.contacts(archive,{'plan':'disconnect'})['total'],0)
  with archive.connect() as db:
   self.assertEqual(db.execute('SELECT count(*) FROM linkedin_contact_review_events').fetchone()[0],2)
   self.assertEqual(db.execute('SELECT count(*) FROM browser_commands').fetchone()[0],0)
  self.assertNotIn('Review professional connection',json.dumps(archive.restore()))
