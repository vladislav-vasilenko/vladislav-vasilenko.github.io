"""Authenticated local UI and extension-only queue endpoints."""
import asyncio
import hmac
import json
from fastapi import HTTPException, Request
from . import linkedin_workspace as workspace


def install(app, token):
    @app.get('/archive/linkedin')
    async def linkedin_status():
        return await asyncio.to_thread(workspace.overview, app.state.archive_store())

    @app.post('/archive/linkedin')
    async def linkedin_action(request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>2_100_000: raise HTTPException(413,'Слишком большой пакет LinkedIn.')
        try:
            data=json.loads(raw)
            if not isinstance(data,dict): raise ValueError('Нужен JSON-объект.')
            op=data.get('op'); archive=app.state.archive_store()
            from .contact_relevance import review as contact_review
            operations={'configure':workspace.configure,'enqueue':workspace.enqueue,'control':workspace.control,'note':workspace.save_note,
                        'claim':workspace.claim,'progress':workspace.progress,'result':workspace.result,'checkpoint':workspace.checkpoint,'import_jobs':workspace.import_jobs,'thread_detail':workspace.thread_detail,'contacts':workspace.contacts,'contact_review':contact_review,'contacts_context':workspace.contacts_context,'profile_history':workspace.profile_history}
            if op in ('claim','progress','result','checkpoint') and not hmac.compare_digest(request.headers.get('x-resume-import-token','').encode(),token.encode()):
                raise HTTPException(403,'Эта операция доступна подключённому расширению.')
            if op=='source': return await asyncio.to_thread(workspace.source,archive,data.get('resume_id'))
            if op not in operations: raise ValueError('Неизвестная операция LinkedIn.')
            return await asyncio.to_thread(operations[op],archive,data)
        except (ValueError,TypeError,KeyError) as error:
            raise HTTPException(422,str(error)) from None
