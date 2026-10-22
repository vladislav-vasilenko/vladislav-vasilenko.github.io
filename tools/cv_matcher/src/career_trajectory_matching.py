"""Local, versioned role/requirement projection shared by plans and vacancy filters."""
import json
import re
from functools import lru_cache
from .career_skills_catalog import SKILLS,VERSION
from .career_skill_requirements import extract,passages,requirement_type,hits

ENGINE='trajectory-role-1:'+VERSION
ROLES={'research':'Исследования и обучение моделей','inference':'Инференс и ML Systems','integration':'Адаптация и интеграция','backend':'Backend / AI-продукты','general':'Профиль требует уточнения'}
PRIORITIES={'required':'Обязательный результат','preferred':'Преимущество','review':'Уточнить обязательность','specialization':'Специализация'}
FOUNDATIONS={'python','pytorch','linear_algebra','calculus','probability','optimization','deep_learning','evaluation','data_curation','model_training','research_methods','agents','containers'}
ANCHORS={'generative':{'diffusion','dit_vae','flow_matching'},'pretraining':{'pretraining'},'post_training':{'alignment','rl','sft'},'ml_systems':{'distributed','fsdp','cuda','profiling','triton','inference','quantization'},'apple':{'mlx','metal'},'robotics':{'robotics','slam','control','ros'}}
TRACK_ROLES={'generative':{'research'},'pretraining':{'research'},'post_training':{'research'},'ml_systems':{'inference'},'apple':{'inference'},'robotics':{'research','integration'}}
PROOFS={
 'python':'Код воспроизводимого пайплайна, инструкция запуска и проверка результатов.',
 'pytorch':'Обучающий цикл, конфигурация, checkpoint и воспроизводимые метрики.',
 'model_training':'Обучение или дообучение модели: данные, конфигурация, baseline и итоговые метрики.',
 'data_curation':'Описание датасета, разбиения, фильтрации и контроля утечек данных.',
 'distributed':'Конфигурация распределённого запуска; число GPU, время, throughput и пиковая память.',
 'fsdp':'Эксперимент FSDP/DeepSpeed: конфигурация sharding и сравнение памяти/скорости с baseline.',
 'research_methods':'Воспроизведение статьи, baseline, сравнение подходов, абляции и ограничения результата.',
 'evaluation':'Выбор метрик, baseline, результаты экспериментов и анализ ошибок.',
 'linear_algebra':'Обоснование математического метода в выполненном эксперименте.',
 'probability':'Обоснование статистики/оценки неопределённости и выводов эксперимента.',
 'optimization':'Выбор оптимизатора и анализ сходимости на воспроизводимом эксперименте.',
 'torch_compile':'Сравнение eager/compiled: корректность, время компиляции, latency и память.',
 'triton':'Ядро с проверкой корректности и benchmark против baseline; ограничения измерений.',
 'quantization':'Замеры качества, памяти и скорости до и после квантизации.',
 'inference':'Работающий serving/inference pipeline с замерами latency, throughput и памяти.',
 'backend':'Работающий API, тесты, обработка ошибок и инструкция развёртывания.',
 'containers':'Воспроизводимое окружение, контейнер/манифесты и проверка запуска.',
 'agents':'Пример применения агента, проверка его кода/результатов и ограничения автоматизации.'}
ROLE_PROOFS={'research':'Исследовательский результат: код, данные/конфигурация, baseline, абляции, метрики и выводы.', 'inference':'Инженерный результат: pipeline инференса, корректность и замеры latency/throughput/VRAM.', 'integration':'Результат адаптации: fine-tuning/интеграция, сравнение качества и воспроизводимое развёртывание.', 'backend':'Работающий AI-сервис: API, тесты, наблюдаемость, обработка ошибок и развёртывание.', 'general':'Проверяемый результат по задачам роли с кодом, измерениями и описанием ограничений.'}

def role(job):
    title=job.get('title','').lower();body=job.get('description','').lower()
    if re.search(r'backend|back.end|full.stack|б[эе]кенд',title):return 'backend'
    if re.search(r'adaptation|integration|интеграц|адаптац',title):return 'integration'
    if re.search(r'inference|serving|инференс|ml systems',title):return 'inference'
    if re.search(r'research|researcher|исследов|scientist',title):return 'research'
    if re.search(r'команда harness|слой инструментов|адаптац.{0,30}интеграц',body):return 'integration'
    if re.search(r'задача.{0,80}инференс|инфраструктур.{0,60}инференс|распредел[её]нного инференса',body):return 'inference'
    if re.search(r'генеративн|diffusion|предобуч|pre.training|исследова',body):return 'research'
    return 'general'

