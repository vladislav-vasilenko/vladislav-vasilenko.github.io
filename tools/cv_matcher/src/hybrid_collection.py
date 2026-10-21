"""Read-only transport routing over the existing durable collection queue.

Each fallback has a new command/receipt identity. No ranking, model, application
form or submission belongs to this module.
"""
import json, secrets, time
from urllib.parse import urlsplit
from .application_workflow import packed

from .collection_policy import MODES, CHROME_HOSTS, PYTHON_HOSTS, prepare


def leaf(store, identifier):
    seen = set()
    with store.connect() as db:
        while identifier not in seen and len(seen) < 4:
            seen.add(identifier)
            row = db.execute('SELECT * FROM browser_commands WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise ValueError('Задача сбора не найдена.')
            value = dict(row); value['payload'] = json.loads(value['payload']); value['result'] = json.loads(value['result'] or '{}')
            next_id = value['payload'].get('hybrid_next')
            if not next_id:
                return value
            identifier = next_id
    raise ValueError('Некорректная цепочка способов сбора.')


def failure_reason(command):
    result = command['result']
    if result.get('coverage') == 'stopped' or command['state'] == 'cancelled':
        return None
    if command['state'] in ('failed', 'needs_input'):
        return result.get('reason') or 'transport_failed'
    if command['state'] != 'complete':
        return None
    if not result.get('ids') and not result.get('verified_empty'):
        return 'unverified_empty'
    progress = result.get('progress') or {}
    if progress.get('failed', 0) or progress.get('review', 0):
        return 'incomplete_descriptions'
    return None


def fallback(store, identifier):
    current = leaf(store, identifier)
    reason = failure_reason(current)
    payload = current['payload']; order = payload.get('transport_order', [])
    if not reason or len(order) < 2:
        return current
    transport = payload.get('collection_transport', 'chrome')
    if transport not in order or order.index(transport) + 1 >= len(order):
        return current
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        actual = db.execute('SELECT * FROM browser_commands WHERE id=?', (current['id'],)).fetchone()
        original = json.loads(actual['payload'])
        if original.get('hybrid_next'):
            return leaf(store, original['hybrid_next'])
        if actual['state'] != current['state']:
            return current
        control = db.execute("SELECT requested FROM agent_task_controls WHERE command_id=? AND requested<>''", (current['id'],)).fetchone()
        run = db.execute('SELECT state FROM discovery_runs WHERE id=?', (payload.get('run_id'),)).fetchone()
        backfill=db.execute('SELECT state FROM collection_backfill_runs WHERE id=?',(payload.get('backfill_run'),)).fetchone()
        if control or run and run[0] not in ('collecting', 'waiting_chrome') or backfill and backfill[0]!='running':
            return current
        history = [*payload.get('transport_history', []), {'command_id':current['id'], 'transport':transport, 'reason':reason, 'state':current['state'], 'ids':current['result'].get('ids', []), 'at':time.time()}]
        next_payload = {**payload, 'collection_transport':order[order.index(transport)+1], 'transport_history':history, 'hybrid_root':payload.get('hybrid_root', current['id']), 'hybrid_prior_ids':list(dict.fromkeys([*payload.get('hybrid_prior_ids', []), *current['result'].get('ids', [])]))}
        next_payload.pop('hybrid_next', None)
        next_id = secrets.token_hex(12)
        db.execute('INSERT INTO browser_commands VALUES(?,NULL,?,?,?,NULL,?,?,NULL)', (next_id,current['kind'],packed(next_payload),'queued',time.time(),time.time()))
        original['hybrid_next'] = next_id
        db.execute('UPDATE browser_commands SET payload=? WHERE id=?', (packed(original),current['id']))
        # An existing UI task remains controllable after its executor changes.
        db.execute('UPDATE agent_task_controls SET command_id=?,revision=revision+1,updated=? WHERE command_id=?', (next_id,time.time(),current['id']))
        if current['kind']=='collect':
            root=payload.get('hybrid_root',current['id'])
            db.execute("INSERT OR IGNORE INTO agent_task_controls VALUES(?,?,0,'',?)",('browser:'+root,next_id,time.time()))
    return leaf(store, next_id)


def merged_result(command):
    result = dict(command['result'])
    result['ids'] = list(dict.fromkeys([*command['payload'].get('hybrid_prior_ids', []), *result.get('ids', [])]))
    result['transport'] = command['payload'].get('collection_transport', 'chrome')
    result['transport_history'] = command['payload'].get('transport_history', [])
    return result


def run_pending(store, archive, runner=None):
    """Claim at most one Python read. Chrome cannot claim these commands."""
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # A crashed Python reader is retried only as a bounded read/fallback.
        stale = db.execute("SELECT id FROM browser_commands WHERE state='running' AND worker_id LIKE 'python-collection:%' AND updated<?", (time.time()-150,)).fetchall()
        for row in stale:
            db.execute("UPDATE browser_commands SET state='failed',result=?,updated=? WHERE id=?", (packed({'state':'failed','ids':[],'reason':'python_interrupted','note':'Python-сбор прерван; данные архива сохранены.'}),time.time(),row['id']))
        row = db.execute("""SELECT * FROM browser_commands c WHERE c.state='queued' AND c.kind IN ('collect','discover')
          AND json_extract(c.payload,'$.collection_transport')='python'
          AND NOT EXISTS(SELECT 1 FROM agent_task_controls a WHERE a.command_id=c.id AND a.requested<>'')
          AND NOT EXISTS(SELECT 1 FROM browser_commands busy WHERE busy.state='running' AND json_extract(busy.payload,'$.collection_transport')='python' AND busy.updated>0)
          AND NOT EXISTS(SELECT 1 FROM collection_backfill_runs b WHERE b.id=json_extract(c.payload,'$.backfill_run') AND b.state<>'running')
          AND NOT EXISTS(SELECT 1 FROM discovery_runs d WHERE d.id=json_extract(c.payload,'$.run_id') AND d.state NOT IN ('collecting','waiting_chrome'))
          ORDER BY c.created LIMIT 1""").fetchone()
        if not row:
            return False
        worker = 'python-collection:'+secrets.token_hex(8)
        db.execute("UPDATE browser_commands SET state='running',worker_id=?,updated=? WHERE id=?", (worker,time.time(),row['id']))
        store.setting_in(db,'python_collection_worker_last_seen',str(time.time()))
        command_id = row['id']; payload = json.loads(row['payload'])
    from .agent_tasks import worker_control
    stopped = lambda:worker_control(store, command_id, worker)['stop']
    try:
        from .python_collection import execute, persist
        response = (runner or execute)(payload, stopped)
        if stopped():
            result = {'state':'complete','coverage':'stopped','ids':[],'note':'Сбор остановлен на безопасной границе.'}
        else:
            result = persist(archive, payload, response)
    except Exception as error:
        from .collection_policy import reason_for
        result = {'state':'failed','ids':[],'reason':reason_for(error),'error_type':type(error).__name__,'note':'Python-сбор не завершён. Резервный способ будет выбран по настройке источника.'}
    store.finish_command(command_id, worker, result)
    fallback(store, command_id)
    return True


def tick(store, archive, runner=None):
    with store.connect() as db:
        # A lost Chrome worker must not strand a manual read forever. Live
        # readers renew updated through their cooperative control heartbeat.
        db.execute("UPDATE browser_commands SET state='failed',result=?,updated=? WHERE kind IN ('collect','discover') AND state='running' AND coalesce(json_extract(payload,'$.collection_transport'),'chrome')='chrome' AND updated<?",(packed({'state':'failed','ids':[],'reason':'chrome_interrupted','note':'Chrome перестал подтверждать чтение. Уже сохранённые описания остаются в архиве.'}),time.time(),time.time()-300))
        completed = [row[0] for row in db.execute("SELECT id FROM browser_commands WHERE kind IN ('collect','discover') AND state IN ('complete','failed','needs_input') AND json_array_length(json_extract(payload,'$.transport_order'))>1 AND json_extract(payload,'$.hybrid_next') IS NULL ORDER BY updated DESC LIMIT 50")]
    for identifier in completed:
        fallback(store, identifier)
    return run_pending(store, archive, runner)
