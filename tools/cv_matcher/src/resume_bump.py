"""Opt-in free HH resume bumps, persisted in the existing settings/Chrome queue.

No publishing, paid promotion or model calls. A claimed click is never replayed.
"""
import json,re,secrets,time
from .application_workflow import packed

INTERVAL=4*3600
CONFIG='hh_resume_bump_config'

def read(db,key,default):
    row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default

def policy(db):return read(db,CONFIG,{'enabled':False,'resume_ids':[],'revision':0})
def saved(db,rid):return read(db,'hh-resume-bump:'+rid,{})
def put(store,db,rid,value):store.setting_in(db,'hh-resume-bump:'+rid,packed(value))

def notify(store,db,command_id,rid,note,raised=False):
    title=next((r['title'] for r in choices(db) if r['id']==rid),rid)
    text=('⬆️ Резюме поднято в поиске HH: ' if raised else '⚠️ Автоподнятие HH требует проверки: ')+title+'\n'+note
    store.enqueue_delivery('resume-bump:'+command_id+(':raised' if raised else ':blocked'),text,[[('Состояние HH','w:menu:status')]],db=db)

def choices(db):
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='entities'").fetchone()
    if not exists:return []
    return [{'id':r['id'],'title':r['title']} for r in db.execute("SELECT id,title,payload FROM entities WHERE kind='resume' ORDER BY title") if re.fullmatch(r'[a-f0-9]{38}',r['id']) and json.loads(r['payload']).get('source_type','hh')=='hh']

def configure(store,value,revision,confirmed=False):
    if not isinstance(value,dict) or type(value.get('enabled')) is not bool or not isinstance(value.get('resume_ids'),list) or type(revision) is not int:raise ValueError('Укажите резюме и версию настроек.')
    ids=value['resume_ids']
    if len(ids)>20 or any(not isinstance(r,str) or not re.fullmatch(r'[a-f0-9]{38}',r) for r in ids) or len(set(ids))!=len(ids):raise ValueError('Выберите до 20 HH-резюме.')
    if value['enabled'] and (not ids or confirmed is not True):raise ValueError('Подтвердите бесплатное поднятие выбранных резюме.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');old=policy(db)
        if old['revision']!=revision:raise ValueError('Настройки изменились. Обновите страницу.')
        if not set(ids)<={r['id'] for r in choices(db)}:raise ValueError('Резюме отсутствует в архиве HH.')
        cfg={'enabled':value['enabled'],'resume_ids':ids,'revision':revision+1}
        store.setting_in(db,CONFIG,packed(cfg))
        db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE kind='resume_bump' AND state='queued'",(time.time(),))
    return status(store)

def status(store,now=None):
    now=time.time() if now is None else now
    with store.connect() as db:
        cfg=policy(db);worker=read(db,'hh_resume_bump_worker',{});ready=worker.get('version')==1 and 0<=now-worker.get('at',0)<180
        pending={json.loads(r['payload'])['resume_id']:r['state'] for r in db.execute("SELECT state,payload FROM browser_commands WHERE kind='resume_bump' AND state IN ('queued','running') ORDER BY created")}
        resumes=[]
        for row in choices(db):
            s=saved(db,row['id']);selected=row['id'] in cfg['resume_ids']
            state='disabled' if not cfg['enabled'] or not selected else 'needs_input' if s.get('blocked') else pending.get(row['id']) or ('waiting_chrome' if not ready else 'cooldown' if s.get('next_at',0)>now else 'scheduled')
            resumes.append({**row,**s,'selected':selected,'state':state})
    return {**cfg,'interval_seconds':INTERVAL,'worker_ready':ready,'resumes':resumes}

