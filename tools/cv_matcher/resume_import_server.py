"""Private loopback service for imports and explicitly requested OpenAI embeddings.

Start: .venv/bin/python resume_import_server.py
Pairing token: .cache/resume_import/token.txt (copy into extension file manager).
"""
import base64
import binascii
import hmac
import os
from pathlib import Path
import secrets
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from src.resume_files import extract_resume, MAX_FILE


def create_app(token, *, ranker=None, cover_writer=None, archive_path=None):
    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(app.state.archive_store().index_legacy_embeddings,Path(__file__).parent/'.cache/extension_embeddings')
        from src.application_store import ApplicationStore
        from src.hh_auto_sync import run
        from contextlib import suppress
        scheduler=asyncio.create_task(run(lambda:ApplicationStore(app.state.archive_store().path)))
        from src.career_runtime import run as run_career
        career=asyncio.create_task(run_career(lambda:ApplicationStore(app.state.archive_store().path)))
        from src.github_collection_import import scheduler as run_github_import
        github_import=asyncio.create_task(run_github_import(app.state.archive_store))
        from src.portfolio_publication import scheduler as run_portfolio_publication
        publication=asyncio.create_task(run_portfolio_publication(app.state.archive_store))
        try:yield
        finally:
            publication.cancel()
            with suppress(asyncio.CancelledError):await publication
            github_import.cancel()
            with suppress(asyncio.CancelledError):await github_import
            for task in list(getattr(app.state,'github_import_tasks',set())):
                with suppress(asyncio.CancelledError):await task
            career.cancel()
            with suppress(asyncio.CancelledError):await career
            scheduler.cancel()
            with suppress(asyncio.CancelledError):await scheduler
    app = FastAPI(title="Local Resume Import", docs_url=None, redoc_url=None, openapi_url=None,lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://[a-p]{32}",
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Resume-Import-Token"])
    ranking_lock=asyncio.Lock()
    cover_lock=asyncio.Lock()
    @app.middleware("http")
    async def authorize(request: Request, call_next):
        if request.url.path=='/archive/calendar/callback':
            request.state.calendar_oauth_query=dict(request.query_params);request.scope['query_string']=b''
        public=request.method=='GET' and (request.url.path in ('/','/archive','/archive/calendar/callback') or request.url.path.startswith('/assets/'))
        login=request.method=='POST' and request.url.path=='/archive/login'
        cookie=getattr(app.state,'archive_access',None)
        if request.method != "OPTIONS" and not (public or login or hmac.compare_digest(request.headers.get("x-resume-import-token", "").encode(), token.encode()) or (cookie and cookie.cookie_allowed(request))):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail":"Неверный код подключения локального импорта."}, status_code=401)
        import secrets,logging,traceback
        from fastapi.responses import JSONResponse
        request_id=secrets.token_hex(8)
        try:response=await call_next(request)
        except Exception as error:
            # Diagnostics deliberately omit query strings, headers, bodies and exception values.
            logging.getLogger(__name__).error('request=%s path=%s type=%s frames=%s',request_id,request.url.path,type(error).__name__,''.join(traceback.format_tb(error.__traceback__)))
            response=JSONResponse({'detail':'Внутренняя ошибка сервиса ('+type(error).__name__+'). Сохранён идентификатор диагностики.','request_id':request_id},status_code=500)
        response.headers['X-Career-Request-Id']=request_id
        return response
    @app.post("/extract")
    async def extract(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_FILE * 4 // 3 + 8192: raise HTTPException(413,"Файл больше 12 МБ.")
        import json
        try:
            payload=json.loads(body)
            content=base64.b64decode(payload["content_base64"], validate=True)
            filename=payload["filename"]
            if not isinstance(filename,str): raise ValueError("Некорректное имя файла")
            return await asyncio.to_thread(extract_resume,content,filename)
        except (ValueError,KeyError,TypeError,binascii.Error) as exc:
            raise HTTPException(422,str(exc)) from exc
        except Exception as exc:
            raise HTTPException(422,"Документ не прочитан полностью. Проверьте формат или экспортируйте копию в DOCX/TXT.") from exc
    @app.get("/health")
    async def health():
        from src.application_store import ApplicationStore
        connections=await asyncio.to_thread(lambda:ApplicationStore(app.state.archive_store().path).browser_status())
        return {"ok":True,"openai_configured":bool(os.environ.get("OPENAI_API_KEY")),"service":"cv-matcher-local","version":13,"supervised_preparation":True,"search_scope":True,"sleep_waiting":True,"agent_layer":True,"task_controls":True,"mcp_backend":True,"hh_auto_sync":True,"daily_discovery":True,"hybrid_collection":True,"collection_backfill":True,"collection_protocol":2,"vacancy_intake":True,"connections":connections,"durable_delivery":True,"shared_application_channels":True,"resume_review":True,"external_analysis":True,"managed_hh":True,"journey":True,"workflow":True,"crm":True,"crm_planning":True,"google_calendar":True,"archive_ranking":True,"external_answers":True,"hh_inline":True,"skill_history":True,"skill_analysis":True,"archive":True,"embedding_archive":True,"cover_letters":True,"cover_model":os.environ.get("COVER_LETTER_MODEL","gpt-4.1-mini"),
            "telegram_operator_configured":all(os.environ.get(k) for k in ["TELEGRAM_BOT_TOKEN","TELEGRAM_OWNER_ID"]),"telethon_session_exists":(Path(__file__).parent/".cache/telegram/recruiter-user.session").exists(),"telegram_configured":all(os.environ.get(k) for k in ['TELEGRAM_API_ID','TELEGRAM_API_HASH','TELEGRAM_BOT_TOKEN','TELEGRAM_OWNER_ID'])}
    async def small_payload(request):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>2*1024*1024:raise HTTPException(413,'Контекст слишком велик.')
        import json
        try:
            data=json.loads(body)
            if not isinstance(data,dict):raise ValueError()
            return data
        except (ValueError,TypeError):raise HTTPException(422,'Нужен JSON-объект.') from None
    def application_store():
        from src.application_store import ApplicationStore
        return ApplicationStore(Path(__file__).parent/'.cache/applications/state.sqlite3')
    @app.post('/applications')
    async def create_application(request:Request):
        payload=await small_payload(request)
        try:return await asyncio.to_thread(application_store().create,payload)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
    @app.post('/answer-draft')
    async def answer_draft(request:Request):
        payload=await small_payload(request)
        try:
            from src.recruiter_answers import draft_answer
            from src.candidate_facts import answer_context
            state=application_store();application=state.get(payload['application_id'])
            return await asyncio.to_thread(draft_answer,answer_context(state,application['context'],preferences=payload.get('comments','')),payload['question'],payload.get('model','luna'),Path(__file__).parent/'.cache/recruiter_answers')
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
    async def rank_archive(packet):
        if ranking_lock.locked():raise HTTPException(409,'Ранжирование уже выполняется. Дождитесь результата.')
        from src.extension_ranking import rank_vacancies
        async with ranking_lock:
            options={} if ranker else {'archive':app.state.archive_store()}
            return await asyncio.to_thread(ranker or rank_vacancies,packet,Path(__file__).parent/'.cache/extension_embeddings',**options)
    app.state.rank_archive=rank_archive
    @app.post("/rank")
    async def rank(request: Request):
        if ranking_lock.locked(): raise HTTPException(409,"Ранжирование уже выполняется. Дождитесь результата.")
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>16*1024*1024: raise HTTPException(413,"Подборка слишком велика.")
        import json
        try:
            payload=json.loads(body)
            if not isinstance(payload,dict): raise ValueError("Нужна подборка и выбранное резюме.")
            from src.extension_ranking import rank_vacancies
            async with ranking_lock:
                options={} if ranker else {'archive':app.state.archive_store()}
                return await asyncio.to_thread(ranker or rank_vacancies,payload,Path(__file__).parent/".cache"/"extension_embeddings",**options)
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            raise HTTPException(422,str(exc)) from exc
        except Exception:
            raise HTTPException(502,"Ранжирование не завершено. Проверьте локальный сервис и соединение с OpenAI.") from None
    @app.post("/cover-letter")
    async def cover_letter(request: Request):
        if cover_lock.locked(): raise HTTPException(409,"Генерация письма уже выполняется. Дождитесь результата.")
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>2*1024*1024: raise HTTPException(413,"CV или вакансия слишком велики.")
        import json
        try:
            payload=json.loads(body)
            if not isinstance(payload,dict): raise ValueError("Нужны выбранное резюме и одна вакансия.")
            from src.cover_letter import generate_cover_letter
            async with cover_lock:
                return await asyncio.to_thread(cover_writer or generate_cover_letter,payload,Path(__file__).parent/".cache"/"cover_letters")
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            raise HTTPException(422,str(exc)) from exc
        except Exception:
            raise HTTPException(502,"Сопроводительный текст не получен. Проверьте локальный сервис.") from None
    from src.archive_routes import install_archive
    install_archive(app,token,Path(__file__).parent,archive_path)
    return app


def main():
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent/".env")
    directory=Path(__file__).parent/".cache"/"resume_import"
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/"token.txt"
    os.chmod(directory,0o700)
    import re
    token=path.read_text().strip() if path.exists() else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}",token):
        token=secrets.token_urlsafe(32)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,"w") as handle: handle.write(token)
    os.chmod(path,0o600)
    print("Локальный сервис CV Matcher: http://127.0.0.1:8788. Код подключения находится в",path,flush=True)
    uvicorn.run(create_app(token),host="127.0.0.1",port=8788,log_level="warning")


if __name__=="__main__": main()
