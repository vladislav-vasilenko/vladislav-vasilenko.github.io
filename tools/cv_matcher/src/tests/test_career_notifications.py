"""Temporary SQLite and fake delivery only; never sends Telegram or calls a model."""
import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from src.tests import test_workflow as fixtures
from src.tests.test_recruiter import Operator
from src.tests.test_archive import job, record
from src.application_workflow import packed, hashed
from src.analysis_store import text_hash, document_text
from src.career_application import CareerApplication
from src.career_notifications import config, plan_reviews, prepare_delivery, review_payload
from src.application_attention import items
from src.workflow_bot import WorkflowBot
from resume_import_server import create_app

class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.f=fixtures.WorkflowTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.store=self.f.store; self.service=CareerApplication(self.store)
        self.now=datetime.now(timezone.utc); self.slot=self.now.replace(minute=0,second=0,microsecond=0)

    def state(self, state):
        with self.store.connect() as db: db.execute('UPDATE application_workflow SET state=? WHERE app_id=?',(state,self.f.id))

    def key(self): return 'review-digest:'+self.slot.isoformat()

    async def test_shared_attention_includes_filled_forms_but_never_done_or_sent_stale_state(self):
        for state in ('needs_input','needs_approval','uncertain','fields_filled'):
            self.state(state); row=items(self.store)[0]
            self.assertTrue(row['needs_attention']); self.assertTrue(row['reminder_due'])
        self.assertIn('сайте компании', row['next'])
        self.store.hh_sync({'source_url':self.f.jd['link'],'records':[{'vacancy_id':self.f.jd['id'],'status':'submitted'}]})
        self.assertFalse(items(self.store)[0]['needs_attention']); self.assertIsNone(review_payload(self.store))
        self.store.set_crm(self.f.id,'offer'); self.assertFalse(items(self.store)[0]['reminder_due'])

    async def test_one_bounded_digest_per_slot_restart_and_second_slot(self):
        self.state('fields_filled'); plan_reviews(self.service,self.slot,self.now)
        plan_reviews(CareerApplication(self.store),self.slot,self.now)
        with self.store.connect() as db:
            rows=db.execute("SELECT key,payload FROM workflow_delivery WHERE key LIKE 'review-digest:%'").fetchall()
        self.assertEqual(len(rows),1); self.assertIn('Проверить перенесённые',json.loads(rows[0]['payload'])['text'])
        self.assertIn(self.f.id, str(json.loads(rows[0]['payload'])['keyboard']))
        plan_reviews(self.service,self.slot+timedelta(hours=9),self.now+timedelta(hours=9))
        with self.store.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM workflow_delivery WHERE key LIKE 'review-digest:%'").fetchone()[0],2)

    async def test_delivery_rechecks_completed_deferred_and_expired_tasks(self):
        plan_reviews(self.service,self.slot,self.now)
        self.store.set_crm(self.f.id,'preparing',follow_up_at=(self.now+timedelta(days=1)).isoformat())
        self.assertFalse(prepare_delivery(self.service,self.key(),self.now))
        self.assertIsNone(review_payload(self.store,now=self.now))
        self.store.set_crm(self.f.id,'preparing',clear_follow_up=True)
        next_slot=self.slot+timedelta(hours=1); plan_reviews(self.service,next_slot,self.now)
        self.assertFalse(prepare_delivery(self.service,'review-digest:'+next_slot.isoformat(),next_slot+timedelta(hours=5)))
        self.assertEqual(self.store.deliveries(),[])

    async def test_pending_payload_updates_before_send_and_uncertain_never_retries(self):
        plan_reviews(self.service,self.slot,self.now); self.state('fields_filled')
        self.assertTrue(prepare_delivery(self.service,self.key(),self.now))
        with self.store.connect() as db:payload=json.loads(db.execute('SELECT payload FROM workflow_delivery WHERE key=?',(self.key(),)).fetchone()[0])
        self.assertIn('перенесённые поля',payload['text'])
        claim=self.store.claim_delivery_send(self.key()); self.store.finish_delivery(self.key(),claim['lease_token'],error=True)
        op=Operator(); await WorkflowBot(self.store,op,42).flush_deliveries(); self.assertEqual(op.messages,[])

    async def test_tasks_mode_never_starts_scheduled_search_but_manual_search_survives(self):
        self.assertEqual(config(self.store)['mode'],'tasks')
        at=self.now.astimezone(self.service.zone).replace(hour=10,minute=30)
        with patch.object(self.service,'begin_digest',new_callable=AsyncMock) as begin, patch.object(self.service,'finish_digest',new_callable=AsyncMock),patch.object(self.service,'plan_reminders',new_callable=AsyncMock):
            await self.service.tick(at); begin.assert_not_called()
        self.assertIsNone(self.store.setting('pending_digest'))
        self.f.archive.sync({'client_id':'notify-test','records':[record('profile',{'primary_id':self.f.cv['id'],'goal':'Generative models'},'profile')]})
        await self.service.search('manual-still-works'); self.assertTrue(self.store.setting('pending_digest'))

    async def test_empty_queue_quiet_and_config_validated_authenticated(self):
        self.store.set_crm(self.f.id,'offer'); plan_reviews(self.service,self.slot,self.now)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM workflow_delivery').fetchone()[0],0)
        for value in ({'mode':'bad'}, {'mode':'off','token':'secret'}, {'mode':[]}, None):
            if value is None:continue
            with self.assertRaises(ValueError):config(self.store,value)
        with TestClient(create_app('fixture',archive_path=self.store.path)) as client:
            body={'op':'notification_config_save','config':{'mode':'off'}}
            self.assertEqual(client.post('/archive/workflow',json=body).status_code,401)
            client.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'})
            self.assertEqual(client.post('/archive/workflow',json=body,headers={'Origin':'https://evil.test'}).status_code,401)
            result=client.post('/archive/workflow',json=body,headers={'Origin':'http://127.0.0.1:8788'})
            self.assertEqual(result.status_code,200);self.assertEqual(result.json()['mode'],'off')
            self.assertEqual(client.get('/archive/journey').json()['notifications']['mode'],'off')

    async def test_candidates_exclude_existing_preparation_and_both_day_key_formats(self):
        fresh=job('hh_2',at=self.now.isoformat(),locations=['London'])
        self.f.archive.sync({'client_id':'notify-test','records':[record('profile',{'primary_id':self.f.cv['id'],'goal':'Generative models'},'profile'),record('vacancy',fresh)]})
        self.f.archive.save_ranking({'resume_id':self.f.cv['id'],'resume_hash':self.f.cv['content_hash'],'goal':'Generative models','model':'text-embedding-3-small','generated_at':self.now.isoformat(),'all':[{'id':j['id'],'score':.9,'cv_similarity':.8,'vacancy_hash':text_hash(document_text('vacancy',j))} for j in (self.f.jd,fresh)]})
        self.assertEqual([c['job']['id'] for c in self.service.candidates(fresh=True)],['hh_2'])
        self.store.enqueue_delivery('job:'+hashed('legacy-slot')[:20]+':hh_2','seen')
        self.assertEqual(self.service.candidates(exclude_day=True),[])
        with self.store.connect() as db:db.execute('DELETE FROM workflow_delivery')
        self.store.enqueue_delivery('job:'+self.now.astimezone(self.service.zone).date().isoformat()+':hh_2','seen')
        self.assertEqual(self.service.candidates(exclude_day=True),[])

    async def test_failed_scheduled_refresh_never_falls_back_to_old_global_ranking(self):
        config(self.store,{'mode':'discovery'})
        self.f.archive.sync({'client_id':'notify-test','records':[record('profile',{'primary_id':self.f.cv['id'],'goal':'Generative models'},'profile')]})
        await self.service.begin_digest('digest:'+self.slot.isoformat())
        run=json.loads(self.store.setting('pending_digest'))['discovery_id']
        with self.store.connect() as db:db.execute("UPDATE discovery_runs SET state='needs_embeddings',result=? WHERE id=?",(packed({'ids':[self.f.jd['id']],'missing_embeddings':1}),run))
        with patch.object(self.service,'candidates',return_value=[]) as candidates:
            await self.service.finish_digest();self.assertTrue(candidates.call_args.kwargs['fresh'])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM workflow_delivery WHERE key LIKE 'job:%'").fetchone()[0],0)
            texts=[json.loads(r[0])['text'] for r in db.execute('SELECT payload FROM workflow_delivery')]
        self.assertTrue(any('без подтверждённой подборки' in t for t in texts));self.assertFalse(any('Топ-10' in t for t in texts))
