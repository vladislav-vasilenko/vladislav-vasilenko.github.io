"""Immutable input provenance for saved reviews. All reads are local, including migration."""
import json
from .analysis_store import document_text,text_hash
from .resume_files import redact_contacts

def ensure_sources(db,report):
    """Link legacy reports only to versions whose actual model-input hash matches."""
    saved=db.execute('SELECT * FROM skill_analysis_sources WHERE key=?',(report['key'],)).fetchone()
    if saved:return dict(saved)
    values={}
    for kind in ('resume','vacancy'):
        values[kind+'_version_id']=None;values[kind+'_text']=None
        for version in db.execute('SELECT * FROM versions WHERE kind=? AND entity_id=? ORDER BY id DESC',(kind,report[kind+'_id'])):
            text=redact_contacts(document_text(kind,json.loads(version['payload'])))
            if text_hash(text)==report[kind+'_hash']:
                values[kind+'_version_id']=version['id'];values[kind+'_text']=text;break
    db.execute('INSERT OR IGNORE INTO skill_analysis_sources VALUES(?,?,?,?,?)',(report['key'],values['resume_version_id'],values['vacancy_version_id'],values['resume_text'],values['vacancy_text']))
    return {'key':report['key'],**values}

def history(store,resume_id='',offset=0,limit=30):
    offset=max(0,offset);limit=max(1,min(100,limit))
    with store.connect() as db:
        clause=' WHERE resume_id=?' if resume_id else '';args=[resume_id] if resume_id else []
        total=db.execute('SELECT COUNT(*) FROM skill_analyses'+clause,args).fetchone()[0]
        reports=db.execute('SELECT payload FROM skill_analyses'+clause+' ORDER BY created_at DESC,key LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
        items=[]
        for row in reports:
            report=json.loads(row[0]);sources=ensure_sources(db,report)
            item={k:report.get(k) for k in ('key','resume_id','vacancy_id','resume_hash','vacancy_hash','goal','model','prompt_version','created_at','recommendation','metrics')}
            for kind in ('resume','vacancy'):
                version=db.execute('SELECT payload FROM versions WHERE id=?',(sources[kind+'_version_id'],)).fetchone()
                payload=json.loads(version[0]) if version else {}
                item[kind+'_title']=payload.get('title',report[kind+'_id']);item[kind+'_version_id']=sources[kind+'_version_id']
                if kind=='vacancy':item['company']=payload.get('company','')
            items.append(item)
    return {'items':items,'total':total}

def detail(store,key):
    with store.connect() as db:
        row=db.execute('SELECT payload FROM skill_analyses WHERE key=?',(key,)).fetchone()
        if not row:raise ValueError('Сохранённый разбор не найден.')
        report=json.loads(row[0]);sources=ensure_sources(db,report);documents={}
        for kind in ('resume','vacancy'):
            version=db.execute('SELECT * FROM versions WHERE id=? AND kind=? AND entity_id=?',(sources[kind+'_version_id'],kind,report[kind+'_id'])).fetchone()
            payload=json.loads(version['payload']) if version else None
            head=db.execute('SELECT payload FROM entities WHERE kind=? AND id=?',(kind,report[kind+'_id'])).fetchone()
            current_hash=text_hash(redact_contacts(document_text(kind,json.loads(head[0])))) if head else None
            documents[kind]={'id':report[kind+'_id'],'version_id':sources[kind+'_version_id'],'text_hash':report[kind+'_hash'],'text':sources[kind+'_text'],'payload':payload,'source_at':version['source_at'] if version else None,'archive_hash':version['content_hash'] if version else None,'matches_current':current_hash==report[kind+'_hash']}
    return {'analysis':{**report,'cached':True,'api_requests':0},'sources':documents}
