"""Whole-source crawls started from the web UI, one at a time, in isolated processes.

Each query runs through python_collection, so workers never see the CV, credentials
or database. Saving happens after each query, so a stop or crash keeps earlier work,
and a repeat run only reads what is still missing. No model calls happen here.
"""
import asyncio
import json
import re
import secrets
import threading
import time

# Also used by scripts/scrape_online.py. Yandex's URL filter beats per-keyword search.
YANDEX_URLS = [
    'https://yandex.ru/jobs/vacancies?professions=ml-developer&professions=backend-developer&professions=database-developer',
]
# ML/AI roles only: a narrow keyword set rather than the full catalog.
SBER_QUERIES = ['ML', 'LLM', 'VAE', 'DPO', 'RLHF', 'Diffusion', 'Audio', 'Speech', 'ASR', 'TTS', 'NLP', 'RAG', 'Search', 'Research']
GOOGLE_QUERIES = ['Machine Learning', 'AI Engineer', 'Deep Learning', 'NLP', 'Computer Vision', 'Applied Scientist', 'Research Scientist']
TENCENT_QUERIES = ['AI', 'machine learning', 'algorithm', 'LLM']

RUSSIA, LABS, BIG, CHINA = 'Россия', 'AI-лаборатории', 'Крупные компании', 'Китай'
GOOGLE_LINK = 'https://www.google.com/about/careers/applications/jobs/results/%'


def _spec(label, group, hint, hosts, *, queries=('',), limit=1000, rounds=1, fast=False, link=None, prefix=None, company=None, known_id=None, tracked=True, whole=True, exclude=None):
    """tracked: its listings report what they saw. whole: a vacancy absent from a complete listing is absent from the source."""
    return {'label': label, 'group': group, 'hint': hint, 'hosts': set(hosts), 'queries': list(queries), 'limit': limit, 'rounds': rounds,
            'fast': fast, 'link': link, 'prefix': prefix, 'company': company, 'known_id': known_id, 'tracked': tracked, 'whole': whole, 'exclude': exclude}


def _google_id(row_id, link):
    """Google rows are stored under a hash of the link, but the scraper checks its own ID."""
    found = re.match(r'\d+', (link or '').rstrip('/').rsplit('/', 1)[-1])
    return 'goog_' + found[0] if found else row_id


GREENHOUSE = {'job-boards.greenhouse.io', 'boards.greenhouse.io'}
ASHBY = {'jobs.ashbyhq.com'}


def _boards():
    from .scrapers.ats import BOARDS, GreenhouseScraper
    return {key: _spec(label, LABS, 'Секунды, открытый API', GREENHOUSE if base is GreenhouseScraper else ASHBY, fast=True) for key, (label, base, _) in BOARDS.items()}


SOURCES = {
    'yandex': _spec('Яндекс', RUSSIA, 'Секунды, открытый API', {'yandex.ru', 'yandex.com'}, queries=YANDEX_URLS, limit=300, fast=True, prefix='yandex_', whole=False),
    'sber': _spec('Сбер', RUSSIA, 'Минута-две, открытый API', {'rabota.sber.ru'}, queries=SBER_QUERIES, limit=500, fast=True, prefix='sber_', whole=False),
    'deepmind': _spec('Google DeepMind', LABS, 'Секунды, страницы Google Careers', {'www.google.com'}, fast=True, link=GOOGLE_LINK, company='DeepMind', known_id=_google_id),
    **_boards(),
    'google': _spec('Google', BIG, 'Несколько минут, также собирается ежедневно в GitHub', {'www.google.com'}, queries=GOOGLE_QUERIES, limit=500, link=GOOGLE_LINK, known_id=_google_id, exclude='DeepMind'),
    'meta': _spec('Meta', BIG, 'Браузер, читает только новые; также собирается ежедневно в GitHub', {'www.metacareers.com'}, limit=500, rounds=3, prefix='meta_'),
    'tencent': _spec('Tencent', CHINA, 'Несколько минут, открытый API', {'careers.tencent.com'}, queries=TENCENT_QUERIES, limit=100, rounds=3, tracked=False),
    'bytedance': _spec('ByteDance / Seed', CHINA, 'Браузер, большая выдача: до 900 вакансий за запуск', {'jobs.bytedance.com'}, limit=300, rounds=3, tracked=False),
    'deepseek': _spec('DeepSeek', CHINA, 'Медленно: около 15 с на вакансию', {'talent.deepseek.com', 'app.mokahr.com'}, limit=30, rounds=10, tracked=False),
}
UNAVAILABLE = {
    CHINA: 'Пока не работают: Moonshot, Zhipu, MiniMax, Shengshu, Alibaba, Kuaishou / Kling. Их страницы не отдали выдачу автоматическому чтению.',
    LABS: 'Пока не подключены: Mistral, Black Forest Labs, Hugging Face, Artlist. Открытую доску вакансий для них найти не удалось.',
}
DEADLINE = 600
STALE_SECONDS = DEADLINE + 120
BATCH = 100
ACTIVE = ('queued', 'running')
TABLE = 'CREATE TABLE IF NOT EXISTS source_runs(id TEXT PRIMARY KEY,source TEXT,state TEXT,payload TEXT,created REAL,updated REAL)'


def _write(archive, run_id, state, progress):
    with archive.connect() as db:
        db.execute('UPDATE source_runs SET state=?,payload=?,updated=? WHERE id=?', (state, json.dumps(progress), time.time(), run_id))


