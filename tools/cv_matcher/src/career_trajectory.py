"""Owner-edited, goal-first career paths in the existing versioned archive metadata."""
import json
import secrets
import time
from . import career_skills_store as storage
from .career_skills_catalog import SKILLS
from .career_skill_requirements import extract,hits
from .resume_source import matching_text
from .career_trajectory_matching import PRIORITIES,ROLES,PROOFS,ROLE_PROOFS,profile,ENGINE

KINDS={'skill':'Навык на практике','project':'Проект / эксперимент','experience':'Практический опыт','learning':'Обучение','employment':'Карьерный переход','document':'Оформленный результат'}
ACCEPTS={'skill':{'professional','project','research'},'project':{'project','research'},'experience':{'professional'},'learning':{'learning'},'employment':{'employment'},'document':{'document'}}
EVIDENCE_KINDS={'professional','project','research','learning','employment','document'}

def owned_evidence(store):
    with store.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT value FROM archive_meta WHERE key LIKE ? ORDER BY key',(storage.PREFIX+'trajectory-evidence:%',))]

def evidence_catalog(store,archive):
    evidence=owned_evidence(store)
    with archive.connect() as db:ids=[r[0] for r in db.execute("SELECT id FROM entities WHERE kind='resume' ORDER BY id")]
    for rid in ids:
        for row in storage.annotations(store,rid):
            if row['kind']=='explicit_gap':continue
            evidence.append({'id':'cv:'+rid+':'+row['skill_id']+':'+row['kind'],'kind':row['kind'],'skill_ids':[row['skill_id']],'note':row['quote'],'url':row['url'],'state':row['state'],'revision':row['revision'],'resume_id':rid,'source':'owner_statement','artifact_verified':False})
    return evidence

def save_evidence(store,data):
    kind=data.get('kind');skills=data.get('skill_ids',[]);note=data.get('note','');revision=data.get('revision',0)
    if kind not in EVIDENCE_KINDS or not isinstance(skills,list) or len(skills)>30 or any(k not in SKILLS for k in skills):raise ValueError('Проверьте тип и навыки подтверждения.')
    if data.get('reviewed') is not True or not isinstance(note,str) or not 15<=len(note.strip())<=4000:raise ValueError('Опишите результат (15–4000 символов) и подтвердите проверку фактов.')
    from .career_skill_evidence import PLANNED,NEGATIVE,LEARNING,PROFESSIONAL
    if kind!='learning' and (PLANNED.search(note) or NEGATIVE.search(note)):raise ValueError('План или отсутствие опыта не закрывает результат. Добавьте описание выполненной работы.')
    if kind=='professional' and LEARNING.search(note) and not PROFESSIONAL.search(note):raise ValueError('Обучение учитывается отдельно от профессионального опыта.')
    identifier=data.get('id') or secrets.token_hex(12)
    if not isinstance(identifier,str) or len(identifier)!=24 or any(c not in 'abcdef0123456789' for c in identifier) or type(revision) is not int:raise ValueError('Некорректная версия подтверждения.')
    state=data.get('state','completed' if kind=='learning' else 'confirmed')
    if state not in ({'completed','retracted'} if kind=='learning' else {'confirmed','retracted'}):raise ValueError('Укажите выполненный результат или отзыв подтверждения.')
    value={'id':identifier,'kind':kind,'skill_ids':sorted(set(skills)),'note':note.strip(),'url':storage.safe_url(data.get('url','')),'state':state,'revision':revision+1,'source':'owner_statement','artifact_verified':False,'updated':time.time()}
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');old=storage.get(db,'trajectory-evidence:'+identifier)
        if revision!=(old or {}).get('revision',0):raise ValueError('Подтверждение изменилось. Обновите страницу.')
        storage.put(db,'trajectory-evidence:'+identifier,value);storage.put(db,'trajectory-evidence-version:'+identifier+':'+str(value['revision']),value)
    return value

