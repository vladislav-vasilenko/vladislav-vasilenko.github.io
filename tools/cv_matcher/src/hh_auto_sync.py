"""Periodic read-only HH jobs. SQLite is the clock and the queue, not bot polling."""
import asyncio
import json
import logging
import secrets
import time

DEFAULT = {'enabled': True, 'interval_seconds': 300}


def _config(db):
    row = db.execute("SELECT value FROM settings WHERE key='hh_auto_sync_config'").fetchone()
    return {**DEFAULT, **json.loads(row[0] if row else '{}')}


def config(store, value=None):
    if value is not None:
        if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
            raise ValueError('Укажите, включена ли синхронизация HH.')
        interval = value.get('interval_seconds', 300)
        if type(interval) is not int or not 60 <= interval <= 3600:
            raise ValueError('Интервал синхронизации — от 60 до 3600 секунд.')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            store.setting_in(db, 'hh_auto_sync_config', json.dumps({'enabled': value['enabled'], 'interval_seconds': interval}))
            if not value['enabled']:
                db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE kind='sync' AND state='queued' AND json_extract(payload,'$.automatic')=1", (time.time(),))
    with store.connect() as db:
        return _config(db)


def _status(db, cfg, now):
    capability = db.execute("SELECT value FROM settings WHERE key='hh_auto_sync_worker'").fetchone()
    worker = json.loads(capability[0]) if capability else {}
    ready = worker.get('enabled') is True and 0 <= now - worker.get('at', 0) < 180
    rows = db.execute("SELECT id,state,created,updated,result FROM browser_commands WHERE kind='sync' AND json_extract(payload,'$.automatic')=1 ORDER BY created DESC,rowid DESC LIMIT 6").fetchall()
    pending = next((r for r in rows if r['state'] in ('queued', 'running')), None)
    last = next((r for r in rows if r['state'] not in ('queued', 'running', 'cancelled')), None)
    success = db.execute("SELECT updated FROM browser_commands WHERE kind='sync' AND state='complete' ORDER BY updated DESC LIMIT 1").fetchone()
    failures = 0
    for row in rows:
        if row['state'] in ('queued', 'running', 'cancelled'):
            continue
        if row['state'] == 'complete':
            break
        failures += 1
    due = (last['updated'] + min(3600, cfg['interval_seconds'] * 2 ** min(failures, 3))) if last else 0
    reason = 'disabled' if not cfg['enabled'] else 'waiting_chrome' if not ready else pending['state'] if pending else 'backoff' if failures and now < due else 'scheduled'
    result = json.loads(last['result'] or '{}') if last else {}
    return {**cfg, 'state': reason, 'worker_ready': ready, 'command_id': pending['id'] if pending else None,
            'last_success': success[0] if success else None, 'next_at': due or None,
            'last_error_at':last['updated'] if last and last['state']!='complete' else None,
            'last_error': result.get('note', '') if last and last['state'] != 'complete' else ''}


def status(store, *, now=None):
    with store.connect() as db:
        return _status(db, _config(db), time.time() if now is None else now)


def tick(store, *, now=None):
    """One atomic decision, safe across service restarts and concurrent schedulers."""
    now = time.time() if now is None else now
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        cfg = _config(db)
        # An interrupted browser read is a failed attempt, never a permanently
        # running lock or an immediate replay on every extension restart.
        db.execute("UPDATE browser_commands SET state='failed',result=?,updated=? WHERE kind='sync' AND state='running' AND json_extract(payload,'$.automatic')=1 AND updated<?",(json.dumps({'state':'failed','reason':'hh_sync_timeout','note':'Chrome не завершил чтение откликов. Проверьте вход на HH; новая проверка отложена.'}),now,now-180))
        current = _status(db, cfg, now)
        if not cfg['enabled'] or not current['worker_ready']:
            return current
        pending = db.execute("SELECT id FROM browser_commands WHERE kind='sync' AND state IN ('queued','running') ORDER BY created LIMIT 1").fetchone()
        if pending:
            return {**current, 'state': 'waiting_task', 'command_id': pending['id']}
        if current['next_at'] and now < current['next_at']:
            return current
        identifier = secrets.token_hex(12)
        db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,?,?,?,?)',
                   (identifier, None, 'sync', '{"automatic":true}', 'queued', None, now, now, None))
        return {**current, 'state': 'queued', 'command_id': identifier}


async def run(store_factory, *, period=30):
    while True:
        try:
            await asyncio.to_thread(tick, store_factory())
            from .resume_bump import tick as bump_tick
            await asyncio.to_thread(bump_tick,store_factory())
        except Exception:
            # A transient DB failure must not kill the scheduler or the HTTP service.
            logging.getLogger(__name__).exception('HH read-only scheduler tick failed')
        await asyncio.sleep(period)
