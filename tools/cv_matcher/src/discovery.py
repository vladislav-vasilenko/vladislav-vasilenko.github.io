"""Durable collect -> current CV -> cached/explicit API ranking pipeline."""
import json,time,secrets
from urllib.parse import urlsplit,parse_qs,urlencode
from pathlib import Path
from .board_import import identity

HOSTS={'hh.ru','career.avito.com','ozon.tech','career.ozon.ru','yandex.ru','yandex.com','rabota.sber.ru','tbank.ru','www.tbank.ru','www.google.com','careers.google.com','metacareers.com','www.metacareers.com'}
DEFAULT={'sources':[],'allow_api':False,'model':'text-embedding-3-small','pages':2,'details':40,'tbank_filters':[],'luna_top':0,'transport':'chrome_only'}

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS discovery_runs(id TEXT PRIMARY KEY,digest_key TEXT UNIQUE,state TEXT,payload TEXT,result TEXT,updated REAL)')

def worker_ready(store):
    try:seen=float(store.setting('collection_worker_last_seen') or 0)
    except ValueError:seen=0
    return 0<=time.time()-seen<180


def source_url(value,detail=False):
    if not isinstance(value,str) or len(value)>4000:raise ValueError('Некорректная ссылка вакансии.')
    u=urlsplit(value)
    if u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None,443):raise ValueError('Поддерживаются HTTPS job boards HH, Yandex, Sber, Avito, Ozon, T-Bank.')
    if u.hostname in ('www.google.com','careers.google.com') and not (u.path.startswith('/about/careers/applications/jobs/results') or u.path.startswith('/jobs/results')):raise ValueError('Для Google нужна страница Google Careers.')
    if u.hostname in ('metacareers.com','www.metacareers.com') and not (u.path=='/jobsearch' or u.path=='/jobs' or u.path.startswith('/jobs/')):raise ValueError('Для Meta нужна страница Meta Careers.')
    if detail:
        if not identity(value):raise ValueError('Нужна ссылка на конкретную вакансию.')
    elif u.hostname=='hh.ru':
        if u.path!='/search/vacancy':raise ValueError('Для поиска HH нужна страница выдачи.')
    elif not any(p in u.path for p in ('/jobs','/vacanc','/career','/search')):raise ValueError('Нужна карьерная страница компании.')
    if u.hostname in ('yandex.ru','yandex.com') and u.path=='/jobs/vacancies' and parse_qs(u.query)=={'professions':['ml-developer']}:return u.scheme+'://'+u.netloc+'/jobs/professions/ml-developer'
    return value

def config(store,data=None):
    if data is None:return {**DEFAULT,**json.loads(store.setting('discovery_config') or '{}')}
    c={**DEFAULT,**data}
    from .hybrid_collection import MODES
    if c['transport'] not in MODES:raise ValueError('Выберите Python, Chrome или гибридный порядок сбора.')
    if type(c['allow_api']) is not bool or c['model'] not in ('text-embedding-3-small','text-embedding-3-large'):raise ValueError('Проверьте режим и модель embeddings.')
    if not isinstance(c['sources'],list) or len(c['sources'])>6:raise ValueError('До шести источников за запуск.')
    c['sources']=list(dict.fromkeys(source_url(u) for u in c['sources']))
    if not isinstance(c['tbank_filters'],list) or len(c['tbank_filters'])>20 or any(not isinstance(v,str) or not 1<=len(v.strip())<=100 for v in c['tbank_filters']):raise ValueError('Фильтры T-Bank: до 20 названий видимых флажков.')
    c['tbank_filters']=list(dict.fromkeys(v.strip() for v in c['tbank_filters']))
    if type(c['pages']) is not int or not 1<=c['pages']<=5 or type(c['details']) is not int or not 1<=c['details']<=100:raise ValueError('Лимиты: 1–5 страниц, 1–100 описаний.')
    if type(c['luna_top']) is not int or not 0<=c['luna_top']<=10 or c['luna_top'] and not c['allow_api']:raise ValueError('Разбор Luna: 0–10 вакансий; платный режим должен быть явно включён.')
    for field in ('max_pages','max_details'):
        if field in c and (type(c[field]) is not int or not 1<=c[field]<=(100 if field=='max_pages' else 2000)):raise ValueError('Проверьте общий лимит сбора.')
    c={k:c[k] for k in (*DEFAULT,'max_pages','max_details') if k in c};store.setting('discovery_config',json.dumps(c));return c

