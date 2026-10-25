import asyncio
import json
from fastapi import HTTPException, Request
from . import portfolio_publication as publication


def install(app):
    @app.get('/archive/portfolio-publication')
    async def publication_status():
        return await asyncio.to_thread(publication.read, app.state.archive_store())

    @app.post('/archive/portfolio-publication')
    async def publication_action(request: Request):
        raw = await request.body()
        if len(raw) > 400000: raise HTTPException(413, 'Слишком большой запрос публикации.')
        try:
            data = json.loads(raw)
            if not isinstance(data, dict): raise ValueError('Нужна операция публикации.')
            archive = app.state.archive_store()
            if data.get('op') == 'preview': return await asyncio.to_thread(publication.preview, archive)
            if data.get('op') in ('visual_preview','visual_settings'):
                from .portfolio_visuals import options, project
                settings=options(data.get('settings'),preview=data['op']=='visual_preview')
                if data['op']=='visual_preview':return {'settings':settings,'payload':await asyncio.to_thread(project,archive,settings)}
                return await asyncio.to_thread(publication.write,archive,visual_settings=settings)
            if data.get('op') == 'visual_choices':
                from .career_trajectory import overview
                value=await asyncio.to_thread(overview,archive,archive)
                return {'paths':value['paths'],'active':value['path']['id'] if value['path'] else None,'settings':publication.read(archive).get('visual_settings',{})}
            if data.get('op') == 'save_about': return await asyncio.to_thread(publication.save_about, archive, data)
            if data.get('op') == 'save_experience_translation': return await asyncio.to_thread(publication.save_experience_translation, archive, data)
            if data.get('op') == 'context': return await asyncio.to_thread(publication.discussion_context, archive)
            if data.get('op') == 'github_activity': return await asyncio.to_thread(publication.refresh_github_activity, archive)
            if data.get('op') == 'publish': return await asyncio.to_thread(publication.publish, archive)
            if data.get('op') == 'configure':
                if type(data.get('enabled')) is not bool: raise ValueError('Укажите режим автопубликации.')
                if data['enabled']: await asyncio.to_thread(publication.preview, archive)
                return await asyncio.to_thread(publication.write, archive, enabled=data['enabled'])
            raise ValueError('Неизвестная операция публикации.')
        except (ValueError, TypeError) as error: raise HTTPException(422, str(error)) from None
