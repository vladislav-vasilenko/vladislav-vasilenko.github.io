import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import HTTPException
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore, digest
from src import auto_scoring as auto, spend_guard
from src.extension_ranking import OpenAIBackend
from src.tests.test_archive import cv, record


def row(identifier, **values):
    return {'id': identifier, 'category': 'diffusion', 'quality': 'full', 'availability': 'active', 'similarity': None, 'alignment': None, 'ranking_stale': False, 'first_seen': '2099-01-01T00:00:00+00:00', **values}


class AutoScoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.archive = ArchiveStore(Path(self.tmp.name) / 'archive.sqlite3')
        self.resume = cv()
        self.archive.sync({'client_id': 'auto-scoring-test', 'records': [record('resume', self.resume),
                          {'kind': 'profile', 'id': 'profile', 'data': {'primary_id': self.resume['id'], 'goal': 'Research Engineer'}, 'digest': digest({'primary_id': self.resume['id'], 'goal': 'Research Engineer'})}]})
        self.calls = []
        detail = self.archive.detail
        def fake_detail(kind, identifier):
            if kind == 'vacancy': return {'availability': 'active', 'content_hash': 'x', 'payload': {'id': identifier, 'title': 'T', 'description': 'd' * 2000}}
            return detail(kind, identifier)
        patcher = patch.object(self.archive, 'detail', fake_detail); patcher.start(); self.addCleanup(patcher.stop)

    def enable(self, cap=1.0):
        return auto.configure(self.archive, {'enabled': True, 'confirmed': True, 'monthly_cap_usd': cap})

    def run_with(self, rows, tokens=1000):
        async def ranker(packet):
            self.calls.append(packet); return {'usage_tokens': tokens, 'new_compared': len(packet['vacancies'])}
        with patch.object(auto, 'snapshot', return_value={'rows': rows}):
            return asyncio.run(auto.run_once(self.archive, ranker))

    def test_off_by_default_and_never_calls_the_api(self):
        self.assertFalse(auto.read(self.archive)['enabled'])
        self.run_with([row('a')])
        self.assertEqual(self.calls, [])

    def test_enabling_needs_consent_and_a_valid_cap(self):
        with self.assertRaises(ValueError): auto.configure(self.archive, {'enabled': True})
        for cap in (0, -1, 21, 'lots', True):
            with self.assertRaises(ValueError): auto.configure(self.archive, {'enabled': True, 'confirmed': True, 'monthly_cap_usd': cap})
        self.assertFalse(auto.read(self.archive)['enabled'])

    def test_scores_only_new_unscored_full_text_vacancies_in_the_public_sample(self):
        self.enable()
        self.run_with([row('new'), row('old', first_seen='2020-01-01T00:00:00+00:00'), row('scored', similarity=.5, alignment=.3),
                       row('stale', similarity=.5, alignment=.3, ranking_stale=True), row('snippet', quality='snippet'), row('closed', availability='closed'), row('backend', category='backend')])
        self.assertEqual([job['id'] for job in self.calls[0]['vacancies']], ['new', 'stale'])
        self.assertEqual(self.calls[0]['goal'], 'Research Engineer')
        self.assertEqual(self.calls[0]['model'], auto.MODEL)
        state = auto.read(self.archive)
        self.assertEqual((state['phase'], state['tokens'], state['vacancies']), ('idle', 1000, 2))

    def test_re_enabling_does_not_turn_the_gap_into_a_backfill_or_move_the_start(self):
        since = self.enable()['since']
        auto.configure(self.archive, {'enabled': False})
        self.assertEqual(self.enable()['since'], since)

    def test_stops_before_a_batch_that_would_pass_the_cap(self):
        self.enable(cap=0.01)
        rows = [row(str(i)) for i in range(25)]
        result = self.run_with(rows, tokens=496000)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['phase'], 'cap_reached')
        self.assertLessEqual(result['tokens'] * auto.USD_PER_TOKEN, .01)

    def test_a_new_month_resets_spending_and_keeps_going(self):
        self.enable(cap=0.01)
        auto.write(self.archive, month='2000-01', tokens=490000)
        self.run_with([row('a')], tokens=10)
        state = auto.read(self.archive)
        self.assertEqual(state['month'], auto.month()); self.assertEqual(state['tokens'], 10)

    def test_api_failure_is_reported_and_busy_ranker_only_waits(self):
        self.enable()
        async def broken(packet): raise ValueError('OpenAI: HTTP 401')
        async def busy(packet): raise HTTPException(409, 'busy')
        with patch.object(auto, 'snapshot', return_value={'rows': [row('a')]}):
            failed = asyncio.run(auto.run_once(self.archive, broken))
            self.assertEqual((failed['phase'], failed['last_error']), ('error', 'OpenAI: HTTP 401'))
            waited = asyncio.run(auto.run_once(self.archive, busy))
        self.assertEqual((waited['phase'], waited['last_error']), ('waiting', ''))

    def test_auto_cap_cannot_exceed_the_shared_ceiling(self):
        with self.assertRaises(ValueError): self.enable(cap=6)
        spend_guard.set_ceiling(self.archive, 10, True)
        self.assertEqual(self.enable(cap=6)['monthly_cap_usd'], 6)
        self.assertEqual([item['action'] for item in spend_guard.read(self.archive)['history']][:2], ['auto_on', 'ceiling'])

    def test_status_counts_older_vacancies_separately_and_spends_nothing(self):
        self.enable()
        with patch.object(auto, 'snapshot', return_value={'rows': [row('new'), row('old', first_seen='2020-01-01T00:00:00+00:00')]}):
            value = auto.status(self.archive)
        self.assertEqual((value['pending'], value['older_unscored'], value['spent_usd']), (1, 1, 0))
        self.assertEqual(self.calls, [])


class SpendGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.archive = ArchiveStore(Path(self.tmp.name) / 'archive.sqlite3')

    def backend(self):
        backend = OpenAIBackend('text-embedding-3-small'); backend.ledger = self.archive; requests = []
        class Embeddings:
            def create(_, **values):
                requests.append(values)
                return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[1.0] * backend.dimensions) for i in range(len(values['input']))], usage=SimpleNamespace(total_tokens=100000))
        backend.client = SimpleNamespace(embeddings=Embeddings())
        return backend, requests

    def test_every_embedding_request_is_counted_and_stopped_at_the_ceiling(self):
        spend_guard.set_ceiling(self.archive, .01, True)
        backend, requests = self.backend()
        for _ in range(5): backend.embed_documents(['x'])
        self.assertEqual(spend_guard.read(self.archive)['tokens'], 500000)
        with self.assertRaises(ValueError): backend.embed_documents(['x' * 10])
        self.assertEqual(len(requests), 5)

    def test_ceiling_needs_confirmation_and_stays_in_range(self):
        with self.assertRaises(ValueError): spend_guard.set_ceiling(self.archive, 2, False)
        for value in (0, 51, 'x', True):
            with self.assertRaises(ValueError): spend_guard.set_ceiling(self.archive, value, True)
        self.assertEqual(spend_guard.read(self.archive)['ceiling_usd'], spend_guard.DEFAULT_CEILING)

    def test_a_new_month_starts_from_zero(self):
        spend_guard.record(self.archive, 500)
        with self.archive.connect() as db:
            state = json.loads(db.execute("SELECT value FROM archive_meta WHERE key='embedding-spend'").fetchone()[0]); state['month'] = '2000-01'
            db.execute("UPDATE archive_meta SET value=? WHERE key='embedding-spend'", (json.dumps(state),))
        self.assertEqual(spend_guard.read(self.archive)['tokens'], 0)


class PaidSettingsAccess(unittest.TestCase):
    ORIGIN = 'http://127.0.0.1:8788'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.app = create_app('t' * 32, archive_path=Path(self.tmp.name) / 'archive.sqlite3')
        self.archive = self.app.state.archive_store(); resume = cv()
        self.archive.sync({'client_id': 'auto-scoring-test', 'records': [record('resume', resume),
                          {'kind': 'profile', 'id': 'profile', 'data': {'primary_id': resume['id'], 'goal': 'Research Engineer'}, 'digest': digest({'primary_id': resume['id'], 'goal': 'Research Engineer'})}]})
        self.turn_on = {'op': 'auto_configure', 'enabled': True, 'confirmed': True, 'monthly_cap_usd': 1}
        self.token = {'X-Resume-Import-Token': 't' * 32}

    def browser(self, client):
        code = client.post('/archive/open', json={}, headers=self.token).json()['url'].split('#connect=')[1]
        self.assertEqual(client.post('/archive/login', json={'code': code}, headers={'Origin': self.ORIGIN}).status_code, 200)

    def test_pairing_token_cannot_turn_spending_on_or_raise_the_ceiling(self):
        with TestClient(self.app) as client:
            self.assertEqual(client.post('/archive/embedding-batch', json=self.turn_on, headers=self.token).status_code, 403)
            self.assertEqual(client.post('/archive/embedding-batch', json={'op': 'spend_ceiling', 'ceiling_usd': 50, 'confirmed': True}, headers=self.token).status_code, 403)
            self.assertEqual(client.post('/archive/embedding-batch', json={**self.turn_on, 'enabled': 'yes'}, headers=self.token).status_code, 403)
        self.assertFalse(auto.read(self.archive)['enabled'])
        self.assertEqual(spend_guard.read(self.archive)['ceiling_usd'], spend_guard.DEFAULT_CEILING)

    def test_other_origins_are_refused_and_the_owner_browser_works(self):
        with TestClient(self.app) as client:
            self.browser(client)
            self.assertEqual(client.post('/archive/embedding-batch', json=self.turn_on, headers={'Origin': 'http://127.0.0.1:5173'}).status_code, 401)
            self.assertEqual(client.post('/archive/embedding-batch', json=self.turn_on).status_code, 401)
            self.assertFalse(auto.read(self.archive)['enabled'])
            response = client.post('/archive/embedding-batch', json=self.turn_on, headers={'Origin': self.ORIGIN})
            self.assertEqual(response.status_code, 200); self.assertTrue(response.json()['enabled'])

    def test_any_authorized_client_can_turn_spending_off(self):
        auto.configure(self.archive, {'enabled': True, 'confirmed': True, 'monthly_cap_usd': 1})
        with TestClient(self.app) as client:
            self.assertEqual(client.post('/archive/embedding-batch', json={'op': 'auto_configure', 'enabled': False}, headers=self.token).status_code, 200)
        self.assertFalse(auto.read(self.archive)['enabled'])