def read(store,identifier):
    with store.connect() as db:r=db.execute('SELECT * FROM discovery_runs WHERE id=?',(identifier,)).fetchone()
    if not r:raise ValueError('Запуск поиска не найден.')
    return {**dict(r),'payload':json.loads(r['payload']),'result':json.loads(r['result'] or '{}')}

def start(store,archive,key,scope=None):
    summary=archive.summary();rid=summary.get('primary_id')
    if not rid:raise ValueError('Сначала выберите резюме и синхронизируйте его с архивом.')
    cv=archive.detail('resume',rid)['payload'];c=config(store)
    from .career_search_scope import validate,sources as scoped_sources,goal as scoped_goal
    scope=validate(scope,archive)
    with store.connect() as db:
        old=db.execute('SELECT id FROM discovery_runs WHERE digest_key=?',(key,)).fetchone()
        if old:
            prior=read(store,old[0])
            if validate(prior['payload'].get('scope'),archive)!=scope:raise ValueError('Идентификатор поиска уже использован с другими условиями.')
            return prior
    default='https://hh.ru/search/vacancy?'+urlencode({'resume':rid}) if cv.get('source_type','hh')=='hh' else 'https://hh.ru/search/vacancy?'+urlencode({'text':summary.get('goal') or cv['title']})
    sources=scoped_sources(scope,archive) or c['sources'] or [default]
    # A configured recommendation URL always follows the currently selected HH CV.
    sources=[source_url(default if urlsplit(u).hostname=='hh.ru' and parse_qs(urlsplit(u).query).get('resume') else u) for u in sources]
    identifier=secrets.token_hex(12);p={'resume_id':rid,'goal':summary.get('goal',''),'ranking_goal':scoped_goal(summary.get('goal',''),scope),'scope':scope,'config':c,'sources':sources,'index':0,'ids':[],'warnings':[]}
    with store.connect() as db:db.execute('INSERT INTO discovery_runs VALUES(?,?,?,?,?,?)',(identifier,key,'collecting',json.dumps(p),None,time.time()))
    queue_source(store,identifier,p)
    return read(store,identifier)

def page_number(url):
    try:value=int(parse_qs(urlsplit(url).query).get('page',['0'])[0])
    except (ValueError,TypeError):raise ValueError('Некорректная страница выдачи.') from None
    if not 0<=value<=100000:raise ValueError('Некорректная страница выдачи.')
    return value

