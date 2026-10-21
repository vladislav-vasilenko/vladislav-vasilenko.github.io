"""Read-only analytics over observed archive history, never an estimate of all jobs."""
import json,re,math
from datetime import datetime,timezone,timedelta
from .analysis_store import text_hash,document_text
from .resume_source import matching_text
from .resume_files import redact_contacts

# One primary category per vacancy keeps widths additive. Tags may overlap.
TAXONOMY=[
 ('pretraining','LLM Pretraining',r'pre[ -]?train|предобуч|претрен'),
 ('post_training','Post-training',r'post[ -]?train|пост.?обуч|\b(?:sft|dpo|rlhf|rlvr)\b'),
 ('diffusion','Diffusion / Flow Matching',r'diffusion|диффуз|flow[\s-]*matching|stable diffusion|\bflux\b|генераци[яию].{0,25}(?:изображ|видео)'),
 ('rag','RAG / LLM Applications',r'\brag\b|retrieval.augmented|llm.{0,25}(?:agent|агент|прилож)|\bllm\b|языков.{0,15}модел'),
 ('cuda','CUDA / GPU kernels',r'\bcuda\b|\bcudnn\b|\bcutlass\b|gpu[ -]?kernel|ядр.{0,10}gpu'),
 ('apple','Apple MLX / MPS / Metal',r'\bmlx\b|\bmps\b|\bmetal\b|apple silicon'),
 ('infrastructure','ML Infrastructure',r'mlops|\btriton\b|inference|инференс|распредел[её]нн.{0,20}обуч|\b(?:fsdp|deepspeed)\b'),
 ('research','DL Engineering / Research',r'deep learning|глубок.{0,12}обуч|\bpytorch\b|нейросет|исследовани[яй].{0,40}(?:модел|генератив)|\b(?:ML|DL|AI)\s+research|research\s+(?:scientist|engineer)'),
 ('classical','Classical ML / Data',r'machine learning|машинн.{0,12}обуч|data scien|\b(?:ml|catboost|xgboost)\b'),
 ('other','Не классифицировано',r'(?!)')]
from .career_taxonomy import DOMAINS,ROLES,matches as market_matches
CORE_TAXONOMY=TAXONOMY[:-1]
TAXONOMY=CORE_TAXONOMY+DOMAINS+ROLES+TAXONOMY[-1:]

def apple_match(text,pattern):
    for match in re.finditer(pattern,text,re.I):
        term=match.group(0).casefold()
        before=text[max(0,match.start()-80):match.start()]
        after=text[match.end():match.end()+80]
        around=before+' '+term+' '+after
        if term=='metal' and re.search(r'bare[\s–—-]*$',before,re.I):continue
        if term=='mlx' or term.startswith('metal performance'):return match
        context=re.sub(r'bare[\s–—-]*metal','physical server',before+' '+after,flags=re.I)
        apple=bool(re.search(r'\bapple\b|macos|\bmetal\b|\bm[1-9]\b',context,re.I))
        if term=='mps':
            if re.search(r'nvidia|multi[ -]?process service',around,re.I) and not apple:continue
            if apple or re.search(r'pytorch|torch|mps\s+(?:backend|device)|(?:device|бэкенд)\s*[:=(]?\s*[\'"]?mps',around,re.I):return match
        elif term=='metal':
            if re.search(r'^\s+(?:performance\s+shaders|shading\s+language|compute|api\b|shaders?\b|kernels?\b)',after,re.I) or apple:return match
        elif re.search(r'pytorch|torch|\bmlx\b|нейросет|обучени|инференс|machine learning',around,re.I):return match
    return None

def classify(data):
    description=data.get('description','')
    # Company marketing / benefit hardware is not a job requirement.
    start=re.search(r'(?:Основные задачи|Что нужно делать|Чем предстоит заниматься|Твои задачи|Обязанности|Требования|Мы жд[её]м,? что вы)\s*:',description,re.I)
    body=description[start.start():] if start else description
    stop=re.search(r'(?:Условия|Мы предлагаем|Что предлагаем|Наши условия|Преимущества работы)\s*:',body,re.I)
    if stop:body=body[:stop.start()]
    skills=re.search(r'Ключевые навыки\s*[:\n]?(.*)',description,re.I|re.S)
    text=data.get('title','')+'\n'+body+('\n'+skills[1] if skills else '')
    tags=[];evidence=[]
    for key,label,pattern in CORE_TAXONOMY:
        match=apple_match(text,pattern) if key=='apple' else re.search(pattern,text,re.I)
        if match:
            tags.append(key)
            evidence.append({'category':key,'match':match.group(0),'quote':text[max(0,match.start()-55):match.end()+75].strip()})
    for item in market_matches(data,body):
        if item['category'] not in tags:tags.append(item['category']);evidence.append(item)
    return {'primary':tags[0] if tags else 'other','tags':tags or ['other'],'evidence':evidence}

