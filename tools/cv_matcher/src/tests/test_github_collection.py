import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from resume_import_server import create_app
from src.archive_store import ArchiveStore, digest
from src import github_collection_import as importer
from src.github_collection_api import GitHubAPI, GitHubError, REPOSITORY

DATE = '2026-10-20T10:00:00+00:00'
TEXT = 'Требования: Python и PyTorch. Обязанности: исследовать модели, обучать и оценивать результаты. ' * 3


def row(number=123, **extra):
    return {'id': 'arbitrary', 'title': 'Research Engineer', 'company': 'Yandex',
            'link': f'https://yandex.ru/jobs/vacancies/research-{number}?utm_source=tracking#apply',
            'description': TEXT, 'description_quality': 'full', 'collected_at': DATE, **extra}


def packet(rows):
    return {'last_updated': DATE, 'total': len(rows), 'stats_last_run': {'yandex': {'errors': 1}}, 'vacancies': rows}


class API:
    run = {'id': 12345, 'run_attempt': 1, 'run_number': 22, 'conclusion': 'success', 'head_sha': 'a' * 40}
    def __init__(self, payload): self.payload = payload; self.calls = 0
    def latest(self): return copy.deepcopy(self.run)
    def export(self, run): self.calls += 1; return copy.deepcopy(self.payload), 'artifact', []


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'archive.sqlite3'; self.archive = ArchiveStore(self.path)

    def test_normalization_and_missing_quality_are_conservative(self):
        item = importer.normalize(row(), importer.timestamp(DATE))
        self.assertEqual(item['id'], 'yandex_123'); self.assertNotIn('utm_', item['link']); self.assertNotIn('#', item['link'])
        self.assertNotIn('archived', item)
        legacy = row(); legacy.pop('description_quality'); legacy.pop('collected_at'); legacy['first_seen'] = DATE
        self.assertEqual(importer.normalize(legacy, importer.timestamp(DATE))['description_quality'], 'needs_review')
        legacy['last_seen'] = '2026-10-22T10:00:00Z'
        self.assertEqual(importer.normalize(legacy, importer.timestamp(DATE))['collected_at'], importer.timestamp(DATE))
        for link in ('https://user:password@yandex.ru/jobs/vacancies/123', 'http://yandex.ru/jobs/vacancies/123', 'https://localhost/private', 'https://hh.ru/search/vacancy'):
            with self.assertRaises(ValueError): importer.normalize(row(link=link), importer.timestamp(DATE))

    def test_chunking_deduplication_retry_and_record_rejection(self):
        rows = [row(i) for i in range(205)] + [row(2, description='Card', description_quality='snippet'), {'title': 'bad'}]
        api = API(packet(rows)); result = importer.pull(self.archive, api=api)
        self.assertEqual(result['phase'], 'complete'); self.assertEqual(result['counts']['added'], 205)
        self.assertEqual(result['counts']['duplicates'], 1); self.assertEqual(result['counts']['rejected'], 1)
        self.assertEqual(result['offset'], 205); self.assertEqual(self.archive.summary()['vacancies'], 205)
        repeat = importer.pull(self.archive, api=api)
        self.assertEqual(repeat['phase'], 'up_to_date'); self.assertEqual(api.calls, 1)
        self.assertEqual(self.archive.detail('vacancy', 'yandex_2')['payload']['description'], TEXT)
        self.assertEqual(repeat['last_import']['sources'][0]['errors'], 1)

    def test_newer_and_full_data_are_protected_and_absence_never_closes(self):
        importer.pull(self.archive, api=API(packet([row()])))
        api = API(packet([row(description='Card', description_quality='snippet')]))
        api.run = {**api.run, 'id': 12346, 'run_number': 23}
        result = importer.pull(self.archive, api=api)
        self.assertEqual(result['counts']['protected'], 1)
        self.assertEqual(self.archive.detail('vacancy', 'yandex_123')['payload']['description'], TEXT)
        api.run = {**api.run, 'id': 12347, 'run_number': 24}; api.payload = packet([])
        importer.pull(self.archive, api=api)
        self.assertEqual(self.archive.summary()['vacancies'], 1)
        self.assertEqual(self.archive.detail('vacancy', 'yandex_123')['availability'], 'unknown')

    def test_stale_full_description_cannot_replace_new_head(self):
        fresh = importer.normalize(row(collected_at='2026-10-21T10:00:00Z'), importer.timestamp('2026-10-21T10:00:00Z'))
        self.archive.sync({'client_id': 'extension-fixture', 'records': [{'kind': 'vacancy', 'id': fresh['id'], 'data': fresh, 'digest': digest(fresh)}]})
        result = importer.pull(self.archive, api=API(packet([row(description='Other old description. ' * 20)])))
        self.assertEqual(result['counts']['protected'], 1)
        self.assertEqual(self.archive.detail('vacancy', 'yandex_123')['payload']['description'], TEXT)

    def test_interrupted_import_resumes_atomically_after_checkpoint(self):
        api = API(packet([row(i) for i in range(205)])); original = importer.apply_batch
        def fail(archive, lease, rows, offset):
            if offset == 100: raise RuntimeError('do not expose source secrets')
            return original(archive, lease, rows, offset)
        with patch.object(importer, 'apply_batch', side_effect=fail):
            result = importer.pull(self.archive, api=api)
        self.assertEqual(result['phase'], 'error'); self.assertEqual(result['offset'], 100)
        self.assertNotIn('secrets', result['error']); self.assertNotIn('cursor', result)
        result = importer.pull(self.archive, api=api)
        self.assertEqual(result['counts']['added'], 205); self.assertEqual(self.archive.summary()['vacancies'], 205)
        self.assertEqual(result['phase'], 'complete')

    def test_corrupt_export_and_network_errors_do_not_advance_cursor(self):
        for payload in ({'vacancies': []}, {**packet([]), 'total': 99}):
            result = importer.pull(self.archive, api=API(payload))
            self.assertEqual(result['phase'], 'error'); self.assertNotIn('cursor', result)
        api = API(packet([]))
        with patch.object(api, 'latest', side_effect=GitHubError('Нет доступа GitHub')):
            self.assertEqual(importer.pull(self.archive, api=api)['error'], 'Нет доступа GitHub')
        self.assertFalse(importer.status(self.archive)['enabled'])

    def test_lease_blocks_parallel_import_and_settings_do_not_lose_progress(self):
        lease = importer.acquire(self.archive)
        self.assertIsNone(importer.acquire(ArchiveStore(self.path)))
        importer.configure(self.archive, True)
        result = importer.pull(self.archive, lease, API(packet([row()])))
        self.assertTrue(result['enabled']); self.assertEqual(result['counts']['added'], 1)
        with self.assertRaises(ValueError): importer.configure(self.archive, 'true')

    def test_routes_require_owner_session_and_do_not_accept_foreign_origin(self):
        app = create_app('fixture', archive_path=self.path)
        with TestClient(app) as client:
            self.assertEqual(client.get('/archive/github-import').status_code, 401)
            client.post('/archive/login', json={}, headers={'X-Resume-Import-Token': 'fixture'})
            self.assertEqual(client.get('/archive/github-import').status_code, 200)
            self.assertEqual(client.post('/archive/github-import', json={'op': 'configure', 'enabled': True}, headers={'Origin': 'https://example.org'}).status_code, 401)
            self.assertEqual(client.post('/archive/github-import', json={'op': 'configure', 'enabled': True}, headers={'Origin': 'http://127.0.0.1:8788'}).status_code, 200)


