"""Versioned field drafts shared by Telegram and the website; approvals bind exact values."""
import json,time

class FormAnswersMixin:
 def answerable_field(self,app_id,field_id,fingerprint,revision):
  with self.connect() as db:
   wf=self._wf(db,app_id);self._blocked_edit(wf);form=json.loads(wf['form'] or 'null')
   if not form or form['fingerprint']!=fingerprint:raise ValueError('Анкета изменилась. Откройте её заново.')
   f=next((f for f in form['fields'] if f['id']==field_id),None)
   row=db.execute('SELECT revision FROM application_field_drafts WHERE app_id=? AND form_fingerprint=? AND field_id=?',(app_id,fingerprint,field_id)).fetchone()
   if not f or revision!=(row[0] if row else 0):raise ValueError('Ответ изменился. Откройте последнюю версию.')
   from .candidate_profile import field_key
   if field_key(f) or f.get('manual_only') or f.get('purpose') in ('contact','cover','resume_url') or f.get('type') not in ('text','textarea'):raise ValueError('Это поле заполняется вашими данными вручную, без генерации ИИ.')
   return f
 def init_form_answers(self,db):
  db.execute('CREATE TABLE IF NOT EXISTS application_form_versions(app_id TEXT,fingerprint TEXT,payload TEXT,created REAL,PRIMARY KEY(app_id,fingerprint))')
  db.execute('CREATE TABLE IF NOT EXISTS application_field_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,app_id TEXT,form_fingerprint TEXT,field_id TEXT,value TEXT,revision INTEGER,actor TEXT,created REAL)')
  db.execute('CREATE TABLE IF NOT EXISTS application_field_drafts(app_id TEXT,form_fingerprint TEXT,field_id TEXT,value TEXT,revision INTEGER,updated REAL,PRIMARY KEY(app_id,form_fingerprint,field_id))')
 def form_answers(self,app_id):
  with self.connect() as db:
   wf=self._wf(db,app_id);form=json.loads(wf['form'] or 'null')
   if not form:return {'values':{},'revisions':{}}
   rows={r['field_id']:dict(r) for r in db.execute('SELECT * FROM application_field_drafts WHERE app_id=? AND form_fingerprint=?',(app_id,form['fingerprint']))}
   from .candidate_profile import defaults
   ctx=json.loads(db.execute('SELECT context FROM applications WHERE id=?',(app_id,)).fetchone()[0]);profile=defaults(db,form['fields'],ctx) if ctx['channel']=='career' else {}
  return {'values':{f['id']:json.loads(rows[f['id']]['value']) if f['id'] in rows and f.get('purpose')!='cover' else wf['draft'] if f.get('purpose')=='cover' else profile.get(f['id'],{}).get('value',f.get('value','')) for f in form['fields']},'revisions':{f['id']:rows.get(f['id'],{}).get('revision',0) for f in form['fields']},'from_profile':{k:v['key'] for k,v in profile.items() if k not in rows and v['key']!='resume_url'},'from_resume':{k:True for k,v in profile.items() if k not in rows and v['key']=='resume_url'}}
 def save_field_answer(self,app_id,field_id,value,fingerprint,revision,actor='user'):
  from .application_workflow import packed,utc
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');wf=self._wf(db,app_id);self._blocked_edit(wf);form=json.loads(wf['form'] or 'null')
   if not form or form['fingerprint']!=fingerprint or form['draft_revision']!=wf['revision']:raise ValueError('Форма изменилась. Откройте её заново.')
   db.execute('INSERT OR IGNORE INTO application_form_versions VALUES(?,?,?,?)',(app_id,fingerprint,packed(form),time.time()))
   field=next((f for f in form['fields'] if f['id']==field_id),None)
   if field and field.get('type')=='file':raise ValueError('Выберите файл на сайте работодателя. Содержимое вложений здесь не загружается.')
   if not field or field.get('purpose')=='cover':raise ValueError('Письмо изменяется отдельным редактором.')
   if field.get('type') in ('checkbox','radio'):
    if type(value) is not bool:raise ValueError('Нужен выбор да / нет.')
   elif not isinstance(value,str) or len(value)>16000:raise ValueError('Ответ должен быть текстом до 16000 символов.')
   if field.get('type')=='select' and value not in [o['value'] for o in field.get('options',[])]:raise ValueError('Выберите вариант формы.')
   row=db.execute('SELECT revision FROM application_field_drafts WHERE app_id=? AND form_fingerprint=? AND field_id=?',(app_id,fingerprint,field_id)).fetchone()
   if revision!=(row[0] if row else 0):raise ValueError('Ответ уже изменён. Откройте последнюю версию.')
   db.execute('INSERT OR REPLACE INTO application_field_drafts VALUES(?,?,?,?,?,?)',(app_id,fingerprint,field_id,packed(value),revision+1,time.time()))
   if field.get('type')=='radio' and value:
    for other in form['fields']:
     if other['id']!=field_id and other.get('type')=='radio' and other.get('group')==field.get('group'):
      db.execute('INSERT INTO application_field_drafts VALUES(?,?,?,?,1,?) ON CONFLICT(app_id,form_fingerprint,field_id) DO UPDATE SET value=excluded.value,revision=application_field_drafts.revision+1,updated=excluded.updated',(app_id,fingerprint,other['id'],packed(False),time.time()))
      db.execute('INSERT INTO application_field_versions(app_id,form_fingerprint,field_id,value,revision,actor,created) SELECT app_id,form_fingerprint,field_id,value,revision,?,updated FROM application_field_drafts WHERE app_id=? AND form_fingerprint=? AND field_id=?',(actor,app_id,fingerprint,other['id']))
   db.execute('INSERT INTO application_field_versions(app_id,form_fingerprint,field_id,value,revision,actor,created) VALUES(?,?,?,?,?,?,?)',(app_id,fingerprint,field_id,packed(value),revision+1,actor,time.time()))
   self._invalidate(db,app_id)
   db.execute("UPDATE application_workflow SET state='needs_approval',updated_at=? WHERE app_id=?",(utc(),app_id))
   self._event(db,app_id,'field_draft_saved',{'field_id':field_id,'revision':revision+1})
  return self.form_answers(app_id)

 def field_history(self,app_id):
  with self.connect() as db:
   rows=db.execute('SELECT v.*,f.payload form_payload FROM application_field_versions v JOIN application_form_versions f ON f.app_id=v.app_id AND f.fingerprint=v.form_fingerprint WHERE v.app_id=? ORDER BY v.id DESC LIMIT 300',(app_id,)).fetchall()
  result=[]
  for row in rows:
   r=dict(row);form=json.loads(r.pop('form_payload'));r['value']=json.loads(r['value']);r['question']=next((f['label'] for f in form['fields'] if f['id']==r['field_id']),'');result.append(r)
  return result

 def record_field_suggestion(self,app_id,field_id,result,fingerprint,revision):
  with self.connect() as db:
   wf=self._wf(db,app_id);self._blocked_edit(wf);form=json.loads(wf['form'] or 'null')
   if not form or form['fingerprint']!=fingerprint:raise ValueError('Анкета изменилась во время подготовки ответа.')
   field=next((f for f in form['fields'] if f['id']==field_id),None)
   row=db.execute('SELECT revision FROM application_field_drafts WHERE app_id=? AND form_fingerprint=? AND field_id=?',(app_id,fingerprint,field_id)).fetchone()
   if not field or revision!=(row[0] if row else 0):raise ValueError('Ответ изменился во время генерации. Сохранённую редакцию не заменяю.')
   self._event(db,app_id,'field_answer_proposed',{'field_id':field_id,'question':field['label'],'form_fingerprint':fingerprint,'base_revision':revision,'result':result})
 def field_suggestions(self,app_id):
  with self.connect() as db:rows=db.execute("SELECT id,payload,at FROM application_events WHERE app_id=? AND type='field_answer_proposed' ORDER BY id DESC LIMIT 100",(app_id,)).fetchall()
  return [{'id':r['id'],'at':r['at'],**json.loads(r['payload'])} for r in rows]
