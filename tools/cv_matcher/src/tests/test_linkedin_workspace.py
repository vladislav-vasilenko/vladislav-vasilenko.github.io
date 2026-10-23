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
  r=li.enqueue(self.archive,{'action':action,**kw});c=li.claim(self.archive,{'worker_id':WORKER,'version':'0.12.0'})['command'];self.assertEqual(c['id'],r['id']);return c
 def finish(self,c,data,state='completed'):
  return li.result(self.archive,{'id':c['id'],'worker_id':WORKER,'outcome':{'state':state,'message':'test','data':data}})
 def test_identity_and_origin_guards(self):
  for u in ('https://www.linkedin.com/jobs/view/123/?trackingId=x','https://www.linkedin.com/jobs/search/?currentJobId=123'):self.assertEqual(identity(u),{'id':'linkedin_123','link':'https://www.linkedin.com/jobs/view/123/'})
  for u in ('https://www.linkedin.com.evil.example/in/me/','http://www.linkedin.com/in/me/','https://x@www.linkedin.com/in/me/','https://www.linkedin.com:443/in/me/','https://www.linkedin.com/in/%2e%2e/'):
   with self.assertRaises(ValueError):li.linkedin_url(u,'profile')
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
  self.assertEqual(self.finish(c,{'items':[row]})['count'],1);self.assertTrue(self.finish(c,{'items':[row]})['duplicate']);c=self.queue('jobs.list');self.finish(c,{'items':[{**row,'description':'Short card','description_quality':'snippet','apply':{}}]});j=li.overview(self.archive)['records']['jobs'][0];self.assertEqual(j['description'],row['description'].strip());self.assertEqual(j['apply']['url'],'https://ats.example/jobs/123?jobId=123');self.assertNotIn('secret',json.dumps(j));self.assertEqual(self.archive.summary()['vacancies'],1)
 def test_wrong_detail_is_atomic(self):
  c=self.queue('jobs.detail',url='https://www.linkedin.com/jobs/view/123/')
  with self.assertRaises(ValueError):self.finish(c,{'items':[{'link':'https://www.linkedin.com/jobs/view/999/'}]})
  self.assertEqual(self.archive.summary()['vacancies'],0)
 def test_notes_revision_and_private_message_storage(self):
  c=self.queue('network.list');self.finish(c,{'items':[{'url':OTHER,'name':'Colleague','text':'Recruiter'}]});note={'kind':'contacts','id':OTHER,'text':'PRIVATE NOTE','revision':0};self.assertEqual(li.save_note(self.archive,note)['revision'],1)
  with self.assertRaises(ValueError):li.save_note(self.archive,note)
  c=self.queue('messages.thread',url='https://www.linkedin.com/messaging/thread/abc/');self.finish(c,{'items':[{'url':c['payload']['url'],'text':'PRIVATE CHAT','name':'Recruiter','vacancy_links':['https://www.linkedin.com/jobs/view/123/']}]});self.assertNotIn('PRIVATE',json.dumps(self.archive.restore()));self.assertEqual(len(li.overview(self.archive)['records']['threads']),1)
 def test_network_exact_preview_no_automatic_write_retry(self):
  c=self.queue('network.prepare',url=OTHER,network_action='connect');r=self.finish(c,{'url':OTHER,'action':'connect','target_fingerprint':'domhash','name':'Colleague','button_label':'Connect'});s=li.overview(self.archive)['snapshots']['network.prepare'];p={'action':'network.execute','snapshot_id':r['snapshot_id'],'fingerprint':s['fingerprint'],'confirmed':True}
  with self.assertRaises(ValueError):li.enqueue(self.archive,{**p,'confirmed':False})
  ident=li.enqueue(self.archive,p)['id'];self.assertEqual(li.enqueue(self.archive,p)['id'],ident);self.assertEqual(li.claim(self.archive,{'worker_id':WORKER})['command']['id'],ident)
  with self.archive.connect() as db:db.execute('UPDATE browser_commands SET updated=? WHERE id=?',(time.time()-400,ident))
  self.assertIsNone(li.claim(self.archive,{'worker_id':WORKER})['command']);self.assertEqual(li.overview(self.archive)['commands'][0]['state'],'uncertain')
 def test_form_transfer_and_save_bind_source_and_field_ids(self):
  c=self.queue('profile.form');self.finish(c,{'url':ACCOUNT+'edit/intro/','title':'Intro','form_fingerprint':'domhash','fields':[{'id':'f0','type':'text','value':'old','label':'Headline','max_length':220}]});s=li.overview(self.archive)['snapshots']['profile.form'];p={'action':'profile.fill','snapshot_id':s['id'],'fingerprint':s['fingerprint'],'source_fingerprint':'basis','confirmed':True,'values':{'f0':'new'}}
  with patch.object(li,'source',return_value={'fingerprint':'basis'}):
   with self.assertRaises(ValueError):li.enqueue(self.archive,{**p,'values':{'unknown':'new'}})
   ident=li.enqueue(self.archive,p)['id'];c=li.claim(self.archive,{'worker_id':WORKER})['command'];self.assertEqual(c['id'],ident)
  self.finish(c,{'url':ACCOUNT+'edit/intro/','form_fingerprint':'newhash','fields':[{'id':'f0','type':'text','value':'new'}]});s=li.overview(self.archive)['snapshots']['profile.fill']
  with patch.object(li,'source',return_value={'fingerprint':'changed'}):
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