class TransportTests(unittest.TestCase):
    def test_mutable_actions_metadata_bypasses_stale_cache(self):
        requests = []
        class Process:
            returncode = 0
            def __init__(self, args, **kwargs):
                requests.append(args[4])
                kwargs['stdout'].write(b'{}')
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def wait(self, **kwargs): return 0
        api = GitHubAPI('fixture')
        endpoint = f'repos/{REPOSITORY}/actions/workflows/daily-scrape.yml/runs?per_page=20'
        immutable = f'repos/{REPOSITORY}/contents/public/online_scraped.json?ref=' + 'a' * 40
        with patch('src.github_collection_api.subprocess.Popen', Process), patch('src.github_collection_api.time.time_ns', side_effect=[100, 101]):
            api.request(endpoint); api.request(endpoint); api.request(immutable, raw=True)
        self.assertEqual(requests, [endpoint + '&_fresh=100', endpoint + '&_fresh=101', immutable])

    def test_artifact_run_binding_and_pinned_legacy_fallback(self):
        api = GitHubAPI('unused'); run = API.run
        value = {**packet([row()]), 'collection_run': {'id': run['id'], 'attempt': 1}}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as bundle: bundle.writestr('online_scraped.json', json.dumps(value))
        with patch.object(api, 'request', side_effect=[{'artifacts': [{'id': 5, 'name': 'vacancies-export-1', 'size_in_bytes': 2000, 'expired': False}]}, buffer.getvalue()]):
            payload, transport, warnings = api.export(run)
        self.assertEqual(transport, 'artifact'); self.assertFalse(warnings)
        with patch.object(api, 'request', side_effect=[{'artifacts': []}, json.dumps(packet([])).encode()]) as request:
            _, transport, warnings = api.export(run)
        self.assertEqual(transport, 'legacy_snapshot'); self.assertTrue(warnings)
        self.assertIn('ref=' + run['head_sha'], request.call_args.args[0])
        with patch.object(api, 'request', side_effect=[{'artifacts': [{'id': 5, 'name': 'vacancies-export-2', 'size_in_bytes': 2000}]}, buffer.getvalue()]):
            with self.assertRaises(GitHubError): api.export({**run, 'run_attempt': 2})

    def test_only_completed_trusted_main_runs_are_considered(self):
        api = GitHubAPI('unused')
        base = {**API.run, 'status': 'completed', 'head_branch': 'main', 'head_repository': {'full_name': REPOSITORY}, 'event': 'schedule'}
        with patch.object(api, 'request', return_value={'workflow_runs': [base, {**base, 'id': 777, 'run_number': 200, 'status': 'in_progress'}, {**base, 'run_number': 201, 'event': 'pull_request'}]}):
            self.assertEqual(api.latest()['id'], base['id'])