def queue_source(store,identifier,p):
    # Read-only jobs may retry; ranking/LLM calls never occur in the Chrome worker.
    payload={'run_id':identifier,'source_url':p.get('cursor') or p['sources'][p['index']],'resume_id':p['resume_id'],'refresh_cv':not p.get('cv_refreshed',False),'options':{'pages':p['config']['pages'],'details':p['config']['details'],'tbank_filters':p['config'].get('tbank_filters',[]),'skip_closed':True,'attempted_ids':p.get('source_attempted',[])}}
    from .career_search_scope import search_terms
    payload['options']['search_terms']=search_terms(p.get('scope',{}),p.get('ranking_goal',p['goal']))
    from .hybrid_collection import prepare
    payload=prepare(payload,p['config'].get('transport','chrome_only'))
    cfg=p['config'];max_details=cfg.get('max_details',cfg['details'] if cfg['allow_api'] else 1000)
    current_page=page_number(payload['source_url'])
    max_pages=cfg.get('max_pages',cfg['pages'] if cfg['allow_api'] else 20)
    payload['options']['pages']=min(cfg['pages'],max(1,max_pages-current_page))
    payload['options']['listing_budget']=max_pages
    payload['options']['details']=min(cfg['details'],max(1,max_details-len(p.get('source_attempted',[]))))
    from .application_workflow import packed
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        active=db.execute('SELECT state FROM discovery_runs WHERE id=?',(identifier,)).fetchone()
        if not active or active[0] not in ('collecting','waiting_chrome'):return
        existing=db.execute("SELECT id FROM browser_commands WHERE kind='discover' AND payload=? AND state IN ('queued','running')",(packed(payload),)).fetchone()
        command=existing[0] if existing else secrets.token_hex(12)
        if not existing:db.execute('INSERT INTO browser_commands VALUES(?,NULL,?,?,?,NULL,?,?,NULL)',(command,'discover',packed(payload),'queued',time.time(),time.time()))
        p['command_id']=command
        db.execute('UPDATE discovery_runs SET state=?,payload=?,updated=? WHERE id=?',('collecting' if payload.get('collection_transport')=='python' or worker_ready(store) else 'waiting_chrome',json.dumps(p),time.time(),identifier))

