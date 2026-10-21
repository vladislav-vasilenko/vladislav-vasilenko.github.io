import unittest
from fastapi.testclient import TestClient
from src import resume_intake
from src.tests import test_workflow as fixtures


class ResumeIntakeTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WorkflowTests('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.store=self.f.store

    def test_any_hh_resume_link_is_normalized_without_requiring_own_catalog(self):
        friend='b'*38
        for url in ['https://hh.ru/resume/'+friend+'?print=true', 'https://spb.hh.ru/resume/'+friend.upper()+'/?hhtmFrom=profile']:
            value=resume_intake.start(self.store,url)
            self.assertEqual(value['resume_id'],friend);self.assertEqual(value['url'],'https://hh.ru/resume/'+friend)
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_commands WHERE kind='resume_import'").fetchone()[0],1)
        # Dedicated capability: old HH/collection workers cannot steal this import.
        self.assertIsNone(self.store.next_command('legacy-worker')['command'])
        command=self.store.next_command('resume-reader',kinds=['resume_import'])['command']
        self.assertEqual(command['payload']['resume_id'],friend)
        self.assertFalse(self.store.browser_status()['auto_sync']['worker_ready'])

    def test_resume_url_rejects_other_hosts_credentials_search_and_non_https(self):
        id='b'*38
        for value in ['https://evilhh.ru/resume/'+id,'https://hh.ru.evil.test/resume/'+id,'http://hh.ru/resume/'+id,'https://user:password@hh.ru/resume/'+id,'https://hh.ru:1234/resume/'+id,'https://hh.ru/search/vacancy?resume='+id,'https://hh.ru/resume/edit/'+id,'https://hh.ru/resume/abcd']:
            with self.assertRaises(ValueError,msg=value):resume_intake.start(self.store,value)

    def test_import_endpoint_requires_local_access_and_status_survives_reload(self):
        from resume_import_server import create_app
        with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
            data={'op':'resume_import','url':'https://hh.ru/resume/'+'b'*38}
            self.assertEqual(client.post('/archive/workflow',json=data).status_code,401)
            headers={'X-Resume-Import-Token':'fixture'}
            result=client.post('/archive/workflow',json=data,headers=headers);self.assertEqual(result.status_code,200)
            command=self.store.next_command('resume-reader',kinds=['resume_import'])['command']
            self.store.finish_command(command['id'],'resume-reader',{'state':'needs_input','note':'HH закрыл доступ к резюме'})
            read=client.post('/archive/workflow',json={'op':'resume_import_status','command_id':result.json()['command_id']},headers=headers).json()
            self.assertEqual(read['state'],'needs_input');self.assertEqual(read['api_requests'],0)
            self.assertEqual(self.store.get(self.f.id)['status'],'queued')