def validate_path(store,value):
    if not isinstance(value,dict):raise ValueError('Нужно описание траектории.')
    label=value.get('label','');goal=value.get('goal','');track=storage.track(store,value.get('track_id'))
    if not track or not isinstance(label,str) or not 1<=len(label.strip())<=180 or not isinstance(goal,str) or not 1<=len(goal.strip())<=2000:raise ValueError('Выберите целевой профиль и опишите карьерную цель.')
    stages=value.get('stages')
    if not isinstance(stages,list) or not 1<=len(stages)<=12:raise ValueError('Траектория содержит от 1 до 12 этапов.')
    identifiers=set();clean=[]
    for stage in stages:
        identifier=stage.get('id','') if isinstance(stage,dict) else ''
        if not isinstance(identifier,str) or not 1<=len(identifier)<=60 or identifier in identifiers:raise ValueError('Этапам нужны уникальные ID.')
        title=stage.get('label','');criteria=stage.get('criteria');parents=stage.get('after',[]);mode=stage.get('mode','all')
        if not isinstance(title,str) or not 1<=len(title.strip())<=180 or mode not in ('all','any') or not isinstance(parents,list) or any(p not in identifiers for p in parents):raise ValueError('Зависимости этапа должны указывать на предыдущие этапы; циклы запрещены.')
        if not isinstance(criteria,list) or not 1<=len(criteria)<=15:raise ValueError('Добавьте 1–15 критериев завершения этапа.')
        checks=[];seen=set()
        for c in criteria:
            if not isinstance(c,dict) or c.get('kind') not in KINDS:raise ValueError('Неизвестный тип критерия.')
            cid=c.get('id');text=c.get('label','');keys=c.get('skill_ids',[]);refs=c.get('evidence_ids',[])
            if not isinstance(cid,str) or not 1<=len(cid)<=60 or cid in seen or not isinstance(text,str) or not 1<=len(text.strip())<=500:raise ValueError('Нужны уникальный ID и описание каждого критерия.')
            if not isinstance(keys,list) or any(k not in SKILLS for k in keys) or not isinstance(refs,list) or len(refs)>30 or any(not isinstance(r,str) or len(r)>180 for r in refs):raise ValueError('Проверьте навыки и ссылки на подтверждения.')
            if c['kind']=='skill' and not keys:raise ValueError('Для критерия навыка выберите хотя бы один навык.')
            priority=c.get('priority','required');proof=c.get('proof_hint','');sources=c.get('sources',[])
            if priority not in PRIORITIES or not isinstance(proof,str) or len(proof)>1000 or not isinstance(sources,list) or len(sources)>3:raise ValueError('Проверьте обязательность и основания критерия.')
            checks.append({'priority':priority,'proof_hint':proof,'sources':sources,'id':cid,'label':text.strip(),'kind':c['kind'],'skill_ids':sorted(set(keys)),'evidence_ids':list(dict.fromkeys(refs))});seen.add(cid)
        clean.append({'id':identifier,'label':title.strip(),'after':list(dict.fromkeys(parents)),'mode':mode,'criteria':checks});identifiers.add(identifier)
    targets=value.get('target_vacancy_ids',[]);roles=value.get('focus_roles',[])
    if not isinstance(targets,list) or len(targets)>30 or any(not isinstance(k,str) or len(k)>200 for k in targets) or not isinstance(roles,list) or any(r not in ROLES for r in roles):raise ValueError('Проверьте целевые вакансии и роли.')
    optional={s['id'] for s in clean if all(c['priority']!='required' for c in s['criteria'])}
    if any(s['id'] not in optional and any(p in optional for p in s['after']) for s in clean):raise ValueError('Дополнительная ветка не должна блокировать обязательный этап.')
    return {'label':label.strip(),'goal':goal.strip(),'track_id':track['id'],'stages':clean,'target_vacancy_ids':list(dict.fromkeys(targets)),'focus_roles':list(dict.fromkeys(roles))}

