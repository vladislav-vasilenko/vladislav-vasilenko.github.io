"""Opt-in scoring of newly collected vacancies, under a monthly spending cap.

Off by default, and enabling needs explicit consent. Only vacancies first seen after
the first enabling are scored, so this never starts a backfill of the archive.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from fastapi import HTTPException
from .archive_store import canonical, now_iso
from .career_analytics import snapshot
from .portfolio_visuals import in_sample
from . import spend_guard

KEY = 'auto-scoring'
MODEL = 'text-embedding-3-small'
USD_PER_TOKEN = spend_guard.USD_PER_TOKEN
DEFAULT_CAP = 1.0
MAX_CAP = 20.0
BATCH = 20
RETRY_SECONDS = 3600


def read(archive):
    with archive.connect() as db:
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {'enabled': False, 'monthly_cap_usd': DEFAULT_CAP, 'phase': 'off'}


def write(archive, **changes):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
        state = json.loads(row[0]) if row else {'enabled': False, 'monthly_cap_usd': DEFAULT_CAP, 'phase': 'off'}
        state.update(changes)
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (KEY, canonical(state)))
    return state


def month(now=None):
    return (now or datetime.now(timezone.utc)).strftime('%Y-%m')


def tokens_this_month(state, now=None):
    return state.get('tokens', 0) if state.get('month') == month(now) else 0


def seen_at(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def rows_to_score(archive, state):
    """Same sample and same resume and goal as the published map. Returns (new, older)."""
    from .portfolio_publication import read as read_publication
    sample = (read_publication(archive).get('visual_settings') or {}).get('sample', 'research')
    rows = snapshot(archive, include_history=False, include_evidence=False)['rows']
    since = seen_at(state.get('since')) if state.get('since') else None
    new, older = [], []
    for row in rows:
        if not in_sample(row['category'], sample): continue
        if row['quality'] != 'full' or row['availability'] == 'closed': continue
        if row['similarity'] is not None and row['alignment'] is not None and not row.get('ranking_stale'): continue
        first = seen_at(row.get('first_seen'))
        (new if since and first and first >= since else older).append(row['id'])
    return new, older


def status(archive):
    state = read(archive); tokens = tokens_this_month(state)
    new, older = rows_to_score(archive, state); ledger = spend_guard.read(archive)
    return {**state, 'ceiling_usd': ledger['ceiling_usd'], 'embeddings_spent_usd': spend_guard.spent_usd(ledger), 'max_ceiling_usd': spend_guard.MAX_CEILING, 'history': ledger['history'], 'model': MODEL, 'tokens_this_month': tokens, 'spent_usd': round(tokens * USD_PER_TOKEN, 4), 'max_cap_usd': MAX_CAP, 'pending': len(new), 'older_unscored': len(older)}


def configure(archive, data):
    if type(data.get('enabled')) is not bool: raise ValueError('Укажите, включён ли автоматический расчёт.')
    cap = data.get('monthly_cap_usd', read(archive).get('monthly_cap_usd', DEFAULT_CAP))
    if type(cap) not in (int, float) or not 0.01 <= cap <= MAX_CAP: raise ValueError(f'Лимит должен быть от $0.01 до ${MAX_CAP:.0f} в месяц.')
    if cap > spend_guard.read(archive)['ceiling_usd']: raise ValueError('Лимит автоматического расчёта не может быть выше общего потолка embeddings.')
    state = read(archive); changes = {'enabled': data['enabled'], 'monthly_cap_usd': round(float(cap), 2)}
    if data['enabled']:
        if data.get('confirmed') is not True: raise ValueError('Подтвердите автоматические платные запросы к OpenAI.')
        summary = archive.summary()
        if not summary.get('primary_id') or not str(summary.get('goal') or '').strip(): raise ValueError('Выберите основное резюме и карьерную цель.')
        if not state.get('since'): changes['since'] = now_iso()
        changes.update(phase='waiting', last_error='')
    else:
        changes['phase'] = 'off'
    spend_guard.log(archive, 'auto_on' if data['enabled'] else 'auto_off', cap_usd=changes['monthly_cap_usd'])
    return write(archive, **changes)


def load_batch(archive, ids):
    jobs = []
    for identifier in ids:
        job = archive.detail('vacancy', identifier)
        if job['availability'] != 'closed': jobs.append(job['payload'])
    return jobs


def estimate_tokens(jobs):
    # Deliberately high: Russian and English text both use fewer tokens than chars / 2.
    return sum(len(job.get('title', '')) + len(job.get('description', '')) for job in jobs) // 2


async def run_once(archive, ranker, *, now=None):
    state = await asyncio.to_thread(read, archive)
    if not state.get('enabled'): return state
    from . import archive_embedding_batch as manual
    from .github_collection_import import status as import_status
    current = await asyncio.to_thread(manual.read, archive)
    if current and current['state'] in ('running', 'pausing'): return write(archive, phase='waiting')
    imported = ((await asyncio.to_thread(import_status, archive)).get('last_import') or {}).get('imported_at')
    summary = archive.summary(); goal = str(summary.get('goal') or '').strip(); resume_id = summary.get('primary_id')
    changes = {'last_run_at': time.time(), 'seen_import': imported, 'last_error': ''}
    if month(now) != state.get('month'): changes.update(month=month(now), tokens=0, vacancies=0)
    state = write(archive, **changes)
    if not goal or not resume_id: return write(archive, phase='needs_input', last_error='Выберите основное резюме и карьерную цель.')
    new, _ = await asyncio.to_thread(rows_to_score, archive, state)
    cv = archive.detail('resume', resume_id)
    try:
        for start in range(0, len(new), BATCH):
            state = read(archive)
            if not state.get('enabled'): return state
            jobs = await asyncio.to_thread(load_batch, archive, new[start:start + BATCH])
            if not jobs: continue
            if (state.get('tokens', 0) + estimate_tokens(jobs)) * USD_PER_TOKEN > state['monthly_cap_usd']:
                return write(archive, phase='cap_reached')
            result = await ranker({'resume_id': resume_id, 'bundle': {'resumes': [cv['payload']]}, 'vacancies': jobs, 'goal': goal, 'model': MODEL, 'allow_api': True})
            state = read(archive)
            write(archive, tokens=state.get('tokens', 0) + result.get('usage_tokens', 0), vacancies=state.get('vacancies', 0) + result.get('new_compared', 0))
    except HTTPException as error:
        if error.status_code == 409: return write(archive, phase='waiting')
        return write(archive, phase='error', last_error=str(error.detail)[:400])
    except (ValueError, KeyError, TypeError) as error:
        return write(archive, phase='error', last_error=str(error)[:400])
    return write(archive, phase='idle', last_finished_at=now_iso())


async def scheduler(archive_factory, ranker_factory, period=60):
    from .github_collection_import import status as import_status
    while True:
        await asyncio.sleep(period)
        archive = archive_factory(); state = read(archive)
        if not state.get('enabled'): continue
        imported = ((await asyncio.to_thread(import_status, archive)).get('last_import') or {}).get('imported_at')
        if imported == state.get('seen_import') and time.time() - state.get('last_run_at', 0) < RETRY_SECONDS: continue
        await run_once(archive, ranker_factory())