def advance(store,archive,identifier,root,ranker=None,analyzer=None):
    run=read(store,identifier)
    if run['state'] in ('pause_requested','cancel_requested'):
        p=run['payload']
        with store.connect() as db:cmd=db.execute('SELECT state,result,updated FROM browser_commands WHERE id=?',(p.get('command_id'),)).fetchone()
        if cmd and cmd['state']=='running' and time.time()-cmd['updated']<300:return run
        if cmd and cmd['result']:
            p['ids']=list(dict.fromkeys(p['ids']+json.loads(cmd['result']).get('ids',[])))[:12000]
        with store.connect() as db:
            if cmd and cmd['state']=='running':db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE id=? AND state='running'",(time.time(),p.get('command_id')))
            db.execute('UPDATE discovery_runs SET state=?,payload=?,updated=? WHERE id=? AND state=?',('paused' if run['state']=='pause_requested' else 'cancelled',json.dumps(p),time.time(),identifier,run['state']))
        return read(store,identifier)
    if run['state']=='ranking_ready':
        with store.connect() as db:changed=db.execute("UPDATE discovery_runs SET state='ranking',updated=? WHERE id=? AND state='ranking_ready'",(time.time(),identifier)).rowcount
        return rank_run(store,archive,identifier,root,ranker,analyzer) if changed else read(store,identifier)
    if run['state']=='ranking' and time.time()-run['updated']>300:
        with store.connect() as db:db.execute("UPDATE discovery_runs SET state='needs_input',result=? WHERE id=? AND state='ranking'",(json.dumps({**run['result'],'note':'Пересчёт прерван. Проверьте историю рейтингов; платный запрос автоматически не повторяется.'}),identifier))
        return read(store,identifier)
    if run['state'] not in ('collecting','waiting_chrome'):return run
    p=run['payload']
    if not p.get('command_id'):queue_source(store,identifier,p);return read(store,identifier)
    from .hybrid_collection import fallback,merged_result
    routed=fallback(store,p['command_id'])
    if p['command_id']!=routed['id']:
        p['command_id']=routed['id']
        with store.connect() as db:db.execute("UPDATE discovery_runs SET payload=? WHERE id=? AND state IN ('collecting','waiting_chrome')",(json.dumps(p),identifier))
    with store.connect() as db:cmd=db.execute('SELECT state,result,created,updated FROM browser_commands WHERE id=?',(p['command_id'],)).fetchone()
    if not cmd:raise ValueError('Потеряна задача сбора.')
    if cmd['state']=='queued':
        # Queue time is not work time: sleeping/offline Chrome may return tomorrow.
        target='collecting' if routed['payload'].get('collection_transport')=='python' or worker_ready(store) else 'waiting_chrome'
        with store.connect() as db:db.execute("UPDATE discovery_runs SET state=? WHERE id=? AND state IN ('collecting','waiting_chrome')",(target,identifier))
        return read(store,identifier)
    if cmd['state']=='running':
        if time.time()-cmd['updated']<300:return run
        # A read-only executor disappeared (sleep/MV3 crash). Preserve the old
        # receipt identity, queue a fresh read, and never retry model/write work.
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute("UPDATE discovery_runs SET state='waiting_chrome' WHERE id=? AND state IN ('collecting','waiting_chrome')",(identifier,)).rowcount
            if not changed:return read(store,identifier)
            db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE id=? AND state='running'",(time.time(),p['command_id']))
            p.pop('command_id',None);db.execute('UPDATE discovery_runs SET payload=?,updated=? WHERE id=?',(json.dumps(p),time.time(),identifier))
        queue_source(store,identifier,p);return read(store,identifier)
    result=merged_result(routed)
    # A finished receipt remains usable after sleep, irrespective of heartbeat.
    with store.connect() as db:db.execute("UPDATE discovery_runs SET state='collecting' WHERE id=? AND state='waiting_chrome'",(identifier,))
    p['ids']=list(dict.fromkeys(p['ids']+result.get('ids',[])))[:12000]
    if cmd['state']=='complete' and routed['payload'].get('collection_transport','chrome')=='chrome':p['cv_refreshed']=True
    try:
        continuation=result.get('continuation')
        if cmd['state']=='complete' and continuation and not result.get('note','').lower().startswith(('hh ограничил','captcha')):
            progress=result.get('progress') or {};old_attempted=set(p.get('source_attempted',[]))
            attempts=result.get('attempted_ids',[])
            if not isinstance(attempts,list) or any(not isinstance(v,str) for v in attempts):raise ValueError('Некорректный checkpoint чтения.')
            p['source_attempted']=list(dict.fromkeys([*p.get('source_attempted',[]),*attempts]))[:2000]
            cfg=p['config'];max_pages=cfg.get('max_pages',cfg['pages'] if cfg['allow_api'] else 20);max_details=cfg.get('max_details',cfg['details'] if cfg['allow_api'] else 1000)
            current=p.get('cursor') or p['sources'][p['index']]
            from urllib.parse import urlsplit,parse_qsl,urlunsplit
            page=page_number(current);p['source_pages']=max(p.get('source_pages',0),page+int(continuation.get('listing_pages',0)))
            remaining=int(continuation.get('remaining',0));next_url=continuation.get('next_url')
            if not 0<=remaining<=100000:raise ValueError('Некорректный остаток.')
            target=current if remaining and set(attempts)-old_attempted else next_url
            if target:
                source_url(target)
                a=urlsplit(current);b=urlsplit(target)
                comparable=lambda u:sorted((k,v) for k,v in parse_qsl(u.query) if k not in ('page','from','hhtmFrom','search_session_id'))
                if a.scheme!=b.scheme or a.netloc!=b.netloc or a.path!=b.path or comparable(a)!=comparable(b):raise ValueError('Продолжение изменило источник или фильтры.')
            budget=len(p['source_attempted'])<max_details and (target==current or p['source_pages']<max_pages)
            if target and budget and result.get('coverage') not in ('failed','stopped'):
                p['cursor']=target;p['packets']=p.get('packets',0)+1
                if p['packets']<=100:
                    queue_source(store,identifier,p);return read(store,identifier)
            if target:p['warnings'].append('Достигнут общий лимит сбора: '+str(max_pages)+' страниц / '+str(max_details)+' описаний. Сохранено прочитанное; можно продолжить отдельным запуском.')
            elif result.get('coverage')=='partial' and result.get('warnings'):
                p['warnings'].append('Не удалось прочитать описаний: '+str(progress['failed'])+'. Повтор в этом поиске не выполняется.' if progress.get('failed') else result.get('note') or 'Источник прочитан частично.')
        elif cmd['state']!='complete' or result.get('warnings'):p['warnings'].append(result.get('note') or '; '.join(result.get('warnings',[])) or 'Источник не прочитан полностью.')
    except (ValueError,TypeError,AttributeError,KeyError):
        p['warnings'].append('Продолжение источника отклонено: некорректный checkpoint или изменились фильтры. Прочитанные данные сохранены.')
    for key in ('cursor','source_attempted','source_pages','packets'):p.pop(key,None)
    p['index']+=1
    if p['index']<len(p['sources']):queue_source(store,identifier,p);return read(store,identifier)
    # Claim before a paid operation. A crash becomes an explicit reconciliation,
    # never an automatic repeat with potentially another API charge.
    with store.connect() as db:
        changed=db.execute("UPDATE discovery_runs SET state='ranking',payload=?,updated=? WHERE id=? AND state='collecting'",(json.dumps(p),time.time(),identifier)).rowcount
    if not changed:return read(store,identifier)
    return rank_run(store,archive,identifier,root,ranker,analyzer)

