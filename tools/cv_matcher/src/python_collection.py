"""Bounded public collection, isolated from CV, credentials, models and live DB."""
import json, os, signal, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .board_import import identity

from .collection_policy import SOURCES, reason_for


def execute(payload, stopped=lambda:False):
    """A subprocess deadline also bounds old Playwright collectors and their children."""
    root = Path(__file__).resolve().parents[1]
    env = {k:v for k,v in os.environ.items() if not any(part in k.upper() for part in ('TOKEN','API_KEY','SESSION','STORAGE_STATE','OPENAI','TELEGRAM'))}
    with tempfile.TemporaryDirectory(prefix='career-python-read-') as directory:
        task = Path(directory)/'task.json'; output = Path(directory)/'result.json'
        task.write_text(json.dumps({key:payload[key] for key in ('source_url','vacancy_id','options') if key in payload}))
        with (Path(directory)/'worker.log').open('wb') as log:
            process = subprocess.Popen([sys.executable,'-m','src.python_collection','--task',str(task),'--output',str(output)],cwd=root,env=env,stdout=log,stderr=log,start_new_session=True)
            deadline = time.monotonic()+75
            try:
                while process.poll() is None:
                    if stopped() or time.monotonic()>=deadline:
                        return {'rows':[],'reason':'stopped' if stopped() else 'python_timeout'}
                    time.sleep(.25)
                if process.returncode or not output.exists():
                    return {'rows':[],'reason':'python_process_failed'}
                if output.stat().st_size>8*1024*1024:
                    return {'rows':[],'reason':'python_output_limit'}
                return json.loads(output.read_text())
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()


def persist(archive, payload, response):
    from .archive_store import digest,FIELDS
    if not isinstance(response,dict):raise ValueError('Некорректный результат сборщика.')
    rows = response.get('rows', [])
    if not isinstance(rows,list) or len(rows)>100:
        raise ValueError('Некорректный пакет Python.')
    host = urlsplit(payload['source_url']).hostname
    provider = SOURCES.get(host)
    stamp = datetime.now(timezone.utc).isoformat()
    records = []; full = 0; review = 0; closed = 0
    for item in rows:
        if not isinstance(item,dict):continue
        target = identity(item.get('link','')); other = SOURCES.get(urlsplit(item.get('link','')).hostname)
        if not target or provider!=other or not isinstance(item.get('title'),str) or not item['title'].strip():continue
        text = item.get('description','')
        if not isinstance(text,str) or len(text)>100000:continue
        quality = item.get('description_quality','needs_review')
        if quality not in ('full','needs_review','snippet'):quality='needs_review'
        if len(text)<150:quality='snippet'
        if payload.get('vacancy_id') and target['id']!=payload['vacancy_id']:continue
        row = {**item,**target,'description_quality':quality,'collector':'python','source_page':item.get('source_page') or item['link'],'collected_at':stamp,'adapter_id':provider,'adapter_version':item.get('adapter_version','python-hybrid-v1')}
        # Full public detail extraction proves visibility now; it never proves a
        # platform submission and never closes unseen jobs in the archive.
        if item.get('archived') is True:
            from .archive_store import source_url_is_detail
            if source_url_is_detail(row['source_page'],target['id']):
                row['availability_checked_at']=stamp;closed+=1
            else:row.pop('archived',None);review+=1
        elif quality=='full':
            from .archive_store import source_url_is_detail
            if source_url_is_detail(row['source_page'],target['id']):row.update(archived=False,availability_checked_at=stamp)
            full+=1
        else:review+=1
        row={key:value for key,value in row.items() if key in FIELDS['vacancy']}
        records.append({'kind':'vacancy','id':target['id'],'data':row,'digest':digest(row)})
    if records:
        synced=archive.sync({'client_id':'python-hybrid-collector','records':records})
        accepted={r['id'] for r in synced['accepted']}
        records=[r for r in records if r['id'] in accepted]
        if synced['rejected']:
            response={**response,'reason':'archive_rejected'}
            full=sum(r['data']['description_quality']=='full' and not r['data'].get('archived') for r in records)
            closed=sum(r['data'].get('archived') is True for r in records)
            review=len(records)-full-closed
    reason=response.get('reason')
    # A list [] from a legacy catch-all exception is never verified empty.
    verified_empty=response.get('verified_empty') is True and not records and not reason
    success=full>0 or closed>0 or verified_empty
    return {'state':'complete' if success else 'needs_input','ids':[r['id'] for r in records],
      'coverage':'partial' if reason or review else 'bounded','verified_empty':verified_empty,
      'progress':{'loaded':full,'review':review,'archived':closed,'failed':1 if reason else 0},
      'attempts':response.get('attempts',[]),
      'reason':reason or ('unverified_empty' if not records else 'incomplete_descriptions' if not success else ''),
      'note':('Python: сохранено полных описаний '+str(full)+', на проверку '+str(review)+'.') if records else 'Python не подтвердил выдачу. Это не означает отсутствие вакансий.'}


def public_html(url):
    """No cookies, login, arbitrary redirect hosts or unbounded response bodies."""
    import requests
    from .board_import import extract_html
    from .discovery import source_url
    current=source_url(url)
    source=SOURCES[urlsplit(current).hostname]
    for _ in range(4):
        with requests.get(current,timeout=(4,10),allow_redirects=False,stream=True,headers={'User-Agent':'CVMatcher/0.11 public vacancy collector'}) as response:
            if response.is_redirect:
                from urllib.parse import urljoin
                next_url=source_url(urljoin(current,response.headers.get('Location','')))
                if SOURCES.get(urlsplit(next_url).hostname)!=source:raise ValueError('Cross-source redirect')
                current=next_url;continue
            response.raise_for_status();chunks=[];size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>3*1024*1024:raise ValueError('Response limit')
                chunks.append(chunk)
            text=b''.join(chunks).decode(response.encoding or 'utf-8',errors='replace')
            return extract_html(text,current)
    raise ValueError('Redirect limit')


