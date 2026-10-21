"""Exact-content approval for transferring company-form drafts, never for submitting.

Company forms may autosave on input. Treat filling as a disclosure: explicit owner
approval, short expiry, one claim, current CV/JD, and a frozen browser snapshot.
Files, radio groups and consents stay on the employer site until a dedicated
adapter can verify them. This operation must never mark an application sent.
"""
import json,secrets,time
from .board_import import identity

FILL_TYPES={'text','email','tel','url','number','date','textarea','select'}

class CareerFieldsMixin:
 def career_fill_status(self,app_id,command_id):
  """Read a receipt without claiming, retrying or transferring any fields."""
  with self.connect() as db:
   cmd=db.execute("SELECT state,result FROM browser_commands WHERE id=? AND app_id=? AND kind='career_fill'",(command_id,app_id)).fetchone()
  if not cmd:raise ValueError('Задача переноса не найдена для этой анкеты.')
  result=json.loads(cmd['result']) if cmd['result'] else {}
  return {'command_id':command_id,'state':cmd['state'],'result_state':result.get('state'),'note':result.get('note','')}

 def career_fill_intent(self,app_id):
  with self.connect() as db:return self._career_fill_intent(db,app_id)

 def _career_fill_intent(self,db,app_id):
  from .application_workflow import hashed
  app=db.execute('SELECT * FROM applications WHERE id=?',(app_id,)).fetchone()
  if not app:raise ValueError('Отклик не найден.')
  ctx=json.loads(app['context']);wf=self._wf(db,app_id);self._blocked_edit(wf)
  form=json.loads(wf['form'] or 'null')
  if ctx['channel']!='career' or not form or form.get('state')!='questionnaire' or form.get('adapter_version') not in ('career-fields-v1','career-fields-v2'):raise ValueError('Откройте форму компании и передайте анкету из обновлённого расширения.')
  crm=db.execute('SELECT stage FROM application_crm WHERE app_id=?',(app_id,)).fetchone()
  if app['status']!='queued' or (crm and crm[0]!='preparing'):raise ValueError('Отклик уже перешёл к подбору. Сначала проверьте его статус.')
  target=identity(form.get('source_url',''))
  if not target or target['id']!=ctx['vacancy']['id'] or wf['revision']!=form.get('draft_revision'):raise ValueError('Форма или контекст изменились. Прочитайте анкету заново.')
  rows={r['field_id']:dict(r) for r in db.execute('SELECT * FROM application_field_drafts WHERE app_id=? AND form_fingerprint=?',(app_id,form['fingerprint']))}
  from .candidate_profile import defaults
  profile=defaults(db,form['fields'],ctx)
  values={f['id']:wf['draft'] if f.get('purpose')=='cover' else json.loads(rows[f['id']]['value']) if f['id'] in rows else profile.get(f['id'],{}).get('value',f.get('value','')) for f in form['fields']}
  answers={};manual=[]
  for f in form['fields']:
   if f.get('manual_only') or f.get('type') not in FILL_TYPES:manual.append(f['label']);continue
   value=values[f['id']]
   if not isinstance(value,str) or len(value)>16000:raise ValueError('Недопустимый текст поля.')
   if f['type']=='select' and value not in [o['value'] for o in f.get('options',[])]:raise ValueError('Выберите вариант из формы.')
   # Empty fields are left untouched, not erased. No inference of personal data.
   if value:answers[f['id']]=value
  if not answers:raise ValueError('Сначала сохраните письмо или ответы для переноса.')
  intent={'action':'career_fill','app_id':app_id,'resume_id':ctx['resume_id'],'resume_hash':ctx['resume_hash'],'vacancy_id':ctx['vacancy']['id'],'source_url':form['source_url'],'provider':form['provider'],'revision':wf['revision'],'draft':wf['draft'],'answers':answers,'profile_revisions':{k:v['revision'] for k,v in profile.items() if k not in rows},'field_revisions':{f['id']:rows.get(f['id'],{}).get('revision',0) for f in form['fields']},'form_fingerprint':form['fingerprint'],'form_snapshot':form,'manual_fields':manual,'limitations':form.get('limitations',[]),'submit_label':'Заполнить согласованные поля'}
  return {**intent,'intent_hash':hashed(intent)}

 def approve_career_fill(self,app_id,intent_hash,confirmed=False):
  from .application_workflow import packed,utc
  if confirmed is not True:raise ValueError('Подтвердите передачу показанных текстов на сайт компании.')
  self.validate_current(app_id,active=True)
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');intent=self._career_fill_intent(db,app_id)
   if intent['intent_hash']!=intent_hash:raise ValueError('Ответы или письмо изменились. Проверьте новую версию.')
   self._invalidate(db,app_id);approval=secrets.token_hex(12);command=secrets.token_hex(12)
   db.execute('INSERT INTO application_approvals VALUES(?,?,?,?,?,?,?)',(approval,app_id,intent_hash,packed(intent),'approved',time.time()+900,utc()))
   db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,?,?,?,?)',(command,app_id,'career_fill',packed({'approval_id':approval}),'queued',None,time.time(),time.time(),None))
   db.execute("UPDATE application_workflow SET state='fill_approved',updated_at=? WHERE app_id=?",(utc(),app_id))
   self._event(db,app_id,'career_fill_approved',{'command_id':command,'intent_hash':intent_hash})
  return {'approval_id':approval,'command_id':command}

 def claim_career_fill(self,command_id,worker,fingerprint):
  from .application_workflow import utc
  with self.connect() as db:cmd=db.execute('SELECT * FROM browser_commands WHERE id=?',(command_id,)).fetchone()
  if not cmd:raise ValueError('Задача не найдена.')
  self.validate_current(cmd['app_id'],active=True)
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');cmd=db.execute('SELECT * FROM browser_commands WHERE id=?',(command_id,)).fetchone()
   if cmd['kind']!='career_fill' or cmd['state']!='running' or cmd['worker_id']!=worker:raise ValueError('Задача принадлежит другому исполнителю.')
   approval=db.execute('SELECT * FROM application_approvals WHERE id=?',(json.loads(cmd['payload'])['approval_id'],)).fetchone()
   if not approval or approval['status']!='approved' or approval['expires']<time.time():raise ValueError('Разрешение использовано, отозвано или истекло.')
   intent=json.loads(approval['payload']);current=self._career_fill_intent(db,cmd['app_id'])
   if current['intent_hash']!=intent['intent_hash'] or fingerprint!=intent['form_fingerprint']:raise ValueError('Анкета изменилась. Нужно новое согласование.')
   db.execute("UPDATE application_approvals SET status='claimed' WHERE id=?",(approval['id'],));db.execute("UPDATE application_workflow SET state='filling',updated_at=? WHERE app_id=?",(utc(),cmd['app_id']))
   self._event(db,cmd['app_id'],'career_fill_claimed',{'command_id':command_id})
  return intent

 def finish_career_fill(self,command_id,worker,result):
  from .application_workflow import packed,utc
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');cmd=db.execute('SELECT * FROM browser_commands WHERE id=?',(command_id,)).fetchone()
   if not cmd or cmd['kind']!='career_fill' or cmd['worker_id']!=worker:raise ValueError('Задача принадлежит другому исполнителю.')
   if cmd['result']:
    if json.loads(cmd['result'])==result:return {'ok':True,'replayed':True}
    raise ValueError('У задачи уже есть результат.')
   if cmd['state'] not in ('running','uncertain'):raise ValueError('Задача уже завершена.')
   approval=db.execute('SELECT * FROM application_approvals WHERE id=?',(json.loads(cmd['payload'])['approval_id'],)).fetchone();intent=json.loads(approval['payload'])
   if result.get('state')=='fields_filled':
    target=identity(result.get('source_url',''))
    from .candidate_profile import same_value
    actual=result.get('values');fields={f['id']:f for f in intent['form_snapshot']['fields']}
    values_match=isinstance(actual,dict) and set(actual)==set(intent['answers']) and all(same_value(fields[k],v,actual[k]) for k,v in intent['answers'].items())
    if approval['status']!='claimed' or not target or target['id']!=intent['vacancy_id'] or result.get('source_url')!=intent['source_url'] or not values_match:raise ValueError('Нет подтверждения точного переноса ответов.')
    state='fields_filled';event='career_fields_filled'
   elif result.get('state')=='failed':state='needs_input';event='career_fill_failed'
   else:raise ValueError('Перенос полей не может подтвердить отправку отклика.')
   db.execute('UPDATE browser_commands SET state=?,result=?,updated=? WHERE id=?',('complete' if state=='fields_filled' else 'failed',packed(result),time.time(),command_id))
   # A late receipt must not erase a newer form captured after crash recovery.
   wf=self._wf(db,cmd['app_id']);current_form=json.loads(wf['form'] or 'null')
   if wf['state']=='filling' or not current_form or current_form['fingerprint']==intent['form_fingerprint']:
    db.execute('UPDATE application_workflow SET state=?,form=NULL,updated_at=? WHERE app_id=?',(state,utc(),cmd['app_id']))
   self._event(db,cmd['app_id'],event,result)
  return {'ok':True}
