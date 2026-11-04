import json
import unittest
from unittest.mock import patch
from src.tests import test_portfolio_publication as fixtures
from src import portfolio_visuals as visuals

class PublicProjection(unittest.TestCase):
    setUp = fixtures.PublicationTests.setUp
    def test_public_projection_is_aggregated_and_rejects_private_analytics(self):
        for key in ('crm','competencies'):
            with self.assertRaises(ValueError):visuals.options({'enabled':True,'reviewed':True,key:True})
        with self.assertRaises(ValueError):visuals.options({'enabled':True})
        cfg=visuals.options({'enabled':True,'market':True,'sample':'research'},preview=True)
        rows=[{'id':'SECRET_JOB','title':'PRIVATE_TITLE','company':'PRIVATE_EMPLOYER','category':'diffusion','quality':'full','similarity':.6543,'alignment':.4123,'ranking_stale':False,'stage':'rejected','application_id':'SECRET_APP','fit':98},
              {'id':'OTHER_JOB','category':'backend','quality':'snippet','similarity':.5,'alignment':.3,'ranking_stale':False}]
        snapshot={'rows':rows,'taxonomy':[{'id':'diffusion','label':'Diffusion'}],'skills':{'learning_evidence':['PRIVATE_QUOTE'],'analyses':20,'dimensions':[]}}
        with patch.object(visuals,'snapshot',return_value=snapshot):value=visuals.project(self.archive,cfg)
        encoded=json.dumps(value)
        for secret in ('SECRET_JOB','PRIVATE_TITLE','PRIVATE_EMPLOYER','SECRET_APP','PRIVATE_QUOTE','rejected','application_id','resume_id','sqlite','fit'):
            self.assertNotIn(secret,encoded)
        self.assertEqual(value['market']['observed'],1)
        self.assertEqual(value['market']['points'],[{'x':.65,'y':.41,'category':'diffusion','market':'other','count':1}])
        self.assertEqual(value['market']['markets'],[{'id':'other','categories':[{'id':'diffusion','total':1,'full':1,'partial':0}]}])
        self.assertNotIn('data_as_of',value['market'])
        dated=[{**rows[0],'first_seen':'2026-11-04T15:59:31+00:00'},{**rows[0],'first_seen':'2026-10-01T00:00:00+00:00'}]
        with patch.object(visuals,'snapshot',return_value={**snapshot,'rows':dated}):self.assertEqual(visuals.project(self.archive,cfg)['market']['data_as_of'],'2026-11-04')
        self.assertIsNone(visuals.project(self.archive,{'enabled':False}))

    def test_examples_are_short_opt_in_and_keep_private_rows_out(self):
        description='О компании Acme Labs.\nОбязанности:\n- Строить RAG-сервисы на Python для Acme Labs и писать на hr@acme.example или https://acme.example/jobs\n- Измерять качество ответов и задержку в продакшене\n'+'длинный текст '*80
        jobs={f'j{i}':{'description':description} for i in range(30)}
        base=dict(company='Acme Labs',category='rag',tags=['rag','research','unknown'],quality='full',availability='active',application_id=None,stage='none',manual_application={'marked':False},similarity=.91,alignment=.5,ranking_stale=False,first_seen='2026-11-04')
        rows=[{**base,'id':key,'title':f'Acme Labs — ML Engineer {key}'} for key in jobs]
        rows+=[{**base,'id':'applied','title':'APPLIED','application_id':'x'},{**base,'id':'draft','title':'DRAFT','stage':'draft'},{**base,'id':'marked','title':'MARKED','manual_application':{'marked':True}},{**base,'id':'closed','title':'CLOSED','availability':'closed'},{**base,'id':'snippet','title':'SNIPPET','quality':'snippet'},{**base,'id':'sales','title':'SALES Account Executive'}]
        class DB:
            def __enter__(s):return s
            def __exit__(s,*a):return False
            def execute(s,sql,ids):return [{'id':key,'payload':json.dumps(jobs[key])} for key in ids if key in jobs]
        with patch.object(self.archive,'connect',return_value=DB()):
            cards=visuals.examples_for(self.archive,rows,lambda r:r['category'],{'research':'DL Research','rag':'RAG'})['rag']
        self.assertEqual(len(cards),25)
        encoded=json.dumps(cards,ensure_ascii=False)
        for secret in ('hr@','https:','acme.example','APPLIED','DRAFT','MARKED','CLOSED','SNIPPET','SALES','0.91','.91','similarity'):self.assertNotIn(secret,encoded)
        self.assertEqual(set(cards[0]),{'title','company','summary','market','keywords'});self.assertEqual((cards[0]['market'],cards[0]['company']),('other','Acme Labs'))
        self.assertTrue(cards[0]['title'].startswith('Acme Labs — ML Engineer'))
        self.assertIn('Строить RAG-сервисы',cards[0]['summary']);self.assertLessEqual(len(cards[0]['summary']),141)
        self.assertEqual(cards[0]['keywords'],['DL Research'])
        self.assertFalse(visuals.options({'enabled':True,'market':True},preview=True)['examples'])

    def test_employer_counts_keep_each_markets_largest_and_no_scores(self):
        from collections import Counter
        cells={('A','us','rag'):Counter(full=3,partial=1),('A','ru','rag'):Counter(full=1),('B','ru','rag'):Counter(full=2),('','us','rag'):Counter(full=9)}
        with patch.object(visuals,'EMPLOYERS_PER_MARKET',1):value=visuals.employer_counts(cells)
        self.assertEqual(value,[{'name':'A','counts':[['us','rag',3,1]]},{'name':'B','counts':[['ru','rag',2,0]]}])

    def test_market_comes_from_location_then_employer_region(self):
        from src.market_regions import market_of
        for location,market in (('San Francisco, CA','us'),('Toronto, ON','canada'),('London, UK','uk'),('Berlin, Germany','europe'),('São Paulo, Brazil','south_america'),('Tokyo, Japan','japan'),('Beijing, China','china'),('Sydney, Australia','au_nz'),('Москва','ru'),('Singapore','other'),('Remote','other')):
            self.assertEqual(market_of({'location':location,'company_region':'us_uk_eu'}),market,location)
        self.assertEqual(market_of({'location':'','company_region':'rus'}),'ru')
        self.assertEqual(market_of({'location':None,'company_region':'us_uk_eu'}),'other')

    def test_experience_sample_adds_applied_directions_only(self):
        self.assertEqual(visuals.options({'enabled':True,'market':True,'sample':'experience'},preview=True)['sample'],'experience')
        with self.assertRaises(ValueError):visuals.options({'enabled':True,'sample':'unknown'},preview=True)
        for category in ('research','rag','ai_automation','vision','nlp'):self.assertTrue(visuals.in_sample(category,'experience'))
        for category in ('classical','other','backend','qa'):self.assertFalse(visuals.in_sample(category,'experience'))
        self.assertFalse(visuals.in_sample('rag','research'));self.assertTrue(visuals.in_sample('qa','all'))
