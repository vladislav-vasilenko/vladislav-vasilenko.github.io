"""Semantic shortlist for one explicitly selected CV; no generative LLM calls."""
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import time
from .resume_source import CachedEmbeddings, _load_resume_bundle, matching_text, normalize
from .resume_files import redact_contacts
from .board_import import identity

MODELS = {'text-embedding-3-small':1536, 'text-embedding-3-large':3072}


def chunks(text, size=950):
    text=normalize(redact_contacts(text))
    out=[]
    while len(text)>size:
        stop=text.rfind(' ', 0, size+1)
        if stop<size//2: stop=size
        out.append(text[:stop]);text=text[stop:].strip()
    if text: out.append(text)
    return out


def unit(vector):
    if not isinstance(vector,list) or not vector or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in vector):
        raise ValueError('API вернул некорректный embedding.')
    norm=math.sqrt(sum(n*n for n in vector))
    if not norm: raise ValueError('API вернул нулевой embedding.')
    return [n/norm for n in vector]


class OpenAIBackend:
    def __init__(self, model):
        if model not in MODELS: raise ValueError('Выбери text-embedding-3-small или text-embedding-3-large.')
        self.client=None;self.allow_api=True
        self.model=model;self.dimensions=MODELS[model];self.base_url='https://api.openai.com/v1'
        self.usage_tokens=0;self.request_count=0;self.started=time.monotonic()
    def embed_documents(self, texts):
        if not self.allow_api:raise ValueError('Для этой версии CV, цели или вакансии не хватает готовых векторов. Режим «Без API» остановлен без платного запроса. Рассчитайте недостающие embeddings через API или выберите сохранённый контекст.')
        if self.client is None:
            key=os.environ.get('OPENAI_API_KEY')
            if not key:raise ValueError('Задайте OPENAI_API_KEY в .env проекта и перезапустите локальный сервис.')
            from openai import OpenAI
            self.client=OpenAI(api_key=key,base_url='https://api.openai.com/v1',timeout=30,max_retries=0)
        out=[]
        for start in range(0,len(texts),64):
            if time.monotonic()-self.started>180: raise ValueError('Лимит времени API. Повторите: уже полученные векторы будут взяты из кэша.')
            try:
                response=self.client.embeddings.create(model=self.model,input=texts[start:start+64],encoding_format='float')
                rows=sorted(response.data,key=lambda row:row.index)
                if [r.index for r in rows]!=list(range(len(texts[start:start+64]))): raise ValueError('API вернул неполную партию векторов.')
                for row in rows:
                    if len(row.embedding)!=self.dimensions: raise ValueError('Размерность embedding не соответствует модели.')
                    out.append(unit(row.embedding))
                self.usage_tokens+=response.usage.total_tokens;self.request_count+=1
            except ValueError: raise
            except Exception as exc:
                code=getattr(exc,'status_code',None)
                raise ValueError(f'OpenAI: HTTP {code}. Проверьте ключ, баланс и доступ к модели.' if code else 'Нет ответа OpenAI. Проверьте сеть локального сервиса.') from None
        return out


