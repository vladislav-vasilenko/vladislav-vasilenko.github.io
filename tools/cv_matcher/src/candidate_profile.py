"""Reusable factual form data, separate from professional CV/model context."""
import json,re,time
from urllib.parse import urlsplit

LABELS={'first_name':'Имя','last_name':'Фамилия','phone':'Телефон','email':'Email','city':'Город','telegram_url':'Соцсети · Telegram','portfolio_url':'Портфолио'}
def same_value(field,expected,observed):
 if expected==observed:return True
 return field_key(field)=='phone' and isinstance(expected,str) and isinstance(observed,str) and len(re.sub(r'\D','',expected))>=7 and re.sub(r'\D','',expected)==re.sub(r'\D','',observed)
def field_key(field):
 if field.get('type') in ('file','checkbox','radio','select') or field.get('purpose') in ('about','cover'):return None
 label=re.sub(r'[\s*:_-]+',' ',str(field.get('label','')).lower()).strip()
 aliases={'first_name':{'имя','ваше имя','first name','given name'},'last_name':{'фамилия','ваша фамилия','last name','surname','family name'},'phone':{'телефон','номер телефона','ваш телефон','phone','phone number','mobile phone'},'email':{'email','e mail','ваш email','электронная почта','адрес электронной почты','почта'},'city':{'город','город проживания','city'},'telegram_url':{'соцсети','ссылки на соцсети','ссылка на соцсети','вконтакте, телеграм и другие','telegram','телеграм'},'portfolio_url':{'портфолио','ссылка на портфолио','сайт с портфолио','portfolio','portfolio url'}}
 return next((key for key,names in aliases.items() if label in names),None)

def init(db):
 db.execute('CREATE TABLE IF NOT EXISTS candidate_profile(field TEXT PRIMARY KEY,value TEXT,revision INTEGER,updated REAL,source TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS candidate_profile_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,field TEXT,value TEXT,revision INTEGER,updated REAL,source TEXT)')

def read_db(db):
 rows={r['field']:dict(r) for r in db.execute('SELECT * FROM candidate_profile')}
 return {'values':{key:rows.get(key,{}).get('value','') for key in LABELS},'revisions':{key:rows.get(key,{}).get('revision',0) for key in LABELS},'labels':LABELS}

def defaults(db,fields,context=None):
 p=read_db(db)
 result={f['id']:{'value':p['values'][key],'revision':p['revisions'][key],'key':key} for f in fields if (key:=field_key(f)) and p['values'].get(key) and not f.get('value') and not f.get('manual_only')}
 # The employer uses a structured city choice. Freeze its exact display label
 # in the preview; a bare search query is never the approved final value.
 for f in fields:
  if f.get('control')=='tbank_city' and f['id'] in result and result[f['id']]['value']=='Москва':result[f['id']]['value']='Россия, г Москва'
 # Composite name fields use only the two explicitly saved profile values.
 for f in fields:
  label=re.sub(r'[\s*:_-]+',' ',str(f.get('label','')).lower()).strip()
  if label in ('фамилия и имя','имя и фамилия') and f.get('type')=='text' and not f.get('value') and not f.get('manual_only') and p['values']['first_name'] and p['values']['last_name']:
   keys=('last_name','first_name') if label.startswith('фамилия') else ('first_name','last_name')
   result[f['id']]={'value':' '.join(p['values'][k] for k in keys),'revision':{k:p['revisions'][k] for k in keys},'key':'first_name+last_name'}
 # Resume URLs belong to the selected application CV, never a global contact profile.
 cv_url=(context or {}).get('resume_url') or ''
 try:
  u=urlsplit(cv_url);valid=u.scheme in ('http','https') and bool(u.hostname) and not u.username and not u.password and not any(ord(c)<32 for c in cv_url)
 except ValueError:valid=False
 if valid:
  for f in fields:
   if f.get('purpose')=='resume_url' and f.get('type') in ('text','url') and not f.get('manual_only') and not f.get('value'):
    result[f['id']]={'value':cv_url,'revision':(context or {}).get('resume_hash',''),'key':'resume_url'}
 return result

def read(store):
 with store.connect() as db:return read_db(db)

def save(store,values,revisions,source='owner'):
 if not isinstance(values,dict) or not values or set(values)-set(LABELS) or not isinstance(revisions,dict):raise ValueError('Неизвестные поля профиля.')
 for key,value in values.items():
  if not isinstance(value,str) or len(value)>254 or any(ord(c)<32 for c in value):raise ValueError('Некорректное значение профиля.')
  value=value.strip()
  if value and key=='email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise ValueError('Проверьте email.')
  if value and key=='phone' and not (re.fullmatch(r'\+?[\d() .-]{7,40}',value) and 7<=len(re.sub(r'\D','',value))<=15):raise ValueError('Проверьте номер телефона с кодом страны.')
  if value and key in ('telegram_url','portfolio_url'):
   try:
    u=urlsplit(value);valid=u.scheme=='https' and bool(u.hostname) and not u.username and not u.password and not any(c.isspace() for c in value)
   except ValueError:valid=False
   if not valid:raise ValueError('Укажите HTTPS-ссылку без логина и пароля.')
 with store.connect() as db:
  db.execute('BEGIN IMMEDIATE');current=read_db(db)
  for key in values:
   if revisions.get(key)!=current['revisions'][key]:raise ValueError('Данные уже изменились. Откройте последнюю версию профиля.')
  for key,value in values.items():
   value=value.strip()
   if value==current['values'][key]:continue
   revision=current['revisions'][key]+1;stamp=time.time()
   db.execute('INSERT OR REPLACE INTO candidate_profile VALUES(?,?,?,?,?)',(key,value,revision,stamp,source))
   db.execute('INSERT INTO candidate_profile_versions(field,value,revision,updated,source) VALUES(?,?,?,?,?)',(key,value,revision,stamp,source))
  # Exact transfer previews include the defaults. Revoke queued approvals on edit.
  for row in db.execute("SELECT DISTINCT a.app_id FROM application_approvals a WHERE a.status='approved' AND json_extract(a.payload,'$.action')='career_fill'").fetchall():
   store._invalidate(db,row['app_id']);db.execute("UPDATE application_workflow SET state='needs_input' WHERE app_id=? AND state='fill_approved'",(row['app_id'],))
 return read(store)

def import_saved_contacts(store):
 """Explicit owner-requested migration; never mine CV text or model drafts."""
 values={};sources={}
 with store.connect() as db:
  rows=db.execute("SELECT v.*,f.payload FROM application_field_versions v JOIN application_form_versions f ON f.app_id=v.app_id AND f.fingerprint=v.form_fingerprint JOIN applications a ON a.id=v.app_id WHERE json_extract(a.context,'$.channel')='career' AND v.actor IN ('user','telegram_user') ORDER BY v.created DESC,v.id DESC LIMIT 1000").fetchall()
  for row in rows:
   form=json.loads(row['payload']);f=next((f for f in form['fields'] if f['id']==row['field_id']),None);key=field_key(f or {})
   value=json.loads(row['value'])
   if key and key not in values and isinstance(value,str) and value.strip():values[key]=value;sources[key]=row['app_id']
  profile=read_db(db)
 values={k:v for k,v in values.items() if not profile['values'][k]}
 if values:save(store,values,{k:profile['revisions'][k] for k in values},'saved_owner_answers')
 return list(values)
