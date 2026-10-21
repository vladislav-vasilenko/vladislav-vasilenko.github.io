from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from src.extension_ranking import rank_vacancies
from src.resume_source import content_hash
from resume_import_server import create_app

NOW=datetime(2026,10,14,12,tzinfo=timezone.utc)
def cv(letter, text):
    r={'id':'file_'+letter*64,'file_hash':letter*64,'source_type':'file','title':text,'quality':'full','checked_at':'2025-01-01T00:00:00Z','reviewed_at':'2026-10-14T10:00:00Z','sections':[{'key':'document','heading':'CV','text':(text+' experience ')*15}]}
    r['content_hash']=content_hash(r);return r

def job(number,text,quality='full'):
    return {'id':'hh_'+str(number),'link':'https://hh.ru/vacancy/'+str(number),'title':text,'company':'Example','description':(text+' responsibilities ')*15,'description_quality':quality}

class FakeBackend:
    calls=[]
    def __init__(self,model):self.model=model;self.dimensions=2;self.usage_tokens=0;self.request_count=0
    def embed_documents(self,texts):
        self.calls.append((self.model,texts));self.usage_tokens+=sum(len(t) for t in texts);self.request_count+=1
        return [[0.,1.] if 'Swift' in t else [1.,0.] for t in texts]

class ExtensionRankingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)
        FakeBackend.calls=[]
        self.ml=cv('a','PyTorch Transformer');self.ios=cv('b','Swift iOS')
    def payload(self,selected=None,model='text-embedding-3-small'):
        return {'resume_id':selected or self.ml['id'],'model':model,'bundle':{'schema_version':2,'primary_id':self.ml['id'],'resumes':[self.ml,self.ios]},'vacancies':[job(1,'PyTorch Transformer'),job(2,'Swift iOS'),job(3,'Snippet','snippet')]}
    def run_rank(self,payload):return rank_vacancies(payload,self.path,backend_factory=FakeBackend,now=NOW)
    def test_selected_resume_changes_ranking_and_reuses_job_vectors(self):
        ml=self.run_rank(self.payload());self.assertEqual(ml['top'][0]['id'],'hh_1')
        ios=self.run_rank(self.payload(self.ios['id']));self.assertEqual(ios['top'][0]['id'],'hh_2');self.assertEqual(ios['resume_id'],self.ios['id'])
        self.assertEqual(ml['excluded'],1);self.assertEqual(ml['ranked_count'],2)
        self.assertEqual(sum('Swift iOS responsibilities' in t for _,texts in FakeBackend.calls for t in texts),1)
        repeat=self.run_rank(self.payload(self.ios['id']));self.assertEqual(repeat['api_requests'],0)
    def test_models_have_separate_caches(self):
        self.run_rank(self.payload());large=self.run_rank(self.payload(model='text-embedding-3-large'));self.assertGreater(large['api_requests'],0)
    def test_primary_freshness_quality_version_and_unselected_cv_are_enforced(self):
        for changes in [{'quality':'needs_review'},{'content_hash':'edited'}]:
            p=self.payload();p['bundle']['resumes']=[{**self.ml,**changes},self.ios]
            with self.assertRaises(ValueError):self.run_rank(p)
        p=self.payload(self.ios['id']);self.run_rank(p)
        self.assertTrue(all(not any('PyTorch Transformer experience' in t for t in texts) for _,texts in FakeBackend.calls))
    def test_rank_endpoint_uses_same_token_and_does_not_return_credentials(self):
        def ranker(payload,path):return rank_vacancies(payload,self.path,backend_factory=FakeBackend,now=NOW)
        token='test-local-pairing-token'
        with TestClient(create_app(token,ranker=ranker)) as client:
            self.assertEqual(client.post('/rank',json=self.payload()).status_code,401)
            response=client.post('/rank',json=self.payload(),headers={'X-Resume-Import-Token':token})
            self.assertEqual(response.status_code,200);self.assertNotIn(token,response.text)
            self.assertEqual(response.json()['resume_id'],self.ml['id'])

if __name__=='__main__':unittest.main()

class OpenAIRequestContractTests(unittest.TestCase):
    def test_server_uses_environment_key_and_requested_embedding_model(self):
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        from src.extension_ranking import OpenAIBackend
        vector=[1.0]+[0.0]*1535
        response=SimpleNamespace(data=[SimpleNamespace(index=0,embedding=vector)],usage=SimpleNamespace(total_tokens=5))
        client=MagicMock();client.embeddings.create.return_value=response
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fixture-server-key'}),patch('openai.OpenAI',return_value=client) as constructor:
            backend=OpenAIBackend('text-embedding-3-small');rows=backend.embed_documents(['CV fixture'])
            self.assertEqual(constructor.call_args.kwargs['api_key'],'fixture-server-key')
            self.assertEqual(constructor.call_args.kwargs['base_url'],'https://api.openai.com/v1')
            self.assertEqual(client.embeddings.create.call_args.kwargs,{'model':'text-embedding-3-small','input':['CV fixture'],'encoding_format':'float'})
            self.assertEqual(len(rows[0]),1536);self.assertEqual(backend.usage_tokens,5)