def playwright_detail(url):
    """Ephemeral browser; reuse the extension's DOM adapters for dynamic pages."""
    from playwright.sync_api import sync_playwright
    from .collection_contract import ADAPTERS, read_browser_board
    from .board_import import extract_html
    from .discovery import source_url
    import ipaddress
    source_url(url, detail=True)
    provider = SOURCES[urlsplit(url).hostname]
    with sync_playwright() as runtime:
        try: browser = runtime.chromium.launch(headless=True)
        except Exception: browser = runtime.chromium.launch(channel='chrome',headless=True)
        try:
            context = browser.new_context(accept_downloads=False,service_workers='block')
            page = context.new_page()
            page.set_default_timeout(6000)
            def route(request_route):
                request = request_route.request
                parsed = urlsplit(request.url)
                host = parsed.hostname or ''
                blocked = parsed.scheme not in ('https','http') or host in ('localhost','localhost.localdomain') or host.endswith('.localhost')
                try: blocked = blocked or not ipaddress.ip_address(host).is_global
                except ValueError: pass
                if request.is_navigation_request() and request.frame == page.main_frame:
                    try: source_url(request.url,detail=True)
                    except ValueError: blocked = True
                    blocked = blocked or SOURCES.get(host) != provider
                if blocked or request.resource_type in ('image','media','font'): request_route.abort()
                else: request_route.continue_()
            context.route('**/*',route)
            page.goto(url,wait_until='domcontentloaded',timeout=20000)
            for attempt in range(4):
                source_url(page.url,detail=True)
                if SOURCES.get(urlsplit(page.url).hostname) != provider: raise ValueError('Cross-source navigation')
                if urlsplit(page.url).hostname in ADAPTERS:
                    result=read_browser_board(page)
                    if result.get('blocked'): return {'rows':[],'reason':'access_required'}
                    rows=result.get('vacancies',[])
                else: rows=extract_html(page.content(),page.url)
                if any(r.get('archived') or r.get('description_quality')=='full' for r in rows): return {'rows':rows}
                if attempt<3: page.wait_for_timeout(700)
            return {'rows':rows,'reason':'unsupported_layout'}
        finally: browser.close()


def detail(payload):
    """HTTP -> rendered DOM -> authorized Chrome (the durable outer router)."""
    url=payload['source_url']; attempts=[]; partial=[]
    for transport,reader in (('http',public_html),('playwright_dom',playwright_detail)):
        started=time.monotonic()
        try:
            value=reader(url)
            response=value if isinstance(value,dict) else {'rows':value}
            rows=response.get('rows',[])
            expected=payload.get('vacancy_id') or identity(url)['id']
            rows=[r for r in rows if isinstance(r,dict) and identity(r.get('link','')) and identity(r['link'])['id']==expected]
            ready=any(r.get('archived') or r.get('description_quality')=='full' and len(r.get('description',''))>=150 for r in rows)
            reason=response.get('reason') or ('' if ready else 'incomplete_descriptions' if rows else 'unverified_empty')
            attempts.append({'transport':transport,'reason':reason,'elapsed_seconds':round(time.monotonic()-started,2),'records':len(rows)})
            if ready:return {'rows':rows,'attempts':attempts}
            if rows:partial=rows
            # Challenges require an authorized session; don't hammer the page.
            if reason in ('access_required','login_required','http_rate_limited'):break
        except Exception as error:
            reason=reason_for(error)
            attempts.append({'transport':transport,'reason':reason,'error_type':type(error).__name__,'elapsed_seconds':round(time.monotonic()-started,2)})
            if reason in ('access_required','login_required','http_rate_limited'):break
    return {'rows':partial,'reason':reason,'attempts':attempts}


def collect(payload):
    """Use specialised legacy parsers for discovery, shared DOM adapters for detail."""
    url=payload['source_url'];host=urlsplit(url).hostname;provider=SOURCES.get(host)
    if not provider:return {'rows':[],'reason':'unsupported_python_source'}
    options=payload.get('options',{});limit=min(100,max(1,int(options.get('details',1 if payload.get('vacancy_id') else 40))))
    if options.get('tbank_filters'):
        return {'rows':[],'reason':'native_filter_requires_chrome'}
    if payload.get('vacancy_id') or identity(url) and not identity(url)['id'].startswith('board_'):
        return detail(payload)
    from .scrapers import SCRAPER_REGISTRY
    query=parse_qs(urlsplit(url).query)
    allowed={'yandex':{'text','professions','profession','page','cursor'},'sber':{'query'},'ozon':{'query','search','q','city'},'avito':{'q','action','direction'},'google':{'q','page'},'meta':set(),'tinkoff':set()}[provider]
    if set(query)-allowed:return {'rows':[],'reason':'filters_not_supported_in_python'}
    search=url if provider in ('yandex','avito','ozon') else query.get('query',query.get('q',['']))[0]
    scraper=SCRAPER_REGISTRY[provider](limit=limit,headless=True,stealth=False,archive_path=False)
    events=[];scraper.event_sink=events.append
    rows=scraper.fetch_jobs(search,existing_ids=set())
    return {'rows':rows[:limit],**({'reason':'python_parser_error'} if any(e.get('type')=='error' for e in events) else {})}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    try:result=collect(json.loads(Path(args.task).read_text()))
    except Exception as error:result={'rows':[],'reason':reason_for(error),'error_type':type(error).__name__}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False))
