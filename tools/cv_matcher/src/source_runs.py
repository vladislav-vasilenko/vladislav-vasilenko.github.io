"""Whole-source crawls started from the web UI, one at a time, in isolated processes.

Each query runs through python_collection, so workers never see the CV, credentials
or database. Saving happens after each query, so a stop or crash keeps earlier work,
and a repeat run only reads what is still missing. No model calls happen here.
"""
import asyncio
import json
import secrets
import threading
import time
from urllib.parse import urlencode

# Also used by scripts/scrape_online.py. Yandex's URL filter beats per-keyword search.
YANDEX_URLS = [
    'https://yandex.ru/jobs/vacancies?professions=ml-developer&professions=backend-developer&professions=database-developer',
]
# ML/AI roles only: a narrow keyword set rather than the full catalog.
SBER_QUERIES = ['ML', 'LLM', 'VAE', 'DPO', 'RLHF', 'Diffusion', 'Audio', 'Speech', 'ASR', 'TTS', 'NLP', 'RAG', 'Search', 'Research']

SOURCES = {
    'yandex': {'label': 'Яндекс', 'prefix': 'yandex_', 'urls': YANDEX_URLS, 'limit': 300},
    'sber': {'label': 'Сбер', 'prefix': 'sber_', 'urls': ['https://rabota.sber.ru/search/?' + urlencode({'query': term}) for term in SBER_QUERIES], 'limit': 500},
}
DEADLINE = 300
STALE_SECONDS = DEADLINE + 120
BATCH = 100
ACTIVE = ('queued', 'running')
TABLE = 'CREATE TABLE IF NOT EXISTS source_runs(id TEXT PRIMARY KEY,source TEXT,state TEXT,payload TEXT,created REAL,updated REAL)'


def _write(archive, run_id, state, progress):
    with archive.connect() as db:
        db.execute('UPDATE source_runs SET state=?,payload=?,updated=? WHERE id=?', (state, json.dumps(progress), time.time(), run_id))


def _known(archive, prefix):
    """All saved IDs for the source, and those with a full text that needn't be read again."""
    rows = {}
    with archive.connect() as db:
        for row in db.execute("SELECT id,json_extract(payload,'$.description_quality') FROM entities WHERE kind='vacancy' AND id LIKE ?", (prefix + '%',)):
            rows[row[0]] = row[1]
    return set(rows), {key for key, quality in rows.items() if quality == 'full'}


def run_one(archive, run_id, source, stop, executor=None, persist=None):
    from .python_collection import execute, persist as save
    executor, persist = executor or execute, persist or save
    spec = SOURCES[source]
    started = time.time()
    progress = {'done': 0, 'total': len(spec['urls']), 'listed': 0, 'new': 0, 'updated': 0, 'errors': 0, 'reasons': [], 'seconds': 0}
    _write(archive, run_id, 'running', progress)
    for url in spec['urls']:
        if stop.is_set():
            break
        existing, complete = _known(archive, spec['prefix'])
        payload = {'source_url': url, 'known_ids': sorted(complete), 'deadline': DEADLINE, 'options': {'details': spec['limit'], 'source_run': True}}
        response = executor(payload, stop.is_set)
        rows = response.get('rows', []) if isinstance(response, dict) else []
        report = response.get('report', {}) if isinstance(response, dict) else {}
        reason = response.get('reason') if isinstance(response, dict) else 'python_error'
        progress['listed'] += max(report.get('listed', 0), len(rows))
        progress['errors'] += report.get('errors', 0) + (1 if reason and reason != 'stopped' and not report.get('errors') else 0)
        if reason and reason != 'stopped' and reason not in progress['reasons']:
            progress['reasons'].append(reason)
        saved = set()
        for start in range(0, len(rows), BATCH):
            result = persist(archive, {'source_url': url}, {'rows': rows[start:start + BATCH]})
            saved |= set(result.get('ids', []))
        progress['new'] += len(saved - existing)
        progress['updated'] += len(saved & existing)
        progress['done'] += 1
        progress['seconds'] = round(time.time() - started, 1)
        _write(archive, run_id, 'running', progress)
    progress['seconds'] = round(time.time() - started, 1)
    # An empty listing means a broken source, not an empty board.
    state = 'stopped' if stop.is_set() else 'failed' if not progress['listed'] else 'partial' if progress['errors'] else 'complete'
    _write(archive, run_id, state, progress)
    return state


