"""No network: periodic HH reading, restart safety, quiet polls and change delivery."""
import asyncio
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from src import hh_auto_sync as auto
from src.tests import test_workflow as fixtures
from src.tests.test_recruiter import Operator
from src.application_store import ApplicationStore
from src.workflow_bot import WorkflowBot


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WorkflowTests('runTest')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.s = self.f.store

    def ready(self):
        self.s.next_command('managed-hh-reader', auto_sync=True)

    def finish(self, command_id, result):
        command = self.s.next_command('managed-hh-reader', auto_sync=True)['command']
        self.assertEqual(command['id'], command_id)
        self.s.finish_command(command_id, 'managed-hh-reader', result)

    def test_no_jobs_offline_or_from_old_or_manually_connected_extension(self):
        self.assertEqual(auto.tick(self.s)['state'], 'waiting_chrome')
        self.s.next_command('legacy-worker')
        self.assertTrue(self.s.browser_status()['connected'])
        self.assertEqual(auto.tick(self.s)['state'], 'waiting_chrome')
        self.ready()
        self.assertEqual(auto.status(self.s, now=time.time()+181)['state'], 'waiting_chrome')
        with self.s.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM browser_commands').fetchone()[0], 0)

    def test_atomic_single_job_across_concurrent_ticks_restart_and_manual_sync(self):
        self.ready()
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: auto.tick(ApplicationStore(self.s.path)), range(5)))
        self.assertEqual(len({r['command_id'] for r in results}), 1)
        identifier = results[0]['command_id']
        self.finish(identifier, {'state': 'complete'})
        self.assertIsNone(auto.tick(ApplicationStore(self.s.path))['command_id'])
        manual = self.s.queue_command('sync')
        self.assertEqual(auto.tick(self.s)['command_id'], manual)

    def test_interval_backoff_and_pause_persist_without_stopping_manual_sync(self):
        self.ready()
        first = auto.tick(self.s)['command_id']
        self.finish(first, {'state': 'failed', 'note': 'HH требует вход или CAPTCHA.'})
        state = auto.tick(self.s)
        self.assertEqual(state['state'], 'backoff')
        self.assertGreater(state['next_at'], time.time()+590)
        auto.config(self.s, {'enabled': True, 'interval_seconds': 60})
        with self.s.connect() as db:
            db.execute('UPDATE browser_commands SET updated=? WHERE id=?', (time.time()-121, first))
        second = auto.tick(self.s)['command_id']
        self.assertNotEqual(second, first)
        auto.config(self.s, {'enabled': False, 'interval_seconds': 300})
        self.assertIsNone(self.s.next_command('managed-hh-reader', auto_sync=True)['command'])
        self.assertEqual(auto.status(ApplicationStore(self.s.path))['state'], 'disabled')
        manual = self.s.queue_command('sync')
        self.assertEqual(self.s.next_command('managed-hh-reader')['command']['id'], manual)
        for interval in (0, 59, 3601, True):
            with self.assertRaises(ValueError):auto.config(self.s, {'enabled': True, 'interval_seconds': interval})

    def test_old_workers_cannot_claim_auto_and_approved_send_has_priority(self):
        self.ready()
        job = auto.tick(self.s)['command_id']
        self.assertIsNone(self.s.next_command('old-worker')['command'])
        approved = self.f.approve()
        command = self.s.next_command('managed-hh-reader', auto_sync=True)['command']
        self.assertEqual(command['id'], approved['command_id'])
        self.s.claim_approval(command['id'], 'managed-hh-reader', 'before')
        self.assertIsNone(self.s.next_command('second-reader', auto_sync=True)['command'])
        with self.s.connect() as db:
            self.assertEqual(db.execute('SELECT state FROM browser_commands WHERE id=?', (job,)).fetchone()[0], 'queued')

    def snapshot(self, state='unknown', messages=None, stamp=None, **record):
        data = {'vacancy_id': 'hh_1', 'thread_id': 'thread:1', 'status': state, **record}
        if messages is not None:data['messages'] = messages
        return {'source_url': 'https://hh.ru/applicant/negotiations', 'observed_at': stamp or datetime.now(timezone.utc).isoformat(), 'records': [data]}

    def events(self, kind):
        with self.s.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM application_events WHERE type=?', (kind,))]

    def test_status_unknown_empty_stale_and_repeated_observations_never_make_false_change(self):
        self.s.hh_sync(self.snapshot('viewed'))
        self.s.hh_sync(self.snapshot('unknown'))
        self.s.hh_sync(self.snapshot('viewed'))
        self.s.hh_sync(self.snapshot('rejected', stamp=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()))
        self.s.hh_sync({**self.snapshot(), 'records': []})
        self.assertEqual(self.s.get(self.f.id)['status'], 'viewed')
        self.assertEqual([e['status'] for e in self.events('hh_status')], ['viewed'])
        self.assertEqual(self.s.workflow(self.f.id)['crm']['stage'], 'applied')

    def test_existing_status_does_not_touch_prepared_form_or_claimed_send(self):
        command, _ = self.f.execute()
        self.s.hh_sync(self.snapshot('submitted'))
        self.assertEqual(self.s.workflow(self.f.id)['workflow']['state'], 'sending')
        self.s.hh_sync(self.snapshot('submitted'))
        with self.s.connect() as db:
            self.assertEqual(db.execute('SELECT state FROM browser_commands WHERE id=?', (command['id'],)).fetchone()[0], 'running')

    def test_first_chat_is_baseline_then_new_non_outgoing_message_event_exactly_once(self):
        old = {'id': 'old', 'text': 'Старая переписка', 'direction': 'incoming'}
        self.s.hh_sync(self.snapshot(messages=[old]))
        self.assertEqual(self.events('hh_message'), [])
        new = {'id': 'new', 'text': 'Приглашаем на следующий этап', 'direction': 'incoming'}
        outgoing = {'id': 'mine', 'text': 'Спасибо', 'direction': 'outgoing'}
        self.s.hh_sync(self.snapshot(messages=[old, new, outgoing]))
        # Same ID with changed relative time/direction must not be a second message.
        self.s.hh_sync(self.snapshot(messages=[{**new, 'at': 'today', 'direction': 'unknown'}]))
        self.assertEqual([e['text'] for e in self.events('hh_message')], [new['text']])
        self.assertEqual(len(self.s.workflow(self.f.id)['hh_messages']), 3)

    def test_unbound_or_wrong_resume_chat_does_not_notify_wrong_application(self):
        self.s.hh_sync(self.snapshot(messages=[{'id': '1', 'text': 'old'}]))
        self.s.hh_sync(self.snapshot(messages=[{'id': '2', 'text': 'wrong CV'}], resume_id='b'*38))
        self.s.hh_sync({'source_url': 'https://hh.ru/chat/2', 'records': [{'thread_id': 'thread:2', 'messages': [{'id': '1', 'text': 'unknown job'}]}]})
        self.assertEqual(self.events('hh_message'), [])

    def test_service_lifespan_starts_scheduler_and_authenticated_config_can_pause_it(self):
        from resume_import_server import create_app
        called = []
        original = auto.tick
        def record(store):
            called.append(store.path)
            return original(store)
        with patch.object(auto, 'tick', side_effect=record):
            with TestClient(create_app('fixture', archive_path=self.s.path)) as client:
                self.assertEqual(client.post('/archive/workflow', json={'op': 'hh_auto_sync'}).status_code, 401)
                headers = {'X-Resume-Import-Token': 'fixture'}
                saved = client.post('/archive/workflow', headers=headers, json={'op': 'hh_auto_sync_save', 'config': {'enabled': False, 'interval_seconds': 300}})
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()['state'], 'disabled')
                with self.s.connect() as db:
                    db.execute("INSERT INTO hh_threads VALUES('valid',NULL,'https://hh.ru/chat/123','now')")
                    db.execute("INSERT INTO hh_threads VALUES('invalid',NULL,'https://evil.example/chat/123','now')")
                targets=client.post('/archive/workflow',headers=headers,json={'op':'hh_sync_targets'}).json()
                self.assertEqual(targets['urls'],['https://hh.ru/chat/123'])
        self.assertIn(self.s.path, called)


class SyncDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.f = fixtures.WorkflowTests('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.s = self.f.store; self.op = Operator(); self.bot = WorkflowBot(self.s, self.op, 42)
        # Keep unrelated twice-daily discovery out of this notification test.
        self.s.setting('telegram_notifications', json.dumps({'mode':'off'}))
        self.bot.finish_digest = AsyncMock(); self.bot.plan_reminders = AsyncMock(); self.bot.begin_digest = AsyncMock()

    async def test_successful_background_polls_quiet_and_identical_failures_one_alert(self):
        for result in ({'state': 'complete'}, {'state': 'failed', 'note': 'CAPTCHA'}, {'state': 'failed', 'note': 'CAPTCHA'}):
            identifier = self.s.queue_command('sync', payload={'automatic': True})
            self.s.next_command('managed-reader', auto_sync=True)
            self.s.finish_command(identifier, 'managed-reader', result)
        await self.bot.tick(); await self.bot.tick()
        self.assertEqual(len(self.op.messages), 1)
        self.assertIn('CAPTCHA', self.op.messages[0][0])

    async def test_new_message_delivery_restarts_idempotently_and_has_application_link(self):
        with self.s.connect() as db:
            self.s._event(db, self.f.id, 'hh_message', {'text': 'Когда удобно интервью?', 'direction': 'incoming'})
        await self.bot.enqueue_event_notifications()
        await WorkflowBot(ApplicationStore(self.s.path), self.op, 42).enqueue_event_notifications()
        self.assertEqual(len(self.op.messages), 1)
        self.assertIn('Когда удобно интервью?', self.op.messages[0][0])
        self.assertIn(self.f.id, self.op.messages[0][1][0][0][1])

    async def test_scheduler_survives_transient_database_error_and_cancels_cleanly(self):
        with patch.object(auto, 'tick', side_effect=[RuntimeError('transient'), {}]) as tick:
            task = asyncio.create_task(auto.run(lambda: self.s, period=.01))
            for _ in range(50):
                if tick.call_count >= 2:break
                await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertGreaterEqual(tick.call_count, 2)
