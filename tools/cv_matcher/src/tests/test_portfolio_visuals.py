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
        self.assertEqual(value['market']['points'],[{'x':.65,'y':.41,'category':'diffusion','count':1}])
        self.assertNotIn('data_as_of',value['market'])
        dated=[{**rows[0],'first_seen':'2026-11-04T15:59:31+00:00'},{**rows[0],'first_seen':'2026-10-01T00:00:00+00:00'}]
        with patch.object(visuals,'snapshot',return_value={**snapshot,'rows':dated}):self.assertEqual(visuals.project(self.archive,cfg)['market']['data_as_of'],'2026-11-04')
        self.assertIsNone(visuals.project(self.archive,{'enabled':False}))

    def test_experience_sample_adds_applied_directions_only(self):
        self.assertEqual(visuals.options({'enabled':True,'market':True,'sample':'experience'},preview=True)['sample'],'experience')
        with self.assertRaises(ValueError):visuals.options({'enabled':True,'sample':'unknown'},preview=True)
        for category in ('research','rag','ai_automation','vision','nlp'):self.assertTrue(visuals.in_sample(category,'experience'))
        for category in ('classical','other','backend','qa'):self.assertFalse(visuals.in_sample(category,'experience'))
        self.assertFalse(visuals.in_sample('rag','research'));self.assertTrue(visuals.in_sample('qa','all'))