def save(store,archive,data):
    clean=validate_path(store,data);identifier=data.get('id') or secrets.token_hex(12);revision=data.get('revision',0)
    if not isinstance(identifier,str) or len(identifier)!=24 or any(c not in 'abcdef0123456789' for c in identifier) or type(revision) is not int:raise ValueError('Некорректная версия траектории.')
    known={e['id'] for e in evidence_catalog(store,archive)}
    if any(ref not in known for s in clean['stages'] for c in s['criteria'] for ref in c['evidence_ids']):raise ValueError('Подтверждение не найдено. Обновите список источников.')
    for target in clean['target_vacancy_ids']:archive.detail('vacancy',target)
    for stage in clean['stages']:
        for criterion in stage['criteria']:
            checked=[]
            for source in criterion['sources']:
                if not isinstance(source,dict) or not isinstance(source.get('quote'),str) or not 5<=len(source['quote'])<=500 or source.get('skill_id') not in criterion['skill_ids']:raise ValueError('Некорректная цитата требования.')
                with archive.connect() as db:row=db.execute("SELECT payload FROM versions WHERE kind='vacancy' AND entity_id=? AND id=?",(source.get('vacancy_id'),source.get('version_id'))).fetchone()
                if not row or source['quote'] not in json.loads(row[0]).get('description',''):raise ValueError('Цитата не найдена в исходной версии вакансии.')
                checked.append({k:source[k] for k in ('vacancy_id','version_id','skill_id','quote')})
            criterion['sources']=checked
    basis=data.get('basis');validated_basis=None
    if basis:
        if not isinstance(basis,dict) or not isinstance(basis.get('resumes'),list):raise ValueError('Некорректные источники черновика.')
        with archive.connect() as db:
            vacancy=db.execute("SELECT id FROM versions WHERE kind='vacancy' AND entity_id=? AND id=?",(basis.get('vacancy_id'),basis.get('vacancy_version'))).fetchone()
            if not vacancy:raise ValueError('Снимок исходной вакансии не найден.')
            for cv in basis['resumes']:
                if not isinstance(cv,dict) or not db.execute("SELECT id FROM versions WHERE kind='resume' AND entity_id=? AND id=?",(cv.get('id'),cv.get('version'))).fetchone():raise ValueError('Снимок исходного CV не найден.')
        method=basis.get('method','local-requirements-v1')
        if not isinstance(method,str) or not 1<=len(method)<=100:raise ValueError('Некорректная версия построения траектории.')
        validated_basis={'vacancy_id':basis['vacancy_id'],'vacancy_version':basis['vacancy_version'],'resumes':[{'id':cv['id'],'version':cv['version']} for cv in basis['resumes']],'method':method}
    value={**clean,'id':identifier,'revision':revision+1,'updated':time.time()}
    if validated_basis:value['basis']=validated_basis
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');old=storage.get(db,'trajectory:'+identifier)
        if revision!=(old or {}).get('revision',0):raise ValueError('Траектория изменена в другой вкладке. Обновите её перед сохранением.')
        storage.put(db,'trajectory:'+identifier,value);storage.put(db,'trajectory-version:'+identifier+':'+str(value['revision']),value);storage.put(db,'trajectory-active',identifier)
    return overview(store,archive)

def defaults(store,track_id):
    track=storage.track(store,track_id)
    if not track:raise ValueError('Целевой профиль не найден.')
    keys=sorted(track['skills'],key=lambda k:(-track['skills'][k]['importance'],k))[:3]
    def criterion(identifier,label,kind,skills):return {'id':identifier,'label':label,'kind':kind,'skill_ids':skills,'evidence_ids':[]}
    return {'track_id':track_id,'label':'Переход в '+track['label'],'goal':track['label'],'revision':0,'stages':[
        {'id':'practice','label':'Подтвердить целевые навыки','after':[],'mode':'all','criteria':[criterion('skill_'+k,'Показать практику: '+SKILLS[k]['label'],'skill',[k]) for k in keys]},
        {'id':'project','label':'Получить проверяемый результат','after':['practice'],'mode':'any','criteria':[criterion('project','Выполненный проект с кодом и результатами','project',keys),criterion('work','Подтверждённая практика в рабочем проекте','experience',keys)]},
        {'id':'presentation','label':'Подготовить материалы для перехода','after':['project'],'mode':'all','criteria':[criterion('document','Оформить результаты и целевую версию резюме','document',[])]}]}

def evaluate(path,evidence):
    rows={e['id']:e for e in evidence};stages=[];states={}
    for stage in path['stages']:
        criteria=[]
        for c in stage['criteria']:
            matches=[rows[r] for r in c['evidence_ids'] if r in rows and rows[r]['kind'] in ACCEPTS[c['kind']] and rows[r]['state'] in ('confirmed','completed')]
            skills={k for e in matches for k in e['skill_ids']};met=bool(matches) and set(c['skill_ids']).issubset(skills)
            criteria.append({**c,'met':met,'accepted_evidence':[e['id'] for e in matches],'note':'По подтверждениям пользователя; артефакты автоматически не проверены.' if met else 'Нужен подходящий результат с подтверждением.'})
        required=[c for c in criteria if c.get('priority','required')=='required'];optional=not required;checks=required or criteria
        ready=all(states[p]=='complete' for p in stage['after']);own=all(c['met'] for c in checks) if stage['mode']=='all' else any(c['met'] for c in checks)
        state='complete' if own and ready else 'blocked' if not ready else 'ready';states[stage['id']]=state
        stages.append({**stage,'optional':optional,'required_met':sum(c['met'] for c in required),'required_total':len(required),'criteria':criteria,'state':state,'met':sum(c['met'] for c in criteria),'total':len(criteria)})
    return {**path,'core_completed':sum(s['state']=='complete' and not s['optional'] for s in stages),'core_total':sum(not s['optional'] for s in stages),'stages':stages,'completed':sum(s['state']=='complete' for s in stages),'total':len(stages)}

