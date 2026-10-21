"""Durable supervised preparation, shared by clients. Never approves or submits."""
import json,time,secrets
from .application_workflow import packed,hashed

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS application_preparations(id TEXT PRIMARY KEY,app_id TEXT,request_id TEXT UNIQUE,context_hash TEXT,revision INTEGER,mode TEXT,state TEXT,result TEXT,updated REAL)')

def enqueue(service,app_id,request_id,mode='offline',expected_revision=None):
    if mode not in ('api','offline'):raise ValueError('Выберите режим API или без API.')
    if not isinstance(request_id,str) or not 1<=len(request_id)<=100:raise ValueError('Нужен идентификатор подготовки.')
    service.store.validate_current(app_id);app=service.store.workflow(app_id)
    service.store._blocked_edit(app['workflow'])
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM application_preparations WHERE request_id=?',(request_id,)).fetchone()
        if old:
            if old['app_id']!=app_id or old['mode']!=mode:raise ValueError('Запрос уже относится к другой подготовке.')
            return view(old)
        if expected_revision is not None and app['workflow']['revision']!=expected_revision:raise ValueError('Письмо изменилось. Откройте карточку и проверьте новую версию перед подготовкой.')
        old=db.execute("SELECT * FROM application_preparations WHERE app_id=? AND state IN ('queued','analyzing','drafting')",(app_id,)).fetchone()
        if old:return view(old)
        identifier=secrets.token_hex(12)
        db.execute('INSERT INTO application_preparations VALUES(?,?,?,?,?,?,?,?,?)',(identifier,app_id,request_id,hashed(app['context']),app['workflow']['revision'],mode,'queued','{}',time.time()))
        return view(db.execute('SELECT * FROM application_preparations WHERE id=?',(identifier,)).fetchone())

def view(row):return {**dict(row),'result':json.loads(row['result'] or '{}')}

def advance(service,*,analyzer=None,drafter=None):
    store=service.store
    with store.connect() as db:
        waiting=db.execute("SELECT * FROM application_preparations WHERE state='waiting_chrome'").fetchall()
        for item in waiting:
            payload=json.loads(item['result'] or '{}');command=db.execute('SELECT state,result FROM browser_commands WHERE id=?',(payload.get('command_id'),)).fetchone()
            if command and command['state'] not in ('queued','running'):
                form=db.execute('SELECT form FROM application_workflow WHERE app_id=?',(item['app_id'],)).fetchone()
                state='awaiting_approval' if command['state']=='complete' and form and form['form'] else 'needs_input'
                db.execute('UPDATE application_preparations SET state=?,updated=? WHERE id=?',(state,time.time(),item['id']))
    # A crash after a model request is ambiguous: ask for reconciliation, never
    # repeat a potentially billed call after restart.
    with store.connect() as db:
        db.execute("UPDATE application_preparations SET state='needs_input',result=?,updated=? WHERE state IN ('analyzing','drafting') AND updated<?",(packed({'note':'Подготовка прервана. Проверьте сохранённые разбор и письмо; платный запрос автоматически не повторяется.'}),time.time(),time.time()-300))
        db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
        row=db.execute("SELECT * FROM application_preparations WHERE state='queued' ORDER BY updated LIMIT 1").fetchone()
        if not row:return None
        db.execute("UPDATE application_preparations SET state='analyzing',updated=? WHERE id=? AND state='queued'",(time.time(),row['id']))
    result={};state='needs_input'
    try:
        store.validate_current(row['app_id']);app=store.workflow(row['app_id']);ctx=app['context']
        if hashed(ctx)!=row['context_hash'] or app['workflow']['revision']!=row['revision']:raise ValueError('CV, цель или письмо изменились. Проверьте новую версию перед подготовкой.')
        if row['mode']=='offline':
            from .external_prompt import build_prompt
            prompt=build_prompt(ctx,'discuss',comments='Подготовь короткое сопроводительное письмо по подтверждённым фактам CV. Не придумывай опыт. Сначала укажи существенные пробелы и вопросы.',draft=app['workflow']['draft'],history=app['discussion'])
            result={'prompt':prompt,'note':'Промпт готов. Скопируйте в ChatGPT, затем вставьте письмо в эту карточку. API модели не вызывался.','api_requests':0};state='awaiting_user'
        else:
            from .skill_analysis import analyze
            from .application_conversation import discuss
            analysis=(analyzer or analyze)(service.archive,ctx['resume_id'],ctx['vacancy']['id'],ctx.get('goal',''))
            result={'analysis_key':analysis['key'],'analysis_recommendation':analysis.get('recommendation'),'api_requests':analysis.get('api_requests',0)}
            with store.connect() as db:db.execute("UPDATE application_preparations SET state='drafting',result=?,updated=? WHERE id=?",(packed(result),time.time(),row['id']))
            store.validate_current(row['app_id']);current=store.workflow(row['app_id'])
            if current['workflow']['revision']!=row['revision']:raise ValueError('Письмо изменилось во время разбора; автоматическая замена остановлена.')
            draft=(drafter or discuss)(store,row['app_id'],'Составь короткое сопроводительное письмо по фактам CV. Не приписывай опыт. Если данных недостаточно, задай вопросы.','prep-'+row['id'],'luna')
            result.update(note=draft['reply'],needs_user=draft['needs_user'],missing=draft.get('missing',[]),api_requests=result['api_requests']+draft.get('api_requests',0))
            if draft['needs_user'] or not draft.get('draft_applied'):state='awaiting_user'
            elif ctx['channel']=='hh':
                result.update(service.prepare_form(row['app_id']));state='waiting_chrome'
            else:
                state='awaiting_form';result['note']+='\nОткройте вакансию компании → «Откликнуться» → в панели расширения передайте анкету. Затем согласуйте перенос полей в Telegram.'
    except Exception as error:
        result['note']=str(error) if isinstance(error,ValueError) else 'Подготовка не завершена. Проверьте сохранённые результаты; запрос модели автоматически не повторяется.'
    with store.connect() as db:
        db.execute('UPDATE application_preparations SET state=?,result=?,updated=? WHERE id=?',(state,packed(result),time.time(),row['id']))
    return {'id':row['id'],'app_id':row['app_id'],'state':state,'result':result}
