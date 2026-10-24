"""Shared career application layer. Durable policy and scheduling; no Telegram transport."""
import asyncio,json,os,time,re
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from .archive_store import ArchiveStore
from .application_workflow import packed,utc,hashed,CRM_STAGES,WORK_STATUSES
from .workflow_messages import TITLES,CHROME_HELP,browser_note

class CareerApplication:
 def __init__(self,store):
  self.store=store;self.archive=ArchiveStore(store.path)
  self.zone=ZoneInfo(os.getenv('TELEGRAM_DIGEST_TIMEZONE','Europe/Moscow'))
  self.times=os.getenv('TELEGRAM_DIGEST_TIMES','10:00,19:00').split(',')
  self.profile=json.loads((Path(__file__).resolve().parents[1]/'hh-research-extension/search-profile.json').read_text())
  for value in self.times:datetime.strptime(value.strip(),'%H:%M')
 def skills_catalog(self):
  from .career_skills import catalog
  return catalog(self.store)
 def skills_plan(self,data=None):
  from .career_skills import plan
  return plan(self.store,self.archive,data)
 def skills_vacancy(self,data):
  from .career_skills import vacancy_plan
  return vacancy_plan(self.store,self.archive,data)
 def skills_evidence(self,data):
  from .career_skills import save_evidence
  return save_evidence(self.store,self.archive,data)
 def skills_track(self,data):
  from .career_skills_store import save_track
  return save_track(self.store,data)
 def skills_history(self,resume_id):
  from .career_skills_store import history
  return {'items':history(self.store,resume_id)}
 async def notify(self,key,text,keyboard=None):
  self.enqueue(key,text,keyboard)
 def enqueue(self,key,text,keyboard=None,*,db=None):
  # Each Telegram message is its own durable attempt, including multi-part notices.
  parts=[];part='';units=0
  for char in text:
   size=len(char.encode('utf-16-le'))//2
   if units+size>3500:parts.append(part);part='';units=0
   part+=char;units+=size
  parts.append(part or ' ')
  for i,part in enumerate(parts):self.store.enqueue_delivery(key if i==0 else key+':part:'+str(i),part,keyboard if i==len(parts)-1 else None,db=db)

 def candidates(self,*,fresh=False,now=None,exclude_day=False,scope=None,ranking_goal=None):
  now=now or datetime.now(timezone.utc);summary=self.archive.summary();cv_id=summary.get('primary_id');goal=summary.get('goal','')
  scope=scope or {};goal=goal if ranking_goal is None else ranking_goal
  if not cv_id:return []
  try:cv=self.archive.detail('resume',cv_id)['payload']
  except ValueError:return []
  from .resume_source import _load_resume_bundle
  try:_load_resume_bundle({'schema_version':2,'primary_id':cv_id,'resumes':[cv]},now=now)
  except ValueError:
   from .resume_source import content_hash
   if fresh or cv.get('source_type','hh')!='hh' or cv.get('quality')!='full' or content_hash(cv)!=cv.get('content_hash'):return []
  with self.store.connect() as db:
   jobs=[json.loads(r[0]) for r in db.execute("SELECT payload FROM entities WHERE kind='vacancy' AND availability<>'closed'")]
   from .manual_applications import all_marks
   applied={jid for jid,mark in all_marks(db).items() if mark['marked']}
   applied.update(r[0] for r in db.execute("SELECT vacancy_id FROM hh_observations WHERE status<>'unknown'"))
   applied.update(json.loads(r[0])['vacancy']['id'] for r in db.execute("SELECT context FROM applications WHERE status IN ('submitted','viewed','invited','rejected','withdrawn','completed')"))
   applied.update(json.loads(r[0])['vacancy']['id'] for r in db.execute("SELECT a.context FROM applications a JOIN application_crm c ON c.app_id=a.id WHERE c.stage<>'preparing'"))
   # A started preparation is already in the action queue, not a new recommendation.
   applied.update(json.loads(r[0])['vacancy']['id'] for r in db.execute("SELECT context FROM applications WHERE status<>'superseded'"))
   day=now.astimezone(self.zone).date().isoformat()
   sent={r[0] for r in db.execute("SELECT key FROM workflow_delivery WHERE key LIKE ? AND state<>'cancelled'",('job:'+day+':%',))} if exclude_day else set()
   if exclude_day:
    start=now.astimezone(self.zone).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat()
    sent.update('job:'+day+':'+r[0].rsplit(':',1)[-1] for r in db.execute("SELECT key FROM workflow_delivery WHERE key LIKE 'job:%' AND created_at>=? AND state<>'cancelled'",(start,)))
  jobs=[j for j in jobs if j.get('description_quality')=='full' and not j.get('archived') and j['id'] not in applied and 'job:'+now.astimezone(self.zone).date().isoformat()+':'+j['id'] not in sent]
  # The same current-version, exact-goal, small-model ranking as the web list.
  rows=self.archive.entities('vacancy',status='full',resume_id=cv_id,goal=goal,model='text-embedding-3-small',ranked_only=True,exclude_closed=True,all_items=True,include_payload=True)['items']
  eligible={j['id'] for j in jobs}
  jobs=[row['payload'] for row in rows if row['id'] in eligible]
  ranked={row['id']:row['ranking'] for row in rows}
  results=[]
  from .career_search_scope import accepts
  for j in jobs:
   if accepts(j,scope,self.archive,now=now):continue
   if j['id'] not in ranked:continue
   try:
    from .archive_store import source_url_is_detail
    verified=j.get('listing_verified_at') or j.get('availability_checked_at') or (j.get('collected_at','') if source_url_is_detail(j.get('source_page',''),j['id']) else '')
    checked=datetime.fromisoformat(str(verified).replace('Z','+00:00'))
    fetched=datetime.fromisoformat(str(j.get('description_fetched_at') or j.get('collected_at','')).replace('Z','+00:00'))
    valid=checked.tzinfo and fetched.tzinfo and -timedelta(minutes=5)<=now-checked<=timedelta(minutes=30) and -timedelta(minutes=5)<=now-fetched<timedelta(hours=24) and not j.get('description_dirty') and j.get('archived') is False
   except ValueError:valid=False
   if fresh and not valid:continue
   feedback=json.loads(self.store.setting('career-feedback:'+hashed([cv_id,j['id']])) or '{}')
   if feedback.get('choice')=='uninteresting' and feedback.get('resume_hash')==cv['content_hash']:continue
   results.append({'job':j,'resume':cv,'goal':goal,'score':ranked[j['id']]['score'],'ranking':ranked[j['id']]})
  return results

 async def begin_digest(self,key,scope=None):
  import secrets
  holder=secrets.token_hex(12)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute("SELECT expires FROM career_leases WHERE name='start_search'").fetchone()
   if old and old[0]>time.time():raise ValueError('Поиск уже запускается. Обновите список задач.')
   db.execute("INSERT OR REPLACE INTO career_leases VALUES('start_search',?,?)",(holder,time.time()+30))
  try:return await self._begin_digest(key,scope)
  finally:
   with self.store.connect() as db:db.execute("DELETE FROM career_leases WHERE name='start_search' AND holder=?",(holder,))
 async def _begin_digest(self,key,scope=None):
  with self.store.connect() as db:
   if db.execute('SELECT 1 FROM workflow_delivery WHERE key=?',(key,)).fetchone():return
  if self.store.setting('pending_digest'):return
  with self.store.connect() as db:orphan=db.execute("SELECT id,digest_key FROM discovery_runs WHERE state IN ('collecting','waiting_chrome','ranking','ranking_ready','paused','pause_requested','cancel_requested') ORDER BY updated DESC LIMIT 1").fetchone()
  if orphan:
   self.store.setting('pending_digest',packed({'key':orphan['digest_key'],'discovery_id':orphan['id'],'started':time.time()}));return
  from .discovery import start
  try:run=start(self.store,self.archive,key,scope)
  except ValueError as e:await self.notify(key,str(e));return
  self.store.setting('pending_digest',packed({'key':key,'discovery_id':run['id'],'started':time.time()}))
  from .agent_progress import text as progress_text
  await self.notify(key+':progress',progress_text(self.task('search:'+run['id']))+'\nAPI: '+('включён в сохранённых настройках поиска.' if run['payload']['config']['allow_api'] else 'выключен.'))


 async def finish_digest(self):
  raw=self.store.setting('pending_digest')
  if not raw:return
  p=json.loads(raw);notes=[]
  scheduled=p['key'].startswith('digest:')
  from .career_notifications import config as notification_config
  if scheduled and notification_config(self.store)['mode'] not in ('both','discovery'):
   # Keep the collected data and task history, but stop scheduled delivery.
   self.store.setting('pending_digest','');return
  if p.get('discovery_id'):
   from .discovery import advance
   run=await asyncio.to_thread(advance,self.store,self.archive,p['discovery_id'],Path(__file__).resolve().parents[1])
   if run['state'] in ('collecting','waiting_chrome','ranking','ranking_ready','paused','pause_requested','cancel_requested'):return
   if run['state']=='cancelled':
    self.store.setting('pending_digest','');return
   p['ids']=run['result'].get('ids',[]);cmd=None
   if run['result'].get('missing_embeddings'):notes.append('🧩 Нет готовых embeddings: '+str(run['result']['missing_embeddings'])+'. API выключен: можно открыть карточки и подготовить письмо без API.')
   if run['result'].get('excluded',{}).get('unknown_publication_date'):notes.append('📅 Без даты публикации: '+str(run['result']['excluded']['unknown_publication_date'])+'. Они не включены в строгий отбор за период. Дата сбора не заменяет дату публикации.')
   if run['result'].get('note'):notes.append(run['result']['note'])
   if run['result'].get('warnings'):notes.append('⚠️ Источники прочитаны частично:\n'+'\n'.join(dict.fromkeys(browser_note(n) for n in run['result']['warnings']))[:1800])
  else:
   # Preserve a refresh queued by a previous version across an upgrade.
   with self.store.connect() as db:cmd=db.execute('SELECT state FROM browser_commands WHERE id=?',(p['command'],)).fetchone()
   if cmd and cmd[0] in ('queued','running') and time.time()-p['started']<600:return
  day=datetime.now(self.zone).date().isoformat()
  scope=run['payload'].get('scope',{}) if p.get('discovery_id') else {}
  ranking_goal=run['payload'].get('ranking_goal',run['payload']['goal']) if p.get('discovery_id') else None
  now=datetime.now(timezone.utc)
  candidates=self.candidates(fresh=scheduled,now=now,exclude_day=scheduled,scope=scope,ranking_goal=ranking_goal)
  if scheduled:
   # A failed refresh must never masquerade as a fresh global cached ranking.
   candidates=[c for c in candidates if c['job']['id'] in p.get('ids',[])] if p.get('discovery_id') and run['state']=='complete' else []
  candidates=candidates[:min(scope.get('limit',10),10)]
  messages=[];refs=[]
  collected_refs=[]
  if not candidates and p.get('discovery_id') and not scheduled:
   for jid in p['ids'][:200]:
    try:
     j=self.archive.detail('vacancy',jid)['payload'];cv=self.archive.detail('resume',run['payload']['resume_id'])['payload']
     if j.get('description_quality')!='full' or j.get('archived'):continue
     with self.store.connect() as db:
      if db.execute("SELECT 1 FROM applications WHERE json_extract(context,'$.vacancy.id')=? AND status<>'superseded'",(jid,)).fetchone():continue
     from .career_search_scope import accepts
     if accepts(j,{**scope,'since_days':None},self.archive):continue
     ref=hashed([p['key'],jid,cv['content_hash']])[:20]
     self.store.setting('recommendation:'+ref,packed({'resume_id':cv['id'],'resume_hash':cv['content_hash'],'vacancy_id':jid,'vacancy_hash':hashed(j['description']),'goal':ranking_goal,'unranked':True}));collected_refs.append(ref)
     if len(collected_refs)>=10:break
    except ValueError:continue
  if not candidates:
   if cmd and cmd[0]=='queued':
    with self.store.connect() as db:db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE id=? AND state='queued'",(time.time(),p['command']))
    message='Chrome не начал проверку за 10 минут. Активность вакансий остаётся неизвестной; это не означает, что они закрыты.\n\n'+CHROME_HELP+'\nПосле подключения отправьте /today.'
   else:message='🧭 Поиск завершён без подтверждённой подборки.\n'+('Прочитанные описания доступны ниже как карточки без подтверждённого рейтинга. Выберите одну для разбора и письма или повторите отбор с другими условиями.' if collected_refs else 'Проверьте доступность источников и условия поиска. Ниже можно запустить новый поиск или проверить Chrome.')
  else:
   message=('🎯 Проверенные вакансии · ' if scheduled else '🎯 Топ-10 без откликов · ')+datetime.now(self.zone).strftime('%d.%m %H:%M')+'\nCV: '+candidates[0]['resume']['title']+'\nПолный сохранённый рейтинг · 3-small · исключены существующие отклики и «Не моё». Явные условия поиска сохранены. Проверим активность перед подготовкой.\nСемантическая близость — не процент покрытия навыков.\n\nСледующий шаг: выберите «Подготовить отклик» у вакансии. Разбор Luna и письмо доступны с API или без API; затем проверим форму в Chrome. Можно написать: «Подготовь отклики на первые две».'
   for c in candidates:
    j=c['job'];key='job:'+(day if scheduled else hashed(p['key'])[:20])+':'+j['id']
    from .career_recommendations import explain
    explanation=explain(self,c);ref=hashed([p['key'],j['id'],c['resume']['content_hash']])[:20];refs.append(ref)
    self.store.setting('recommendation:'+ref,packed({'resume_id':c['resume']['id'],'resume_hash':c['resume']['content_hash'],'vacancy_id':j['id'],'vacancy_hash':hashed(j['description']),'goal':c['goal'],'explanation':explanation}))
    fit=explanation['qualification_fit']['semantic_similarity'];align=explanation['career_alignment']['semantic_similarity']
    metrics='Близость к CV: '+str(round(fit,3))+((' · к цели: '+str(round(align,3))) if align is not None else '')
    messages.append((key,'💼 '+j['title']+' · '+j.get('company','')+'\n'+metrics+'\n'+('Luna: есть сохранённый разбор.' if explanation['analysis_key'] else 'Luna: разбор можно выполнить перед подготовкой.')+'\n'+j['link'],[[('Подробный разбор',f'w:rreview:{ref}'),('Подготовить отклик',f'w:pick:{ref}')],[('Почему подходит',f'w:why:{ref}')],[('👍 Интересно',f'w:feedback:{ref}@interesting'),('👎 Не моё',f'w:feedback:{ref}@uninteresting'),('⭐ Приоритет',f'w:feedback:{ref}@priority')]]))
  if notes:message+='\n\n'+'\n\n'.join(notes)
  controls=[[('Открыть вакансии','w:menu:results')],[('Новый поиск','w:menu:today'),('Состояние Chrome','w:menu:status')]]
  if scope.get('since_days') and p.get('discovery_id'):controls.insert(0,[('Повторить без ограничения даты',f'w:nodate:{p["discovery_id"]}')])
  # Header, all recommendations and completion of planning commit together.
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');self.enqueue(p['key'],message,controls,db=db)
   for key,text,keyboard in messages:
    self.enqueue(key,text,keyboard,db=db)
    if scheduled:self.store.setting_in(db,'notification:'+key,packed({'kind':'recommendation','vacancy_id':key.rsplit(':',1)[-1],'expires':now.timestamp()+30*60}))
   self.store.setting_in(db,'pending_digest','')
   self.store.setting_in(db,'last-selection',packed({'refs':refs or collected_refs,'created':time.time(),'ranked':bool(refs)}))
   if collected_refs:self.store.setting_in(db,'last-collected',packed({'refs':collected_refs,'created':time.time()}))
   if refs:self.store.setting_in(db,'last-recommendations',packed({'refs':refs,'created':time.time()}))

 async def tick(self,now=None):
  now=now or datetime.now(self.zone)
  from .hybrid_collection import tick as hybrid_tick
  from .collection_backfill import tick as backfill_tick
  await asyncio.to_thread(backfill_tick,self.store,self.archive)
  await asyncio.to_thread(hybrid_tick,self.store,self.archive)
  await asyncio.to_thread(backfill_tick,self.store,self.archive)
  await self.finish_digest()
  await self.advance_preparations()
  from .luna_batch import advance as advance_luna_batch
  await advance_luna_batch(self)
  await self.plan_reminders(now)
  # Catch up only the latest slot within four hours, never replay an entire day.
  slots=[]
  for stamp in self.times:
   hour,minute=map(int,stamp.strip().split(':'));slot=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
   if 0<=(now-slot).total_seconds()<4*3600:slots.append(slot)
  from .career_notifications import config as notification_config,plan_reviews
  notification_mode=notification_config(self.store)['mode']
  if slots:
   slot=max(slots)
   if notification_mode in ('tasks','both'):plan_reviews(self,slot,now)
   if notification_mode in ('both','discovery') and not self.store.setting('pending_digest'):await self.begin_digest('digest:'+slot.isoformat())
  await self.enqueue_event_notifications()
  await self.enqueue_task_notifications()
  with self.store.connect() as db:commands=[dict(r) for r in db.execute("SELECT * FROM browser_commands WHERE kind='sync' AND state IN ('complete','failed','needs_input') ORDER BY created DESC LIMIT 10")]
  for c in commands:
   key='sync-result:'+c['id']
   r=json.loads(c['result'] or '{}')
   if json.loads(c['payload']).get('automatic') is True:
    # Successful background polls stay quiet; changes have their own durable events.
    if c['state']=='complete':continue
    with self.store.connect() as db:previous=db.execute("SELECT id FROM browser_commands WHERE kind='sync' AND state='complete' AND updated<=? ORDER BY updated DESC LIMIT 1",(c['created'],)).fetchone()
    key='hh-auto-sync-error:'+hashed([previous[0] if previous else 'initial',r.get('note','')])
    await self.notify(key,'Не удалось автоматически обновить HH.\n'+browser_note(r.get('note','Проверьте подключение HH.'))+'\nПовторная проверка будет с увеличенным интервалом. /status — состояние связи.')
    continue
   await self.notify(key,'Синхронизация HH: '+('прочитано наблюдений '+str(r.get('observations_added',0))+', новых сообщений '+str(r.get('messages_added',0)) if c['state']=='complete' else r.get('note','Нужно проверить вкладку HH.'))+ ('\n'+'; '.join(r['warnings']) if r.get('warnings') else ''))

 async def enqueue_event_notifications(self):
  # Missing outbox rows, not a moving tail window. Crash rolls back the whole page.
  kinds=('hh_status','hh_message','browser_result','form_prepared','crm_stage','giga_invite','questionnaire_received','career_fields_filled','career_fill_failed','integration_conflict')
  for _ in range(10):
   with self.store.connect() as db:
    db.execute('BEGIN IMMEDIATE')
    events=[dict(r) for r in db.execute("SELECT e.* FROM application_events e LEFT JOIN workflow_delivery d ON d.key='event:'||e.id WHERE e.type IN ("+','.join('?' for _ in kinds)+") AND (d.key IS NULL OR d.payload IS NULL) ORDER BY e.id LIMIT 100",kinds)]
    for e in events:
     app=self.store.get(e['app_id']);p=json.loads(e['payload'])
     if e['type']=='questionnaire_received':note='Анкета работодателя сохранена. Вопросов: '+str(p.get('questions',0))+'. Откройте отклик, чтобы подготовить ответы с API или без API.'
     elif e['type']=='hh_message':note=('Новое сообщение HH' if p.get('direction')=='incoming' else 'Новое сообщение в переписке HH (автор не распознан)')+'\n'+p.get('text','')
     elif e['type'] in ('career_fields_filled','career_fill_failed','integration_conflict'):note=p.get('note','Проверьте анкету компании.')
     elif e['type']=='giga_invite':note='В чате HH найдено приглашение ГигаРекрутера. Откройте карточку, чтобы связать и продолжить интервью.'
     elif e['type']=='crm_stage':note='Этап CRM: '+CRM_STAGES[p['stage']]+('\n'+p.get('note','') if p.get('note') else '')
     elif e['type']=='form_prepared':note='Форма готова к проверке. Все вопросы анкеты доступны в карточке.'
     else:note=TITLES.get(p.get('status'),p.get('note')) or TITLES.get(p.get('state'),'Задача Chrome завершена')
     self.enqueue('event:'+str(e['id']),app['context']['vacancy']['title']+'\n'+browser_note(note),[[('Открыть отклик',f'w:open:{app["id"]}')]],db=db)
   if len(events)<100:break

 async def plan_reminders(self,now):
  with self.store.connect() as db:
   due=[dict(r) for r in db.execute("SELECT c.*,json_extract(a.context,'$.vacancy.title') title FROM application_crm c JOIN applications a ON a.id=c.app_id WHERE c.follow_up_at IS NOT NULL AND c.work_status<>'done' AND c.stage NOT IN ('offer','rejected') AND a.status NOT IN ('superseded','completed','rejected','withdrawn')")]
   meetings=[dict(r) for r in db.execute("SELECT m.*,json_extract(a.context,'$.vacancy.company') company FROM application_appointments m JOIN applications a ON a.id=m.app_id WHERE m.status='scheduled' AND a.status<>'superseded'")]
  for plan in due:
   if self.store.case_id(plan['app_id'])!=plan['app_id']:continue
   if datetime.fromisoformat(plan['follow_up_at'])>now:continue
   key='followup:'+plan['app_id']+':'+plan['follow_up_at']
   await self.notify(key,'Пора проверить следующий шаг\n'+plan['title']+'\n'+WORK_STATUSES[plan['work_status']]+' · '+plan['next_action'],[[('Открыть план',f'w:open:{plan["app_id"]}')]])
  for meeting in meetings:
   start=datetime.fromisoformat(meeting['start_at']);delta=(start-now).total_seconds()
   if not 0<=delta<=3600:continue
   key='interview:'+meeting['id']+':'+meeting['start_at']
   await self.notify(key,'Скоро интервью · '+meeting['company']+'\n'+meeting['title']+'\n'+start.astimezone(ZoneInfo(meeting['time_zone'])).strftime('%d.%m %H:%M')+' · '+meeting['time_zone']+'\n'+meeting['location']+'\n'+meeting['notes'],[[('Открыть план',f'w:open:{meeting["app_id"]}')]])

 def task(self,identifier):
  from .agent_tasks import get
  return get(self.store,identifier)
 def tasks(self):
  from .agent_tasks import listing
  return listing(self.store)
 def control_task(self,identifier,action,revision,actor='local_owner'):
  from .agent_tasks import control
  return control(self.store,identifier,action,revision,actor=actor)
 def state(self):
  from .journey import overview
  return {**overview(self.store),'tasks':self.tasks(),'capabilities':{'conversation':'bounded_intents','durable_tasks':True,'task_controls':'per_task_actions','mcp_approval':False,'agent_api':'saved_search_policy_only'},'review_url':'http://127.0.0.1:8788/?view=applications'}
 async def search(self,request_id,scope=None):
  if not isinstance(request_id,str) or not 1<=len(request_id)<=100:raise ValueError('Нужен request_id длиной до 100 символов.')
  if not self.archive.summary().get('primary_id'):raise ValueError('Сначала выберите резюме.')
  from .career_search_scope import validate
  scope=validate(scope,self.archive)
  pending=json.loads(self.store.setting('pending_digest') or '{}')
  if pending.get('discovery_id'):
   from .discovery import read
   current=validate(read(self.store,pending['discovery_id'])['payload'].get('scope'),self.archive)
   if current!=scope:raise ValueError('Уже идёт поиск с другими условиями. Откройте /tasks, дождитесь результата или отмените его перед новым поиском.')
  await self.begin_digest('agent:'+request_id,scope)
  raw=self.store.setting('pending_digest')
  if raw:return self.task('search:'+json.loads(raw)['discovery_id'])
  with self.store.connect() as db:old=db.execute('SELECT id FROM discovery_runs WHERE digest_key=?',('agent:'+request_id,)).fetchone()
  if old:return self.task('search:'+old[0])
  raise ValueError('Не удалось начать поиск. Проверьте выбранное CV и настройки источников.')
 def recommendation_context(self,ref):
  data=json.loads(self.store.setting('recommendation:'+ref) or '{}')
  if not data:raise ValueError('Рекомендация не найдена. Откройте последнюю подборку.')
  cv=self.archive.detail('resume',data['resume_id'])['payload'];job=self.archive.detail('vacancy',data['vacancy_id'])['payload']
  if data.get('resume_hash') and cv['content_hash']!=data['resume_hash'] or data.get('vacancy_hash') and hashed(job['description'])!=data['vacancy_hash']:raise ValueError('CV или вакансия изменились. Откройте обновлённую подборку перед подготовкой.')
  return {**data,'resume':cv,'vacancy':job}
 def select_recommendation(self,ref):
  data=self.recommendation_context(ref)
  return self.make_application(data['resume_id'],data['vacancy_id'],data['goal'])
 def make_application(self,resume_id,vacancy_id,goal=''):
  from .manual_applications import all_marks
  with self.store.connect() as db:manual=all_marks(db).get(vacancy_id,{})
  if manual.get('marked'):raise ValueError('Отклик уже отмечен вами как сделанный. Если это ошибка, снимите отметку на карточке вакансии.')
  cv=self.archive.detail('resume',resume_id)['payload'];job=self.archive.detail('vacancy',vacancy_id)['payload']
  result=self.store.create({'resume_id':cv['id'],'bundle':{'schema_version':2,'primary_id':cv['id'],'resumes':[cv]},'vacancy':job,'goal':goal,'channel':'hh' if job['id'].startswith('hh_') else 'career'})
  return self.store.workflow(result['id'])
 def prepare_application(self,resume_id,vacancy_id,goal='',draft=None,revision=None,open_form=False):
  item=self.make_application(resume_id,vacancy_id,goal);identifier=item['id']
  if draft is not None:
   if type(revision) is not int:raise ValueError('Для сохранения письма нужна его текущая версия.')
   self.store.save_letter(identifier,draft,revision)
  if open_form:self.prepare_form(identifier)
  return self.store.workflow(identifier)
 def prepare_form(self,app_id):
  self.store.validate_current(app_id);a=self.store.workflow(app_id);wf=a['workflow'];self.store._blocked_edit(wf)
  if a['context']['channel']!='hh':raise ValueError('Откройте анкету компании в Chrome и передайте её через панель расширения.')
  if not wf['draft']:raise ValueError('Сначала сохраните сопроводительный текст.')
  if self.store.setting('needs_clarification:'+app_id)=='yes':raise ValueError('Сначала уточните факты и проверьте письмо. Модель запросила дополнительные сведения.')
  with self.store.connect() as db:old=db.execute("SELECT id FROM browser_commands WHERE app_id=? AND kind='prepare' AND state IN ('queued','running','paused')",(app_id,)).fetchone()
  return {'command_id':old[0] if old else self.store.queue_command('prepare',app_id)}
 def queue_preparation(self,app_id,request_id,mode='offline',expected_revision=None):
  from .application_preparation import enqueue
  return enqueue(self,app_id,request_id,mode,expected_revision)
 async def advance_preparations(self):
  from .application_preparation import advance
  await asyncio.to_thread(advance,self)
  with self.store.connect() as db:rows=[dict(r) for r in db.execute("SELECT * FROM application_preparations WHERE state NOT IN ('queued','analyzing','drafting') AND NOT EXISTS (SELECT 1 FROM workflow_delivery d WHERE d.key='preparation:'||application_preparations.id) ORDER BY updated LIMIT 100")]
  for row in rows:
   result=json.loads(row['result'] or '{}');app=self.store.get(row['app_id'])
   await self.notify('preparation:'+row['id'],'✍️ Подготовка отклика · '+app['context']['vacancy']['title']+'\n'+result.get('note','Откройте карточку, чтобы продолжить.')+'\n\nСледующий шаг: '+('дождаться Chrome; заполненная форма придёт на проверку.' if row['state']=='waiting_chrome' else 'открыть карточку отклика.'),[[('Продолжить отклик',f'w:open:{row["app_id"]}')]])
 def review_action(self,app_id):
  item=self.store.workflow(app_id)
  return {'application':item,'requires_human_approval':True,'review_url':'http://127.0.0.1:8788/?application='+app_id,'note':'Проверьте точные тексты и подтвердите действие в Telegram или веб-сервисе. MCP не выдаёт разрешения.'}
 def analyze(self,resume_id,vacancy_id,goal='',mode='cached'):
  if mode=='offline':
   from .external_analysis import export_review
   return export_review(self.archive,resume_id,vacancy_id,goal)
  if mode!='cached':raise ValueError('Через agent доступны cached/offline. Платный разбор запускается владельцем из существующего интерфейса.')
  from .skill_analysis import context,cached
  return {'analysis':cached(self.archive,context(self.archive,resume_id,vacancy_id,goal)),'api_called':False}
 def analyze_owned(self,app_id):
  """Explicit owner action. Cached success or ambiguous attempt never recharges."""
  from .skill_analysis import analyze,context,cached
  self.store.validate_current(app_id);app=self.store.get(app_id);c=app['context']
  return self.analyze_context(c['resume_id'],c['vacancy']['id'],c.get('goal',''))
 def analyze_context(self,resume_id,vacancy_id,goal=''):
  from .skill_analysis import analyze,context,cached
  ctx=context(self.archive,resume_id,vacancy_id,goal)
  saved=cached(self.archive,ctx)
  if saved:return saved
  key='owned-analysis:'+ctx['key']
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT 1 FROM settings WHERE key=?',(key,)).fetchone():raise ValueError('Этот разбор уже запущен или не завершился. Проверьте сохранённый результат; платный запрос автоматически не повторяется.')
   self.store.setting_in(db,key,packed({'state':'started','at':time.time()}))
  try:
   result=analyze(self.archive,resume_id,vacancy_id,goal)
   self.store.setting(key,packed({'state':'complete','key':result['key']}));return result
  except Exception:
   self.store.setting(key,packed({'state':'needs_input','at':time.time()}));raise
 def rank(self,resume_id,vacancy_ids,goal='',model='text-embedding-3-small'):
  if not isinstance(vacancy_ids,list) or not 1<=len(vacancy_ids)<=200 or any(not isinstance(v,str) for v in vacancy_ids):raise ValueError('Выберите от 1 до 200 вакансий.')
  from .extension_ranking import rank_vacancies
  cv=self.archive.detail('resume',resume_id)['payload'];jobs=[self.archive.detail('vacancy',v)['payload'] for v in dict.fromkeys(vacancy_ids)]
  return rank_vacancies({'resume_id':resume_id,'bundle':{'resumes':[cv]},'vacancies':jobs,'goal':goal,'model':model,'allow_api':False},Path(__file__).resolve().parents[1]/'.cache/extension_embeddings',archive=self.archive)
 async def converse(self,text,request_id,actor='local_owner'):
  from .career_orchestrator import converse
  return await converse(self,text,request_id,actor)

 async def enqueue_task_notifications(self):
  with self.store.connect() as db:
   events=[dict(r) for r in db.execute("SELECT e.* FROM agent_task_events e LEFT JOIN workflow_delivery d ON d.key='task-event:'||e.id WHERE d.key IS NULL ORDER BY e.id LIMIT 100")]
  for event in events:
   task=self.task(event['task_id'])
   self.enqueue('task-event:'+str(event['id']),'Задача агента · '+event['task_id']+'\n'+{'pause':'Запрошена пауза','resume':'Возобновление','cancel':'Запрошена отмена'}[event['action']]+' · '+task['state'],[[('Задачи агента','w:menu:tasks')]])