def rank_run(store,archive,identifier,root,ranker=None,analyzer=None):
    from .application_workflow import hashed
    run=read(store,identifier);p=run['payload'];checkpoint=p.get('ranking_checkpoint',{})
    outcome=checkpoint.get('outcome') or {'ids':p['ids'],'warnings':p['warnings'],'missing_embeddings':0,'ranked_count':0,'api_requests':0}
    def stopped():
        latest=read(store,identifier)
        if latest['state'] not in ('pause_requested','cancel_requested'):return False
        with store.connect() as db:db.execute('UPDATE discovery_runs SET state=?,payload=?,result=?,updated=? WHERE id=? AND state=?',('paused' if latest['state']=='pause_requested' else 'cancelled',json.dumps(p),json.dumps(outcome),time.time(),identifier,latest['state']))
        return True
    try:
        cv=archive.detail('resume',p['resume_id'])['payload'];current=archive.summary()
        if current['primary_id']!=p['resume_id'] or current.get('goal','')!=p['goal']:raise ValueError('CV или цель поиска изменились. Запустите поиск заново.')
        if checkpoint and checkpoint['resume_hash']!=cv['content_hash']:raise ValueError('Версия CV изменилась во время паузы. Начните новый поиск.')
        jobs=[];excluded={}
        from .career_search_scope import accepts
        for jid in checkpoint.get('job_ids',p['ids']):
            try:
                record=archive.detail('vacancy',jid)
                if record['availability']!='closed' and record['payload'].get('description_quality')=='full' and record['payload'].get('archived') is False:
                    reason=accepts(record['payload'],p.get('scope',{}),archive)
                    if reason:excluded[reason]=excluded.get(reason,0)+1
                    else:jobs.append(record['payload'])
            except ValueError:continue
        outcome['excluded']=excluded
        if not jobs:raise ValueError('Описания сохранены, но не прошли условия поиска. Без даты публикации нельзя подтвердить период: '+str(p.get('scope',{}).get('since_days'))+' дней.' if excluded else 'Нет подтверждённых полных активных описаний после сбора.')
        if checkpoint and checkpoint['jobs_hash']!=hashed(jobs):raise ValueError('Описания изменились во время паузы. Сохранённый рейтинг доступен; начните новый поиск.')
        from .extension_ranking import rank_vacancies,chunks,OpenAIBackend
        if not checkpoint and not p['config']['allow_api'] and ranker is None:
            from .resume_source import CachedEmbeddings,matching_text
            backend=OpenAIBackend(p['config']['model']);backend.allow_api=False
            cache=CachedEmbeddings(backend,Path(root)/'.cache/extension_embeddings',version='extension-ranking-v1',vector_store=archive)
            common=chunks(matching_text(cv))+chunks(p.get('ranking_goal',p['goal']));ready=[]
            for j in jobs:
                try:cache.embed_documents(common+chunks(j['title']+'\n'+j['description']));ready.append(j)
                except ValueError:outcome['missing_embeddings']+=1
            jobs=ready
        p['ranking_checkpoint']={'offset':checkpoint.get('offset',0),'outcome':outcome,'resume_hash':cv['content_hash'],'job_ids':[j['id'] for j in jobs],'jobs_hash':hashed(jobs)}
        for offset in range(p['ranking_checkpoint']['offset'],len(jobs),200):
            if stopped():return read(store,identifier)
            result=(ranker or rank_vacancies)({'resume_id':cv['id'],'bundle':{'resumes':[cv]},'vacancies':jobs[offset:offset+200],'goal':p.get('ranking_goal',p['goal']),'model':p['config']['model'],'allow_api':p['config']['allow_api']},Path(root)/'.cache/extension_embeddings',archive=archive)
            for k in ('ranked_count','api_requests'):outcome[k]+=result[k]
            p['ranking_checkpoint']['offset']=offset+len(jobs[offset:offset+200])
            with store.connect() as db:db.execute('UPDATE discovery_runs SET payload=?,result=?,updated=? WHERE id=?',(json.dumps(p),json.dumps(outcome),time.time(),identifier))
        if stopped():return read(store,identifier)
        # Explicit opt-in only. Persist the started marker BEFORE every model
        # request so a restart/pause never silently repeats a billed call.
        count=p['config'].get('luna_top',0) if p['config']['allow_api'] else 0
        if count:
            from .skill_analysis import analyze
            ranked=archive.cached_ranking_items(cv['id'],cv['content_hash'],p.get('ranking_goal',p['goal']),p['config']['model'],jobs)
            selected=sorted(ranked.values(),key=lambda item:-item['score'])[:count]
            ledger=p.setdefault('luna_checkpoint',{})
            for item in selected:
                if stopped():return read(store,identifier)
                if item['id'] in ledger:continue
                ledger[item['id']]={'state':'started'}
                with store.connect() as db:db.execute('UPDATE discovery_runs SET payload=?,updated=? WHERE id=?',(json.dumps(p),time.time(),identifier))
                try:
                    analysis=(analyzer or analyze)(archive,cv['id'],item['id'],p.get('ranking_goal',p['goal']))
                    ledger[item['id']]={'state':'complete','key':analysis['key']}
                    outcome['luna_api_requests']=outcome.get('luna_api_requests',0)+analysis.get('api_requests',0)
                except Exception:
                    ledger[item['id']]={'state':'needs_input'};outcome['warnings'].append('Разбор Luna не завершён для '+item['id']+'. Рейтинг сохранён; платный запрос автоматически не повторяется.')
                with store.connect() as db:db.execute('UPDATE discovery_runs SET payload=?,result=?,updated=? WHERE id=?',(json.dumps(p),json.dumps(outcome),time.time(),identifier))
        state='needs_embeddings' if outcome['missing_embeddings'] else 'complete'
    except Exception as e:
        state='needs_input';outcome['note']=str(e) if isinstance(e,ValueError) else 'Сбор сохранён, пересчёт не завершён. Проверьте сервис.'
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # A concurrent control always wins, including a request during validation.
        latest=db.execute('SELECT state FROM discovery_runs WHERE id=?',(identifier,)).fetchone()[0]
        if latest=='cancel_requested':state='cancelled'
        elif latest=='pause_requested':
            if state!='needs_input':state='paused'
        elif latest!='ranking':return read(store,identifier)
        db.execute('UPDATE discovery_runs SET state=?,payload=?,result=?,updated=? WHERE id=?',(state,json.dumps(p),json.dumps(outcome),time.time(),identifier))
    return read(store,identifier)
