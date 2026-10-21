"""Versioned first-person user clarifications, separate from the imported CV."""
import json,time

def init(db):
 db.execute('CREATE TABLE IF NOT EXISTS candidate_facts(id INTEGER PRIMARY KEY AUTOINCREMENT,resume_id TEXT NOT NULL,fact_key TEXT NOT NULL,text TEXT NOT NULL,source TEXT NOT NULL,created REAL NOT NULL)')

def save(store,resume_id,key,text,source='user_statement'):
 if not isinstance(text,str) or not 1<=len(text.strip())<=8000 or not isinstance(key,str) or not 1<=len(key)<=100:raise ValueError('Нужен краткий факт и его ключ.')
 from .archive_store import ArchiveStore
 ArchiveStore(store.path).detail('resume',resume_id)
 with store.connect() as db:
  init(db);old=db.execute('SELECT text FROM candidate_facts WHERE resume_id=? AND fact_key=? ORDER BY id DESC LIMIT 1',(resume_id,key)).fetchone()
  if not old or old[0]!=text.strip():db.execute('INSERT INTO candidate_facts(resume_id,fact_key,text,source,created) VALUES(?,?,?,?,?)',(resume_id,key,text.strip(),source,time.time()))
 return read(store,resume_id)

def read(store,resume_id):
 with store.connect() as db:
  init(db);rows=db.execute('SELECT * FROM candidate_facts WHERE resume_id=? ORDER BY id',(resume_id,)).fetchall()
 latest={r['fact_key']:dict(r) for r in rows}
 return list(latest.values())

def answer_context(store,context,**extra):
 return {**context,'user_facts':read(store,context['resume_id']),**extra}
