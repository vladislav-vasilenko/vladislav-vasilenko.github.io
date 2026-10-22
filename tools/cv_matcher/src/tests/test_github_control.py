import tempfile
import unittest
from pathlib import Path
from src.archive_store import ArchiveStore
from src import github_collection_control as control
from src.github_collection_api import REPOSITORY

class Fake:
    def __init__(self): self.commands=[]; self.active=False
    def request(self, endpoint):
        if '/jobs?' in endpoint:return {'jobs':[{'name':'scrape','status':'completed','conclusion':'failure','steps':[{'name':'Run scraper','conclusion':'failure'}]}]}
        row={'id':123,'run_number':1,'status':'in_progress' if self.active else 'completed','head_branch':'main','path':'.github/workflows/daily-scrape.yml','head_repository':{'full_name':REPOSITORY}}
        return {'workflow_runs':[row]} if 'workflows/' in endpoint else row
    def mutate(self, suffix, body):self.commands.append((suffix,body))

class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.archive=ArchiveStore(Path(self.tmp.name)/'state.sqlite');self.fake=Fake()
    def test_settings_validate_and_dispatch_fixed_main_without_models(self):
        for data in ({'sources':['unknown'],'limit':5},{'sources':['yandex'],'limit':0},{'sources':[],'limit':20}):
            with self.assertRaises(ValueError): control.configure(self.archive,data)
        control.configure(self.archive,{'sources':['yandex'],'limit':5})
        result=control.dispatch(self.archive,self.fake);self.assertEqual(result['dispatch_status'],'accepted')
        suffix,body=self.fake.commands[0];self.assertEqual(suffix,'workflows/daily-scrape.yml/dispatches');self.assertEqual(body,{'ref':'main','inputs':{'sources':'yandex','limit':'5'}})
        with self.assertRaises(ValueError):control.dispatch(self.archive,self.fake)
        self.assertEqual(len(self.fake.commands),1)
    def test_running_blocks_duplicate_and_cancel_is_bound_to_workflow(self):
        self.fake.active=True
        with self.assertRaises(ValueError):control.dispatch(self.archive,self.fake)
        self.assertTrue(control.cancel(123,self.fake)['accepted'])
        self.assertEqual(self.fake.commands[0][0],'runs/123/cancel')
        self.fake.active=False
        with self.assertRaises(ValueError):control.cancel(123,self.fake)
        with self.assertRaises(ValueError):control.run_detail('../123',self.fake)
    def test_adapter_catalog_distinguishes_ci_and_local_and_exposes_steps(self):
        result=control.overview(self.archive,self.fake)
        self.assertTrue(next(a for a in result['adapters'] if a['id']=='google')['github_actions'])
        self.assertFalse(next(a for a in result['adapters'] if a['id']=='hh')['github_actions'])
        self.assertEqual(control.run_detail(123,self.fake)['jobs'][0]['steps'][0]['conclusion'],'failure')
