"""User supplied professional facts, explicitly separate from imported HH snapshots."""
import json
from datetime import date,datetime,timezone
from .archive_store import canonical

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS resume_supplements(id INTEGER PRIMARY KEY AUTOINCREMENT,resume_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)')

def read(store,resume_id):
    with store.connect() as db:
        init(db);rows=db.execute('SELECT * FROM resume_supplements WHERE resume_id=? ORDER BY id',(resume_id,)).fetchall()
    latest={}
    for row in rows:
        p=json.loads(row['payload']);latest[p['key']]={**p,'version_id':row['id'],'created_at':row['created_at'],'source':'user_confirmed'}
    return list(latest.values())

def save(store,resume_id,value):
    store.detail('resume',resume_id)
    if not isinstance(value,dict):raise ValueError('Нужен блок опыта.')
    clean={}
    for k,limit in [('key',100),('company',300),('role',500),('description',10000)]:
        v=value.get(k)
        if not isinstance(v,str) or not 1<=len(v.strip())<=limit:raise ValueError('Проверьте поле: '+k)
        clean[k]=v.strip()
    try:
        clean['start']=date.fromisoformat(value['start']).isoformat();clean['end']=date.fromisoformat(value['end']).isoformat()
        if clean['end']<clean['start']:raise ValueError()
    except (ValueError,KeyError,TypeError):raise ValueError('Проверьте даты работы.') from None
    with store.connect() as db:
        init(db);old=db.execute("SELECT payload FROM resume_supplements WHERE resume_id=? AND json_extract(payload,'$.key')=? ORDER BY id DESC LIMIT 1",(resume_id,clean['key'])).fetchone()
        if not old or json.loads(old[0])!=clean:db.execute('INSERT INTO resume_supplements(resume_id,payload,created_at) VALUES(?,?,?)',(resume_id,canonical(clean),datetime.now(timezone.utc).isoformat()))
    return read(store,resume_id)
