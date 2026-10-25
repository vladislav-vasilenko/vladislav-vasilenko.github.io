import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore
from src.board_import import identity
from src import linkedin_workspace as li
ACCOUNT='https://www.linkedin.com/in/owner/'
OTHER='https://www.linkedin.com/in/colleague/'
WORKER='linkedin-test-worker-123'
class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.archive=ArchiveStore(Path(self.tmp.name)/'state.sqlite');li.configure(self.archive,{'profile_url':ACCOUNT,'own_profile':True})
 def queue(self,action,**kw):
  # Unrelated workspace tests advance the persisted read schedule explicitly.
  with self.archive.connect() as db:
   config=li.settings(db)
   if config.get('read_pacing'):config['read_pacing']['next_at']=0;li.save_settings(db,config)
  r=li.enqueue(self.archive,{'action':action,**kw});c=li.claim(self.archive,{'worker_id':WORKER,'version':'0.12.4'})['command'];self.assertEqual(c['id'],r['id']);return c
 def finish(self,c,data,state='completed'):
  return li.result(self.archive,{'id':c['id'],'worker_id':WORKER,'outcome':{'state':state,'message':'test','data':data}})
 def test_identity_and_origin_guards(self):
  for u in ('https://www.linkedin.com/jobs/view/123/?trackingId=x','https://www.linkedin.com/jobs/search/?currentJobId=123'):self.assertEqual(identity(u),{'id':'linkedin_123','link':'https://www.linkedin.com/jobs/view/123/'})
  for u in ('https://www.linkedin.com.evil.example/in/me/','http://www.linkedin.com/in/me/','https://x@www.linkedin.com/in/me/','https://www.linkedin.com:443/in/me/','https://www.linkedin.com/in/%2e%2e/'):
   with self.assertRaises(ValueError):li.linkedin_url(u,'profile')
 def test_unicode_profile_slugs_are_canonical_and_never_accept_encoded_path_separators(self):
  from urllib.parse import quote
  for name in ('иван-петров','研究-engineer','élise-dupont'):
   url='https://www.linkedin.com/in/'+quote(name)+'/';self.assertEqual(li.linkedin_url(url,'profile'),url)
  for name in ('%2e%2e','ivan%2fadmin','ivan%5cadmin','%252fadmin'):
   with self.assertRaises(ValueError):li.linkedin_url('https://www.linkedin.com/in/'+name+'/','profile')
 def test_observed_profile_editor_can_be_opened_from_service_and_becomes_a_form_snapshot(self):
  command=self.queue('profile.read');self.finish(command,{'url':ACCOUNT,'headline':'Original','intro_edit_url':ACCOUNT+'edit/intro/','sections':{}});saved=li.overview(self.archive)['snapshots']['profile.read']
  with self.assertRaises(ValueError):li.enqueue(self.archive,{'action':'profile.open','snapshot_id':saved['id'],'url':ACCOUNT+'edit/not-observed/','section':'headline'})
  key=li.enqueue(self.archive,{'action':'profile.open','snapshot_id':saved['id'],'url':ACCOUNT+'edit/intro/','section':'headline'})['id'];command=li.claim(self.archive,{'worker_id':WORKER,'version':'0.13.0'})['command'];self.assertEqual(command['id'],key)
  self.finish(command,{'url':ACCOUNT+'edit/intro/','title':'Edit intro','form_fingerprint':'actual-fields','fields':[{'id':'f0','label':'Headline','type':'text','value':'Original'}]});form=li.overview(self.archive)['snapshots']['profile.form'];self.assertEqual(form['payload']['section'],'headline')
 def test_profile_fill_claim_reads_real_hh_source_outside_sqlite_write_transaction(self):
  from src.tests import test_workflow as fixtures
  fixture=fixtures.WorkflowTests('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups);archive=fixture.archive
  archive.sync({'client_id':fixtures.CLIENT,'records':[fixtures.record('profile',{'primary_id':fixture.cv['id']},'profile')]})
  li.configure(archive,{'profile_url':ACCOUNT,'own_profile':True});basis=li.source(archive)
  with archive.connect() as db:identifier=li._put_snapshot(db,ACCOUNT,'profile.form',{'url':ACCOUNT+'edit/intro/','form_fingerprint':'fields','fields':[{'id':'f0','label':'Headline','type':'text','value':'Old','max_length':300}]})
  form=li.overview(archive)['snapshots']['profile.form'];key=li.enqueue(archive,{'action':'profile.fill','snapshot_id':identifier,'fingerprint':form['fingerprint'],'source_fingerprint':basis['fingerprint'],'values':{'f0':'Reviewed headline'},'confirmed':True})['id'];command=li.claim(archive,{'worker_id':WORKER,'version':'0.13.0'})['command'];self.assertEqual(command['id'],key)
 def test_selected_hh_resume_fill_save_and_verification_keep_history_without_assuming_dialog_close_is_success(self):
  from src.tests import test_workflow as fixtures
  fixture=fixtures.WorkflowTests('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups);archive=fixture.archive
  other={**fixture.cv,'id':'b'*38,'title':'Selected Research CV'};other['content_hash']=fixtures.content_hash(other)
  archive.sync({'client_id':fixtures.CLIENT,'records':[fixtures.record('resume',other),fixtures.record('profile',{'primary_id':fixture.cv['id']},'profile')]})
  li.configure(archive,{'profile_url':ACCOUNT,'own_profile':True});basis=li.source(archive,other['id']);self.assertEqual(basis['resume_id'],other['id']);self.assertEqual(basis['headline'],'Selected Research CV')
  with archive.connect() as db:identifier=li._put_snapshot(db,ACCOUNT,'profile.form',{'url':ACCOUNT+'edit/intro/','profile_language':'en','section':'headline','form_fingerprint':'fields','fields':[{'id':'f0','label':'Headline','type':'text','value':'Previous headline','max_length':300}]})
  form=li.overview(archive)['snapshots']['profile.form'];li.enqueue(archive,{'action':'profile.fill','snapshot_id':identifier,'fingerprint':form['fingerprint'],'resume_id':other['id'],'source_fingerprint':basis['fingerprint'],'values':{'f0':'Selected Research CV'},'confirmed':True});command=li.claim(archive,{'worker_id':WORKER,'version':'0.13.1'})['command'];self.assertEqual(command['payload']['source_resume_id'],other['id'])
  li.result(archive,{'id':command['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'Filled','data':{'url':ACCOUNT+'edit/intro/','profile_language':'en','form_fingerprint':'new-fields','fields':[{'id':'f0','label':'Headline','type':'text','value':'Selected Research CV'}]}}})
  filled=li.overview(archive)['snapshots']['profile.fill'];request={'action':'profile.save','snapshot_id':filled['id'],'fingerprint':filled['fingerprint'],'source_fingerprint':basis['fingerprint'],'resume_id':other['id'],'confirmed':True};self.assertEqual(filled['payload']['changes'][0]['before'],'Previous headline')
  li.enqueue(archive,request);command=li.claim(archive,{'worker_id':WORKER,'version':'0.13.1'})['command'];li.result(archive,{'id':command['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'Dialog closed','data':{'url':ACCOUNT,'dialog_open':False}}})
  verification=li.claim(archive,{'worker_id':WORKER,'version':'0.13.1'})['command'];self.assertEqual(verification['kind'],'linkedin.profile.read');self.assertEqual(verification['payload']['profile_language'],'en')
  li.result(archive,{'id':verification['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'Read','data':{'url':ACCOUNT,'profile_language':'en','headline':'Still old headline','sections':{}}}})
  self.assertEqual(li.overview(archive)['snapshots']['profile.read']['payload']['verification']['state'],'needs_review');self.assertEqual(li.profile_history(archive,{'id':identifier})['payload']['fields'][0]['value'],'Previous headline')
 def test_account_change_cancels_pending_and_preserves_account_separation(self):
  li.enqueue(self.archive,{'action':'profile.read'});li.configure(self.archive,{'profile_url':OTHER,'own_profile':True});self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER})['command']);c=self.queue('profile.read')
  with self.assertRaises(ValueError):li.configure(self.archive,{'profile_url':ACCOUNT,'own_profile':True})
  self.finish(c,{'url':OTHER,'headline':'Original'});self.assertIn('profile.read',li.overview(self.archive)['snapshots']);li.configure(self.archive,{'profile_url':ACCOUNT,'own_profile':True});self.assertEqual(li.overview(self.archive)['snapshots'],{})
 def test_single_claim_pause_stop_and_worker_binding(self):
  c=self.queue('jobs.list',limit=5);self.assertIsNone(li.claim(self.archive,{'worker_id':'linkedin-other-worker'})['command'])
  with self.assertRaises(ValueError):li.progress(self.archive,{'id':c['id'],'worker_id':'linkedin-wrong-worker'})
  li.configure(self.archive,{'paused':True});self.assertFalse(li.progress(self.archive,{'id':c['id'],'worker_id':WORKER})['continue']);li.control(self.archive,{'id':c['id']});self.finish(c,{'items':[]},'cancelled')
 def test_full_description_and_apply_survive_card_refresh_and_receipt_retry(self):
  c=self.queue('jobs.detail',url='https://www.linkedin.com/jobs/view/123/');row={'link':c['payload']['url'],'title':'ML Engineer','company':'Lab','description':'Research and model training. '*20,'description_quality':'full','apply':{'kind':'external','url':'https://ats.example/jobs/123?jobId=123&session=secret'}}
  self.assertEqual(self.finish(c,{'items':[row]})['count'],1);self.assertTrue(self.finish(c,{'items':[row]})['duplicate']);c=self.queue('jobs.list');self.finish(c,{'items':[{**row,'description':'Short card','description_quality':'snippet','apply':{}}]});j=li.overview(self.archive)['records']['jobs'][0];self.assertEqual(j['description'],row['description'].strip());self.assertEqual(j['apply']['url'],'https://ats.example/jobs/123?jobId=123');self.assertNotIn('secret',json.dumps(j));self.assertEqual(self.archive.summary()['vacancies'],0);first=li.import_jobs(self.archive,{'ids':[j['id']]});self.assertEqual(first['added'],1);self.assertEqual(li.import_jobs(self.archive,{'ids':[j['id']]})['unchanged'],1);self.assertEqual(self.archive.summary()['vacancies'],1)
 def test_wrong_detail_is_atomic(self):
  c=self.queue('jobs.detail',url='https://www.linkedin.com/jobs/view/123/')
  with self.assertRaises(ValueError):self.finish(c,{'items':[{'link':'https://www.linkedin.com/jobs/view/999/'}]})
  self.assertEqual(self.archive.summary()['vacancies'],0)
 def test_notes_revision_and_private_message_storage(self):
  c=self.queue('network.list');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague','text':'Recruiter'}]});note={'kind':'contacts','id':OTHER,'text':'PRIVATE NOTE','revision':0};self.assertEqual(li.save_note(self.archive,note)['revision'],1)
  with self.assertRaises(ValueError):li.save_note(self.archive,note)
  c=self.queue('messages.thread',url='https://www.linkedin.com/messaging/thread/abc/');self.finish(c,{'items':[{'url':c['payload']['url'],'text':'PRIVATE CHAT','name':'Recruiter','vacancy_links':['https://www.linkedin.com/jobs/view/123/']}]});self.assertNotIn('PRIVATE',json.dumps(self.archive.restore()));self.assertEqual(len(li.overview(self.archive)['records']['threads']),1)
 def test_chat_sender_avatars_and_observed_dates_are_preserved_without_replacing_the_conversation_avatar(self):
  url='https://www.linkedin.com/messaging/thread/avatars/'
  command=self.queue('messages.list');self.finish(command,{'items':[{'url':url,'name':'Recruiter','avatar_url':'https://media.licdn.com/recruiter.jpg'}]})
  command=self.queue('messages.thread',url=url);self.finish(command,{'items':[{'url':url,'name':'Recruiter','avatar_url':'','headline':'Research recruiter','messages':[{'id':'m1','sender':'Recruiter','text':'Interview','avatar_url':'https://media.licdn.com/sender.jpg','date_label':'MONDAY','sent_label':'12:38 PM'},{'id':'m2','sender':'Unknown','text':'Another message','avatar_url':'https://untrusted.example/track.gif'}]}]})
  detail=li.thread_detail(self.archive,{'url':url});self.assertEqual(detail['avatar_url'],'https://media.licdn.com/recruiter.jpg');self.assertEqual(detail['headline'],'Research recruiter');self.assertEqual(detail['messages'][0]['date_label'],'MONDAY');self.assertEqual(detail['messages'][0]['avatar_url'],'https://media.licdn.com/sender.jpg');self.assertEqual(detail['messages'][1]['avatar_url'],'')
 def test_contact_batches_preserve_richer_fields_notes_and_search_across_scopes(self):
  c=self.queue('network.list',scope='connections',limit=3)
  batch={'id':c['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'batch','data':{'items':[{'url':OTHER,'name':'Коллега','headline':'Engineer at Lab','company':'Lab','badges':['Verified'],'degree':'1st'}]}}}
  li.checkpoint(self.archive,batch);self.assertEqual(self.finish(c,{'items':[],'collected_contacts':[OTHER]})['count'],1)
  li.save_note(self.archive,{'kind':'contacts','id':OTHER,'text':'ОБСУДИТЬ ИССЛЕДОВАНИЯ','revision':0})
  c=self.queue('network.list',scope='sent');self.finish(c,{'items':[{'url':OTHER,'name':'Коллега','text':'Short invitation'}]})
  records=li.contacts(self.archive,{'query':'обсудить','scope':'connections','limit':1});self.assertEqual(records['total'],1)
  record=records['items'][0];self.assertEqual(record['headline'],'Engineer at Lab');self.assertEqual(record['company'],'Lab');self.assertEqual(record['degree'],'1st');self.assertEqual(record['revision'],1);self.assertEqual(record['scopes'],['connections','sent']);self.assertIn('first_seen_at',record)
  self.assertEqual(li.contacts(self.archive,{'query':'КОЛЛЕГА','scope':'sent'})['total'],1)
  self.assertEqual(li.contacts(self.archive,{'scope':'received'})['total'],0)
  c=self.queue('network.list',limit=2)
  with self.assertRaises(ValueError):self.finish(c,{'items':[],'collected_contacts':['https://www.linkedin.com/in/not-saved/']})
  for request in ({'offset':True},{'limit':501},{'scope':'strangers'}):
   with self.assertRaises(ValueError):li.contacts(self.archive,request)
 def test_contact_company_requires_observed_company_link_not_a_phrase_ending_in_at_scale(self):
  c=self.queue('network.list');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague','company':'Scale'}]})
  c=self.queue('network.list');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague','headline':'Delivery at Scale','company':'','company_source':''}]})
  self.assertEqual(li.contacts(self.archive,{})['items'][0]['company'],'')
  c=self.queue('network.list');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague','company':'Lab','company_source':'profile_link'}]})
  c=self.queue('network.list');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague','company':'','company_source':''}]})
  self.assertEqual(li.contacts(self.archive,{})['items'][0]['company'],'Lab');self.assertEqual(li.contacts(self.archive,{})['items'][0]['company_source'],'profile_link')
 def test_linkedin_contact_and_chat_assets_are_served(self):
  with TestClient(create_app('fixture',archive_path=self.archive.path)) as client:
   for name in ('linkedin-contacts.js','linkedin-chats.js'):
    response=client.get('/assets/'+name,headers={'X-Resume-Import-Token':'fixture'});self.assertEqual(response.status_code,200);self.assertIn('const LinkedIn',response.text)
 def test_contact_continuation_skips_only_profiles_already_observed_in_that_source(self):
  c=self.queue('network.list',scope='connections');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague'}]})
  c=self.queue('network.list',scope='connections',only_new=True);self.assertEqual(c['payload']['known_contacts'],[OTHER]);self.assertTrue(c['payload']['only_new'])
  overview=li.overview(self.archive)['commands'][0]['payload'];self.assertNotIn('known_contacts',overview);self.assertEqual(overview['known_contacts_count'],1);self.finish(c,{'items':[],'collected_contacts':[]})
  c=self.queue('network.list',scope='received',only_new=True);self.assertEqual(c['payload']['known_contacts'],[])
  with self.assertRaises(ValueError):li.enqueue(self.archive,{'action':'network.list','only_new':'true'})
 def test_old_contact_worker_cannot_silently_repeat_first_page_in_continuation_mode(self):
  for version in ('0.12.3','old-worker'):
   key=li.enqueue(self.archive,{'action':'network.list','only_new':True})['id']
   self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER,'version':version})['command'])
   row=next(c for c in li.overview(self.archive)['commands'] if c['id']==key);self.assertEqual(row['state'],'needs_input');self.assertIn('0.12.4',row['result']['message'])
 def test_complete_contact_collection_crosses_1000_in_durable_batches_with_exact_count(self):
  first=li.enqueue(self.archive,{'action':'network.list','collect_all':True,'scope':'connections'})
  self.assertTrue(li.enqueue(self.archive,{'action':'network.list','collect_all':True,'scope':'connections'})['duplicate'])
  for start in range(0,1024,300):
   c=li.claim(self.archive,{'worker_id':WORKER,'version':'0.12.4'})['command'];self.assertEqual(c['payload']['limit'],300)
   if start:self.assertEqual(len(c['payload']['known_contacts']),start)
   rows=[{'url':'https://www.linkedin.com/in/contact-'+str(i)+'/','name':'Person '+str(i)} for i in range(start,min(1024,start+300))]
   for offset in range(0,len(rows),50):li.checkpoint(self.archive,{'id':c['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'batch','data':{'items':rows[offset:offset+50]}}})
   payload={'items':[],'collected_contacts':[row['url'] for row in rows],'diagnostics':{'expected_total':1024}}
   result=self.finish(c,payload);self.assertEqual(result['collection']['count'],min(1024,start+300));self.assertTrue(self.finish(c,payload)['duplicate'])
  collection=li.contacts(self.archive,{})['collection'];self.assertEqual(collection['state'],'completed');self.assertEqual(collection['count'],1024);self.assertEqual(collection['expected_total'],1024)
  self.assertEqual(li.contacts(self.archive,{})['total'],1024);self.assertEqual(len(li.overview(self.archive)['records']['contacts']),1000)
  self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER,'version':'0.12.4'})['command'])
 def test_stopping_complete_collection_does_not_spawn_another_batch(self):
  c=self.queue('network.list',collect_all=True);li.control(self.archive,{'id':c['id']});self.finish(c,{'items':[],'collected_contacts':[]},'cancelled')
  self.assertEqual(li.contacts(self.archive,{})['collection']['state'],'cancelled')
  self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER,'version':'0.12.4'})['command'])
 def test_complete_chat_collection_never_creates_or_resumes_a_contact_collection(self):
  command=self.queue('messages.list',collect_all=True,scope='all',load_threads=False)
  self.assertEqual(command['payload']['limit'],10000);self.assertNotIn('collection_id',command['payload']);self.assertNotIn('known_contacts',command['payload'])
  with self.archive.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM linkedin_contact_collections').fetchone()[0],0)
  with self.archive.connect() as db:
   from src.linkedin_contacts import start
   start(db,'legacy-chat-walk',{'account':ACCOUNT,'scope':'all'})
  self.finish(command,{'items':[],'collected_threads':[]});self.assertIsNone(li.overview(self.archive)['contact_collection'])
 def test_network_exact_preview_no_automatic_write_retry(self):
  c=self.queue('network.prepare',url=OTHER,network_action='connect');r=self.finish(c,{'url':OTHER,'action':'connect','target_fingerprint':'domhash','name':'Colleague','button_label':'Connect'});s=li.overview(self.archive)['snapshots']['network.prepare'];p={'action':'network.execute','snapshot_id':r['snapshot_id'],'fingerprint':s['fingerprint'],'confirmed':True}
  with self.assertRaises(ValueError):li.enqueue(self.archive,{**p,'confirmed':False})
  ident=li.enqueue(self.archive,p)['id'];self.assertEqual(li.enqueue(self.archive,p)['id'],ident);self.assertEqual(li.claim(self.archive,{'worker_id':WORKER})['command']['id'],ident)
  with self.archive.connect() as db:db.execute('UPDATE browser_commands SET updated=? WHERE id=?',(time.time()-400,ident))
  self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER})['command']);self.assertEqual(li.overview(self.archive)['commands'][0]['state'],'uncertain')
 def test_form_transfer_and_save_bind_source_and_field_ids(self):
  c=self.queue('profile.form');self.finish(c,{'url':ACCOUNT+'edit/intro/','title':'Intro','form_fingerprint':'domhash','fields':[{'id':'f0','type':'text','value':'old','label':'Headline','max_length':220}]});s=li.overview(self.archive)['snapshots']['profile.form'];p={'action':'profile.fill','snapshot_id':s['id'],'fingerprint':s['fingerprint'],'source_fingerprint':'basis','confirmed':True,'values':{'f0':'new'}}
  with patch.object(li,'source',return_value={'fingerprint':'basis','resume_id':'fixture-cv'}):
   with self.assertRaises(ValueError):li.enqueue(self.archive,{**p,'values':{'unknown':'new'}})
   ident=li.enqueue(self.archive,p)['id'];c=li.claim(self.archive,{'worker_id':WORKER})['command'];self.assertEqual(c['id'],ident)
  self.finish(c,{'url':ACCOUNT+'edit/intro/','form_fingerprint':'newhash','fields':[{'id':'f0','type':'text','value':'new'}]});s=li.overview(self.archive)['snapshots']['profile.fill']
  with patch.object(li,'source',return_value={'fingerprint':'changed','resume_id':'fixture-cv'}):
   with self.assertRaises(ValueError):li.enqueue(self.archive,{'action':'profile.save','snapshot_id':s['id'],'fingerprint':s['fingerprint'],'source_fingerprint':'changed','confirmed':True})
 def test_ui_auth_cannot_impersonate_extension_and_rejects_cross_site_post(self):
  app=create_app('test-local-token',archive_path=self.archive.path)
  with TestClient(app) as c:
   self.assertEqual(c.get('/archive/linkedin').status_code,401);c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'test-local-token'});self.assertEqual(c.get('/archive/linkedin').status_code,200)
   self.assertEqual(c.post('/archive/linkedin',json={'op':'claim','worker_id':WORKER},headers={'Origin':'http://127.0.0.1:8788'}).status_code,403);self.assertEqual(c.post('/archive/linkedin',json={'op':'configure','paused':True},headers={'Origin':'https://evil.example'}).status_code,401)
   for asset in ('linkedin.js','linkedin.css'):self.assertEqual(c.get('/assets/'+asset).status_code,200)

 def test_checkpoint_preserves_partial_records_without_finishing_command(self):
  c=self.queue('network.list')
  packet={'id':c['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'partial','data':{'items':[{'url':OTHER,'name':'Contact','text':'Visible card'}]}}}
  self.assertTrue(li.checkpoint(self.archive,packet)['continue'])
  self.assertEqual(li.overview(self.archive)['commands'][0]['state'],'running')
  self.assertEqual(len(li.overview(self.archive)['records']['contacts']),1)
  li.control(self.archive,{'id':c['id']})
  self.assertFalse(li.checkpoint(self.archive,packet)['continue'])
  self.finish(c,{'items':[]},'cancelled')
  self.assertEqual(len(li.overview(self.archive)['records']['contacts']),1)

 def test_partial_profile_is_saved_for_review_and_wrong_owner_is_rejected(self):
  c=self.queue('profile.read')
  self.finish(c,{'url':ACCOUNT,'headline':'','sections':{'experience':{'text':'Observed experience','coverage':'visible_only'}}},'needs_input')
  self.assertEqual(li.overview(self.archive)['snapshots']['profile.read']['payload']['sections']['experience']['text'],'Observed experience')
  c=self.queue('profile.read')
  with self.assertRaises(ValueError):self.finish(c,{'url':OTHER,'headline':'Different person','sections':{}})

 def test_three_recommendation_sections_full_queue_and_explicit_import(self):
  c=self.queue('jobs.list',limit=10,collection='all',load_details=True)
  rows=[{'link':'https://www.linkedin.com/jobs/view/'+str(i)+'/','title':'ML Engineer '+str(i),'company':'Research Lab','location':'London (Hybrid)','description':'Short card','recommendation_sections':[scope]} for i,scope in [(123,'profile'),(124,'more'),(125,'preferences')]]
  result=self.finish(c,{'items':rows});self.assertEqual(result['details_queued'],3)
  self.assertEqual(self.archive.summary()['vacancies'],0)
  state=li.overview(self.archive);self.assertEqual(len(state['records']['jobs']),3);self.assertEqual(len([c for c in state['commands'] if c['state']=='queued']),3)
  # Repeating a listing never duplicates the pending full-text work.
  with self.archive.connect() as db:
   db.execute("UPDATE browser_commands SET state='completed' WHERE kind='linkedin.jobs.detail'")
  detail=self.queue('jobs.detail',url=rows[0]['link']);self.finish(detail,{'items':[{**rows[0],'description':'Full verified description. '*20,'description_quality':'full','apply':{'kind':'easy_apply','url':rows[0]['link']}}]})
  imported=li.import_jobs(self.archive,{'ids':['linkedin_123','linkedin_123']});self.assertEqual(imported['added'],1);self.assertEqual(imported['count'],1)
  self.assertEqual(self.archive.detail('vacancy','linkedin_123')['payload']['locations'],['London (Hybrid)'])
  self.assertEqual(li.import_jobs(self.archive,{'ids':['linkedin_123']})['unchanged'],1)
  self.assertTrue(next(j for j in li.overview(self.archive)['records']['jobs'] if j['id']=='linkedin_123')['in_archive'])
  self.assertEqual(self.archive.summary()['vacancies'],1)  # Other selections stay local to LinkedIn workspace.

 def test_import_rejects_other_accounts_unknown_ids_and_never_downgrades_archive(self):
  c=self.queue('jobs.list');self.finish(c,{'items':[{'link':'https://www.linkedin.com/jobs/view/123/','title':'Engineer','description':'Card','recommendation_sections':['more']}]})
  for ids in ([],['hh_1'],['linkedin_999'],['linkedin_123','linkedin_999']):
   with self.assertRaises(ValueError):li.import_jobs(self.archive,{'ids':ids})
  self.assertEqual(self.archive.summary()['vacancies'],0)
  li.configure(self.archive,{'profile_url':OTHER,'own_profile':True})
  with self.assertRaises(ValueError):li.import_jobs(self.archive,{'ids':['linkedin_123']})
  li.configure(self.archive,{'profile_url':ACCOUNT,'own_profile':True})
  with self.archive.connect() as db:self.archive._entity(db,'vacancy','linkedin_123',{'id':'linkedin_123','link':'https://www.linkedin.com/jobs/view/123/','title':'Engineer','description':'Full newer details. '*20,'description_quality':'full','collected_at':'2099-01-01T00:00:00Z'},'2099-01-01T00:00:00Z')
  result=li.import_jobs(self.archive,{'ids':['linkedin_123']});self.assertEqual(result['protected'],1)
  self.assertEqual(self.archive.detail('vacancy','linkedin_123')['payload']['description_quality'],'full')

 def test_search_filters_survive_normalization_but_tracking_is_removed(self):
  url='https://www.linkedin.com/jobs/search-results/?keywords=Senior+LLM+Engineer&geoId=90009496&originToLandingJobPostings=123%2C456&lipi=tracking-secret'
  clean=li.linkedin_url(url);self.assertIn('keywords=Senior+LLM+Engineer',clean);self.assertIn('geoId=90009496',clean);self.assertIn('originToLandingJobPostings=123%2C456',clean);self.assertNotIn('lipi',clean)

 def test_five_hundred_cards_checkpoint_in_small_batches_and_finalize_by_ids(self):
  c=self.queue('jobs.list',limit=500,load_details=True)
  links=['https://www.linkedin.com/jobs/view/'+str(i)+'/' for i in range(1000,1500)]
  for start in range(0,500,50):
   rows=[{'link':u,'title':'Research Engineer','company':'Lab','description':'Card','recommendation_sections':['more']} for u in links[start:start+50]]
   li.checkpoint(self.archive,{'id':c['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'batch','data':{'items':rows}}})
  result=self.finish(c,{'items':[],'collected_links':links});self.assertEqual(result['count'],500);self.assertEqual(result['details_queued'],500)
  self.assertEqual(len(li.overview(self.archive)['records']['jobs']),500);self.assertEqual(self.archive.summary()['vacancies'],0)
  with self.assertRaises(ValueError):li.enqueue(self.archive,{'action':'jobs.list','limit':501})

 def test_random_read_delay_survives_reclaim_and_does_not_block_profile_reads(self):
  first=self.queue('jobs.detail',url='https://www.linkedin.com/jobs/view/123/')
  self.finish(first,{'items':[]},'needs_input')
  second=li.enqueue(self.archive,{'action':'jobs.detail','url':'https://www.linkedin.com/jobs/view/124/'})
  with self.archive.connect() as db:scheduled=li.settings(db)['read_pacing'].copy()
  self.assertGreaterEqual(scheduled['last_delay_ms'],3000);self.assertLessEqual(scheduled['last_delay_ms'],8000)
  claim=li.claim(self.archive,{'worker_id':WORKER});self.assertIsNone(claim['command']);self.assertGreater(claim['retry_after_ms'],0)
  li.enqueue(self.archive,{'action':'profile.read'});self.assertEqual(li.claim(self.archive,{'worker_id':WORKER})['command']['kind'],'linkedin.profile.read')
  with self.archive.connect() as db:self.assertEqual(li.settings(db)['read_pacing']['next_at'],scheduled['next_at'])

 def test_restriction_stops_the_remaining_queue(self):
  command=self.queue('jobs.detail',url='https://www.linkedin.com/jobs/view/123/')
  li.result(self.archive,{'id':command['id'],'worker_id':WORKER,'outcome':{'state':'needs_input','message':'LinkedIn требует вход или ручную проверку.','data':{}}})
  li.enqueue(self.archive,{'action':'jobs.detail','url':'https://www.linkedin.com/jobs/view/124/'})
  self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER})['command']);self.assertTrue(li.overview(self.archive)['settings']['paused'])

 def test_padded_conversation_ids_batch_reading_and_local_message_pagination(self):
  url='https://www.linkedin.com/messaging/thread/2-example==/'
  self.assertEqual(li.linkedin_url(url.replace('==','%3D%3D'),'thread'),url)
  command=self.queue('messages.list',limit=3,load_threads=True)
  li.checkpoint(self.archive,{'id':command['id'],'worker_id':WORKER,'outcome':{'state':'completed','message':'preview','data':{'items':[{'url':url,'name':'Recruiter','text':'Preview','preview':'Preview','badges':['InMail']}]}}})
  result=self.finish(command,{'items':[],'collected_threads':[url],'listing_coverage':'available_boundary'});self.assertEqual(result['count'],1);self.assertEqual(result['threads_queued'],1);self.assertEqual(result['listing_coverage'],'available_boundary')
  command=li.claim(self.archive,{'worker_id':WORKER})['command'];self.assertEqual(command['kind'],'linkedin.messages.thread')
  rows=[{'id':str(i),'sender':'Recruiter','text':'Message '+str(i),'sent_label':'Today','attachments':[],'badges':[]} for i in range(60)]
  self.finish(command,{'items':[{'url':url,'name':'Recruiter','text':'PRIVATE THREAD','messages':rows}],'history_coverage':'message_limit'})
  state=li.overview(self.archive);self.assertNotIn('messages',state['records']['threads'][0]);self.assertEqual(state['records']['threads'][0]['message_count'],60)
  first=li.thread_detail(self.archive,{'url':url,'limit':50});self.assertEqual(len(first['messages']),50);self.assertEqual(first['next_offset'],50)
  older=li.thread_detail(self.archive,{'url':url,'limit':50,'offset':50});self.assertEqual(len(older['messages']),10);self.assertIsNone(older['next_offset'])
