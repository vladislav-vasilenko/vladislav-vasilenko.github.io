import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from fastapi.testclient import TestClient
from src.archive_store import ArchiveStore,digest
from src.analysis_store import document_text,text_hash
from src.resume_source import CachedEmbeddings,content_hash
from src.extension_ranking import rank_vacancies,chunks
from src.tests.test_extension_ranking import FakeBackend,cv,job,NOW
from resume_import_server import create_app

class AnalysisStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=ArchiveStore(self.root/'state.sqlite3');self.cache=self.root/'legacy';FakeBackend.calls=[]
        self.cv=cv('a','PyTorch Transformer');self.job=job(1,'PyTorch Transformer');self.job['collected_at']='2026-10-14T10:00:00Z'
        self.payload={'resume_id':self.cv['id'],'bundle':{'schema_version':2,'resumes':[self.cv]},'vacancies':[self.job],'goal':'Generative ML'}
    def rank(self,**kwargs):return rank_vacancies(self.payload,self.cache,backend_factory=FakeBackend,now=kwargs.pop('now',NOW),**kwargs)
    def test_merged_ranking_of_2000_jobs_syncs_without_truncation_and_preserves_progress_metadata(self):
        result=self.rank(archive=self.store);base=result['all'][0]
        result.update(all=[{**base,'id':'hh_'+str(i),'link':'https://hh.ru/vacancy/'+str(i)} for i in range(2000)],ranked_count=2000,requested_count=2000,processed_count=2000,batches_completed=10,partial=False)
        data={k:result[k] for k in ('generated_at','resume_id','resume_hash','resume_title','model','goal','all','ranked_count','requested_count','processed_count','batches_completed','partial')}
        other=ArchiveStore(self.root/'merged.sqlite3')
        report=other.sync({'client_id':'browser-fixture','records':[{'kind':'ranking','id':digest(data),'data':data,'digest':digest(data)}]})
        self.assertEqual(report['rejected'],[]);saved=other.ranking_history()['items'][0]
        self.assertEqual(len(saved['all']),2000);self.assertEqual(saved['processed_count'],2000)
        oversized={**data,'all':data['all']+[base]}
        with self.assertRaisesRegex(ValueError,'2000'):other.save_ranking(oversized)
    def test_new_vectors_live_only_in_sqlite_and_survive_restart_without_api(self):
        result=self.rank(archive=self.store);self.assertGreater(result['api_requests'],0)
        self.assertFalse(list(self.cache.glob('*.json')))
        restarted=ArchiveStore(self.store.path);again=self.rank(archive=restarted,now=NOW+timedelta(seconds=1));self.assertEqual(again['api_requests'],0)
        self.assertEqual(again['all'],result['all']);self.assertEqual(len(restarted.ranking_history()['items']),2)
        detail=restarted.detail('vacancy','hh_1',self.cv['id'],self.payload['goal']);self.assertEqual(detail['embedding']['status'],'generated');self.assertIsNotNone(detail['ranking'])
    def test_legacy_file_cache_is_adopted_without_another_backend_request(self):
        self.rank();self.assertTrue(list(self.cache.glob('*.json')))
        result=self.rank(archive=self.store);self.assertEqual(result['api_requests'],0)
        with self.store.connect() as db:self.assertGreater(db.execute('SELECT COUNT(*) FROM embedding_vectors').fetchone()[0],0)
    def test_changed_text_invalidates_vector_status_and_score_but_recheck_does_not(self):
        self.rank(archive=self.store)
        changed={**self.job,'collected_at':'2026-10-14T11:00:00Z'}
        with self.store.connect() as db:self.store._entity(db,'vacancy','hh_1',changed,'2026-10-14T12:00:00Z')
        self.assertEqual(self.store.detail('vacancy','hh_1',self.cv['id'],'Generative ML')['embedding']['status'],'generated')
        changed['description']+=' CUDA distributed training'
        with self.store.connect() as db:self.store._entity(db,'vacancy','hh_1',changed,'2026-10-14T13:00:00Z')
        state=self.store.detail('vacancy','hh_1',self.cv['id'],'Generative ML');self.assertEqual(state['embedding']['status'],'stale');self.assertIsNone(state['ranking']);self.assertTrue(state['ranking_stale'])
    def test_model_goal_and_cv_version_never_share_wrong_scores(self):
        self.rank(archive=self.store)
        self.assertIsNone(self.store.detail('vacancy','hh_1',self.cv['id'],'Different goal')['ranking'])
        self.assertEqual(self.store.detail('vacancy','hh_1',model='text-embedding-3-large')['embedding']['status'],'not_generated')
        changed=json.loads(json.dumps(self.cv));changed['sections'][0]['text']+=' DDP';changed['content_hash']=content_hash(changed)
        with self.store.connect() as db:self.store._entity(db,'resume',changed['id'],changed,'2026-10-15T12:00:00Z')
        self.assertIsNone(self.store.detail('vacancy','hh_1',self.cv['id'],'Generative ML')['ranking'])
    def test_partial_chunks_and_invalid_vectors_do_not_claim_generated(self):
        data={**self.job,'description':('PyTorch research engineering '*180)}
        with self.store.connect() as db:self.store._entity(db,'vacancy',data['id'],data,'2026-10-14T12:00:00Z')
        backend=FakeBackend('text-embedding-3-small');cache=CachedEmbeddings(backend,self.cache,'extension-ranking-v1',vector_store=self.store)
        parts=chunks(document_text('vacancy',data));cache.embed_documents(parts[:1]);self.store.bind_document('vacancy',data['id'],document_text('vacancy',data),cache,parts)
        state=self.store.detail('vacancy',data['id']);self.assertEqual(state['embedding']['status'],'partial');self.assertEqual(state['embedding']['chunks_ready'],1)
        for vector in ([float('nan'),1],[0,0],[1],[]):
            with self.assertRaises(ValueError):self.store.save_vector('invalid',cache.namespace,'x',vector)
    def test_browser_ranking_sync_is_idempotent_and_backup_contains_vectors(self):
        result=self.rank(archive=self.store);data={k:result[k] for k in ('generated_at','resume_id','resume_hash','resume_title','model','goal','all')}
        envelope={'kind':'ranking','id':digest(data),'data':data,'digest':digest(data)}
        other=ArchiveStore(self.root/'other.sqlite3');request={'client_id':'browser-fixture','records':[envelope]}
        self.assertEqual(len(other.sync(request)['accepted']),1);other.sync(request);self.assertEqual(len(other.ranking_history()['items']),1)
        with TestClient(create_app('test-token',archive_path=self.store.path)) as client:
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'test-token'})
            response=client.get('/archive/export');self.assertEqual(response.status_code,200)
            backup=response.json();self.assertTrue(backup['tables']['embedding_vectors']);self.assertEqual(backup['vector_encoding'],'base64-float32-le')
            self.assertEqual(client.get('/archive/rankings').status_code,200)
    def test_initial_snapshot_does_not_fill_changes_feed_but_new_jobs_do(self):
        from src.tests.test_archive import record
        self.store.sync({'client_id':'browser-fixture','records':[record('vacancy',self.job),{'kind':'profile','id':'profile','data':{},'digest':digest({})}]})
        self.assertEqual(self.store.timeline()['items'],[])
        self.store.sync({'client_id':'browser-fixture','records':[record('vacancy',job(2,'New ML role'))]})
        self.assertEqual(len(self.store.timeline()['items']),1)
    def test_automatic_legacy_index_uses_exact_model_namespace_and_never_calls_api(self):
        data={**self.job,'description':'PyTorch research '*20}
        with self.store.connect() as db:self.store._entity(db,'vacancy',data['id'],data,'2026-10-14T12:00:00Z')
        namespace=json.dumps({'class':'src.extension_ranking.OpenAIBackend','model':'text-embedding-3-small','endpoint':'https://api.openai.com/v1','dimensions':1536,'version':'extension-ranking-v1'},sort_keys=True)
        cache=CachedEmbeddings.__new__(CachedEmbeddings);cache.namespace=namespace;parts=chunks(document_text('vacancy',data));self.cache.mkdir()
        for key in cache.keys(parts):(self.cache/(key+'.json')).write_text(json.dumps([1.]+[0.]*1535))
        self.store.index_legacy_embeddings(self.cache);self.assertEqual(self.store.detail('vacancy',data['id'])['embedding']['status'],'generated')
        self.assertEqual(FakeBackend.calls,[])
    def test_filter_and_cached_ranking_sort_before_pagination(self):
        self.payload['vacancies']=[self.job,job(2,'Swift iOS')];self.rank(archive=self.store)
        rows=self.store.entities('vacancy',status='embedding_generated',resume_id=self.cv['id'],goal='Generative ML',limit=1)
        self.assertEqual(rows['total'],2);self.assertEqual(rows['items'][0]['id'],'hh_1')
        with self.store.connect() as db:
            noisy={**job(3,'Java Developer'),'origin_query':'Kandinsky'};self.store._entity(db,'vacancy',noisy['id'],noisy,'2026-10-14T12:00:00Z')
        self.assertEqual(self.store.entities('vacancy',q='Kandinsky')['total'],0)
    def test_company_scope_returns_existing_pair_scores_without_constructing_embedding_backend(self):
        self.job['company']='Сбер. Data Science';other={**job(2,'Swift iOS'),'company':'Ozon'};self.payload['vacancies']=[self.job,other];self.rank(archive=self.store)
        self.payload['company_filter']='sber'
        def forbidden(model):raise AssertionError('Cached comparison must not initialize or call embedding backend')
        result=rank_vacancies(self.payload,self.cache,backend_factory=forbidden,archive=self.store,now=NOW+timedelta(seconds=1))
        self.assertEqual([row['id'] for row in result['all']],['hh_1']);self.assertEqual(result['api_requests'],0);self.assertEqual(result['cache_reused'],1);self.assertEqual(result['new_compared'],0)
    def test_only_new_pairs_are_compared_and_only_missing_text_is_embedded(self):
        self.rank(archive=self.store);FakeBackend.calls=[]
        self.payload['vacancies'].append(job(2,'Previously unseen CUDA systems'))
        result=self.rank(archive=self.store,now=NOW+timedelta(seconds=1));self.assertEqual(result['cache_reused'],1);self.assertEqual(result['new_compared'],1)
        self.assertTrue(all('Previously unseen' in text for _,texts in FakeBackend.calls for text in texts))
    def test_changed_job_cannot_reuse_old_pair_even_if_snapshot_date_is_unchanged(self):
        self.rank(archive=self.store);self.payload['vacancies'][0]['description']+=' CUDA kernel optimization'
        result=self.rank(archive=self.store,now=NOW+timedelta(seconds=1));self.assertEqual(result['cache_reused'],0);self.assertEqual(result['new_compared'],1)

if __name__=='__main__':unittest.main()
