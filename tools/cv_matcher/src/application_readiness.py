"""Read-only preparation checks; actionable refresh uses the existing Chrome queue."""
import json
from datetime import datetime,timezone,timedelta
from .archive_store import source_url_is_detail

def read(store,app_id):
 app=store.get(app_id);ctx=app['context'];issues=[]
 try:store.validate_current(app_id)
 except ValueError as error:issues.append({'code':'context','message':str(error)})
 with store.connect() as db:row=db.execute("SELECT payload,availability FROM entities WHERE kind='vacancy' AND id=?",(ctx['vacancy']['id'],)).fetchone()
 jd=json.loads(row['payload']) if row else {};checked=None
 try:checked=datetime.fromisoformat(str(jd.get('availability_checked_at') or (jd.get('collected_at','') if source_url_is_detail(jd.get('source_page',''),ctx['vacancy']['id']) else '')).replace('Z','+00:00'))
 except ValueError:pass
 active=bool(row and row['availability']=='active' and checked and checked.tzinfo and -timedelta(minutes=5)<=datetime.now(timezone.utc)-checked<=timedelta(minutes=30))
 if not active:issues.append({'code':'activity','message':'Активность вакансии не проверялась в последние 30 минут. Письмо можно готовить по сохранённому тексту; перед переносом и отправкой обновите страницу вакансии через Chrome.'})
 return {'can_prepare':not any(i['code']=='context' for i in issues),'activity_fresh':active,'issues':issues,'checked_at':checked.isoformat() if checked else None,'api_requests':0,'browser':store.browser_status()['workers']['career']}

def open_career(store,app_id):
 from .board_import import identity
 from .career_questionnaires import HOSTS
 from urllib.parse import urlsplit
 app=store.validate_current(app_id);ctx=app['context']
 if ctx['channel']!='career':raise ValueError('Открытие формы компании доступно для карьерных сайтов.')
 with store.connect() as db:
  wf=store._wf(db,app_id);store._blocked_edit(wf);form=json.loads(wf['form'] or 'null')
 url=(form or {}).get('source_url') or ctx['vacancy']['link'];target=identity(url);u=urlsplit(url)
 if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.hostname not in set().union(*HOSTS.values()) or not target or target['id']!=ctx['vacancy']['id']:raise ValueError('Не найдена проверенная ссылка на эту вакансию компании.')
 return {'command_id':store.queue_command('career_open',app_id,{'url':url}),'browser':store.browser_status()['workers']['career'],'api_requests':0,'note':'Открытие и чтение анкеты в очереди Chrome. Ответы и письмо не передаются сайту до отдельного разрешения.'}
