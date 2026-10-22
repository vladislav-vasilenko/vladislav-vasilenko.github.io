"""Authenticated asynchronous controls; only fixed-repository GETs reach GitHub."""
import asyncio
from fastapi import HTTPException, Request
from . import github_collection_import as imports
from . import github_collection_control as control


def install(app):
    tasks = set()
    app.state.github_import_tasks = tasks

    @app.get('/archive/github-import')
    async def github_import_status():
        return await asyncio.to_thread(imports.status, app.state.archive_store())

    @app.post('/archive/github-import')
    async def github_import_action(request: Request):
        raw = await request.body()
        if len(raw) > 1000: raise HTTPException(413, 'Слишком большой запрос импорта.')
        import json
        try:
            data = json.loads(raw)
            if not isinstance(data, dict): raise ValueError('Нужна операция импорта.')
            archive = app.state.archive_store()
            if data.get('op') == 'runs': return await asyncio.to_thread(control.overview, archive)
            if data.get('op') == 'run': return await asyncio.to_thread(control.run_detail, data.get('run_id'))
            if data.get('op') == 'dispatch': return await asyncio.to_thread(control.dispatch, archive)
            if data.get('op') == 'cancel': return await asyncio.to_thread(control.cancel, data.get('run_id'))
            if data.get('op') == 'settings': return await asyncio.to_thread(control.configure, archive, data)
            if data.get('op') == 'configure':
                return await asyncio.to_thread(imports.configure, archive, data.get('enabled'))
            if data.get('op') != 'start': raise ValueError('Неизвестная операция импорта.')
            lease = await asyncio.to_thread(imports.acquire, archive)
            if lease:
                task = asyncio.create_task(asyncio.to_thread(imports.pull, archive, lease))
                tasks.add(task); task.add_done_callback(tasks.discard)
            return await asyncio.to_thread(imports.status, archive)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from None
