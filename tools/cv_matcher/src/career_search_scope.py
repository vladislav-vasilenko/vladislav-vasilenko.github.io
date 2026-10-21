"""Explicit bounded search scope; publication date is never inferred from collection."""
import re
from datetime import datetime,timezone,timedelta
from .company_catalog import raw_catalog,ADAPTERS
from .company_filter import company_key,clean

TOPICS={'llm_pretraining':('LLM Pretraining',r'pre[ -]?train|предобуч|претрен'), 'post_training':('Post-training',r'post[ -]?train|пост.?обуч|посттрен|sft|dpo|rlhf'), 'diffusion':('Diffusion / Flow Matching',r'diffusion|диффуз|flow matching|\bdit\b'), 'research':('Deep Learning Research',r'deep learning|исследоват|\bresearch\b')}
TOPICS.update({'cuda':('CUDA / GPU kernels',r'\bcuda\b|\bcutlass\b|gpu[ -]?kernels?'), 'apple_ml':('Apple MLX / MPS / Metal',r'\bmlx\b|\bmps\b|\bmetal\b|apple silicon')})
WORDS={'один':1,'две':2,'два':2,'три':3,'пять':5,'семь':7,'десять':10,'двадцать':20,'тридцать':30}

def validate(scope,archive):
    if scope is None:scope={}
    if not isinstance(scope,dict) or set(scope)-{'companies','topics','since_days','limit'}:raise ValueError('Неподдерживаемые параметры поиска.')
    result={};companies=scope.get('companies',[]);catalog=raw_catalog(archive)
    if not isinstance(companies,list) or len(companies)>6 or any(c not in {r['id'] for r in catalog} for c in companies):raise ValueError('Выберите до шести компаний из настроенного каталога.')
    topics=scope.get('topics',[])
    if not isinstance(topics,list) or any(t not in TOPICS for t in topics):raise ValueError('Неизвестное направление поиска.')
    days=scope.get('since_days');limit=scope.get('limit',10)
    if days is not None and (type(days) is not int or not 1<=days<=90):raise ValueError('Период поиска: 1–90 дней.')
    if type(limit) is not int or not 1<=limit<=20:raise ValueError('Размер подборки: 1–20 вакансий.')
    result.update(companies=list(dict.fromkeys(companies)),topics=list(dict.fromkeys(topics)),since_days=days,limit=limit)
    return result

def parse(text,archive):
    if not re.match(r'^(найди|найти|проверь|подбери|ищи|покажи)\b',text.strip(),re.I) or not re.search(r'ваканси|позици',text,re.I):return None
    catalog=raw_catalog(archive);value=clean(text)
    companies=[r['id'] for r in catalog if any(len(clean(a))>=4 and clean(a) in value for a in [r['label'],*r['aliases']])]
    topics=[key for key,(_,pattern) in TOPICS.items() if re.search(pattern,text,re.I)]
    number=r'(\d{1,2}|один|две|два|три|пять|семь|десять|двадцать|тридцать)'
    period=re.search(r'(?:последн\w*|за)\s+'+number+r'\s+дн',text,re.I)
    limit=re.search(r'(?:выбери|отбери|покажи|подбери)\s+'+number,text,re.I)
    integer=lambda m:int(m[1]) if m[1].isdigit() else WORDS[m[1].lower()]
    days=integer(period) if period else 7 if re.search(r'за\s+(?:последнюю\s+)?недел',text,re.I) else None
    return validate({'companies':companies,'topics':topics,'since_days':days,'limit':integer(limit) if limit else 10},archive)

def sources(scope,archive):
    selected=scope.get('companies',[])
    if not selected:return None
    result=[];missing=[]
    for company in raw_catalog(archive):
        if company['id'] not in selected:continue
        valid=[]
        for board in company['boards']:
            from urllib.parse import urlsplit
            if urlsplit(board['url']).hostname not in ADAPTERS:continue
            from .discovery import source_url
            try:valid.append(source_url(board['url']))
            except ValueError:continue
        if valid:result.append(valid[0])
        else:missing.append(company['label'])
    if missing:raise ValueError('Нет поддержанного источника для: '+', '.join(missing)+'. Настройте job board или уточните поиск.')
    return result

def goal(base,scope):
    suffix=' / '.join(TOPICS[key][0] for key in scope.get('topics',[]))
    return (base+'\nНаправления текущего поиска: '+suffix).strip() if suffix else base

def accepts(job,scope,archive,*,now=None):
    if scope.get('companies') and company_key(job.get('company',''),raw_catalog(archive)) not in scope['companies']:return 'company'
    if scope.get('since_days'):
        try:
            stamp=datetime.fromisoformat(str(job.get('pub_date','')).replace('Z','+00:00'))
            # A date without time is explicitly a publication date, assumed UTC.
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        except ValueError:return 'unknown_publication_date'
        now=now or datetime.now(timezone.utc)
        if stamp>now+timedelta(minutes=5) or now-stamp>timedelta(days=scope['since_days']):return 'publication_date'
    return None

def describe(scope,archive):
    labels={r['id']:r['label'] for r in raw_catalog(archive)}
    return 'Компании: '+(', '.join(labels[c] for c in scope.get('companies',[])) or 'источники из настроек')+'\nПериод: '+('последние '+str(scope['since_days'])+' дн. по дате публикации; неизвестные даты исключаются' if scope.get('since_days') else 'без ограничения даты публикации')+'\nНаправления: '+(' / '.join(TOPICS[t][0] for t in scope.get('topics',[])) or 'сохранённая карьерная цель')+'\nДо '+str(scope.get('limit',10))+' рекомендаций, без дополнения неподходящими позициями.'


def search_terms(scope,base_goal=''):
    """Ozon's two native searches; analytical topics remain in the ranking goal."""
    if not scope.get('topics') and not re.search(r'генератив|generative|diffusion|flow matching|\bml\b|transformer|deep learning',base_goal,re.I):return []
    return ['ML','PyTorch']
