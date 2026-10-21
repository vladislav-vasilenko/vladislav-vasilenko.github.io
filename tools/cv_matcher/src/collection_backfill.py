"""Resumable enrichment of archived links, independent of search and paid ranking."""
import json
import secrets
import time
from collections import Counter
from urllib.parse import urlsplit
from .collection_policy import CHROME_HOSTS, PYTHON_HOSTS, prepare, retry_delay

TERMINAL = ('complete','closed','needs_input','failed','cancelled')


def init(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS collection_backfill_runs(
        id TEXT PRIMARY KEY,state TEXT NOT NULL,mode TEXT NOT NULL,created REAL,updated REAL);
    CREATE TABLE IF NOT EXISTS collection_backfill_items(
        run_id TEXT NOT NULL,vacancy_id TEXT NOT NULL,source_url TEXT NOT NULL,
        host TEXT NOT NULL,state TEXT NOT NULL,command_id TEXT,attempts INTEGER NOT NULL DEFAULT 0,
        next_at REAL NOT NULL DEFAULT 0,reason TEXT NOT NULL DEFAULT '',updated REAL,
        PRIMARY KEY(run_id,vacancy_id));
    CREATE TABLE IF NOT EXISTS collection_source_health(host TEXT PRIMARY KEY,blocked_until REAL NOT NULL DEFAULT 0,reason TEXT NOT NULL DEFAULT '',failures INTEGER NOT NULL DEFAULT 0,updated REAL);
    CREATE INDEX IF NOT EXISTS collection_backfill_pending ON collection_backfill_items(run_id,state,next_at);''')


def start(store, *, mode=None):
    from .discovery import config
    mode=mode or config(store)['transport']
    # Validate even an empty archive/config before committing a run.
    prepare({'source_url':'https://career.avito.com/vacancies/'},mode)
    stamp=time.time()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute("SELECT id FROM collection_backfill_runs WHERE state IN ('running','paused') ORDER BY created DESC LIMIT 1").fetchone()
        if old: identifier=old[0]
        else:
            identifier=secrets.token_hex(12)
            db.execute('INSERT INTO collection_backfill_runs VALUES(?,?,?,?,?)',(identifier,'running',mode,stamp,stamp))
            # Explicit user retry begins a new bounded source attempt.
            db.execute('UPDATE collection_source_health SET blocked_until=0,failures=0,reason=?', ('',))
            for row in db.execute("SELECT id,payload,availability FROM entities WHERE kind='vacancy'").fetchall():
                payload=json.loads(row['payload']);url=payload.get('link','');host=urlsplit(url).hostname
                if payload.get('description_quality')=='full' or row['availability']=='closed': continue
                state='pending';reason=''
                try:prepare({'source_url':url,'vacancy_id':row['id']},mode)
                except ValueError:state='needs_input';reason='unsupported_transport'
                db.execute('INSERT INTO collection_backfill_items VALUES(?,?,?,?,?,NULL,0,0,?,?)',(identifier,row['id'],url,host or '',state,reason,stamp))
    return status(store,identifier)


def status(store, identifier=None):
    with store.connect() as db:
        row=db.execute('SELECT * FROM collection_backfill_runs '+('WHERE id=?' if identifier else 'ORDER BY created DESC LIMIT 1'),(identifier,) if identifier else ()).fetchone()
        if not row:return {'run':None,'counts':{},'sources':[],'issues':[]}
        items=[dict(r) for r in db.execute('SELECT * FROM collection_backfill_items WHERE run_id=?',(row['id'],))]
        counts=Counter(r['state'] for r in items);sources={}
        for item in items:sources.setdefault(item['host'],Counter())[item['state']]+=1
        protocol=db.execute("SELECT value FROM settings WHERE key='collection_worker_protocol'").fetchone()
        return {'run':dict(row),'counts':dict(counts),'total':len(items),'sources':[{'host':host,'counts':dict(value)} for host,value in sorted(sources.items())],
            'chrome_requires_update':any(r['state']=='reading' and r['host']=='hh.ru' for r in items) and (not protocol or int(protocol[0])<2),
            'issues':[{'vacancy_id':r['vacancy_id'],'source_url':r['source_url'],'state':r['state'],'reason':r['reason'],'attempts':r['attempts']} for r in items if r['state'] in ('needs_input','failed')][:30]}


def control(store, identifier, action):
    if action not in ('pause','resume','cancel'):raise ValueError('Доступны pause, resume, cancel.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        run=db.execute('SELECT state FROM collection_backfill_runs WHERE id=?',(identifier,)).fetchone()
        if not run:raise ValueError('Дозагрузка не найдена.')
        if run[0] not in ('running','paused'):return status(store,identifier)
        state={'pause':'paused','resume':'running','cancel':'cancelled'}[action]
        db.execute('UPDATE collection_backfill_runs SET state=?,updated=? WHERE id=?',(state,time.time(),identifier))
        if state=='cancelled':
            db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE state='queued' AND json_extract(payload,'$.backfill_run')=?",(time.time(),identifier))
            db.execute("UPDATE collection_backfill_items SET state='cancelled',updated=? WHERE run_id=? AND state IN ('pending','retry','reading')",(time.time(),identifier))
    return status(store,identifier)


def tick(store, archive, *, now=None):
    """Reconcile receipts, then enqueue a bounded window; one read per source."""
    from .hybrid_collection import fallback, merged_result
    now=time.time() if now is None else now
    with store.connect() as db:
        run=db.execute("SELECT * FROM collection_backfill_runs WHERE state='running' ORDER BY created LIMIT 1").fetchone()
        if not run:return
        items=[dict(r) for r in db.execute('SELECT * FROM collection_backfill_items WHERE run_id=?',(run['id'],))]
    for item in items:
        if item['state'] in TERMINAL: continue
        detail=archive.detail('vacancy',item['vacancy_id'])
        state='closed' if detail['availability']=='closed' else 'complete' if detail['payload'].get('description_quality')=='full' else None
        command=None;reason='';next_at=0
        if not state and item['command_id']:
            command=fallback(store,item['command_id'])
            if command['state'] not in ('queued','running'):
                result=merged_result(command);reason=result.get('reason') or ('incomplete_descriptions' if command['state']=='complete' else 'transport_failed')
                if result.get('coverage')=='stopped':state='pending'
                else:
                    delay=retry_delay(reason,item['attempts'])
                    state='retry' if delay is not None else 'needs_input'
                    next_at=now+delay if delay is not None else 0
        if state:
            with store.connect() as db:
                if state in ('complete','closed'):
                    db.execute('DELETE FROM collection_source_health WHERE host=?',(item['host'],))
                elif reason=='http_rate_limited':
                    old=db.execute('SELECT failures FROM collection_source_health WHERE host=?',(item['host'],)).fetchone()
                    failures=(old[0] if old else 0)+1
                    db.execute('INSERT OR REPLACE INTO collection_source_health VALUES(?,?,?,?,?)',(item['host'],now+min(1800,60*3**min(failures-1,3)),reason,failures,now))
                    if failures>=3:reason='access_required';state='needs_input'
                if reason in ('access_required','login_required','unsupported_layout'):
                    db.execute("UPDATE collection_backfill_items SET state='needs_input',reason=?,updated=? WHERE run_id=? AND host=? AND state IN ('pending','retry')",(reason,now,run['id'],item['host']))
                db.execute("UPDATE collection_backfill_items SET state=?,command_id=NULL,reason=?,next_at=?,updated=? WHERE run_id=? AND vacancy_id=? AND state NOT IN ('cancelled','complete','closed')",(state,reason,next_at,now,run['id'],item['vacancy_id']))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT state FROM collection_backfill_runs WHERE id=?',(run['id'],)).fetchone()
        if current[0]!='running':return
        active=[dict(r) for r in db.execute("SELECT * FROM collection_backfill_items WHERE run_id=? AND state='reading'",(run['id'],))]
        hosts={r['host'] for r in active};capacity=max(0,3-len(active))
        candidates=db.execute("SELECT * FROM collection_backfill_items WHERE run_id=? AND state IN ('pending','retry') AND next_at<=? ORDER BY attempts,host,vacancy_id",(run['id'],now)).fetchall()
        for item in candidates:
            if not capacity:break
            if item['host'] in hosts:continue
            cooling=db.execute('SELECT blocked_until FROM collection_source_health WHERE host=?',(item['host'],)).fetchone()
            if cooling and cooling[0]>now:continue
            # Recheck current text in this transaction: a manual import wins.
            saved=db.execute("SELECT payload FROM entities WHERE kind='vacancy' AND id=?",(item['vacancy_id'],)).fetchone()
            if saved and json.loads(saved[0]).get('description_quality')=='full':
                db.execute("UPDATE collection_backfill_items SET state='complete',updated=? WHERE run_id=? AND vacancy_id=?",(now,run['id'],item['vacancy_id']));continue
            payload=prepare({'source_url':item['source_url'],'vacancy_id':item['vacancy_id'],'backfill_run':run['id']},run['mode'])
            # Reuse a matching in-flight manual read instead of opening it twice.
            existing=db.execute("SELECT id FROM browser_commands WHERE kind='collect' AND state IN ('queued','running') AND json_extract(payload,'$.vacancy_id')=? ORDER BY created LIMIT 1",(item['vacancy_id'],)).fetchone()
            identifier=existing[0] if existing else secrets.token_hex(12)
            if not existing:db.execute('INSERT INTO browser_commands VALUES(?,NULL,?,?,?,NULL,?,?,NULL)',(identifier,'collect',json.dumps(payload),'queued',now,now))
            db.execute("UPDATE collection_backfill_items SET state='reading',command_id=?,attempts=attempts+1,updated=? WHERE run_id=? AND vacancy_id=?",(identifier,now,run['id'],item['vacancy_id']))
            hosts.add(item['host']);capacity-=1
        remaining=db.execute("SELECT 1 FROM collection_backfill_items WHERE run_id=? AND state IN ('pending','retry','reading') LIMIT 1",(run['id'],)).fetchone()
        if not remaining:
            issues=db.execute("SELECT 1 FROM collection_backfill_items WHERE run_id=? AND state IN ('needs_input','failed') LIMIT 1",(run['id'],)).fetchone()
            db.execute('UPDATE collection_backfill_runs SET state=?,updated=? WHERE id=?',('needs_input' if issues else 'complete',now,run['id']))
