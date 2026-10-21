"""Existing backend seam for a future MCP adapter; isolated DB and fake transports.

This is not a live Chrome/MCP/Giga test. It stops at human approval.
"""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from resume_import_server import create_app
from src import discovery
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src.cover_letter import source_passages
from src.extension_ranking import rank_vacancies
from src.hh_auto_sync import config as sync_config
from src.resume_source import content_hash
from src.skill_analysis import analyze, context
from src.tests.test_archive import cv, job, record
from src.tests.test_extension_ranking import FakeBackend
from src.tests.test_recruiter import Operator
from src.workflow_bot import WorkflowBot


class ArchitectureFlowTests(unittest.TestCase):
    def test_discovery_analysis_crm_browser_queue_and_owner_approval_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'state.sqlite3'
            store=ApplicationStore(path);archive=ArchiveStore(path)
            sync_config(store,{'enabled':False})
            at=datetime.now(timezone.utc).isoformat();goal='Generative models'
            resume=cv(text='Обучал Transformer на PyTorch. '*15,at=at)
            resume['content_hash']=content_hash(resume)
            vacancy=job(text='Разработка моделей на PyTorch. '*15,at=at)
            vacancy.update(archived=False,availability_checked_at=at)
            archive.sync({'client_id':'architecture-test','records':[record('resume',resume),record('profile',{'primary_id':resume['id'],'goal':goal},'profile')]})
            discovery.config(store,{**discovery.DEFAULT,'allow_api':True})
            run=discovery.start(store,archive,'architecture-flow')
            read_command=store.next_command('fixture-collector',kinds=['discover','collect'])['command']
            self.assertEqual(read_command['kind'],'discover')
            # The browser result is substituted, not a real Chrome crawl.
            archive.sync({'client_id':'architecture-test','records':[record('vacancy',vacancy)]})
            store.finish_command(read_command['id'],'fixture-collector',{'state':'complete','ids':[vacancy['id']]})
            ranked=[]
            def ranker(packet,cache,**options):
                result=rank_vacancies(packet,root/'vectors',backend_factory=FakeBackend,archive=archive)
                ranked.append(result);return result
            completed=discovery.advance(store,archive,run['id'],root,ranker=ranker)
            self.assertEqual(completed['state'],'complete',completed['result'])
            self.assertEqual(ranked[0]['all'][0]['id'],vacancy['id'])
            sources=context(archive,resume['id'],vacancy['id'],goal)
            jd=source_passages(sources['jd_text'],'J');rs=source_passages(sources['cv_text'],'R')
            raw={'requirements':[{'requirement':'Практика PyTorch','dimension':'engineering','importance':'must','status':'confirmed','job_passage_id':next(iter(jd)),'job_quote':next(iter(jd.values()))[:80],'resume_passage_ids':[next(iter(rs))],'explanation':'Практика указана в CV.','action':'Подготовить пример.'}],'goal_alignment':'Соответствует цели.','recommendation':'apply','recommendation_reason':'Есть подтверждение в тексте.','questions':[],'limitations':['Только текстовые источники.']}
            model=Mock();model.responses.create.return_value=SimpleNamespace(status='completed',output_text=json.dumps(raw),usage=SimpleNamespace(input_tokens=100,output_tokens=50))
            report=analyze(archive,resume['id'],vacancy['id'],goal,client_factory=lambda:model)
            self.assertEqual(model.responses.create.call_count,1)
            self.assertEqual(report['vacancy_id'],vacancy['id'])
            self.assertEqual(report['resume_id'],resume['id'])
            token='architecture-fixture';headers={'X-Resume-Import-Token':token}
            with TestClient(create_app(token,archive_path=path)) as client:
                def action(op,**values):
                    response=client.post('/archive/workflow',json={'op':op,**values},headers=headers)
                    self.assertEqual(response.status_code,200,response.text);return response.json()
                app=action('make',resume_id=resume['id'],vacancy_id=vacancy['id'],goal=goal)
                app_id=app['id'];action('draft',app_id=app_id,text='Обучал Transformer на PyTorch.',revision=0)
                command_id=action('prepare',app_id=app_id)['command_id']
                command=action('next',worker_id='fixture-browser')['command']
                self.assertEqual(command['id'],command_id)
                snapshot={'state':'form','selected_resume_id':resume['id'],'fingerprint':'fixture-form','submit_label':'Отправить','fields':[{'id':'letter','purpose':'cover','label':'Сопроводительное письмо','type':'textarea','required':False,'value':'Обучал Transformer на PyTorch.','options':[]}]}
                action('prepared',command_id=command_id,worker_id='fixture-browser',snapshot=snapshot)
                action('result',command_id=command_id,worker_id='fixture-browser',result={'state':'complete'})
                current=client.get('/archive/workflow',params={'app_id':app_id},headers=headers).json()
                self.assertEqual(current['workflow']['state'],'needs_approval')
                self.assertEqual(current['context']['resume_hash'],resume['content_hash'])
                preview=action('intent',app_id=app_id)
                self.assertTrue(preview['intent_hash'])
                self.assertIsNone(action('next',worker_id='fixture-browser')['command'])
                # A website session is not allowed to claim a browser command.
                client.post('/archive/login',json={},headers=headers)
                response=client.post('/archive/workflow',json={'op':'next','worker_id':'untrusted-ui'},headers={'Origin':'http://127.0.0.1:8788'})
                self.assertEqual(response.status_code,403)
            operator=Operator();bot=WorkflowBot(store,operator,42)
            asyncio.run(bot.enqueue_event_notifications())
            self.assertTrue(operator.messages)
            with store.connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM browser_commands WHERE kind='execute'").fetchone()[0],0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM skill_analyses').fetchone()[0],1)
                self.assertTrue(db.execute("SELECT COUNT(*) FROM workflow_delivery WHERE state='sent'").fetchone()[0])
