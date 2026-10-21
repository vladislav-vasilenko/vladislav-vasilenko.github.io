"""Versioned skills projections in existing ArchiveStore.archive_meta; no new DB."""
import copy,json,math,re,time
from urllib.parse import urlsplit
from .application_workflow import packed
from .career_skills_catalog import SKILLS,TRACKS,VERSION

PREFIX='career-skills:'
KINDS={'professional','project','research','learning','explicit_gap'}

def get(db,key,default=None):
 row=db.execute('SELECT value FROM archive_meta WHERE key=?',(PREFIX+key,)).fetchone()
 return json.loads(row[0]) if row else copy.deepcopy(default)
def put(db,key,value):db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)',(PREFIX+key,packed(value)))

def tracks(store):
 with store.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  for key,value in TRACKS.items():
   if get(db,'track:'+key) is None:
    put(db,'track:'+key,value);put(db,'track-version:'+key+':1',value)
  return [json.loads(r[0]) for r in db.execute("SELECT value FROM archive_meta WHERE key LIKE ? ORDER BY key",(PREFIX+'track:%',))]

def track(store,key):
 return next((t for t in tracks(store) if t['id']==key),None)

def save_track(store,data):
 if not isinstance(data,dict):raise ValueError('Нужно описание трека.')
 key=data.get('id');label=data.get('label');skills=data.get('skills');revision=data.get('revision')
 if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,49}',key) or not isinstance(label,str) or not 1<=len(label.strip())<=100 or type(revision) is not int:raise ValueError('Проверьте название и версию трека.')
 if not isinstance(skills,dict) or not 1<=len(skills)<=len(SKILLS) or set(skills)-set(SKILLS):raise ValueError('Выберите известные компетенции трека.')
 for value in skills.values():
  if not isinstance(value,dict) or type(value.get('importance')) is not int or not 1<=value['importance']<=3:raise ValueError('Важность навыка — 1–3.')
  hours=value.get('effort_hours')
  if not isinstance(hours,list) or len(hours)!=2 or any(type(h) not in (int,float) or not math.isfinite(h) for h in hours) or not .5<=hours[0]<=hours[1]<=500:raise ValueError('Оценка упражнения — от 0,5 до 500 часов.')
 tracks(store)
 with store.connect() as db:
  db.execute('BEGIN IMMEDIATE');old=get(db,'track:'+key)
  if revision!=(old or {}).get('revision',0):raise ValueError('Трек уже изменён. Откройте последнюю версию.')
  value={'id':key,'label':label.strip(),'skills':{k:{'importance':v['importance'],'effort_hours':v['effort_hours']} for k,v in skills.items()},'revision':revision+1,'catalog_version':VERSION,'source':'owner','updated':time.time(),'aliases':(old or {}).get('aliases',[])}
  put(db,'track:'+key,value);put(db,'track-version:'+key+':'+str(value['revision']),value)
 return value

def safe_url(url):
 if not url:return ''
 if not isinstance(url,str) or len(url)>1000:raise ValueError('Ссылка слишком длинная.')
 try:
  u=urlsplit(url)
  if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or any(c.isspace() for c in url):raise ValueError()
 except ValueError:raise ValueError('Нужна HTTPS-ссылка без паролей, query и fragment.') from None
 return url

def annotations(store,resume_id):
 with store.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT value FROM archive_meta WHERE key LIKE ? ORDER BY key',(PREFIX+'evidence:'+resume_id+':%',))]

def save_evidence(store,archive,data):
 if not isinstance(data,dict):raise ValueError('Нужно подтверждение навыка.')
 rid=data.get('resume_id');key=data.get('skill_id');kind=data.get('kind');state=data.get('state');revision=data.get('revision')
 if not isinstance(rid,str) or key not in SKILLS or kind not in KINDS or type(revision) is not int:raise ValueError('Проверьте CV, навык, тип и версию подтверждения.')
 allowed={'studying','completed','planned','retracted'} if kind=='learning' else {'confirmed','not_confirmed','retracted'}
 if state not in allowed:raise ValueError('Некорректный статус подтверждения.')
 note=data.get('note','')
 if not isinstance(note,str) or not 15<=len(note.strip())<=4000:raise ValueError('Опишите конкретный опыт или результат: 15–4000 символов.')
 if kind=='professional' and state=='confirmed':
  from .career_skill_evidence import NEGATIVE,PLANNED,LEARNING,PROFESSIONAL
  if NEGATIVE.search(note) or PLANNED.search(note) or (LEARNING.search(note) and not PROFESSIONAL.search(note)):raise ValueError('План или курс не подтверждает профессиональный опыт. Выберите обучение, проект или уточните рабочий результат.')
 url=safe_url(data.get('url',''));detail=archive.detail('resume',rid)
 name='evidence:'+rid+':'+key+':'+kind
 with store.connect() as db:
  db.execute('BEGIN IMMEDIATE');old=get(db,name)
  if revision!=(old or {}).get('revision',0):raise ValueError('Подтверждение изменилось. Откройте последнюю версию.')
  value={'resume_id':rid,'skill_id':key,'kind':kind,'state':state,'quote':note.strip(),'url':url,'revision':revision+1,'created':time.time(),'source':'owner_statement','resume_version_id':detail['version_id'],'artifact_verified':False}
  put(db,name,value);put(db,'evidence-version:'+rid+':'+key+':'+kind+':'+str(value['revision']),value)
 return value

def selection(store,resume_id):
 with store.connect() as db:return get(db,'selection:'+resume_id)

def save_selection(store,resume_id,value):
 with store.connect() as db:put(db,'selection:'+resume_id,value)

def save_plan(store,key,value):
 with store.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  old=get(db,'plan:'+key)
  if old:return old
  put(db,'plan:'+key,value)
 return value

def history(store,resume_id,limit=20):
 with store.connect() as db:
  rows=db.execute("SELECT value FROM archive_meta WHERE key LIKE ? AND json_extract(value,'$.resume.id')=? ORDER BY json_extract(value,'$.created') DESC LIMIT ?",(PREFIX+'plan:%',resume_id,limit)).fetchall()
  return [{'id':p['id'],'created':p['created'],'track':p['track']['label'],'track_revision':p['track']['revision'],'selected':len(p['vacancies']),'requirements':len(p['requirements']),'confirmed':p['summary']['confirmed'],'unknown':p['summary']['unknown'],'studying':p['summary']['studying'],'fingerprint':p['fingerprint']} for p in map(lambda r:json.loads(r[0]),rows)]

def read_plan(store,identifier):
 if not isinstance(identifier,str) or not re.fullmatch(r'[a-f0-9]{64}',identifier):raise ValueError('Некорректный идентификатор плана.')
 with store.connect() as db:p=get(db,'plan:'+identifier)
 if not p:raise ValueError('План не найден.')
 return p