@lru_cache(maxsize=2048)
def _profile(serialized):
    job=json.loads(serialized);extraction=extract(job,None);rows=list(extraction['requirements']);text=job.get('description','')
    for quote,mode,section,offset in passages(text):
        kind,negated,strictness=requirement_type(quote,mode,section)
        # "Core stack" is stronger than a casual technology mention, but does not
        # turn an explicitly preferred or negated sentence into a blocker.
        core=bool(re.search(r'основной стек|core stack|must.have stack',section,re.I))
        for key,_ in hits(quote):
            rows.append({'skill_id':key,'quote':quote[:500],'quote_start':offset,'type':'required' if core and kind=='mentioned' and not negated else kind,'strictness':strictness,'negated':negated,'section':section,'source':'core_stack' if core else 'local_rules'})
    grouped={};weights={'required':3,'preferred':2,'mentioned':1}
    for r in rows:
        if r['negated']:continue
        old=grouped.get(r['skill_id'])
        if old is None or weights[r['type']]>weights[old['type']]:grouped[r['skill_id']]=r
    return {'role':role(job),'role_label':ROLES[role(job)],'requirements':list(grouped.values()),'unmapped':extraction['unmapped'],'engine':ENGINE}

def profile(job):return _profile(json.dumps(job,sort_keys=True,ensure_ascii=False))

def paths(store):
    with store.connect() as db:return [json.loads(r[0]) for r in db.execute("SELECT value FROM archive_meta WHERE key LIKE 'career-skills:trajectory:%' ORDER BY key")]

def relations(store,job,path_rows=None):
    routes=paths(store) if path_rows is None else path_rows
    p=profile(job) if job.get('description_quality')=='full' else {'role':role(job),'requirements':[]};demand={r['skill_id'] for r in p['requirements']};links=[]
    for route in routes:
        explicit=job['id'] in route.get('target_vacancy_ids',[]) or job['id']==route.get('basis',{}).get('vacancy_id')
        # Domain mentions can associate a role without becoming completion blockers.
        keys={k for s in route['stages'] for c in s['criteria'] if c.get('priority','required') in ('required','review') for k in c['skill_ids']}
        intersection=keys&demand;distinct=intersection-FOUNDATIONS
        allowed=set(route.get('focus_roles') or TRACK_ROLES.get(route['track_id'],[]))
        if not allowed:allowed={p['role']}
        systems={r['skill_id'] for r in p['requirements'] if r['type']=='required'}&{'distributed','fsdp','cuda','profiling','inference'}
        role_matches=p['role'] in allowed or route['track_id']=='ml_systems' and len(systems)>=2
        anchor=bool(distinct&ANCHORS.get(route['track_id'],distinct))
        inferred=job.get('description_quality')=='full' and role_matches and anchor and (len(intersection)>=2 or bool(distinct&{'diffusion','flow_matching','pretraining','alignment','robotics','inference','backend'}))
        if explicit or inferred:
            quotes=[r['quote'] for r in p['requirements'] if r['skill_id'] in intersection][:3]
            links.append({'path_id':route['id'],'label':route['label'],'revision':route['revision'],'kind':'target' if explicit else 'suggested','role':p['role'],'skills':[SKILLS[k]['label'] for k in sorted(intersection)],'quotes':list(dict.fromkeys(quotes)),'reason':'Вакансия выбрана целью маршрута' if explicit else 'Совпадают роль и навыки маршрута; это не оценка готовности кандидата'})
    return {'links':links,'state':'linked' if links else 'needs_description' if job.get('description_quality')!='full' else 'unassigned','intersection':len(links)>1,'role':p['role']}

def accepts(value,projection):
    if not value:return True
    if value=='unassigned':return not projection['links']
    if value=='intersection':return projection['intersection']
    if value=='needs_description':return projection['state']=='needs_description'
    return any(r['path_id']==value for r in projection['links'])
