import asyncio,json,tempfile,unittest
from pathlib import Path
from src.archive_store import ArchiveStore
from src import archive_embedding_batch as batch
from src.company_catalog import raw_catalog
from src.vacancy_locations import normalize_locations
from src.scrapers.parsers.meta import parse_meta_graphql,parse_meta_rendered_detail
from src.tests.test_archive import cv,job,record,CLIENT

class CollectionContracts(unittest.TestCase):
 def test_meta_v2_and_old_graphql_preserve_all_locations(self):
  for key in ('job_search_with_featured_jobs_v2','job_search_with_featured_jobs'):
   body=json.dumps({'data':{key:{'all_jobs':[{'id':'123','title':'Research','locations':['Paris, France','London, UK'],'teams':['AI']}]}}})
   r=parse_meta_graphql(body);self.assertEqual(r[0]['locations'],['Paris, France','London, UK']);self.assertTrue(r[0]['locations_complete'])
  self.assertEqual(parse_meta_graphql('{"data":{"some_unrelated_query":[]}}'),[])
 def test_meta_current_rendered_detail_excludes_footer_and_requires_qualifications(self):
  html='<h1>Research Engineer</h1><div><div>Work on generative models, train and evaluate reproducible scientific experiments.</div><div><h2>Research Engineer Responsibilities</h2><ul><li>Build experiments and reusable code.</li></ul></div><div><h2>Minimum Qualifications</h2><ul><li>Experience with PyTorch and research.</li></ul></div><div><h2>About Meta</h2>Company boilerplate</div></div><footer>Private footer not JD</footer>'
  r=parse_meta_rendered_detail(html);self.assertIn('generative',r['description']);self.assertIn('PyTorch',r['qualifications']);self.assertNotIn('boilerplate',r['description']);self.assertNotIn('footer',r['qualifications'])
 def test_location_fallback_is_explicit_deduplicated_and_no_title_inference(self):
  self.assertEqual(normalize_locations({'title':'London Research'})['locations_status'],'missing')
  r=normalize_locations({'locations':['Paris, France','Paris, France','Remote'],'location':'London'});self.assertEqual(r['locations'],['Paris, France','Remote']);self.assertEqual(r['work_formats'],['remote'])
 def test_company_selection_batches_more_than_200_and_can_pause(self):
  with tempfile.TemporaryDirectory() as t:
   a=ArchiveStore(Path(t)/'s.sqlite');records=[record('resume',cv()),*[record('vacancy',job('hh_'+str(i),company='Google',text='Research PyTorch experiments. '*15,locations=['Paris','Remote'])) for i in range(1,206)],record('vacancy',job('hh_999',company='Meta',text='Research experiments. '*15))]
   for offset in range(0,len(records),100):a.sync({'client_id':CLIENT,'records':records[offset:offset+100]})
   self.assertTrue({'google','meta'}<={c['id'] for c in raw_catalog(a)})
   p=batch.prepare(a,{'resume_id':cv()['id'],'companies':['google'],'goal':'Generative research'});self.assertEqual(p['total'],205)
   calls=[]
   async def rank(packet):
    calls.append(packet);self.assertTrue(all(j['company']=='Google' for j in packet['vacancies']));self.assertLessEqual(len(packet['vacancies']),20)
    return {'api_requests':1,'new_compared':len(packet['vacancies']),'cache_reused':0}
   batch.control(a,{'id':p['id'],'action':'start','confirmed':True});asyncio.run(batch.run(a,p['id'],rank));r=batch.read(a,p['id']);self.assertEqual(r['state'],'complete');self.assertEqual(r['result']['processed'],205);self.assertEqual(len(calls),11)
   p=batch.prepare(a,{'resume_id':cv()['id'],'companies':['meta'],'goal':'Generative research'});batch.control(a,{'id':p['id'],'action':'start','confirmed':True});batch.control(a,{'id':p['id'],'action':'pause'});asyncio.run(batch.run(a,p['id'],rank));self.assertEqual(batch.read(a,p['id'])['state'],'paused')
 def test_source_locations_survive_short_card_without_location(self):
  with tempfile.TemporaryDirectory() as t:
   a=ArchiveStore(Path(t)/'s.sqlite');a.sync({'client_id':CLIENT,'records':[record('vacancy',job(locations=['Paris','Remote']))]});a.sync({'client_id':CLIENT,'records':[record('vacancy',job(text='Card',at='2026-10-14T11:00:00Z',description_quality='snippet',locations=[]))]})
   self.assertEqual(a.detail('vacancy','hh_1')['payload']['locations'],['Paris','Remote']);self.assertEqual(a.entities('vacancy')['items'][0]['work_formats'],['remote'])