def overview(store,archive,identifier=None):
    with store.connect() as db:
        paths=[json.loads(r[0]) for r in db.execute('SELECT value FROM archive_meta WHERE key LIKE ? ORDER BY key',(storage.PREFIX+'trajectory:%',))]
        active=identifier or storage.get(db,'trajectory-active')
        if identifier and identifier not in {p['id'] for p in paths}:raise ValueError('Траектория не найдена.')
    selected=next((p for p in paths if p['id']==active),None);evidence=evidence_catalog(store,archive)
    with archive.connect() as db:resumes=[{'id':r['id'],'title':r['title'],'version':r['version_id']} for r in db.execute("SELECT id,title,version_id FROM entities WHERE kind='resume' ORDER BY title")]
    return {'paths':[{'id':p['id'],'label':p['label'],'track_id':p['track_id']} for p in paths],'path':evaluate(selected,evidence) if selected else None,'evidence':evidence,'resumes':resumes,'tracks':storage.tracks(store),'skills':[{'id':k,'label':v['label']} for k,v in SKILLS.items()],'criterion_kinds':KINDS,'priorities':PRIORITIES,'roles':ROLES,'api_requests':0}

def stage_detail(store,archive,identifier,stage_id):
    value=overview(store,archive,identifier);path=value['path'];stage=next((s for s in path['stages'] if s['id']==stage_id),None)
    if not stage:raise ValueError('Этап не найден.')
    track=storage.track(store,path['track_id']);keys={k for c in stage['criteria'] for k in c['skill_ids']} or set(track['skills'])
    weights={k:track['skills'].get(k,{}).get('importance',2) for k in keys};resumes=[]
    from .career_skill_evidence import collect
    practical={k for e in value['evidence'] if e['kind'] in ('professional','project','research') and e['state']=='confirmed' for k in e['skill_ids']}
    for cv in value['resumes']:
        collected=collect(store,archive,cv['id'],[]);text=matching_text(collected['resume']['payload']);mentioned={k for k,_ in hits(text)}&keys
        confirmed={k for k in keys if collected['skills'][k]['state']=='confirmed'};practical.update(confirmed)
        resumes.append({**cv,'mentioned':[SKILLS[k]['label'] for k in sorted(mentioned)],'missing':[SKILLS[k]['label'] for k in sorted(keys-mentioned)],'coverage':sum(weights[k] for k in mentioned),'practical':len(confirmed)})
    resumes.sort(key=lambda r:(-r['coverage'],-r['practical'],r['id']))
    with archive.connect() as db:jobs=[dict(r) for r in db.execute("SELECT id,payload,availability FROM entities WHERE kind='vacancy' AND availability<>'closed'")]
    matches=[];incomplete=0
    for row in jobs:
        job=json.loads(row['payload'])
        if job.get('archived'):continue
        if job.get('description_quality')!='full':incomplete+=1;continue
        required=extract(job,None)['requirements'];by_skill={}
        for r in required:
            if r['skill_id'] not in keys or r['negated']:continue
            weight=1 if r['type']=='required' else .5 if r['type']=='preferred' else .2
            if r['skill_id'] not in by_skill or weight>by_skill[r['skill_id']][0]:by_skill[r['skill_id']]=(weight,r)
        if not by_skill:continue
        score=sum(weights[k]*w for k,(w,_) in by_skill.items());gaps=[k for k,(_,r) in by_skill.items() if r['type']=='required' and k not in practical]
        matches.append({'id':row['id'],'title':job['title'],'company':job.get('company',''),'url':job.get('link',''),'availability':row['availability'],'score':round(score,3),'requirements':[r for _,r in by_skill.values()],'unconfirmed':[SKILLS[k]['label'] for k in gaps]})
    matches.sort(key=lambda j:(-j['score'],j['id']))
    return {'path':path,'stage':stage,'resumes':resumes,'vacancies':matches[:40],'matched_total':len(matches),'incomplete':incomplete,'skill_ids':sorted(keys),'api_requests':0,'method':'Локальный поиск требований этапа во всех полных незакрытых вакансиях, без фильтра по сходству с выбранным CV. Порядок — по важности и типу требований; это не вероятность найма. Подтверждения в профиле не гарантируют готовность ко всем требованиям вакансии.'}


