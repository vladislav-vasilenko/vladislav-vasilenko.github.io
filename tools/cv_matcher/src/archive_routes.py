"""Local dashboard, archive, and explicitly requested cached skill reviews."""
import asyncio
import hmac
import json
from pathlib import Path
import secrets
import time
from functools import lru_cache
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from .archive_store import ArchiveStore

ORIGIN='http://127.0.0.1:8788'
class ArchiveAccess:
    def __init__(self):self.codes={};self.sessions={}
    def prune(self):
        now=time.time();self.codes={k:v for k,v in self.codes.items() if v>now};self.sessions={k:v for k,v in self.sessions.items() if v>now}
    def cookie_allowed(self,request):
        self.prune()
        read_paths=('/archive/analytics-batch/','/archive/analytics','/archive/agent','/archive/summary','/archive/entities','/archive/entity/','/archive/diff','/archive/events','/archive/scans','/archive/restore','/archive/export','/archive/rankings','/archive/skill-analysis','/archive/skill-history','/archive/skill-history/','/archive/workflow','/archive/journey','/archive/companies','/archive/company-settings','/archive/calendar/status','/archive/calendar/ics')
        readonly=request.method=='GET' and any(request.url.path==p or (p.endswith('/') and request.url.path.startswith(p)) for p in read_paths)
        readonly=readonly or (request.method=='POST' and request.url.path=='/archive/compare' and request.headers.get('origin') in (None,ORIGIN))
        readonly=readonly or (request.method=='POST' and request.url.path in ('/archive/resume-source','/archive/analytics-batch','/archive/agent','/archive/resume-review','/archive/skill-analysis','/archive/skill-external','/archive/confirm-description','/archive/workflow','/archive/rank','/archive/company-settings','/archive/calendar') and request.headers.get('origin')==ORIGIN)
        return readonly and self.sessions.get(request.cookies.get('archive_session',''),0)>time.time()

