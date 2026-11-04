"""Saved per-version results of the slow local rules. Regenerable: safe to drop, not in backups.

Keyed by (vacancy, content hash, family). Each family's engine is a hash of the
source files holding its rules, so a rule change recomputes it automatically.
No network or model calls happen here.
"""
import asyncio
import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
import threading
import time

FILES = {
    'basic': ('analysis_store.py', 'extension_ranking.py', 'resume_source.py'),
    'taxonomy': ('career_analytics.py', 'career_taxonomy.py'),
    'profile': ('career_trajectory_matching.py', 'career_skill_requirements.py', 'career_skills_catalog.py'),
}
# Prepared in this order: the opportunities screen waits on taxonomy, the optional trajectory filter on profile.
PLAN = (('basic', False), ('taxonomy', False), ('taxonomy', True), ('profile', False))
BATCH = 25
CHUNK = 500
TABLE = 'CREATE TABLE IF NOT EXISTS vacancy_derived(entity_id TEXT,content_hash TEXT,family TEXT,engine TEXT,value TEXT,PRIMARY KEY(entity_id,content_hash,family));'


@lru_cache(maxsize=None)
def engine(family):
    digest = hashlib.sha256()
    for name in FILES[family]:
        digest.update((Path(__file__).parent / name).read_bytes())
    return digest.hexdigest()[:16]


def compute(family, data):
    if family == 'basic':
        from .analysis_store import document_text, text_hash
        from .extension_ranking import chunks
        text = document_text('vacancy', data)
        return {'quality': data.get('description_quality'), 'text_hash': text_hash(text), 'chunks': len(chunks(text))}
    if family == 'taxonomy':
        from .career_analytics import classify
        from .career_taxonomy import classify_work_format
        found = classify(data)
        work_format, region = classify_work_format(data, data.get('description', ''))
        return {**found, 'work_format': work_format, 'region': region}
    from .career_trajectory_matching import profile_value
    return profile_value(data)


def split(values):
    values = list(values)
    return [values[i:i + CHUNK] for i in range(0, len(values), CHUNK)]


def _missing(db, family, versions, ids, limit):
    bound = ' LIMIT ' + str(int(limit)) if limit else ''
    table, key, group = ('versions', 'entity_id', ' GROUP BY v.entity_id,v.content_hash') if versions else ('entities', 'id', '')
    head = 'SELECT v.' + key + ' entity_id,v.content_hash,MAX(v.rowid) row_id FROM ' + table + " v LEFT JOIN vacancy_derived d ON d.entity_id=v." + key + " AND d.content_hash=v.content_hash AND d.family=? AND d.engine=? WHERE v.kind='vacancy' AND d.entity_id IS NULL"
    args = [family, engine(family)]
    if ids is not None:
        head += ' AND v.' + key + ' IN (' + ','.join('?' * len(ids)) + ')'
        args += list(ids)
    return db.execute(head + (group or ' GROUP BY v.rowid') + bound, args).fetchall(), table


def ensure(db, family, *, versions=False, ids=None, limit=None):
    """Compute whatever is missing, committing in short batches so writers aren't held up."""
    if ids is not None:
        return sum(_ensure(db, family, versions, part, limit) for part in split(ids))
    return _ensure(db, family, versions, None, limit)


def _ensure(db, family, versions, ids, limit):
    rows, table = _missing(db, family, versions, ids, limit)
    current = engine(family)
    for part in split(rows):
        placeholders = ','.join('?' * len(part))
        payloads = {r[0]: r[1] for r in db.execute('SELECT rowid,payload FROM ' + table + ' WHERE rowid IN (' + placeholders + ')', [r['row_id'] for r in part])}
        values = [(r['entity_id'], r['content_hash'], family, current, json.dumps(compute(family, json.loads(payloads[r['row_id']])), ensure_ascii=False, separators=(',', ':'))) for r in part if r['row_id'] in payloads]
        db.executemany('INSERT OR REPLACE INTO vacancy_derived VALUES(?,?,?,?,?)', values)
        db.commit()
    return len(rows)


def heads(db, family, ids=None):
    """Saved values for the current version of each vacancy, by vacancy ID."""
    query = "SELECT d.entity_id,d.value FROM vacancy_derived d JOIN entities e ON e.kind='vacancy' AND e.id=d.entity_id AND e.content_hash=d.content_hash WHERE d.family=? AND d.engine=?"
    if ids is None:
        return {r[0]: json.loads(r[1]) for r in db.execute(query, (family, engine(family)))}
    result = {}
    for part in split(ids):
        result.update({r[0]: json.loads(r[1]) for r in db.execute(query + ' AND d.entity_id IN (' + ','.join('?' * len(part)) + ')', (family, engine(family), *part))})
    return result


def version_categories(db):
    """Primary category of every saved version, for the history chart."""
    rows = db.execute("SELECT entity_id,content_hash,json_extract(value,'$.primary') FROM vacancy_derived WHERE family='taxonomy' AND engine=?", (engine('taxonomy'),))
    return {(r[0], r[1]): r[2] for r in rows}


def status(archive):
    with archive.connect() as db:
        total = db.execute("SELECT COUNT(*) FROM entities WHERE kind='vacancy'").fetchone()[0]
        missing = {}
        for family, versions in PLAN:
            table, key = ('versions', 'entity_id') if versions else ('entities', 'id')
            columns = 'DISTINCT v.entity_id,v.content_hash' if versions else 'v.id'
            missing[family + ('_versions' if versions else '')] = db.execute('SELECT COUNT(*) FROM (SELECT ' + columns + ' FROM ' + table + ' v LEFT JOIN vacancy_derived d ON d.entity_id=v.' + key + " AND d.content_hash=v.content_hash AND d.family=? AND d.engine=? WHERE v.kind='vacancy' AND d.entity_id IS NULL)", (family, engine(family))).fetchone()[0]
    return {'total': total, 'missing': missing, 'rows_ready': not (missing['basic'] or missing['taxonomy']), 'history_ready': not missing['taxonomy_versions']}


def warm(archive, stop=None, pause=0.02):
    """Prepare everything in small steps, yielding so the service stays responsive."""
    done = 0
    for family, versions in PLAN:
        while not (stop and stop.is_set()):
            with archive.connect() as db:
                count = ensure(db, family, versions=versions, limit=BATCH)
            done += count
            if not count:
                break
            time.sleep(pause)
    return done


class Warmer:
    """At most one background preparation, started on demand and on a slow timer."""

    def __init__(self, archive_factory):
        self.factory = archive_factory
        self.stop = threading.Event()
        self.task = None

    def kick(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())
        return self.task

    async def _run(self):
        try:
            await asyncio.to_thread(warm, self.factory(), self.stop)
        except Exception as error:
            # Requests still compute what they need. Vacancy text never enters logs.
            logging.getLogger(__name__).error('derived preparation failed: %s', type(error).__name__)

    async def scheduler(self, period=30):
        try:
            while True:
                await self.kick()
                await asyncio.sleep(period)
        finally:
            self.stop.set()
