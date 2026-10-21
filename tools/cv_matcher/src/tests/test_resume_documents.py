import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore
from src.application_store import ApplicationStore
from src import resume_documents as documents
from src.tests.test_archive import cv,record,CV_ID

class ResumeDocumentTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'test.sqlite3';self.archive=ArchiveStore(self.path);self.queue=ApplicationStore(self.path)
 def data(self):return {'filename':'CV.md','content_base64':base64.b64encode(('## Research\n\nImplemented models with PyTorch. '*8+'\nemail@test.example').encode()).decode()}
 def test_review_required_and_double_save_does_not_duplicate_or_replace_primary(self):
  self.archive.sync({'client_id':'browser-fixture','records':[record('resume',cv()),record('profile',{'primary_id':CV_ID,'goal':'Research'},'profile')]})
  p=documents.extract(self.archive,self.data());self.assertIn('[email скрыт]',p['candidate']['text']);self.assertEqual(self.archive.summary()['resumes'],1)
  request={'preview_id':p['preview_id'],'title':'Imported CV','text':p['candidate']['text'],'confirmed':False}
  with self.assertRaises(ValueError):documents.save(self.archive,request)
  request['confirmed']=True;first=documents.save(self.archive,request);second=documents.save(self.archive,request);self.assertEqual(first,second)
  self.assertEqual(self.archive.summary()['resumes'],2);self.assertEqual(self.archive.summary()['primary_id'],CV_ID)
  imported=self.archive.detail('resume',first['resume_id']);self.assertEqual(len(imported['versions']),1);self.assertEqual(imported['payload']['quality'],'full');self.assertEqual(imported['payload']['source_type'],'file')
  with self.assertRaises(ValueError):documents.save(self.archive,{**request,'text':request['text']+' changed'})
 def test_expiry_corrupt_files_and_unsafe_urls_fail_before_saving(self):
  for data in [{'filename':'bad.md','content_base64':'!'}, {'filename':'bad.exe','content_base64':'eA=='}]:
   with self.assertRaises(ValueError):documents.extract(self.archive,data)
  p=documents.extract(self.archive,self.data())
  with self.archive.connect() as db:
   p['expires']=time.time()-1;db.execute('UPDATE archive_meta SET value=? WHERE key=?',(json.dumps(p),documents.PREFIX+p['preview_id']))
  with self.assertRaises(ValueError):documents.save(self.archive,{'preview_id':p['preview_id'],'title':'CV','text':p['candidate']['text'],'confirmed':True})
  for url in ['http://docs.google.com/document/d/abcdefghijk/edit','https://docs.google.com.evil.test/document/d/abcdefghijk/edit','https://user@docs.google.com/document/d/abcdefghijk/edit','https://docs.google.com:90/document/d/abcdefghijk/edit','https://docs.google.com/spreadsheets/d/abcdefghijk/edit']:
   with self.assertRaises(ValueError):documents.google_start(self.queue,url)
  self.assertEqual(self.archive.summary()['resumes'],0)
 def test_google_reads_are_queued_deduplicated_and_bound_to_requested_document(self):
  url='https://docs.google.com/document/d/abcdefghijk/edit';first=documents.google_start(self.queue,url);self.assertEqual(first,documents.google_start(self.queue,url+'?usp=sharing'))
  self.assertEqual(documents.google_status(self.queue,self.archive,first['command_id'])['state'],'queued')
  self.assertIsNone(self.queue.next_command('old-document-reader',kinds=['resume_import'])['command'])
  cmd=self.queue.next_command('document-reader',kinds=['resume_import'],resume_import_version=2)['command'];candidate={'id':'gdoc_abcdefghijk','source_url':url,'text':'Research experience with PyTorch. '*8,'title':'Google CV'}
  self.queue.finish_command(cmd['id'],'document-reader',{'state':'complete','candidate':candidate})
  one=documents.google_status(self.queue,self.archive,cmd['id']);self.assertEqual(one['preview_id'],documents.google_status(self.queue,self.archive,cmd['id'])['preview_id']);self.assertEqual(self.archive.summary()['resumes'],0)
  saved=documents.save(self.archive,{'preview_id':one['preview_id'],'title':'Google CV','text':candidate['text'],'confirmed':True});self.assertEqual(saved['resume_id'],candidate['id'])
 def test_historical_snapshots_are_resume_scoped_and_do_not_include_current_annotations(self):
  first=cv();second=cv('Changed experience','2026-10-15T10:00:00Z');self.archive.sync({'client_id':'browser-fixture','records':[record('resume',first)]});old=self.archive.detail('resume',CV_ID)['version_id'];self.archive.sync({'client_id':'browser-fixture','records':[record('resume',second)]})
  snapshot=self.archive.resume_snapshot(CV_ID,old);self.assertEqual(snapshot['payload']['sections'],first['sections']);self.assertNotIn('supplements',snapshot);self.assertNotEqual(snapshot['version_id'],snapshot['current_version_id'])
  with self.assertRaises(ValueError):self.archive.resume_snapshot('b'*38,old)
 def test_document_routes_require_same_origin_session_and_assets_are_served(self):
  with TestClient(create_app('fixture-token',archive_path=self.path)) as client:
   endpoint='/archive/resume-source';self.assertEqual(client.post(endpoint,json={'op':'extract',**self.data()}).status_code,401)
   client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture-token'})
   self.assertEqual(client.post(endpoint,json={'op':'extract',**self.data()},headers={'Origin':'https://evil.test'}).status_code,401)
   read=client.post(endpoint,json={'op':'extract',**self.data()},headers={'Origin':'http://127.0.0.1:8788'});self.assertEqual(read.status_code,200)
   for asset in ['resume-sources.js','resume-compare.js','resume-compare-core.js','vacancy-document.js']:self.assertEqual(client.get('/assets/'+asset).status_code,200)