def _known(archive, spec, source):
    """Saved IDs for the source, and the scraper-side IDs of rows with a full text to skip."""
    where, args = ["kind='vacancy'"], []
    if spec['prefix']:
        where.append('id LIKE ?');args.append(spec['prefix'] + '%')
    elif spec['link']:
        where.append("json_extract(payload,'$.link') LIKE ?");args.append(spec['link'])
    else:
        # Portals keep hashed IDs, so their rows are recognised by the company name.
        where.append('company=?');args.append(spec['label'])
    existing, complete, scraper_ids = set(), set(), {}
    with archive.connect() as db:
        for row in db.execute("SELECT id,company,json_extract(payload,'$.description_quality') quality,json_extract(payload,'$.link') link FROM entities WHERE " + ' AND '.join(where), args):
            existing.add(row['id'])
            scraper_ids[spec['known_id'](row['id'], row['link']) if spec['known_id'] else row['id']] = row['id']
            # A role first seen in the Google run must still be relabelled by the DeepMind run.
            if row['quality'] == 'full' and (not spec['company'] or row['company'] == spec['company']):
                complete.add(spec['known_id'](row['id'], row['link']) if spec['known_id'] else row['id'])
    return existing, complete, scraper_ids


def scope_of(source):
    return 'https://' + min(SOURCES[source]['hosts']) + '/#' + source


def universe(archive, source):
    """Saved vacancies a complete listing should have shown; empty when the listing can't speak for them."""
    spec = SOURCES[source]
    if not spec['whole']:
        return set()
    existing = _known(archive, spec, source)[0]
    if not (spec['company'] or spec['exclude']):
        return existing
    with archive.connect() as db:
        rows = db.execute("SELECT id,company FROM entities WHERE kind='vacancy'").fetchall()
    # Roles on a shared site belong to one company's listing or the other's.
    return {r['id'] for r in rows if r['id'] in existing and (r['company'] == spec['company'] if spec['company'] else r['company'] != spec['exclude'])}


def source_for(job):
    """The tracked source whose listing can re-check this vacancy, if any."""
    from urllib.parse import urlsplit
    host = urlsplit(job.get('link', '')).hostname
    matches = [key for key, spec in SOURCES.items() if spec['tracked'] and host in spec['hosts']]
    named = [key for key in matches if SOURCES[key]['label'] == job.get('company') or SOURCES[key]['company'] == job.get('company')]
    if named:
        return named[0]
    return next((key for key in matches if SOURCES[key]['exclude'] or len(matches) == 1), None)


def run_one(archive, run_id, source, stop, executor=None, persist=None):
    from .python_collection import execute, persist as save
    executor, persist = executor or execute, persist or save
    spec = SOURCES[source]
    started = time.time()
    progress = {'done': 0, 'total': len(spec['queries']), 'listed': 0, 'new': 0, 'updated': 0, 'errors': 0, 'reasons': [], 'seconds': 0}
    _write(archive, run_id, 'running', progress)
    seen, whole_listing = set(), True
    for query in spec['queries']:
        query_whole = False
        for _ in range(spec['rounds']):
            if stop.is_set():
                break
            existing, complete, scraper_ids = _known(archive, spec, source)
            payload = {'source_key': source, 'query': query, 'known_ids': sorted(complete), 'deadline': DEADLINE, 'options': {'details': spec['limit'], 'source_run': True}}
            response = executor(payload, stop.is_set)
            response = response if isinstance(response, dict) else {'reason': 'python_error'}
            rows, report, reason = response.get('rows', []), response.get('report', {}), response.get('reason')
            progress['listed'] += max(report.get('listed', 0), len(rows))
            progress['errors'] += report.get('errors', 0) + (1 if reason and reason != 'stopped' and not report.get('errors') else 0)
            if reason and reason != 'stopped' and reason not in progress['reasons']:
                progress['reasons'].append(reason)
            saved = set()
            target = {'allowed_hosts': spec['hosts'], 'adapter_id': source}
            for start in range(0, len(rows), BATCH):
                saved |= set(persist(archive, target, {'rows': rows[start:start + BATCH]}).get('ids', []))
            seen |= saved | {scraper_ids.get(item, item) for item in response.get('seen_ids', [])}
            query_whole = report.get('coverage') == 'listing_exhausted' and not report.get('errors') and not reason
            progress['new'] += len(saved - existing)
            progress['updated'] += len(saved & existing)
            progress['seconds'] = round(time.time() - started, 1)
            _write(archive, run_id, 'running', progress)
            # A batch that hit its limit may have more behind it; saving now keeps the work.
            if report.get('coverage') != 'limited' or not saved:
                break
        whole_listing = whole_listing and query_whole
        if stop.is_set():
            break
        progress['done'] += 1
        _write(archive, run_id, 'running', progress)
    if spec['tracked'] and seen:
        observed = archive.record_listing('run:' + run_id, source, scope_of(source), seen, complete=whole_listing and not stop.is_set(), universe=universe(archive, source))
        progress['still_listed'] = observed['seen']
        if observed.get('suspicious'):
            progress['reasons'].append('listing_shrank')
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
                _write(self.archive, run_id, 'failed', {'done': 0, 'total': len(SOURCES[source]['queries']), 'listed': 0, 'new': 0, 'updated': 0, 'errors': 1, 'reasons': [type(error).__name__], 'seconds': 0})
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
                items.append({'source': source, 'label': spec['label'], 'group': spec['group'], 'hint': spec['hint'], 'fast': spec['fast'], 'last': last})
        from .application_store import ApplicationStore
        workers = ApplicationStore(self.archive.path).browser_status()
        return {'items': items, 'unavailable': UNAVAILABLE, 'running': any(i['last'] and i['last']['state'] in ACTIVE for i in items), 'chrome_connected': bool(workers.get('collection', {}).get('connected') or workers.get('hh', {}).get('connected'))}
