"""Read-only, bounded metadata for HH and employer overlays. Never creates analyses or embeddings."""
import json
import re
from .analysis_store import document_text,text_hash
from .resume_files import redact_contacts
from .resume_source import content_hash
from .skill_analysis import MODEL,EXTERNAL_MODEL

def lookup(store,data):
    ids=data.get('ids');resume_id=data.get('resume_id');goal=data.get('goal','');model=data.get('model','text-embedding-3-small')
    provider=data.get('provider','hh')
    uuid=r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}'
    patterns={'hh':r'hh_\d{1,20}','yandex':r'yandex_\d{1,20}','avito':r'avito_\d{1,20}','sber':r'sber_\d{1,20}','ozon':r'ozon_(?:\d{1,20}|'+uuid+')','tbank':r'tbank_'+uuid}
    if provider not in patterns or not isinstance(ids,list) or len(ids)>100 or any(not isinstance(i,str) or not re.fullmatch(patterns[provider],i) for i in ids):raise ValueError('Нужны ID до 100 видимых вакансий одного поддерживаемого источника.')
    if not isinstance(resume_id,str) or not isinstance(goal,str) or len(goal)>2000:raise ValueError('Выберите CV и цель поиска.')
    if model not in ('text-embedding-3-small','text-embedding-3-large'):raise ValueError('Неизвестная embedding-модель.')
    with store.connect() as db:
        cv=db.execute("SELECT payload FROM entities WHERE kind='resume' AND id=?",(resume_id,)).fetchone()
        cv=json.loads(cv[0]) if cv else None
        cv_ready=bool(cv and cv.get('quality')=='full' and content_hash(cv)==data.get('resume_hash'))
        result={'resume_id':resume_id,'resume_title':cv.get('title','') if cv else '', 'goal':goal,'model':model,'cv_ready':cv_ready,'items':[]}
        rows=db.execute("SELECT * FROM entities WHERE kind='vacancy' AND id IN ("+','.join('?' for _ in ids)+')',ids).fetchall() if ids else []
        states=store.analysis_states(db,[dict(r) for r in rows],resume_id,goal,model) if cv_ready else [dict(r) for r in rows]
        cv_hash=text_hash(redact_contacts(document_text('resume',cv))) if cv_ready else None
        for row in states:
            job=json.loads(row['payload']);item={'id':row['id'],'title':job['title'],'saved':True,'source_at':row['source_at'],'full':job.get('description_quality')=='full','closed':row['availability']=='closed'}
            if cv_ready:
                item['score']=row['ranking']['score'] if item['full'] and row.get('ranking') else None;item['ranking_stale']=row.get('ranking_stale',False)
                job_hash=text_hash(redact_contacts(document_text('vacancy',job)))
                saved=db.execute('SELECT payload FROM skill_analyses WHERE resume_id=? AND vacancy_id=? AND resume_hash=? AND vacancy_hash=? AND goal=? AND model IN (?,?) ORDER BY created_at DESC LIMIT 1',(resume_id,row['id'],cv_hash,job_hash,goal.strip(),MODEL,EXTERNAL_MODEL)).fetchone()
                if saved and item['full']:
                    report=json.loads(saved[0]);missing=[r['requirement'] for r in report['requirements'] if r['status'] in ('not_evidenced','explicit_gap')]
                    item['recommendation_reason']=report.get('recommendation_reason','');item['coverage']=report['metrics']['overall']['percent'];item['missing_skills']=missing[:24];item['missing_count']=len(missing);item['analysis_key']=report['key']
                else:item['analysis_stale']=bool(db.execute('SELECT 1 FROM skill_analyses WHERE resume_id=? AND vacancy_id=? LIMIT 1',(resume_id,row['id'])).fetchone())
            result['items'].append(item)
    return result
