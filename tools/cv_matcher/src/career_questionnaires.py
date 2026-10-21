"""Company form snapshots use the same question history; sending remains adapter-gated."""
import json,time,re
from urllib.parse import urlsplit
from .board_import import identity

HOSTS={'yandex':{'yandex.ru','yandex.com'},'sber':{'rabota.sber.ru'},'avito':{'career.avito.com'},'ozon':{'ozon.tech','career.ozon.ru'},'tbank':{'tbank.ru','www.tbank.ru'}}
def capture(store,app_id,snapshot):
 from .application_workflow import packed,utc
 app=store.get(app_id);ctx=app['context'];target=identity(snapshot.get('source_url',''));provider=snapshot.get('provider')
 if ctx['channel']!='career' or provider not in HOSTS or urlsplit(snapshot.get('source_url','')).netloc not in HOSTS[provider] or not target or target['id']!=ctx['vacancy']['id']:raise ValueError('Анкета относится к другой вакансии или источнику.')
 if snapshot.get('state')!='questionnaire' or snapshot.get('execution_supported') is not False:raise ValueError('Этот адаптер пока только читает анкету.')
 fields=snapshot.get('fields')
 if not isinstance(fields,list) or not fields or len(fields)>80 or len(packed(snapshot))>200000:raise ValueError('Некорректная анкета.')
 ids=set()
 for f in fields:
  if not isinstance(f,dict) or not isinstance(f.get('id'),str) or f['id'] in ids or not isinstance(f.get('label'),str) or not 0<len(f['label'])<=2000 or f.get('type') not in ('text','email','tel','url','number','date','textarea','select','radio','checkbox','file'):raise ValueError('Тип или вопрос поля не поддерживается.')
  ids.add(f['id'])
  if f.get('control') and not (f['control']=='tbank_city' and provider=='tbank' and snapshot.get('adapter_version')=='career-fields-v2' and f['type']=='text' and re.fullmatch(r'Город[ *:]*',f['label'],re.I)):raise ValueError('Неподдерживаемый контрол анкеты.')
 # Chrome's scripting result may reorder dictionary keys; the serialized
 # fingerprint was produced inside the page before that transport. Compare its
 # complete JSON value, never an order-dependent reserialization of dictionaries.
 try:version=json.loads(snapshot.get('fingerprint',''))
 except (ValueError,TypeError):raise ValueError('Версия анкеты не совпала.') from None
 if version!=[provider,target['id'],fields]:raise ValueError('Версия анкеты не совпала.')
 with store.connect() as db:
  db.execute('BEGIN IMMEDIATE');wf=store._wf(db,app_id);store._blocked_edit(wf);store._invalidate(db,app_id)
  form={**snapshot,'draft_revision':wf['revision'],'selected_resume_id':ctx['resume_id']}
  fresh=db.execute('INSERT OR IGNORE INTO application_form_versions VALUES(?,?,?,?)',(app_id,form['fingerprint'],packed(form),time.time())).rowcount
  db.execute("UPDATE application_workflow SET form=?,state='needs_input',updated_at=? WHERE app_id=?",(packed(form),utc(),app_id))
  if fresh:store._event(db,app_id,'questionnaire_received',{'provider':provider,'questions':len(fields),'source_url':snapshot['source_url']})
 return store.workflow(app_id)
