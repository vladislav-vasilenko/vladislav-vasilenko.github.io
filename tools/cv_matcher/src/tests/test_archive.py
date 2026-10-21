from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from fastapi.testclient import TestClient
from src.archive_store import ArchiveStore,digest,scope_url
from resume_import_server import create_app

CLIENT='browser-test-client'
CV_ID='a'*38
def cv(text='В самостоятельном проекте реализовал Transformer на PyTorch. Изучаю Flow Matching.',at='2026-10-14T10:00:00Z'):
    return {'id':CV_ID,'title':'Research CV','source_type':'hh','source_url':'https://hh.ru/resume/'+CV_ID,'content_hash':'browser-hash','quality':'full','checked_at':at,'sections':[{'key':'experience','heading':'Опыт','text':text}]}
def job(id='hh_1',text='Разрабатывать модели на PyTorch; исследовать генерацию. Нужен опыт CUDA и Flow Matching.',at='2026-10-14T10:00:00Z',**extra):
    return {'id':id,'title':'Research Engineer','company':'Sber','link':'https://hh.ru/vacancy/'+id[3:],'source_page':'https://hh.ru/vacancy/'+id[3:],'description':text,'description_quality':'full','locations':['Москва'],'collected_at':at,'archived':False,**extra}
def record(kind,data,id=None):return {'kind':kind,'id':id or data['id'],'data':data,'digest':digest(data)}
def scan(id,ids,at='2026-10-14T12:00:00Z',complete=True,url='https://hh.ru/search/vacancy?text=ML',kind='vacancy_search',**extra):
    return {'id':id,'scan_kind':kind,'scope_url':url,'started_at':at,'completed_at':at,'ids':ids,'listing_complete':complete,'state':'complete' if complete else 'partial','pages':2,'start_page':0,**extra}
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.path=self.root/'archive.sqlite3';self.store=ArchiveStore(self.path)
    def sync(self,*records,client=CLIENT):return self.store.sync({'client_id':client,'records':list(records)})
    def test_idempotence_new_metadata_and_whitespace_do_not_create_fake_versions(self):
        self.sync(record('resume',cv()),record('vacancy',job()))
        again=self.sync(record('resume',cv()),record('vacancy',job()))
        self.assertEqual(len(again['accepted']),2);self.assertEqual(self.store.summary()['versions'],2)
        current=cv(at='2026-10-14T11:00:00Z');current['sections'][0]['text']=current['sections'][0]['text'].replace(' ','  ')
        self.sync(record('resume',current));self.assertEqual(self.store.summary()['versions'],2)
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
    def test_versions_diff_reversion_and_restore_keep_complete_professional_text(self):
        self.sync(record('resume',cv()),record('vacancy',job()))
        new=cv('Реализовал Transformer на PyTorch. Добавил DDP эксперименты.','2026-10-14T11:00:00Z');self.sync(record('resume',new))
        detail=self.store.detail('resume',CV_ID);self.assertEqual(len(detail['versions']),2)
        result=self.store.diff('resume',CV_ID,detail['versions'][1]['id'],detail['version_id'])
        self.assertIn('DDP',''.join(p['text'] for p in result['segments'] if p['type']=='insert'))
        original=cv(at='2026-10-14T12:00:00Z');self.sync(record('resume',original));self.assertEqual(len(self.store.detail('resume',CV_ID)['versions']),3)
        self.assertEqual(self.store.restore()['resume_bundle']['resumes'][0]['sections'],original['sections'])
    def test_delayed_upload_adds_history_without_replacing_newer_head(self):
        self.sync(record('vacancy',job(text='Новая версия',at='2026-10-14T12:00:00Z')))
        self.sync(record('vacancy',job(text='Старая версия',at='2026-10-14T10:00:00Z')))
        detail=self.store.detail('vacancy','hh_1');self.assertEqual(detail['payload']['description'],'Новая версия');self.assertEqual(len(detail['versions']),2)
        self.assertEqual(detail['versions'][0]['id'],detail['version_id'])
    def test_snippet_does_not_destroy_description_or_confirm_closure(self):
        self.sync(record('vacancy',job()))
        snippet=job(text='Краткая карточка',at='2026-10-14T11:00:00Z',description_quality='snippet',source_page='https://hh.ru/search/vacancy?text=ML',archived=True);snippet.pop('locations')
        self.sync(record('vacancy',snippet));detail=self.store.detail('vacancy','hh_1')
        self.assertEqual(detail['payload']['description'],job()['description']);self.assertEqual(detail['payload']['locations'],['Москва']);self.assertEqual(detail['availability'],'active');self.assertEqual(len(detail['versions']),1)
    def test_archived_detail_is_saved_and_only_a_new_full_detail_can_reopen_it(self):
        self.sync(record('vacancy',job()))
        archived=job(text='',at='2026-10-14T11:00:00Z',description_quality='missing',archived=True)
        self.sync(record('vacancy',archived));self.assertEqual(self.store.detail('vacancy','hh_1')['availability'],'closed');self.assertEqual(self.store.detail('vacancy','hh_1')['payload']['description'],job()['description'])
        self.sync(record('vacancy',job(text='Карточка',at='2026-10-14T12:00:00Z',description_quality='snippet',source_page='https://hh.ru/search/vacancy',archived=False)))
        self.assertEqual(self.store.detail('vacancy','hh_1')['availability'],'closed')
        self.sync(record('vacancy',job(at='2026-10-14T13:00:00Z')));self.assertEqual(self.store.detail('vacancy','hh_1')['availability'],'active')
        events=[r['event'] for r in self.store.timeline()['items']];self.assertIn('closed',events);self.assertIn('reopened',events)
    def test_only_complete_comparable_scan_can_mark_missing_and_partial_scan_can_show_return(self):
        self.sync(record('vacancy',job()),record('vacancy',job('hh_2')))
        self.sync(record('scan',scan('run_1',['hh_1','hh_2'])))
        self.sync(record('scan',scan('run_2',['hh_1'],at='2026-10-14T13:00:00Z',complete=False)))
        self.assertEqual(self.store.summary()['missing_in_search'],0)
        self.sync(record('scan',scan('run_other',['hh_1'],at='2026-10-14T13:30:00Z',url='https://hh.ru/search/vacancy?text=Java')))
        self.assertEqual(self.store.summary()['missing_in_search'],0)
        self.sync(record('scan',scan('run_3',['hh_1'],at='2026-10-14T14:00:00Z',url='https://hh.ru/search/vacancy?text=ML&page=0&search_session_id=x')))
        detail=self.store.detail('vacancy','hh_2');self.assertEqual(detail['availability'],'active');self.assertEqual(detail['membership'][0]['present'],0)
        self.assertEqual(self.store.summary()['missing_in_search'],1)
        self.sync(record('scan',scan('run_4',['hh_2'],at='2026-10-14T15:00:00Z',complete=False)))
        self.assertEqual(self.store.summary()['missing_in_search'],0)
    def test_failed_stopped_later_page_and_late_offline_scans_do_not_invent_disappearances(self):
        self.sync(record('vacancy',job()),record('scan',scan('baseline',['hh_1'],at='2026-10-14T15:00:00Z')))
        for i,extra in enumerate([{'state':'failed'},{'state':'stopped'},{'start_page':1}]):self.sync(record('scan',scan('bad_'+str(i),[],at='2026-10-14T16:00:00Z',**extra)))
        self.sync(record('scan',scan('older',[],at='2026-10-14T14:00:00Z')))
        self.assertEqual(self.store.summary()['missing_in_search'],0)
        self.assertEqual(self.store.detail('vacancy','hh_1')['membership'][0]['present'],1)
    def test_catalog_absence_keeps_cv_and_versions_in_archive(self):
        self.sync(record('resume',cv()),record('scan',scan('catalog_1',[CV_ID],url='https://hh.ru/applicant/profile/me',kind='resume_catalog')))
        self.sync(record('scan',scan('catalog_2',[],at='2026-10-14T14:00:00Z',url='https://hh.ru/applicant/profile/me',kind='resume_catalog')))
        detail=self.store.detail('resume',CV_ID);self.assertEqual(detail['membership'][0]['present'],0);self.assertEqual(len(detail['versions']),1);self.assertIn('Transformer',detail['text'])
    def test_rejected_record_does_not_rollback_other_records_and_receipts_are_client_scoped(self):
        bad=cv();bad['OPENAI_API_KEY']='secret';result=self.sync(record('resume',bad),record('vacancy',job()))
        self.assertEqual(len(result['accepted']),1);self.assertEqual(len(result['rejected']),1)
        self.assertNotIn('secret',json.dumps(self.store.restore()));self.assertEqual(self.store.manifest('another-client')['records'],{})
        self.assertIn('vacancy:hh_1',self.store.manifest(CLIENT)['records'])
    def test_scan_identity_is_immutable_and_filters_preserve_resume_and_location_scope(self):
        first=scan('unique',['hh_1']);self.sync(record('scan',first));self.assertEqual(len(self.sync(record('scan',{**first,'ids':[]}))['rejected']),1)
        self.assertNotEqual(scope_url('https://hh.ru/search/vacancy?resume=one','vacancy_search'),scope_url('https://hh.ru/search/vacancy?resume=two','vacancy_search'))
        self.assertNotEqual(scope_url('https://hh.ru/search/vacancy?area=1','vacancy_search'),scope_url('https://hh.ru/search/vacancy?area=2','vacancy_search'))
    def test_local_comparison_reports_mentions_and_absence_of_evidence_without_api(self):
        self.sync(record('resume',cv()),record('vacancy',job()));result=self.store.compare(CV_ID,'hh_1');skills={r['skill']:r for r in result['items']}
        self.assertTrue(skills['PyTorch']['mentioned_in_cv']);self.assertFalse(skills['CUDA']['mentioned_in_cv']);self.assertIn('API не вызываются',result['note'])
    def test_auth_dashboard_cookie_is_read_only_and_one_time_link_cannot_be_reused(self):
        app=create_app('local-test-token',archive_path=self.path)
        with TestClient(app) as client:
            self.assertEqual(client.get('/').status_code,200);self.assertEqual(client.get('/archive/summary').status_code,401)
            self.assertIn('frame-ancestors',client.get('/').headers['content-security-policy'])
            link=client.post('/archive/open',json={},headers={'X-Resume-Import-Token':'local-test-token'}).json()['url'];code=link.split('connect=')[1]
            self.assertNotIn('local-test-token',link)
            self.assertEqual(client.post('/archive/login',json={'code':code},headers={'Origin':'https://evil.example'}).status_code,403)
            self.assertEqual(client.post('/archive/login',json={'code':code}).status_code,200)
            self.assertEqual(client.get('/archive/summary').status_code,200)
            self.assertEqual(client.post('/archive/sync',json={}).status_code,401)
            self.assertEqual(client.post('/rank',json={}).status_code,401)
            self.assertEqual(client.post('/archive/login',json={'code':code}).status_code,401)
            self.assertEqual(client.post('/archive/compare',json={},headers={'Origin':'https://evil.example'}).status_code,401)
            export=client.get('/archive/export');self.assertEqual(export.status_code,200);self.assertIn('versions',export.json()['tables'])
            self.assertEqual(client.get('/assets/../../.env').status_code,401)

if __name__=='__main__':unittest.main()
