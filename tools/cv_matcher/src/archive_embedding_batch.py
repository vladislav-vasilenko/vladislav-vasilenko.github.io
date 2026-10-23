"""Explicit, resumable embedding/ranking of an archived company selection."""
import json
import secrets
import time
from .archive_store import canonical,digest


def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS archive_embedding_batches(id TEXT PRIMARY KEY,state TEXT,payload TEXT,result TEXT,updated REAL)')


def read(archive, identifier=None):
    with archive.connect() as db:
        init(db)
        db.execute("UPDATE archive_embedding_batches SET state='needs_input' WHERE state IN ('running','pausing') AND updated<?",(time.time()-360,))
        r=db.execute('SELECT * FROM archive_embedding_batches WHERE id=?',(identifier,)).fetchone() if identifier else db.execute('SELECT * FROM archive_embedding_batches ORDER BY updated DESC LIMIT 1').fetchone()
    if not r:return None
    p=json.loads(r['payload']);return {'id':r['id'],'state':r['state'],'resume_id':p['resume_id'],'resume_title':p['resume_title'],'companies':p['companies'],'goal':p['goal'],'model':p['model'],'total':len(p['jobs']),'batch_size':p['batch_size'],'result':json.loads(r['result']),'updated':r['updated']}


def prepare(archive,data):
    from .company_catalog import selection
    companies=selection(data.get('companies'))
    if not companies:raise ValueError('Отметьте конкретные компании флажками. Пустой выбор не запускает расчёт всего архива.')
    cv=archive.detail('resume',data.get('resume_id',''))
    if cv['payload'].get('quality')!='full':raise ValueError('Нужно полное резюме.')
    goal=data.get('goal','')
    if not isinstance(goal,str) or not goal.strip() or len(goal)>2000:raise ValueError('Укажите карьерную цель перед сравнением.')
    model=data.get('model','text-embedding-3-small')
    if model!='text-embedding-3-small':raise ValueError('Для пакетного расчёта используйте text-embedding-3-small.')
    rows=archive.entities('vacancy',companies=companies,status='full',exclude_closed=True,all_items=True)['items']
    jobs=[{'id':r['id'],'hash':r['content_hash']} for r in rows]
    if not jobs:raise ValueError('У выбранных компаний нет полных описаний. Сначала выполните дозагрузку.')
    if len(jobs)>20000:raise ValueError('Сузьте набор компаний.')
    p={'resume_id':cv['id'],'resume_title':cv['title'],'resume_hash':cv['content_hash'],'companies':companies,'goal':goal.strip(),'model':model,'jobs':jobs,'batch_size':20}
    ident=secrets.token_hex(12)
    with archive.connect() as db:
        init(db);db.execute('INSERT INTO archive_embedding_batches VALUES(?,?,?,?,?)',(ident,'prepared',canonical(p),canonical({'processed':0,'api_requests':0,'cache_reused':0,'new_compared':0}),time.time()))
    return read(archive,ident)


def control(archive,data):
    with archive.connect() as db:
        init(db);db.execute('BEGIN IMMEDIATE')
        r=db.execute('SELECT * FROM archive_embedding_batches WHERE id=?',(data.get('id'),)).fetchone()
        if not r:raise ValueError('Пакет не найден.')
        action=data.get('action')
        if action=='pause':
            if r['state']=='running':db.execute("UPDATE archive_embedding_batches SET state='pausing' WHERE id=?",(r['id'],))
        elif action=='start':
            if data.get('confirmed') is not True:raise ValueError('Подтвердите расчёт через API для этой выборки.')
            if r['state'] not in ('prepared','paused','needs_input'):raise ValueError('Этот пакет уже выполняется или завершён.')
            if db.execute("SELECT 1 FROM archive_embedding_batches WHERE state IN ('running','pausing')").fetchone():raise ValueError('Другой пакет уже выполняется.')
            db.execute("UPDATE archive_embedding_batches SET state='running',updated=? WHERE id=?",(time.time(),r['id']))
        else:raise ValueError('Выберите запуск или паузу.')
    return read(archive,data['id'])


async def run(archive,identifier,ranker):
    try:
        while True:
            with archive.connect() as db:r=db.execute('SELECT * FROM archive_embedding_batches WHERE id=?',(identifier,)).fetchone()
            if not r or r['state'] not in ('running','pausing'):return
            if r['state']=='pausing':
                with archive.connect() as db:db.execute("UPDATE archive_embedding_batches SET state='paused',updated=? WHERE id=?",(time.time(),identifier))
                return
            p=json.loads(r['payload']);out=json.loads(r['result']);offset=out['processed']
            cv=archive.detail('resume',p['resume_id'])
            if cv['content_hash']!=p['resume_hash']:raise ValueError('Резюме изменилось. Подготовьте новую выборку; полученные векторы сохранены.')
            chosen=p['jobs'][offset:offset+p['batch_size']]
            if not chosen:
                with archive.connect() as db:db.execute("UPDATE archive_embedding_batches SET state='complete',updated=? WHERE id=?",(time.time(),identifier))
                return
            jobs=[]
            for item in chosen:
                job=archive.detail('vacancy',item['id'])
                if job['content_hash']!=item['hash'] or job['availability']=='closed':raise ValueError('Вакансия изменена или закрыта. Подготовьте новую выборку.')
                jobs.append(job['payload'])
            result=await ranker({'resume_id':p['resume_id'],'bundle':{'resumes':[cv['payload']]},'vacancies':jobs,'goal':p['goal'],'model':p['model'],'allow_api':True,'companies_filter':p['companies']})
            out['processed']+=len(chosen)
            for key in ('api_requests','cache_reused','new_compared'):out[key]+=result.get(key,0)
            with archive.connect() as db:db.execute('UPDATE archive_embedding_batches SET result=?,updated=? WHERE id=?',(canonical(out),time.time(),identifier))
    except Exception as error:
        with archive.connect() as db:
            row=db.execute('SELECT result FROM archive_embedding_batches WHERE id=?',(identifier,)).fetchone()
            out=json.loads(row[0]);out['error']=str(getattr(error,'detail',error))[:1000]
            db.execute("UPDATE archive_embedding_batches SET state='needs_input',result=?,updated=? WHERE id=?",(canonical(out),time.time(),identifier))
