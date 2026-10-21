"""Bounded conversational routing shared by all clients; documents are never commands.

No LLM call, inferred approval, arbitrary URL or guessed application context.
Unrecognized requests ask for clarification instead of taking a risky action.
"""
import re,json
from .application_workflow import hashed,packed

HELP='Можно: «найди вакансии», «мои задачи», «статус», «подготовь отклик hh_123», «пауза search:ID», «продолжи search:ID», «отмени search:ID». Отправку подтверждайте отдельной кнопкой после проверки текста.'

def intent(text):
    if not isinstance(text,str) or not 1<=len(text.strip())<=2000:raise ValueError('Запрос должен содержать от 1 до 2000 символов.')
    value=text.strip().lower()
    task=re.fullmatch(r'(пауза|приостанови|продолжи|возобнови|отмени|pause|resume|cancel|/pause|/resume|/cancel)\s+((?:search|browser):[a-f0-9]{12,40})',value)
    if task:return ('control',{'task_id':task[2],'action':{'пауза':'pause','приостанови':'pause','продолжи':'resume','возобнови':'resume','отмени':'cancel'}.get(task[1],task[1].lstrip('/'))})
    if value in ('статус','состояние','что происходит','/status'):return ('state',{})
    if value in ('мои задачи','задачи','покажи задачи','/tasks'):return ('tasks',{})
    if re.search(r'навык|компетенц|план обуч|чему учиться|что изуч|skills|learning plan',value):return ('skills',{})
    if re.fullmatch(r'(найди|найти|покажи|подбери|ищи) (новые |лучшие |подходящие )?вакансии[.!]?',value) or value=='/today':return ('search',{})
    app=re.fullmatch(r'(?:подготовь|подготовить) отклик\s+([a-z0-9_-]{3,150})',value)
    if app:return ('prepare',{'vacancy_id':app[1]})
    if re.search(r'отправ|соглас|approve|submit',value):return ('review',{})
    return ('clarify',{})

async def converse(service,text,request_id,actor):
    if not isinstance(request_id,str) or not 1<=len(request_id)<=100:raise ValueError('Нужен request_id длиной до 100 символов.')
    key='agent-request:'+actor+':'+request_id;fingerprint=hashed(text)
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        if old:
            prior=json.loads(old[0])
            if prior['hash']!=fingerprint:raise ValueError('request_id уже использован для другого текста.')
            if 'reply' not in prior:raise ValueError('Запрос уже принят. Проверьте задачи; действие автоматически не повторяется.')
            return prior['reply']
        service.store.setting_in(db,key,packed({'hash':fingerprint}))
    op,args=intent(text)
    batch=re.fullmatch(r'подготовь отклики? на (?:первые? )?(две|два|три|[1-3])[.!]?',text.strip(),re.I)
    if batch:op='prepare_batch'
    from .career_search_scope import parse,describe
    scope=parse(text,service.archive) if op in ('clarify','search') else None
    if scope is not None:op='search'
    if op=='skills':
        from .career_skills import telegram,track_from_text
        selected_track=track_from_text(text,service.skills_catalog()['tracks'])
        p=service.skills_plan({'track_id':selected_track,'mode':'track'} if selected_track else {})
        result={'skills_plan_id':p['id'],'message':telegram(p)}
    elif op=='state':result={'state':service.state(),'message':'Состояние сервиса обновлено. /tasks — задачи; /hh — отклики.'}
    elif op=='tasks':result={'tasks':service.tasks(),'message':'Задачи сохранены в сервисе. Доступные действия указаны отдельно для каждой.'}
    elif op=='search':
        task=await service.search(request_id,scope);result={'task':task,'message':'🔎 Поиск сохранён. '+(describe(scope,service.archive)+'\n' if scope else '')+task['label']+'. '+(task['next_action'] or 'Результат придёт в Telegram и появится в веб-сервисе.')}
    elif op=='control':
        task=service.task(args['task_id']);result={'task':service.control_task(args['task_id'],args['action'],task['revision'],actor),'message':'Запрос управления сохранён. Текущее чтение/расчёт остановится на безопасной границе.'}
    elif op=='prepare_batch':
        from .career_search_scope import WORDS
        number=int(batch[1]) if batch[1].isdigit() else WORDS[batch[1].lower()]
        refs=json.loads(service.store.setting('last-selection') or service.store.setting('last-recommendations') or '{}').get('refs',[])[:number]
        if len(refs)<number:raise ValueError('В последней подборке недостаточно вакансий. Сначала запустите поиск или выберите карточку.')
        selected=[json.loads(service.store.setting('recommendation:'+ref) or '{}') for ref in refs]
        # Resolve all references before creating anything; no guessed ordinal or CV.
        for item in selected:
            cv=service.archive.detail('resume',item['resume_id'])['payload'];job=service.archive.detail('vacancy',item['vacancy_id'])['payload']
            if cv['content_hash']!=item.get('resume_hash') or job.get('archived'):raise ValueError('Подборка устарела. Обновите её перед подготовкой.')
        apps=[service.select_recommendation(ref) for ref in refs]
        result={'application_ids':[a['id'] for a in apps],'message':'✍️ Выбрано откликов: '+str(len(apps))+'. Для каждого показаны CV и режимы подготовки. Выберите API или без API; затем получите форму на проверку. Отправки не было.'}
    elif op=='prepare':
        summary=service.archive.summary()
        if not summary.get('primary_id'):raise ValueError('Сначала выберите CV.')
        app=service.make_application(summary['primary_id'],args['vacancy_id'],summary.get('goal',''))
        result={'application_id':app['id'],'message':'Карточка отклика готова. Составьте письмо и проверьте анкету. Отправки не было.','review_url':'http://127.0.0.1:8788/?application='+app['id']}
    elif op=='review':result={'message':'Отправка требует просмотра точных CV, письма и ответов и отдельного одноразового подтверждения в карточке отклика.','review_url':'http://127.0.0.1:8788/?view=applications'}
    else:result={'needs_input':True,'message':HELP}
    with service.store.connect() as db:service.store.setting_in(db,key,packed({'hash':fingerprint,'reply':result}))
    return result
