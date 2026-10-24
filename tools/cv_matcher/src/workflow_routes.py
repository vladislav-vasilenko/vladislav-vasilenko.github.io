"""Shared website/extension workflow API. Browser execution operations require the token."""
import asyncio,json,hmac
from fastapi import HTTPException,Request
from .application_store import ApplicationStore

def install_workflow(app,token,root):
    from .agent_routes import install_agent
    install_agent(app)
    locks={}
    def store():return ApplicationStore(app.state.archive_store().path)
    from .calendar_routes import install_calendar
    install_calendar(app,root,store)
    @app.get('/archive/workflow')
    async def read_workflow(app_id:str=''):
        def read():
            s=store()
            if app_id:return s.workflow(app_id)
            with s.connect() as db:plans={r['app_id']:dict(r) for r in db.execute('SELECT * FROM application_crm')};states={r['app_id']:r['state'] for r in db.execute('SELECT app_id,state FROM application_workflow')}
            from .application_workflow import CRM_STAGES,WORK_STATUSES,STAGE_DEFAULTS,crm_value
            from .manual_applications import listing as manual_listing
            return {'manual_marks':manual_listing(s),'items':[{'id':a['id'],'status':a['status'],'workflow_state':states.get(a['id'],'draft'),'crm_stage':plans.get(a['id'],{}).get('stage','preparing'),'crm':crm_value(plans.get(a['id'])),'title':a['context']['vacancy']['title'],'company':a['context']['vacancy']['company'],'resume_title':a['context']['resume_title'],'vacancy_id':a['context']['vacancy']['id'],'channel':a['context']['channel'],'created':a['created']} for a in s.list() if s.case_id(a['id'])==a['id']],'deliveries':s.deliveries(),'hh':s.hh_inbox(),'crm_stages':CRM_STAGES,'work_statuses':WORK_STATUSES,'stage_defaults':STAGE_DEFAULTS,'browser':s.browser_status()}
        try:return await asyncio.to_thread(read)
        except ValueError as error:raise HTTPException(422,str(error)) from None
    @app.get('/archive/journey')
    async def journey():
        from .journey import overview
        return await asyncio.to_thread(overview,store())
    @app.post('/archive/workflow')
    async def workflow_action(request:Request):
        body=await request.body()
        if len(body)>4*1024*1024:raise HTTPException(413,'Снимок слишком большой.')
        try:
            data=json.loads(body);op=data['op'];s=store()
            if op in ('observe','next','prepared','claim','result','career_form','career_fill_claim','career_fill_result','task_control_status','task_progress','resume_bump_claim') and not hmac.compare_digest(request.headers.get('x-resume-import-token',''),token):raise HTTPException(403,'Эта операция доступна только расширению.')
            def action():
                if op in ('application_readiness','career_open'):
                    from .application_readiness import read,open_career
                    return read(s,data['app_id']) if op=='application_readiness' else open_career(s,data['app_id'])
                if op=='career_form_for_application':
                    if not hmac.compare_digest(request.headers.get('x-resume-import-token',''),token):raise HTTPException(403,'Чтение анкеты доступно расширению.')
                    from .career_questionnaires import capture
                    s.validate_current(data['app_id'])
                    return capture(s,data['app_id'],data['snapshot'])
                if op in ('resume_bump','resume_bump_save','resume_bump_retry','resume_bump_claim'):
                    from . import resume_bump
                    if op=='resume_bump':return resume_bump.status(s)
                    if op=='resume_bump_claim':return resume_bump.claim(s,data['command_id'],data['worker_id'])
                    if op=='resume_bump_retry':return resume_bump.retry(s,data['resume_id'],data.get('confirmed',False))
                    result=resume_bump.configure(s,data['config'],data['revision'],data.get('confirmed',False));resume_bump.tick(s);return resume_bump.status(s)
                if op=='manual_application':
                    from .manual_applications import set_mark
                    return set_mark(app.state.archive_store(),data['vacancy_id'],data['marked'],data['revision'])
                if op=='task_progress':
                    from .agent_progress import report
                    return report(s,data['command_id'],data['worker_id'],data['sequence'],data['progress'])
                if op=='task_control_status':
                    from .agent_tasks import worker_control
                    return worker_control(s,data['command_id'],data['worker_id'])
                if op=='vacancy_selection_prompt':
                    from .vacancy_selection import build
                    return build(app.state.archive_store(),data)
                if op=='hh_sync_targets':
                    import re
                    with s.connect() as db:rows=db.execute('SELECT source_url FROM hh_threads ORDER BY updated_at DESC LIMIT 500').fetchall()
                    return {'urls':list(dict.fromkeys(r[0] for r in rows if re.fullmatch(r'https://hh\.ru/chat/\d{1,25}/?',r[0] or '')))}
                if op in ('resume_import','resume_import_status'):
                    from .resume_intake import start,read
                    return start(s,data['url']) if op=='resume_import' else read(s,data['command_id'])
                if op in ('notification_config','notification_config_save'):
                    from .career_notifications import config,status
                    from .career_application import CareerApplication
                    if op=='notification_config_save':config(s,data['config'])
                    return status(CareerApplication(s))
                if op in ('hh_auto_sync','hh_auto_sync_save'):
                    from .hh_auto_sync import config,status
                    if op=='hh_auto_sync_save':config(s,data['config'])
                    return status(s)
                if op in ('collection_backfill','collection_backfill_start','collection_backfill_control'):
                    from .collection_backfill import status,start,control
                    if op=='collection_backfill_start':return start(s)
                    if op=='collection_backfill_control':return control(s,data['run_id'],data['action'])
                    return status(s)
                if op in ('vacancy_import','collect_one','collection_status'):
                    from .vacancy_intake import import_text,collect_one,status
                    if op=='vacancy_import':return import_text(app.state.archive_store(),data)
                    if op=='collect_one':return collect_one(s,data['url'])
                    return status(s,data['command_id'])
                if op in ('discovery_config','discovery_config_save','discovery_start','discovery_status'):
                    from .discovery import config,start,read
                    if op=='discovery_config':return config(s)
                    if op=='discovery_config_save':return config(s,data['config'])
                    if op=='discovery_status':return read(s,data['run_id'])
                    raise ValueError('Запуск поиска использует общий application layer.')
                if op in ('candidate_profile','candidate_profile_save'):
                    from .candidate_profile import read,save
                    return read(s) if op=='candidate_profile' else save(s,data['values'],data['revisions'])
                if op=='career_form':
                    from .career_questionnaires import capture
                    archive=app.state.archive_store();cv=archive.detail('resume',data['resume_id'])['payload'];job=archive.detail('vacancy',data['vacancy_id'])['payload']
                    if cv['content_hash']!=data['resume_hash']:raise ValueError('CV изменилось. Обновите панель.')
                    item=s.create({'resume_id':cv['id'],'bundle':{'resumes':[cv]},'vacancy':job,'goal':data.get('goal',''),'channel':'career'})
                    s.validate_current(item['id'])
                    return capture(s,item['id'],data['snapshot'])
                if op=='make':
                    from .career_application import CareerApplication
                    return CareerApplication(s).make_application(data['resume_id'],data['vacancy_id'],data.get('goal',''))
                if op=='delivery_resolve':return s.resolve_delivery(data['key'],data['revision'],data['resolution'],data.get('confirmed',False))
                if op=='start_screening':return s.start_screening(data['app_id'],data.get('confirmed',False))
                if op=='screening_preview':return s.screening_preview(data['app_id'])
                if op=='complete_screening':return s.complete_screening(data['app_id'],data['token'],data.get('confirmed',False))
                if op=='field_answer':return s.save_field_answer(data['app_id'],data['field_id'],data['value'],data['fingerprint'],data['revision'])
                if op=='draft':return s.save_letter(data['app_id'],data['text'],data['revision'])
                if op=='crm':return s.set_crm(data['app_id'],data['stage'],data.get('note',''),**{k:data[k] for k in ('work_status','next_action','follow_up_at','revision','clear_follow_up') if k in data})
                if op=='appointment':return s.save_appointment(data['app_id'],data['appointment'])
                if op=='renew':
                    archive=app.state.archive_store();old=s.get(data['app_id'])
                    return s.renew_context(data['app_id'],archive.detail('resume',data['resume_id'])['payload'],archive.detail('vacancy',old['context']['vacancy']['id'])['payload'],data.get('goal',old['context']['goal']))
                if op=='answer':
                    from .recruiter_answers import draft_answer
                    item=s.get(data['app_id'])
                    question=s.answerable_field(data['app_id'],data['field_id'],data['fingerprint'],data['revision'])['label'] if data.get('field_id') else data['question']
                    from .candidate_facts import answer_context
                    result=draft_answer(answer_context(s,item['context'],preferences=data.get('comments','')),question,data.get('model','luna'),root/'.cache/recruiter_answers')
                    if data.get('field_id'):s.record_field_suggestion(data['app_id'],data['field_id'],result,data['fingerprint'],data['revision'])
                    return result
                if op=='recover':return s.recover_unsent(data['app_id'],data.get('confirmed',False))
                if op=='prepare':
                    from .career_application import CareerApplication
                    return CareerApplication(s).prepare_form(data['app_id'])
                if op=='intent':return s.intent(data['app_id'],data.get('answers'))
                if op=='approve':return s.approve(data['app_id'],data['intent_hash'],data.get('answers'),data.get('confirmed',False))
                if op=='observe':return s.hh_sync(data['snapshot'])
                if op=='bind':return s.bind_thread(data['thread_id'],data['app_id'],data.get('confirmed',False))
                if op=='career_fill_intent':return s.career_fill_intent(data['app_id'])
                if op=='career_fill_status':return s.career_fill_status(data['app_id'],data['command_id'])
                if op=='career_fill_approve':return s.approve_career_fill(data['app_id'],data['intent_hash'],data.get('confirmed',False))
                if op=='career_fill_claim':return s.claim_career_fill(data['command_id'],data['worker_id'],data['fingerprint'])
                if op=='career_fill_result':return s.finish_career_fill(data['command_id'],data['worker_id'],data['result'])
                if op=='next':return s.next_command(data['worker_id'],data.get('kinds'),data.get('app_ids'),auto_sync=data.get('auto_sync',False),resume_bump_version=data.get('resume_bump_version'),resume_import_version=data.get('resume_import_version'),collection_version=data.get('collection_version'))
                if op in ('prepared','result','claim'):
                    with s.connect() as db:cmd=db.execute('SELECT * FROM browser_commands WHERE id=?',(data['command_id'],)).fetchone()
                    if not cmd or cmd['worker_id']!=data['worker_id'] or (op!='result' and cmd['state']!='running'):raise ValueError('Задача Chrome уже завершена или принадлежит другой вкладке.')
                    if op=='prepared':return s.prepared(cmd['app_id'],data['snapshot'],command_id=cmd['id'])
                    if op=='claim':return s.claim_approval(data['command_id'],data['worker_id'],data['fingerprint'])
                    return s.finish_command(data['command_id'],data['worker_id'],data['result'])
                if op=='sync':return {'command_id':s.queue_command('sync',payload={'source_url':data['source_url']} if data.get('source_url') else None)}
                if op=='refresh':return {'command_id':s.queue_command('refresh',payload={'ids':data.get('ids',[])[:20],**({'resume_id':data['resume_id']} if data.get('resume_id') else {})})}
                raise ValueError('Неизвестное действие.')
            if op=='discovery_start':
                from .career_application import CareerApplication
                import time
                task=await CareerApplication(s).search(data.get('request_id') or str(time.time_ns()))
                from .discovery import read
                return read(s,task['id'].split(':',1)[1])
            if op=='chat':
                from .application_conversation import discuss
                lock=locks.setdefault(data['app_id'],asyncio.Lock())
                if lock.locked():raise ValueError('Редактор уже отвечает в этом обсуждении.')
                async with lock:return await asyncio.to_thread(discuss,s,data['app_id'],data['message'],data['request_id'],data.get('model','luna'))
            return await asyncio.to_thread(action)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