class Runner:
    """Works through queued runs in order. Only this process runs them, so leftovers are stale."""

    def __init__(self, archive, executor=None):
        self.archive = archive
        self.executor = executor
        self.stops = {}
        self.task = None
        with archive.connect() as db:
            db.execute(TABLE)
            db.execute("UPDATE source_runs SET state='interrupted',updated=? WHERE state IN ('queued','running')", (time.time(),))

    def start(self, sources):
        if not isinstance(sources, list) or not sources or any(source not in SOURCES for source in sources):
            raise ValueError('Выберите источник из списка.')
        started = []
        with self.archive.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for source in dict.fromkeys(sources):
                if db.execute("SELECT 1 FROM source_runs WHERE source=? AND state IN ('queued','running')", (source,)).fetchone():
                    continue
                run_id = secrets.token_hex(8)
                db.execute('INSERT INTO source_runs VALUES(?,?,?,?,?,?)', (run_id, source, 'queued', '{}', time.time(), time.time()))
                started.append(source)
        return {'started': started}

    def stop(self, source):
        if source not in SOURCES:
            raise ValueError('Выберите источник из списка.')
        with self.archive.connect() as db:
            db.execute("UPDATE source_runs SET state='stopped',updated=? WHERE source=? AND state='queued'", (time.time(), source))
            row = db.execute("SELECT id FROM source_runs WHERE source=? AND state='running'", (source,)).fetchone()
        if row and row[0] in self.stops:
            self.stops[row[0]].set()
        return {'ok': True}

    def kick(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._drain())
        return self.task

    def _next(self):
        with self.archive.connect() as db:
            return db.execute("SELECT id,source FROM source_runs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()

    async def _drain(self):
        while True:
            row = await asyncio.to_thread(self._next)
            if not row:
                return
            run_id, source = row[0], row[1]
            stop = self.stops[run_id] = threading.Event()
            try:
                await asyncio.to_thread(run_one, self.archive, run_id, source, stop, self.executor)
            except Exception as error:
                # Keep only the type: exception text may quote page contents.
                _write(self.archive, run_id, 'failed', {'done': 0, 'total': len(SOURCES[source]['urls']), 'listed': 0, 'new': 0, 'updated': 0, 'errors': 1, 'reasons': [type(error).__name__], 'seconds': 0})
            finally:
                self.stops.pop(run_id, None)

    def shutdown(self):
        for stop in self.stops.values():
            stop.set()

    def status(self):
        items = []
        with self.archive.connect() as db:
            for source, spec in SOURCES.items():
                row = db.execute('SELECT state,payload,created,updated FROM source_runs WHERE source=? ORDER BY created DESC LIMIT 1', (source,)).fetchone()
                last = None
                if row:
                    state = 'interrupted' if row[0] == 'running' and time.time() - row[3] > STALE_SECONDS else row[0]
                    last = {'state': state, 'progress': json.loads(row[1]), 'created': row[2], 'updated': row[3]}
                items.append({'source': source, 'label': spec['label'], 'last': last})
        from .application_store import ApplicationStore
        workers = ApplicationStore(self.archive.path).browser_status()
        return {'items': items, 'running': any(i['last'] and i['last']['state'] in ACTIVE for i in items), 'chrome_connected': bool(workers.get('collection', {}).get('connected') or workers.get('hh', {}).get('connected'))}