def parsed(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if not d.tzinfo else d.astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def number(value,lo,hi):
    return value if type(value) in (int,float) and math.isfinite(value) and lo<=value<=hi else None

def history(entities,versions,events,now):
    """As-known-at snapshots: received versions, explicit closure/reopen only."""
    first=min((parsed(r['first_seen']) for r in entities if parsed(r['first_seen'])),default=None)
    if first is None:return [],None
    by_id={};changes={}
    for version in versions:by_id.setdefault(version['entity_id'],[]).append(version)
    for event in events:changes.setdefault(event['entity_id'],[]).append(event)
    start=max(first,now-timedelta(days=730));cursor=start.replace(day=1,hour=0,minute=0,second=0,microsecond=0);points=[]
    while cursor<=now:
        next_month=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1);cut=min(next_month-timedelta(microseconds=1),now)
        buckets={key:[] for key,_,_ in TAXONOMY}
        for entity in entities:
            if (parsed(entity['first_seen']) or now)>cut:continue
            available=[v for v in by_id.get(entity['id'],[]) if (parsed(v['received_at']) or now)<=cut]
            if not available:continue
            latest=max(available,key=lambda v:(parsed(v['received_at']),v['id']));data=json.loads(latest['payload'])
            known=[e for e in changes.get(entity['id'],[]) if (parsed(e['at']) or now)<=cut]
            closed=bool(data.get('archived'))
            if known:closed=max(known,key=lambda e:(parsed(e['at']),e['id']))['event']=='closed'
            if not closed:buckets[classify(data)['primary']].append(entity['id'])
        points.append({'month':cursor.strftime('%Y-%m'),'as_of':cut.isoformat(),'ids':buckets,'partial_month':cut==now})
        cursor=next_month
    return points,first.isoformat()