def install_archive(app,token,root,path=None):
    root=Path(root);access=ArchiveAccess();app.state.archive_access=access
    # Reuse the application queue's SQLite file instead of introducing another database.
    @lru_cache(maxsize=1)
    def store():
        target=path or root/'.cache/applications/state.sqlite3'
        from .application_store import ApplicationStore
        ApplicationStore(target)
        return ArchiveStore(target)
    app.state.archive_store=store
    from .workflow_routes import install_workflow
    install_workflow(app,token,root)
    skill_lock=asyncio.Lock()
    async def payload(request,limit=8*1024*1024):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>limit:raise HTTPException(413,'Пакет превышает допустимый размер.')
        try:
            data=json.loads(body)
            if not isinstance(data,dict):raise ValueError()
            return data
        except (ValueError,TypeError):raise HTTPException(422,'Нужен JSON-объект.') from None
    async def call(method,*args,**kwargs):
        try:return await asyncio.to_thread(getattr(store(),method),*args,**kwargs)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/')
    @app.get('/archive')
    async def dashboard():
        return FileResponse(root/'archive-web/index.html',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"})
    @app.get('/assets/{name}')
    async def asset(name:str):
        if name in ('resume-portfolio.js','workflow-core.js','workflow-letter.js','workflow-career.js','vacancy-map.js','resume-sources.js','resume-compare.js','resume-compare-core.js','vacancy-selection.js','vacancy-document.js'):return FileResponse(root/'archive-web'/name,headers={'Cache-Control':'no-cache'})
        if name in ('trajectory-badges.js','career-trajectory.js','learning-impact.js','career-analytics.js','career-charts.js','career-skills.js','career-analytics.css'):return FileResponse(root/'archive-web'/name,headers={'Cache-Control':'no-cache'})
        allowed={'intake.js':root/'archive-web/intake.js','resume-profile.js':root/'archive-web/resume-profile.js','resume-profile-core.js':root/'archive-web/resume-profile-core.js','resume-profile.css':root/'archive-web/resume-profile.css','company-settings.js':root/'archive-web/company-settings.js','company-picker.js':root/'archive-web/company-picker.js','crm-planning.js':root/'archive-web/crm-planning.js','workflow.js':root/'archive-web/workflow.js','workflow.css':root/'archive-web/workflow.css','journey.js':root/'archive-web/journey.js','skill-analysis-ui.js':root/'archive-web/skill-analysis-ui.js','archive.js':root/'archive-web/archive.js','archive.css':root/'archive-web/archive.css','chatgpt-export.js':root/'hh-research-extension/chatgpt-export.js'}
        if name not in allowed:raise HTTPException(404)
        return FileResponse(allowed[name],headers={'Cache-Control':'no-cache'})
    @app.post('/archive/open')
    async def open_dashboard(request:Request):
        access.prune();code=secrets.token_urlsafe(32);access.codes[code]=time.time()+60
        data=await payload(request)
        from urllib.parse import urlencode
        options={}
        if data.get('view')=='settings':options['view']='settings'
        if isinstance(data.get('resume_id'),str) and len(data['resume_id'])<180:options['resume_id']=data['resume_id']
        if isinstance(data.get('goal'),str) and len(data['goal'])<=2000:options['goal']=data['goal']
        return {'url':ORIGIN+'/'+('?' + urlencode(options) if options else '')+'#connect='+code}
    @app.post('/archive/login')
    async def login(request:Request):
        if request.headers.get('origin') not in (None,ORIGIN):raise HTTPException(403,'Подключайтесь из локального интерфейса.')
        access.prune();data=await payload(request)
        header=request.headers.get('x-resume-import-token','')
        by_token=bool(header) and hmac.compare_digest(header.encode(),token.encode())
        by_code=access.codes.pop(str(data.get('code','')),0)>time.time()
        if not by_token and not by_code:raise HTTPException(401,'Неверный код или ссылка подключения устарела. Откройте сайт из расширения заново.')
        session=secrets.token_urlsafe(32);access.sessions[session]=time.time()+12*3600
        response=JSONResponse({'ok':True});response.set_cookie('archive_session',session,max_age=12*3600,httponly=True,samesite='strict',path='/archive')
        return response
    @app.post('/archive/manifest')
    async def manifest(request:Request):return await call('manifest',(await payload(request)).get('client_id'))
    @app.post('/archive/sync')
    async def sync(request:Request):
        data=await payload(request);result=await call('sync',data)
        if any(r.get('kind') in ('profile','ranking','resume','vacancy') for r in data.get('records',[])):
            await asyncio.to_thread(store().index_legacy_embeddings,root/'.cache/extension_embeddings')
        return result
    review_locks={}
    @app.post('/archive/resume-review')
    async def resume_review(request:Request):
        from . import resume_review as review
        data=await payload(request)
        try:
            op=data.get('op')
            if op=='prepare_portfolio':
                from .resume_portfolio import prepare
                return await asyncio.to_thread(prepare,store(),data)
            if op=='save_supplement':
                from .resume_supplements import save
                if data.get('confirmed') is not True:raise ValueError('Подтвердите свои факты опыта.')
                return {'items':await asyncio.to_thread(save,store(),data['resume_id'],data['supplement'])}
            if op=='prepare':return await asyncio.to_thread(review.prepare,store(),data['resume_id'],data.get('goal',''),data.get('model','luna'))
            if op=='prompt':
                with store().connect() as db:
                    review.init(db);row=db.execute('SELECT payload FROM resume_review_contexts WHERE key=?',(data['context_key'],)).fetchone()
                if not row:raise ValueError('Сначала подготовьте источники.')
                return {'prompt':review.prompt(json.loads(row[0])),'api_requests':0}
            if op not in ('generate','import'):raise ValueError('Неизвестное действие разбора CV.')
            if op=='import' and not isinstance(data.get('analysis'),dict):raise ValueError('В режиме без API нужен JSON-объект ответа; модель не вызывается.')
            key=data['context_key'];lock=review_locks.setdefault(key,asyncio.Lock())
            if lock.locked():raise ValueError('Этот разбор уже выполняется. Не запускайте повторно.')
            async with lock:return await asyncio.to_thread(review.run,store(),key,raw=data['analysis'] if op=='import' else None,confirmed=data.get('confirmed',False))
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/analytics')
    async def analytics(resume_id:str='',goal:str|None=None,model:str='text-embedding-3-small',q:str='',status:str='',companies:str|None=None):
        from .career_analytics import snapshot
        try:
            data=await asyncio.to_thread(snapshot,store(),resume_id,goal,model)
            if q or status or companies is not None:
                selected=json.loads(companies) if companies is not None else None
                subset=await call('entities','vacancy',q=q,status=status,companies=selected,all_items=True)
                identifiers={r['id'] for r in subset['items']};data['rows']=[r for r in data['rows'] if r['id'] in identifiers]
            return data
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/analytics-batch/{identifier}')
    async def analytics_batch_status(identifier:str):
        from .luna_batch import task
        from .application_store import ApplicationStore
        try:return await asyncio.to_thread(task,ApplicationStore(store().path),identifier)
        except ValueError as error:raise HTTPException(404,str(error)) from None
    @app.post('/archive/analytics-batch')
    async def analytics_batch_action(request:Request):
        from . import luna_batch as batch
        from .application_store import ApplicationStore
        data=await payload(request);applications=ApplicationStore(store().path);archive=store()
        try:
            op=data.get('op')
            if op=='preview':return await asyncio.to_thread(batch.preview,applications,archive,data)
            if op=='start':return await asyncio.to_thread(batch.start,applications,archive,data['plan_id'])
            if op=='export':return await asyncio.to_thread(batch.export_prompt,applications,archive,data['plan_id'])
            if op=='import':return await asyncio.to_thread(batch.import_results,applications,archive,data['plan_id'],data['answer'])
            if op=='control':return await asyncio.to_thread(batch.control,applications,data['batch_id'],data['action'],data['revision'])
            raise ValueError('Выберите предпросмотр, запуск, экспорт, импорт или управление пакетом.')
        except (ValueError,KeyError,TypeError,RecursionError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/summary')
    async def summary():return await call('summary')
    @app.post('/archive/resume-source')
    async def resume_source(request:Request):
        from . import resume_documents as documents
        from .application_store import ApplicationStore
        from .resume_files import MAX_FILE
        data=await payload(request,MAX_FILE*4//3+8192)
        try:
            archive=store();queue=ApplicationStore(archive.path);op=data.get('op')
            if op=='extract_evidence':
                from .resume_evidence import extract
                return await asyncio.to_thread(extract,data)
            if op=='extract':return await asyncio.to_thread(documents.extract,archive,data)
            if op=='google_start':return await asyncio.to_thread(documents.google_start,queue,data.get('url'))
            if op=='google_status':return await asyncio.to_thread(documents.google_status,queue,archive,data.get('command_id'))
            if op=='save':return await asyncio.to_thread(documents.save,archive,data)
            raise ValueError('Неизвестное действие импорта резюме.')
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/entities')
    async def entities(kind:str='vacancy',q:str='',status:str='',offset:int=0,limit:int=50,resume_id:str='',goal:str|None=None,model:str='text-embedding-3-small',company:str='',companies:str|None=None,ranked_only:bool=False,exclude_closed:bool=False,trajectory:str=''):
        try:selected=json.loads(companies) if companies is not None else None
        except ValueError:raise HTTPException(422,'Некорректный список компаний.')
        return await call('entities',kind,q=q,status=status,offset=offset,limit=limit,resume_id=resume_id,goal=goal,model=model,company=company,companies=selected,ranked_only=ranked_only,exclude_closed=exclude_closed,trajectory=trajectory)
    @app.get('/archive/entity/{kind}/{identifier}')
    async def entity(kind:str,identifier:str,resume_id:str='',goal:str|None=None,model:str='text-embedding-3-small',version_id:int|None=None):
        if version_id is not None:
            if kind!='resume':raise HTTPException(422,'Выбор снимка доступен для резюме.')
            return await call('resume_snapshot',identifier,version_id)
        result=await call('detail',kind,identifier,resume_id,goal,model)
        if kind=='vacancy' and resume_id:
            from .vacancy_terms import mentions
            cv=await call('detail','resume',resume_id)
            result['term_mentions']=mentions(cv['payload'],result['payload'].get('description',''))
            result['term_resume']={'id':resume_id,'title':cv['title'],'version_id':cv['version_id']}
        if kind=='resume':
            from .resume_supplements import read
            result['supplements']=await asyncio.to_thread(read,store(),identifier)
            from .candidate_facts import read as read_facts
            result['user_facts']=await asyncio.to_thread(read_facts,store(),identifier)
        return result
    @app.get('/archive/company-settings')
    async def company_settings():
        from .company_catalog import read
        return await asyncio.to_thread(read,store())
    @app.post('/archive/company-settings')
    async def save_company_settings(request:Request):
        from .company_catalog import save
        data=await payload(request)
        try:return await asyncio.to_thread(save,store(),data)
        except (ValueError,TypeError,KeyError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/companies')
    async def companies():
        def read():
            from .company_filter import company_key
            from .company_catalog import raw_catalog
            catalog=raw_catalog(store());definitions={g['id']:g for g in catalog};counts={g['id']:{'id':g['id'],'label':g['label'],'tier':g['tier'],'count':0} for g in catalog}
            with store().connect() as db:
                for row in db.execute("SELECT company,COUNT(*) n FROM entities WHERE kind='vacancy' GROUP BY company"):
                    key=company_key(row['company'],catalog);definition=definitions.get(key,{});entry=counts.setdefault(key,{'id':key,'label':definition.get('label',row['company'] or 'Компания не указана'),'tier':definition.get('tier','others'),'count':0});entry['count']+=row['n']
            return {'items':sorted(counts.values(),key=lambda r:r['label'].casefold())}
        return await asyncio.to_thread(read)
    @app.post('/archive/rank')
    async def rank_archive(request:Request):
        data=await payload(request)
        try:
            archive=store();cv=archive.detail('resume',data['resume_id'])['payload']
            from .company_catalog import selection
            company=data.get('company','');selected=selection(data.get('companies'),company);goal=data.get('goal','');model=data.get('model','text-embedding-3-small')
            if not isinstance(company,str) or len(company)>300:raise ValueError('Некорректный фильтр компании.')
            # Select before any embedding/model call; never silently rank an arbitrary first 200.
            result=archive.entities('vacancy',status='full',companies=selected,limit=200,exclude_closed=True)
            if result['total']>200:raise ValueError('Сузьте выбор компаний: в подборке больше 200 вакансий.')
            jobs=[archive.detail('vacancy',r['id'])['payload'] for r in result['items'] if r['availability']!='closed']
            packet={'resume_id':cv['id'],'bundle':{'resumes':[cv]},'vacancies':jobs,'goal':goal,'model':model,'company_filter':company,'companies_filter':selected,'allow_api':data.get('allow_api',True)}
            return await app.state.rank_archive(packet)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
        except HTTPException:raise
        except Exception:raise HTTPException(502,'Не удалось завершить ранжирование. Уже полученные векторы сохранены; проверьте сервис и повторите.') from None
    @app.get('/archive/rankings')
    async def rankings(resume_id:str=''):return await call('ranking_history',resume_id)
    @app.get('/archive/diff')
    async def diff(kind:str,id:str,before:int,after:int):return await call('diff',kind,id,before,after)
    @app.get('/archive/events')
    async def events(offset:int=0):return await call('timeline',offset)
    @app.get('/archive/scans')
    async def scans(offset:int=0):return await call('scans',offset)
    @app.get('/archive/restore')
    async def restore():return await call('restore')
    @app.post('/archive/compare')
    async def compare(request:Request):
        data=await payload(request);return await call('compare',data.get('resume_id'),data.get('vacancy_id'))
    @app.get('/archive/skill-analysis')
    async def saved_skills(resume_id:str,vacancy_id:str,goal:str=''):
        from .skill_analysis import context,cached
        try:
            ctx=await asyncio.to_thread(context,store(),resume_id,vacancy_id,goal)
            return {'analysis':await asyncio.to_thread(cached,store(),ctx)}
        except (ValueError,TypeError,KeyError) as error:raise HTTPException(422,str(error)) from None
    @app.post('/archive/hh-inline')
    async def hh_inline(request:Request):
        data=await payload(request)
        if skill_lock.locked():raise HTTPException(409,'Генерация уже выполняется. Дождитесь результата.')
        from .hh_inline import run
        try:
            async with skill_lock:return await asyncio.to_thread(run,store(),data,root)
        except (ValueError,TypeError,KeyError) as error:raise HTTPException(422,str(error)) from None
    @app.post('/archive/hh-badges')
    async def hh_badges(request:Request):
        from .hh_badges import lookup
        try:return await asyncio.to_thread(lookup,store(),await payload(request))
        except (ValueError,TypeError,KeyError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/skill-history')
    async def skill_history(resume_id:str='',offset:int=0,limit:int=30):
        from .skill_history import history
        return await asyncio.to_thread(history,store(),resume_id,offset,limit)
    @app.get('/archive/skill-history/{key}')
    async def skill_history_detail(key:str):
        from .skill_history import detail
        try:return await asyncio.to_thread(detail,store(),key)
        except ValueError as error:raise HTTPException(404,str(error)) from None
    @app.post('/archive/skill-external')
    async def external_skills(request:Request):
        data=await payload(request)
        from .external_analysis import export_review,import_review
        try:
            if data.get('op')=='export':return await asyncio.to_thread(export_review,store(),data.get('resume_id'),data.get('vacancy_id'),data.get('goal',''))
            if data.get('op')=='import':return await asyncio.to_thread(import_review,store(),data.get('export_id'),data.get('answer'))
            raise ValueError('Выберите экспорт промпта или импорт ответа.')
        except (ValueError,TypeError,KeyError,RecursionError) as error:raise HTTPException(422,str(error)) from None
    @app.post('/archive/confirm-description')
    async def confirm_description(request:Request):
        data=await payload(request);return await call('confirm_description',data.get('vacancy_id'),data.get('content_hash'))
    @app.post('/archive/skill-analysis')
    async def generate_skills(request:Request):
        if skill_lock.locked():raise HTTPException(409,'Подробный разбор уже выполняется. Дождитесь результата.')
        data=await payload(request)
        from .skill_analysis import analyze
        try:
            async with skill_lock:return await asyncio.to_thread(analyze,store(),data.get('resume_id'),data.get('vacancy_id'),data.get('goal',''))
        except (ValueError,TypeError,KeyError) as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/export')
    async def export():
        def backup():
            archive=store()
            with archive.connect() as db:
                import base64
                db.execute('CREATE TABLE IF NOT EXISTS company_catalog_history(revision TEXT PRIMARY KEY,payload TEXT,saved_at TEXT DEFAULT CURRENT_TIMESTAMP)')
                tables={name:[dict(r) for r in db.execute('SELECT * FROM '+name)] for name in ('company_catalog_history','entities','versions','scans','membership','events','profiles','ranking_runs','document_embeddings','embedding_vectors','archive_meta','skill_analyses','skill_analysis_sources','skill_analysis_failures','external_analysis_requests','discovery_runs','applications','application_crm','application_appointments','calendar_links','application_workflow','application_discussion','application_drafts','application_approvals','application_events','application_chat_requests','browser_commands','hh_observations','hh_threads','hh_messages','workflow_delivery')}
                for name in ('analysis_batches','application_channels','giga_invites','giga_starts','application_field_drafts','application_field_versions','application_form_versions','turns','resume_supplements','candidate_facts','candidate_profile','candidate_profile_versions','resume_review_contexts','resume_reviews','resume_review_attempts','agent_task_controls','agent_task_events','browser_command_progress'):
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():tables[name]=[dict(r) for r in db.execute('SELECT * FROM '+name)]
                for row in tables['embedding_vectors']:row['vector']=base64.b64encode(row['vector']).decode('ascii')
                return {'schema_version':2,'vector_encoding':'base64-float32-le','tables':tables}
        data=await asyncio.to_thread(backup)
        return JSONResponse(data,headers={'Content-Disposition':'attachment; filename="cv-matcher-archive.json"','Cache-Control':'no-store'})
