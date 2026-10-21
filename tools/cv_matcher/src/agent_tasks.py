"""Versioned controls over existing SQLite search runs and browser commands.

An in-flight browser read stops cooperatively. A claimed external write is never
reported as cancelled. Resume creates a NEW browser receipt identity.
"""
import json,time,secrets
from .application_workflow import packed

READS={'discover','collect'}
STATE_LABELS={'waiting_chrome':'Ждём Chrome','queued':'В очереди','running':'Выполняется в Chrome','collecting':'Собираем вакансии','ranking':'Обновляем рейтинг','ranking_ready':'Продолжаем рейтинг','pause_requested':'Останавливаем на безопасной границе','cancel_requested':'Завершаем отмену','paused':'На паузе','cancelled':'Отменено','complete':'Готово','needs_input':'Нужно ваше действие','needs_embeddings':'Нужны embeddings для новых текстов','failed':'Не удалось завершить','submitted':'Отправлено','uncertain':'Нужно сверить результат на сайте'}
TERMINAL={'complete','failed','needs_input','needs_embeddings','submitted','uncertain','cancelled'}

def init(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS agent_task_controls(id TEXT PRIMARY KEY,command_id TEXT,revision INTEGER NOT NULL DEFAULT 0,requested TEXT NOT NULL DEFAULT '',updated REAL);
    CREATE TABLE IF NOT EXISTS agent_task_events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,revision INTEGER,action TEXT,actor TEXT,at REAL);
    CREATE TABLE IF NOT EXISTS career_leases(name TEXT PRIMARY KEY,holder TEXT,expires REAL);''')

def locate(db,task_id):
    if not isinstance(task_id,str) or ':' not in task_id:raise ValueError('Укажите идентификатор задачи search:… или browser:….')
    kind,key=task_id.split(':',1)
    if kind not in ('search','browser'):raise ValueError('Неизвестный тип задачи.')
    old=db.execute('SELECT * FROM agent_task_controls WHERE id=?',(task_id,)).fetchone()
    row=db.execute('SELECT * FROM '+('discovery_runs' if kind=='search' else 'browser_commands')+' WHERE id=?',(old['command_id'] if old and kind=='browser' else key,)).fetchone()
    if not row:raise ValueError('Задача не найдена.')
    db.execute('INSERT OR IGNORE INTO agent_task_controls VALUES(?,?,0,?,?)',(task_id,key,'',time.time()))
    return kind,dict(row),dict(db.execute('SELECT * FROM agent_task_controls WHERE id=?',(task_id,)).fetchone())

def view(kind,row,ctl):
    state=row['state'];p=json.loads(row['payload']);result=json.loads(row['result'] or '{}')
    if kind=='browser' and ctl['requested']:
        state=ctl['requested']+'_requested' if state=='running' and time.time()-row['updated']<300 else ('paused' if ctl['requested']=='pause' else 'cancelled')
    actions=[]
    if kind=='search':
        if state in ('collecting','waiting_chrome','ranking','ranking_ready'):actions=['pause','cancel']
        elif state=='paused':actions=['resume','cancel']
    else:
        if state=='queued':actions=['cancel'] if row['kind'] in ('execute','career_fill','resume_bump') else ['pause','cancel']
        elif state=='running' and row['kind'] in READS:actions=['pause','cancel']
        elif state=='paused':actions=['resume','cancel']
    return {'id':ctl['id'],'kind':kind if kind=='search' else row['kind'],'state':state,'label':('Читаем через Python' if state=='running' and p.get('collection_transport')=='python' else STATE_LABELS.get(state,state)), 'transport':p.get('collection_transport','chrome') if kind=='browser' else None,'next_action':'Задача сохранена. Откройте ноутбук и Chrome с подключённым расширением — продолжим автоматически.' if state=='waiting_chrome' else 'Можно продолжить или отменить задачу.' if state=='paused' else '', 'revision':ctl['revision'],'actions':actions,'updated':row['updated'],'command_id':row['id'] if kind=='browser' else p.get('command_id'),'progress':{'sources_done':p.get('index',0),'sources_total':len(p.get('sources',[])),'collected':len(p.get('ids',result.get('ids',[]))),'ranked':result.get('ranked_count',0)},'note':result.get('note',''),'app_id':row.get('app_id'),'resume_id':p.get('resume_id')}

def get(store,task_id):
    if isinstance(task_id,str) and task_id.startswith('analysis:'):
        from .luna_batch import task
        return task(store,task_id)
    with store.connect() as db:
        kind,row,ctl=locate(db,task_id);task=view(kind,row,ctl)
    from .agent_progress import snapshot
    task['progress'].update(snapshot(store,kind,row));return task

def listing(store):
    with store.connect() as db:
        batches=[r[0] for r in db.execute("SELECT id FROM analysis_batches WHERE state<>'preview' ORDER BY updated DESC LIMIT 30")]
        searches=['search:'+r[0] for r in db.execute('SELECT id FROM discovery_runs ORDER BY updated DESC LIMIT 30')]
        mapped={r['command_id']:r['id'] for r in db.execute("SELECT * FROM agent_task_controls WHERE id LIKE 'browser:%'")}
        roots={v.split(':',1)[1] for v in mapped.values()}
        commands=[mapped.get(r['id'],'browser:'+r['id']) for r in db.execute("SELECT id FROM browser_commands WHERE kind<>'discover' ORDER BY created DESC LIMIT 60") if r['id'] not in roots or mapped.get(r['id'])=='browser:'+r['id']]
        commands.extend(mapped.values())
    return [get(store,i) for i in dict.fromkeys(batches+searches+commands)][:60]

def control(store,task_id,action,revision,*,actor):
    if isinstance(task_id,str) and task_id.startswith('analysis:'):
        from .luna_batch import control as control_batch
        return control_batch(store,task_id,action,revision,actor)
    if action not in ('pause','resume','cancel') or type(revision) is not int:raise ValueError('Нужны pause/resume/cancel и версия задачи.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');kind,row,ctl=locate(db,task_id);current=view(kind,row,ctl)
        if revision!=ctl['revision']:raise ValueError('Задача изменилась. Обновите состояние и повторите действие.')
        if action not in current['actions']:raise ValueError('Действие сейчас недоступно. Начатую отправку нельзя отменить; проверьте результат на сайте.')
        requested=''
        if kind=='search':
            state=row['state'];p=json.loads(row['payload'])
            if action=='resume':
                state='ranking_ready' if p.get('ranking_checkpoint') else 'collecting'
                if state=='collecting':p.pop('command_id',None)
            elif action=='cancel' and state=='paused':state='cancelled'
            elif state in ('ranking','collecting','waiting_chrome'):
                cmd=db.execute('SELECT * FROM browser_commands WHERE id=?',(p.get('command_id'),)).fetchone()
                busy=state=='ranking' or cmd and cmd['state']=='running'
                state=action+'_requested' if busy else ('paused' if action=='pause' else 'cancelled')
                if cmd and cmd['state']=='queued':db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE id=?",(time.time(),cmd['id']))
            else:state='paused' if action=='pause' else 'cancelled'
            db.execute('UPDATE discovery_runs SET state=?,payload=?,updated=? WHERE id=?',(state,packed(p),time.time(),row['id']))
        else:
            if action=='resume':
                # Preserve old receipts; a delayed old worker cannot finish a resumed read.
                command=secrets.token_hex(12)
                db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,NULL,?,?,NULL)',(command,row['app_id'],row['kind'],row['payload'],'queued',time.time(),time.time()))
                db.execute('UPDATE agent_task_controls SET command_id=? WHERE id=?',(command,task_id))
            else:
                requested=action
                if row['state']=='queued':db.execute('UPDATE browser_commands SET state=?,updated=? WHERE id=?',('paused' if action=='pause' else 'cancelled',time.time(),row['id']))
                if row['kind']=='resume_bump':
                    from .resume_bump import saved,put
                    rid=json.loads(row['payload'])['resume_id'];value=saved(db,rid);value.update(blocked=True,note='Автоподнятие этого резюме остановлено владельцем.');put(store,db,rid,value)
                # Revoke any queued write approval before it could be claimed.
                if action=='cancel' and row.get('app_id') and row['kind'] in ('execute','career_fill'):
                    store._invalidate(db,row['app_id'])
                    db.execute("UPDATE application_workflow SET state='needs_approval' WHERE app_id=? AND state IN ('approved','fill_approved')",(row['app_id'],))
        db.execute('UPDATE agent_task_controls SET revision=revision+1,requested=?,updated=? WHERE id=?',(requested,time.time(),task_id))
        db.execute('INSERT INTO agent_task_events(task_id,revision,action,actor,at) VALUES(?,?,?,?,?)',(task_id,revision+1,action,actor,time.time()))
    return get(store,task_id)

def worker_control(store,command_id,worker):
    with store.connect() as db:
        row=db.execute('SELECT * FROM browser_commands WHERE id=? AND worker_id=?',(command_id,worker)).fetchone()
        if not row:raise ValueError('Чтение принадлежит другому исполнителю.')
        if row['kind'] not in READS:return {'stop':False}
        if row['state']!='running':return {'stop':True,'action':'cancel'}
        db.execute('UPDATE browser_commands SET updated=? WHERE id=? AND state=?',(time.time(),command_id,'running'))
        ctl=db.execute('SELECT requested FROM agent_task_controls WHERE command_id=?',(command_id,)).fetchone()
        p=json.loads(row['payload']);run=db.execute('SELECT state FROM discovery_runs WHERE id=?',(p.get('run_id'),)).fetchone()
        action=(ctl[0] if ctl else '') or (run[0].split('_')[0] if run and run[0] in ('pause_requested','cancel_requested','paused','cancelled') else '')
        backfill=db.execute('SELECT state FROM collection_backfill_runs WHERE id=?',(p.get('backfill_run'),)).fetchone()
        if backfill and backfill[0]!='running':action='pause' if backfill[0]=='paused' else 'cancel'
        return {'stop':bool(action),'action':action}