def snapshot(archive,resume_id='',goal=None,model='text-embedding-3-small',*,now=None):
    if model not in ('text-embedding-3-small','text-embedding-3-large'):raise ValueError('Неизвестная embedding-модель.')
    summary=archive.summary();resume_id=resume_id or summary.get('primary_id') or '';goal=summary.get('goal','') if goal is None else goal
    if len(goal)>2000:raise ValueError('Цель слишком длинная.')
    now=now or datetime.now(timezone.utc)
    with archive.connect() as db:
        entities=[dict(r) for r in db.execute("SELECT * FROM entities WHERE kind='vacancy' ORDER BY id")]
        archive.analysis_states(db,entities,resume_id,goal,model)
        cv_row=db.execute("SELECT payload FROM entities WHERE kind='resume' AND id=?",(resume_id,)).fetchone()
        cv=json.loads(cv_row[0]) if cv_row else None
        analyses=[dict(r) for r in db.execute('SELECT * FROM skill_analyses WHERE resume_id=? AND goal=? ORDER BY created_at DESC',(resume_id,goal))]
        applications=[dict(r) for r in db.execute('SELECT a.id,a.context,a.status,c.stage FROM applications a LEFT JOIN application_crm c ON c.app_id=a.id ORDER BY a.created DESC')]
        observations=[dict(r) for r in db.execute('SELECT vacancy_id,status FROM hh_observations ORDER BY observed_at DESC')]
        versions=[dict(r) for r in db.execute("SELECT id,entity_id,payload,received_at FROM versions WHERE kind='vacancy' ORDER BY received_at,id")]
        events=[dict(r) for r in db.execute("SELECT id,entity_id,event,at FROM events WHERE kind='vacancy' AND event IN ('closed','reopened') ORDER BY at,id")]
    cv_hash=text_hash(redact_contacts(matching_text(cv))) if cv else None
    apps={}
    for a in applications:
        ctx=json.loads(a['context'])
        if ctx.get('resume_id')==resume_id:apps.setdefault(ctx['vacancy']['id'],a)
    observed={}
    for o in observations:
        if o['status']!='unknown':observed.setdefault(o['vacancy_id'],o['status'])
    valid_analyses={};rows=[]
    for entity in entities:
        data=json.loads(entity['payload']);jid=entity['id'];jh=text_hash(document_text('vacancy',data))
        review=next((a for a in analyses if a['vacancy_id']==jid and a['resume_hash']==cv_hash and a['vacancy_hash']==jh),None)
        analysis=json.loads(review['payload']) if review else None
        # Recompute from validated statuses, do not trust a saved model percentage.
        from .skill_analysis import metrics
        percent=metrics(analysis['requirements'])['overall']['percent'] if analysis else None
        if analysis:valid_analyses[jid]=analysis
        a=apps.get(jid);stage='none'
        if a:
            crm=a['stage'];state=a['status']
            stage='offer' if crm=='offer' else 'interview' if crm in ('stage_1','stage_2','stage_3','ai_screened') else 'rejected' if crm=='rejected' or state=='rejected' else 'applied' if crm and crm!='preparing' or state in ('submitted','viewed','invited','completed','withdrawn') else 'draft'
        if stage in ('none','draft'):
            status=observed.get(jid)
            if status=='rejected':stage='rejected'
            elif status in ('submitted','viewed','invited'):stage='applied'
        manual=entity.get('manual_application',{})
        if manual.get('marked') and stage in ('none','draft'):stage='applied'
        ranking=entity.get('ranking') or {};taxonomy=classify(data)
        from .career_taxonomy import classify_work_format
        work_fmt,reg=classify_work_format(data,data.get('description',''))
        rows.append({'id':jid,'title':entity['title'],'company':entity['company'],'url':data.get('link'),'category':taxonomy['primary'],'tags':taxonomy['tags'],'classification_evidence':taxonomy['evidence'],
                     'work_format':work_fmt,'region':reg,'location':data.get('location') or data.get('city') or (data.get('locations') or [''])[0],
                     'manual_application':manual,'first_seen':entity['first_seen'],'availability':entity['availability'],'quality':data.get('description_quality'),'fit':number(percent,0,100),'alignment':number(ranking.get('goal_similarity'),-1,1),'similarity':number(ranking.get('cv_similarity'),-1,1),'ranking':number(ranking.get('score'),-1,1),'ranking_stale':entity.get('ranking_stale',False),
                     'stage':stage,'application_id':a['id'] if a else None,'analysis_key':analysis.get('key') if analysis else None,'dimensions':metrics(analysis['requirements'])['dimensions'] if analysis else [],'salary':None})
    points,first=history(entities,versions,events,now)
    dimensions={}
    for a in valid_analyses.values():
        for d in metrics(a['requirements'])['dimensions']:
            target=dimensions.setdefault(d['id'],{'label':d['label'],'requirements':0,'confirmed':0,'partial':0,'studying':0,'not_evidenced':0,'explicit_gap':0})
            target['requirements']+=d['requirements']
            for status,count in d['statuses'].items():target[status]+=count
    # Links are evidence references already present in the CV, not a GitHub audit.
    cv_text=matching_text(cv) if cv else ''
    learning=[]
    for match in re.finditer(r'6\.S184|flow[\s-]*matching|diffusion|диффуз',cv_text,re.I):
        excerpt=cv_text[max(0,match.start()-100):match.end()+220].strip()
        if re.search(r'изуч|курс|лаборатор|учеб|stud|course|lecture|MIT',excerpt,re.I) and excerpt not in learning:learning.append(excerpt)
    links=sorted(set(re.findall(r'https://github\.com/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?',cv_text)))
    return {'as_of':now.isoformat(),'resume':{'id':resume_id,'title':cv['title'] if cv else 'CV не выбрано','goal':goal,'model':model},'rows':rows,'history':points,'first_observation':first,'taxonomy':[{'id':key,'label':label} for key,label,_ in TAXONOMY],
            'skills':{'analyses':len(valid_analyses),'dimensions':list(dimensions.values()),'github_links':links,'learning_evidence':learning[:6]},'api_requests':0,
            'methodology':['Это собранная выборка, не весь рынок. Одна вакансия на разных площадках считается отдельно.','Направления определены правилами, без LLM. Основная категория одна; теги технологий, ролей и отраслей пересекаются. Основания показаны в карточке. Дроны/спутники сами по себе не означают оборонную тематику. Возможная связь по работодателю — предположение, не проверенный госконтракт.','X карты зависит от режима: косинусная близость к CV или покрытие требований Luna. Y — косинусная близость к цели. При приближении оси показывают фактический диапазон данных.','Неизвестные оценки не заменяются нулём. Устаревшие CV/JD/цель не используются как текущие оценки.','История отражает полученные снимки и явные закрытия. Исчезновение из выдачи закрытием не считается.','Зарплаты не сохранены структурированно; размер точек одинаковый. GitHub-ссылки не подтверждают качество исследований.']}
