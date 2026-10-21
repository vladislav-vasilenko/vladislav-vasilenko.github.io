"""Authenticated application API. No approval or browser executor capabilities."""
import asyncio,json
from fastapi import Request,HTTPException
from .application_store import ApplicationStore
from .career_application import CareerApplication

def install_agent(app):
    def service():return CareerApplication(ApplicationStore(app.state.archive_store().path))
    @app.get('/archive/agent')
    async def agent_state():return await asyncio.to_thread(service().state)
    @app.post('/archive/agent')
    async def agent_action(request:Request):
        raw=await request.body()
        if len(raw)>32000:raise HTTPException(413,'Слишком большой запрос агента.')
        try:
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError('Нужен объект запроса.')
            op=data['op'];s=service()
            if op=='search':return await s.search(data['request_id'],data.get('scope'))
            if op=='converse':return await s.converse(data['text'],data['request_id'],'local_owner')
            def action():
                if op=='skills_catalog':return s.skills_catalog()
                if op=='skills_vacancy':return s.skills_vacancy(data)
                if op=='skills_plan':return s.skills_plan({k:v for k,v in data.items() if k!='op'})
                if op=='skills_evidence':return s.skills_evidence(data)
                if op=='skills_track':return s.skills_track(data)
                if op=='skills_history':return s.skills_history(data['resume_id'])
                if op=='tasks':return {'tasks':s.tasks()}
                if op=='get_task':return s.task(data['task_id'])
                if op=='control_task':return s.control_task(data['task_id'],data['action'],data['revision'])
                if op=='prepare_application':return s.prepare_application(data['resume_id'],data['vacancy_id'],data.get('goal',''),data.get('draft'),data.get('revision'),data.get('open_form') is True)
                if op=='queue_preparation':
                    if data.get('mode','offline')!='offline':raise ValueError('API-подготовка запускается отдельным действием владельца в Telegram.')
                    return s.queue_preparation(data['app_id'],data['request_id'],'offline')
                if op=='get_application':return s.store.workflow(data['app_id'])
                if op=='review_action':return s.review_action(data['app_id'])
                if op=='rank':return s.rank(data['resume_id'],data['vacancy_ids'],data.get('goal',''),data.get('model','text-embedding-3-small'))
                if op=='analyze':return s.analyze(data['resume_id'],data['vacancy_id'],data.get('goal',''),data.get('mode','cached'))
                raise ValueError('Неизвестная операция агента. Подтверждения доступны только в пульте владельца.')
            return await asyncio.to_thread(action)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
