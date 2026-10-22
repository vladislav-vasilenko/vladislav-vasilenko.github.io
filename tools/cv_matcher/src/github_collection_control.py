"""Fixed-workflow controls. No arbitrary ref, script, repository or model dispatch."""
import json
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from .github_collection_api import GitHubAPI, GitHubError, REPOSITORY, WORKFLOW

CI_SOURCES = ('yandex', 'google', 'meta', 'sber')
SETTINGS_KEY = 'github-collection-controls'


def state(archive):
    with archive.connect() as db:
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (SETTINGS_KEY,)).fetchone()
    return json.loads(row[0]) if row else {'sources': ['yandex', 'google', 'meta'], 'limit': 100}


def save(archive, **changes):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (SETTINGS_KEY,)).fetchone()
        value = json.loads(row[0]) if row else {'sources': ['yandex', 'google', 'meta'], 'limit': 100}
        value.update(changes)
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (SETTINGS_KEY, json.dumps(value)))
    return value


def configure(archive, data):
    sources = data.get('sources'); limit = data.get('limit')
    if not isinstance(sources, list) or not sources or len(sources) > 4 or any(s not in CI_SOURCES for s in sources) or len(set(sources)) != len(sources):
        raise ValueError('Выберите источники Yandex, Google, Meta или Sber.')
    if type(limit) is not int or not 1 <= limit <= 500: raise ValueError('Лимит должен быть от 1 до 500 на запрос источника.')
    return save(archive, sources=sources, limit=limit)


def clean_run(r):
    return {k: r.get(k) for k in ('id', 'run_number', 'run_attempt', 'status', 'conclusion', 'event', 'created_at', 'updated_at', 'html_url')}


def overview(archive, client=None):
    from .scrapers import SCRAPER_REGISTRY
    client = client or GitHubAPI()
    runs = client.request(f'repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/runs?branch=main&per_page=20').get('workflow_runs', [])
    runs = [clean_run(r) for r in runs if r.get('head_branch') == 'main' and r.get('head_repository', {}).get('full_name') == REPOSITORY]
    return {'settings': state(archive), 'runs': runs, 'schedule': '07:00 UTC ежедневно · .github/workflows/daily-scrape.yml',
            'adapters': [{'id': key, 'adapter': value.__name__, 'github_actions': key in CI_SOURCES,
                         'note': 'Sber: возможны блокировки WAF в CI; предпочтителен локальный сбор.' if key == 'sber' else 'Python / Playwright' if key in CI_SOURCES else 'Доступен локально; пока не включён в этот GitHub workflow.'}
                         for key, value in SCRAPER_REGISTRY.items()], 'api_requests_models': 0}


def run_detail(identifier, client=None):
    if type(identifier) is not int or identifier < 1: raise ValueError('Некорректный номер запуска.')
    client = client or GitHubAPI()
    run = client.request(f'repos/{REPOSITORY}/actions/runs/{identifier}')
    if run.get('path') != '.github/workflows/' + WORKFLOW or run.get('head_branch') != 'main':
        raise ValueError('Разрешены только запуски сбора вакансий на main.')
    jobs = client.request(f'repos/{REPOSITORY}/actions/runs/{identifier}/jobs?per_page=30').get('jobs', [])
    return {'run': clean_run(run), 'jobs': [{'name': j.get('name'), 'status': j.get('status'), 'conclusion': j.get('conclusion'),
        'steps': [{k: s.get(k) for k in ('name', 'status', 'conclusion', 'number')} for s in j.get('steps', [])]} for j in jobs]}


class Controller(GitHubAPI):
    def mutate(self, suffix, body):
        if suffix != f'workflows/{WORKFLOW}/dispatches' and not re.fullmatch(r'runs/[1-9][0-9]*/cancel', suffix):
            raise ValueError('Недопустимая операция GitHub Actions.')
        if not self.executable: raise GitHubError('Нужен GitHub CLI с выполненным входом.')
        with tempfile.TemporaryFile(mode='w+') as request:
            json.dump(body, request); request.seek(0)
            result = subprocess.run([self.executable, 'api', '--method', 'POST', f'repos/{REPOSITORY}/actions/{suffix}', '--input', '-'],
                                    stdin=request, capture_output=True, text=True, timeout=30)
        if result.returncode: raise GitHubError('GitHub не принял команду. Проверьте права Actions:write и актуальность workflow на main.')


def dispatch(archive, client=None):
    client = client or Controller(); settings = state(archive)
    if settings.get('dispatched_epoch', 0) > time.time() - 60: raise ValueError('Запуск уже запрошен. Обновите историю через несколько секунд.')
    active = overview(archive, client)['runs']
    if any(r['status'] != 'completed' for r in active): raise ValueError('Сбор уже выполняется или стоит в очереди. Дождитесь его завершения.')
    # Claim the local dispatch slot transactionally before the external mutation.
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (SETTINGS_KEY,)).fetchone()
        latest = json.loads(row[0]) if row else settings
        if latest.get('dispatched_epoch', 0) > time.time() - 60: raise ValueError('Запуск уже запрошен.')
        latest.update(dispatched_epoch=time.time(), dispatch_status='sending')
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (SETTINGS_KEY, json.dumps(latest)))
    try:
        client.mutate(f'workflows/{WORKFLOW}/dispatches', {'ref': 'main', 'inputs': {'sources': ','.join(settings['sources']), 'limit': str(settings['limit'])}})
    except Exception:
        save(archive, dispatch_status='error'); raise
    return save(archive, dispatch_status='accepted', dispatched_at=datetime.now(timezone.utc).isoformat())


def cancel(identifier, client=None):
    client = client or Controller(); detail = run_detail(identifier, client)
    if detail['run']['status'] == 'completed': raise ValueError('Этот запуск уже завершён.')
    client.mutate(f'runs/{identifier}/cancel', {})
    return {'accepted': True, 'run_id': identifier}