def tick(store,now=None):
    now=time.time() if now is None else now
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cfg=policy(db)
        # MV3 suspension after a claim must not create another click.
        for cmd in db.execute("SELECT * FROM browser_commands WHERE kind='resume_bump' AND state='running' AND updated<?",(now-300,)).fetchall():
            rid=json.loads(cmd['payload'])['resume_id'];s=saved(db,rid)
            if s.get('claimed_command')==cmd['id']:
                s.update(blocked=True,note='Результат поднятия не подтверждён. Проверьте резюме на HH перед новой попыткой.');put(store,db,rid,s)
                db.execute("UPDATE browser_commands SET state='uncertain' WHERE id=?",(cmd['id'],))
            else:db.execute("UPDATE browser_commands SET state='queued',worker_id=NULL,updated=? WHERE id=?",(now,cmd['id']))
        for cmd in db.execute("SELECT id,payload FROM browser_commands WHERE kind='resume_bump' AND state='uncertain' AND result IS NULL").fetchall():
            rid=json.loads(cmd['payload'])['resume_id'];s=saved(db,rid)
            notify(store,db,cmd['id'],rid,s.get('note','Результат не подтверждён. Проверьте HH перед новой попыткой.'))
        if not cfg['enabled']:return
        for rid in cfg['resume_ids']:
            s=saved(db,rid)
            if s.get('blocked') or s.get('next_at',0)>now:continue
            if db.execute("SELECT 1 FROM browser_commands WHERE kind='resume_bump' AND json_extract(payload,'$.resume_id')=? AND state IN ('queued','running')",(rid,)).fetchone():continue
            db.execute('INSERT INTO browser_commands VALUES(?,NULL,?,?,?,?,?,?,NULL)',(secrets.token_hex(12),'resume_bump',packed({'resume_id':rid,'policy_revision':cfg['revision']}),'queued',None,now,now))

def claim(store,command_id,worker):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cmd=db.execute("SELECT * FROM browser_commands WHERE id=? AND worker_id=? AND kind='resume_bump' AND state='running'",(command_id,worker)).fetchone()
        if not cmd:raise ValueError('Поднятие не принадлежит этому исполнителю.')
        p=json.loads(cmd['payload']);cfg=policy(db);rid=p['resume_id'];s=saved(db,rid)
        if not cfg['enabled'] or rid not in cfg['resume_ids'] or cfg['revision']!=p['policy_revision']:raise ValueError('Разрешение на автоподнятие изменилось.')
        if s.get('blocked') or s.get('next_at',0)>time.time() or s.get('claimed_command')==command_id:raise ValueError('Повторный клик запрещён или ещё действует интервал HH.')
        ctl=db.execute('SELECT requested FROM agent_task_controls WHERE command_id=?',(command_id,)).fetchone()
        if ctl and ctl[0]:raise ValueError('Задача остановлена владельцем.')
        s.update(claimed_command=command_id,claimed_at=time.time());put(store,db,rid,s)
    return {'resume_id':rid,'command_id':command_id,'free_only':True}

def finish(store,command_id,worker,result):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cmd=db.execute("SELECT * FROM browser_commands WHERE id=? AND worker_id=? AND kind='resume_bump'",(command_id,worker)).fetchone()
        if not cmd:raise ValueError('Поднятие не принадлежит этому исполнителю.')
        if cmd['result'] is not None:
            if json.loads(cmd['result'])==result:return {'ok':True,'replayed':True}
            raise ValueError('Результат уже сохранён.')
        if cmd['state'] not in ('running','uncertain'):raise ValueError('Задача уже завершена.')
        p=json.loads(cmd['payload']);rid=p['resume_id'];s=saved(db,rid);outcome=result.get('outcome');claimed=s.get('claimed_command')==command_id
        if result.get('resume_id') not in (None,rid):raise ValueError('Результат относится к другому резюме.')
        if outcome=='raised' and (not claimed or not result.get('evidence') or result.get('source_url')!='https://hh.ru/applicant/profile/me'):raise ValueError('Нет подтверждения бесплатного поднятия выбранного резюме.')
        now=time.time();good=outcome in ('raised','cooldown') and (outcome=='raised' or not claimed)
        s.update(last_checked=now,outcome=outcome or 'needs_input',note=str(result.get('note',''))[:1000],blocked=not good)
        if outcome=='raised':s.update(last_success=now,next_at=now+INTERVAL)
        elif outcome=='cooldown' and not claimed:s.update(next_at=now+900)
        put(store,db,rid,s);state='complete' if good else 'uncertain' if claimed else 'needs_input'
        db.execute('UPDATE browser_commands SET state=?,result=?,updated=? WHERE id=?',(state,packed(result),now,command_id))
        if outcome=='raised' or not good:
            notify(store,db,command_id,rid,s['note'],outcome=='raised')
    return {'ok':True}

def retry(store,rid,confirmed):
    if confirmed is not True:raise ValueError('Сначала проверьте результат на HH.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');s=saved(db,rid)
        if not s.get('blocked'):raise ValueError('Ручная сверка не требуется.')
        if db.execute("SELECT 1 FROM browser_commands WHERE kind='resume_bump' AND state='running' AND json_extract(payload,'$.resume_id')=?",(rid,)).fetchone():raise ValueError('Поднятие ещё выполняется.')
        s.update(blocked=False,note='Результат проверен владельцем; разрешена следующая проверка.');put(store,db,rid,s)
    tick(store);return status(store)