def rank_vacancies(payload, cache_dir, *, backend_factory=OpenAIBackend, now=None, archive=None):
    now=now or datetime.now(timezone.utc)
    allow_api=payload.get('allow_api',True)
    if not isinstance(allow_api,bool):raise ValueError('Режим API должен быть явно включён или выключен.')
    selected=payload.get('resume_id')
    resume=_load_resume_bundle({**payload['bundle'],'primary_id':selected},now=now)['primary']
    model=payload.get('model','text-embedding-3-small')
    if model not in MODELS: raise ValueError('Неподдерживаемая embedding-модель.')
    goal=str(payload.get('goal') or '').strip()
    if len(goal)>2000: raise ValueError('Карьерная цель больше 2000 символов.')
    rows=payload.get('vacancies',[])
    if not isinstance(rows,list) or len(rows)>200: raise ValueError('За один запуск можно сравнить до 200 вакансий. Ограничьте подборку в расширении.')
    company=payload.get('company_filter','')
    if not isinstance(company,str) or len(company)>300:raise ValueError('Некорректный фильтр компании.')
    from .company_catalog import selection,raw_catalog
    selected_companies=selection(payload.get('companies_filter'),company)
    if selected_companies is not None:
        from .company_filter import company_key
        catalog=raw_catalog(archive) if archive else None
        rows=[r for r in rows if isinstance(r,dict) and company_key(r.get('company',''),catalog) in selected_companies]
    jobs={};excluded=0
    for row in rows:
        if not isinstance(row,dict): excluded+=1;continue
        valid=identity(row.get('link',''))
        if not valid or row.get('description_quality')!='full' or row.get('archived') or len(row.get('description',''))<150:
            excluded+=1;continue
        if not row.get('title') or len(row['description'])>100000: raise ValueError('Проверьте название и размер полного описания вакансии.')
        jobs[valid['id']]={**row,**valid,'description':redact_contacts(row['description'])}
    jobs=list(jobs.values())
    if not jobs: raise ValueError('Нет полных описаний вакансий. Сначала выполните сбор.')
    all_jobs=jobs
    if archive:
        from .archive_store import now_iso
        with archive.connect() as db:
            archive._entity(db,'resume',resume['id'],resume,now_iso())
            for job in all_jobs:archive._entity(db,'vacancy',job['id'],job,now_iso())
    saved=archive.cached_ranking_items(selected,resume['content_hash'],goal,model,all_jobs) if archive else {}
    jobs=[job for job in all_jobs if job['id'] not in saved]
    def finish(ranked,backend=None):
        ranked.sort(key=lambda r:(-r['score'],r['id']))
        result={'generated_at':now.isoformat(),'model':model,'resume_id':selected,'resume_title':resume['title'],'resume_hash':resume['content_hash'],
            'input_count':len(rows),'ranked_count':len(all_jobs),'excluded':excluded,'goal':goal,'company_filter':company,'companies_filter':selected_companies,
            'method':'Mean of 2 strongest JD chunks matched to CV chunks; 80% CV + 20% goal if supplied, otherwise CV only.',
            'score_warning':'Семантическая близость, не процент соответствия и не вероятность найма. Близкие фрагменты не доказывают наличие всех требований.',
            'usage_tokens':getattr(backend,'usage_tokens',0),'api_requests':getattr(backend,'request_count',0),
            'cache_reused':len(saved),'new_compared':len(jobs),'cached':not jobs,'top':ranked[:10],'all':ranked}
        if archive:archive.save_ranking(result)
        return result
    if not jobs:return finish(list(saved.values()))
    cv=chunks(matching_text(resume));texts=list(cv)
    goal_index=len(texts) if goal else None
    if goal: texts.extend(chunks(goal))
    goal_stop=len(texts)
    ranges=[]
    for job in jobs:
        start=len(texts);texts.extend(chunks(job['title']+'\n'+job['description']));ranges.append((start,len(texts)))
    if len(texts)>4000: raise ValueError('Больше 4000 текстовых фрагментов. Уменьшите подборку вакансий.')
    backend=backend_factory(model);backend.allow_api=allow_api
    cache=CachedEmbeddings(backend,cache_dir,version='extension-ranking-v1',vector_store=archive)
    # Cache each batch before the next request so interruption does not discard paid results.
    if archive:
        from .analysis_store import document_text
    vectors=[]
    try:
        for start in range(0,len(texts),64):vectors.extend(cache.embed_documents(texts[start:start+64]))
    finally:
        if archive:
            archive.bind_document('resume',resume['id'],document_text('resume',resume),cache,cv)
            for job,(start,stop) in zip(jobs,ranges):archive.bind_document('vacancy',job['id'],document_text('vacancy',job),cache,texts[start:stop])
    vectors=[unit(v) for v in vectors]
    def dot(a,b):
        if len(a)!=len(b): raise ValueError('Размерности векторов в кэше не совпадают. Очистите кэш этой модели.')
        return sum(x*y for x,y in zip(a,b))
    ranked=[]
    for job,(start,stop) in zip(jobs,ranges):
        pairs=[]
        for index in range(start,stop):
            score,cv_index=max((dot(vectors[index],vectors[c]),c) for c in range(len(cv)))
            pairs.append((score,index,cv_index))
        pairs.sort(reverse=True)
        semantic=sum(row[0] for row in pairs[:2])/min(2,len(pairs))
        direction=max(dot(vectors[i],vectors[g]) for i in range(start,stop) for g in range(goal_index,goal_stop)) if goal else None
        score=.8*semantic+.2*direction if goal else semantic
        evidence=pairs[0]
        ranked.append({'id':job['id'],'title':job['title'],'company':job.get('company',''),'link':job['link'],
                       'score':round(score,4),'cv_similarity':round(semantic,4),'goal_similarity':round(direction,4) if direction is not None else None,
                       'evidence':{'resume':texts[evidence[2]],'vacancy':texts[evidence[1]]},'collected_at':job.get('collected_at'),
                       'vacancy_hash':hashlib.sha256(normalize(job['title']+'\n'+job['description']).encode()).hexdigest(),'ranked_at':now.isoformat()})
    return finish([*ranked,*saved.values()],backend)