def vacancy_draft(store,archive,vacancy_id,track_id=None,existing=None):
    """Role-aware proposal. Never saves, calls a model or invents candidate facts."""
    detail=archive.detail('vacancy',vacancy_id);job=detail['payload']
    if job.get('description_quality')!='full':raise ValueError('Для построения траектории нужно полное сохранённое описание вакансии.')
    projection=profile(job);grouped={r['skill_id']:r for r in projection['requirements']}
    if not any(r['type']=='required' for r in grouped.values()):raise ValueError('Не найдены однозначные обязательные навыки. Уточните требования вручную: упоминания и пожелания не превращаются в обязательные этапы.')
    catalog=overview(store,archive)
    if not track_id:track_id=(existing or catalog.get('path') or {}).get('track_id','generative')
    base=defaults(store,track_id);base['label']=('Подготовка к '+job['title'])[:180];base['goal']=job['title']+' · '+job.get('company','');base['stages']=[]
    if existing:base.update({k:existing[k] for k in ('id','revision','label','goal')})
    base['focus_roles']=[projection['role']];base['target_vacancy_ids']=list(dict.fromkeys([*(existing or {}).get('target_vacancy_ids',[]),vacancy_id]))
    from .career_skill_evidence import collect
    profiles=[collect(store,archive,cv['id'],[]) for cv in catalog['resumes']]
    manual=catalog['evidence'];old_criteria=[c for s in (existing or {}).get('stages',[]) for c in s['criteria']]
    buckets={k:[] for k in ('validate','learn','practice','preferred','review','specialization')};recommendations=[]
    def refs_for(keys,kind):return [e['id'] for e in manual if e['state'] in ('confirmed','completed') and e['kind'] in ACCEPTS[kind] and set(e['skill_ids'])&set(keys)]
    for key,r in sorted(grouped.items(),key=lambda item:(item[1]['type']!='required',item[1].get('strictness')!='hard',item[0])):
        signals=[p['skills'][key] for p in profiles];own=refs_for([key],'skill')
        practical=bool(own) or any(p['state']=='confirmed' for p in signals)
        conflict=any(p['state']=='conflict' for p in signals) or practical and any(p['state']=='explicit_gap' for p in signals)
        explicit=not practical and not conflict and any(p['state']=='explicit_gap' for p in signals)
        studying=not practical and not conflict and any(p['state']=='studying' for p in signals)
        priority={'required':'required','preferred':'preferred','mentioned':'review'}[r['type']]
        action='validate';label=('Уточнить противоречия: ' if conflict else 'Связать подтверждение: ' if practical else 'Проверить и подтвердить: ')+SKILLS[key]['label']
        if explicit:action='learn';label='Изучить основы: '+SKILLS[key]['label']
        elif studying:action='practice';label='Закрепить на практике: '+SKILLS[key]['label']
        source={'vacancy_id':vacancy_id,'version_id':detail['version_id'],'skill_id':key,'quote':r['quote'][:500]}
        criterion={'id':action+'_'+key,'label':label,'kind':'learning' if explicit else 'skill','skill_ids':[key],'evidence_ids':[] if conflict else refs_for([key],'learning' if explicit else 'skill'),'priority':priority,'proof_hint':PROOFS.get(key,'Выполненный эксперимент или рабочий проект с кодом, результатами и ограничениями.'),'sources':[source]}
        buckets[action if priority=='required' else 'preferred' if priority=='preferred' else 'review'].append(criterion)
        if explicit and priority=='required':buckets['practice'].append({**criterion,'id':'practice_'+key,'label':'Показать практический результат: '+SKILLS[key]['label'],'kind':'skill','evidence_ids':refs_for([key],'skill')})
        recommendations.append({'skill_id':key,'label':SKILLS[key]['label'],'action':action,'priority':priority,'quote':r['quote'],'conflict':conflict,'cv_mentions':[p['resume']['id'] for p in profiles if p['skills'][key]['flags']['cv_mention']]})
    # Existing specializations are retained, but cannot become blockers just
    # because a generic template happened to require them.
    for key in sorted({k for c in old_criteria for k in c['skill_ids']}-set(grouped)):
        buckets['specialization'].append({'id':'specialization_'+key,'label':'Развивать специализацию: '+SKILLS[key]['label'],'kind':'skill','skill_ids':[key],'evidence_ids':refs_for([key],'skill'),'priority':'specialization','proof_hint':PROOFS.get(key,'Проект по выбранной специализации.'),'sources':[]})
    previous=[]
    for prefix,label in [('validate','Сверить имеющийся опыт'),('learn','Закрыть явно отмеченные пробелы'),('practice','Подтвердить практику')]:
        for offset in range(0,len(buckets[prefix]),15):
            sid=prefix+'_'+str(offset//15+1);base['stages'].append({'id':sid,'label':label,'after':list(previous),'mode':'all','criteria':buckets[prefix][offset:offset+15]});previous=[sid]
    role_keys=[r['skill_id'] for r in recommendations if r['priority']=='required']
    proof=ROLE_PROOFS[projection['role']]
    # Owner-reviewed existing project/work evidence is reusable across stages.
    project={'id':'project','label':'Оформить проверяемый результат по задачам роли','kind':'project','skill_ids':role_keys,'evidence_ids':refs_for(role_keys,'project'),'priority':'required','proof_hint':proof,'sources':[]}
    work={**project,'id':'work','label':'Подтвердить результаты выполненной профессиональной работы','kind':'experience','evidence_ids':refs_for(role_keys,'experience')}
    base['stages'].append({'id':'result','label':'Оформить результат для роли','after':previous,'mode':'any','criteria':[project,work]})
    base['stages'].append({'id':'application','label':'Подготовить CV и отклик','after':['result'],'mode':'all','criteria':[{'id':'cv','label':'Оформить целевое CV с проверенными датами и результатами','kind':'document','skill_ids':[],'evidence_ids':[],'priority':'required','proof_hint':'Сверить даты с источниками, описать релевантные результаты без выдуманного опыта.','sources':[]},{'id':'letter','label':'Подготовить сопроводительное письмо с релевантным опытом','kind':'document','skill_ids':[],'evidence_ids':[],'priority':'required','proof_hint':'Связать ключевые требования с реальными проектами и ограничениями опыта.','sources':[]}]})
    for prefix,label in [('preferred','Дополнительно · преимущества'),('review','Уточнить · технологии и методы'),('specialization','Дополнительно · специализация')]:
        for offset in range(0,len(buckets[prefix]),15):base['stages'].append({'id':prefix+'_'+str(offset//15+1),'label':label,'after':[],'mode':'all','criteria':buckets[prefix][offset:offset+15]})
    base['basis']={'vacancy_id':vacancy_id,'vacancy_version':detail['version_id'],'resumes':[{'id':p['resume']['id'],'version':p['resume']['version_id']} for p in profiles],'method':ENGINE}
    base['proposal']={'requirements':recommendations,'preferred':[SKILLS[k]['label'] for k,r in grouped.items() if r['type']=='preferred'],'mentioned':[SKILLS[k]['label'] for k,r in grouped.items() if r['type']=='mentioned'],'role':projection['role_label'],'unmapped':projection['unmapped'],'note':'Черновик по роли и требованиям вакансии, всем текущим CV и сохранённым подтверждениям. Основной стек выделяется по явному заголовку. Преимущества, спорные упоминания и специализации не блокируют обязательные этапы. Уже подтверждённые результаты засчитываются; CV-цитаты требуют проверки. API: 0.'}
    validate_path(store,base)
    return base


def adapt(store,archive,identifier,vacancy_id,revision):
    old=overview(store,archive,identifier)['path']
    if old['revision']!=revision:raise ValueError('Траектория изменена. Обновите её перед адаптацией.')
    return vacancy_draft(store,archive,vacancy_id,old['track_id'],existing=old)


def candidates(archive,query=''):
    if not isinstance(query,str) or len(query)>200:raise ValueError('Поиск вакансии: до 200 символов.')
    with archive.connect() as db:rows=[dict(r) for r in db.execute("SELECT id,title,company FROM entities WHERE kind='vacancy' AND availability<>'closed' AND json_extract(payload,'$.description_quality')='full' ORDER BY last_seen DESC,id")]
    query=query.casefold().strip();rows=[r for r in rows if not query or query in (r['title']+' '+r['company']).casefold()]
    return {'items':rows[:40],'total':len(rows)}
