"""Private operator UI and twice-daily, cached-ranking digest. No automatic applications."""
import asyncio,json,os,time,re
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from .archive_store import ArchiveStore
from .application_workflow import packed,utc,hashed,CRM_STAGES,WORK_STATUSES
from .application_conversation import discuss

from .career_application import CareerApplication
from .workflow_messages import TITLES,CHROME_HELP,browser_note

class WorkflowBot(CareerApplication):
 def __init__(self,store,operator,owner,*,drafter=discuss):
  super().__init__(store)
  self.operator=operator;self.owner=int(owner);self.drafter=drafter;self.lock=asyncio.Lock();self.progress_lock=asyncio.Lock();self.giga_ready=False
 async def tick(self,now=None):
  await self.flush_deliveries()
  from .career_runtime import scheduled_tick
  await scheduled_tick(self,now)
  await self.flush_deliveries()
  await self.refresh_progress()
 async def finish_digest(self):
  await super().finish_digest();await self.flush_deliveries()
 async def enqueue_event_notifications(self):
  await super().enqueue_event_notifications();await self.flush_deliveries()
 async def flush_deliveries(self):
  from .delivery_store import DeliveryRejected
  self.store.deliveries()
  with self.store.connect() as db:pending=[dict(r) for r in db.execute("SELECT key FROM workflow_delivery WHERE state='pending' AND payload IS NOT NULL ORDER BY created_at LIMIT 100")]
  for row in pending:
   claim=self.store.claim_delivery_send(row['key'])
   if not claim:continue
   try:
    result=await self.operator.send(claim['payload']['text'],claim['payload']['keyboard'])
   except DeliveryRejected:self.store.finish_delivery(row['key'],claim['lease_token'],rejected=True)
   except Exception:self.store.finish_delivery(row['key'],claim['lease_token'],error=True)
   else:self.store.finish_delivery(row['key'],claim['lease_token'],message_ids=result if isinstance(result,list) else [])
 async def notify(self,key,text,keyboard=None):
  self.enqueue(key,text,keyboard);await self.flush_deliveries()
 async def show(self,app_id):
  a=self.store.workflow(app_id);w=a['workflow'];c=a['context']
  sent=c['channel']=='hh' and a['status'] in ('submitted','viewed','invited','rejected','withdrawn')
  giga=next((channel for channel in a['channels'] if channel['channel']=='telegram'),None)
  if c['channel']=='career':
   next_step='Ответить на анкету компании' if w['form'] else 'Подготовить письмо и открыть форму компании'
   primary=([[('Ответить на вопросы анкеты',f'w:fields:{app_id}@0')],[('Проверить перенос в Chrome',f'w:preview:{app_id}')]] if w['form'] and w['state'] not in ('fill_approved','filling') else [])+[[('Письмо · API',f'w:talk:{app_id}'),('Письмо без API',f'w:offline:{app_id}')],[('Своя редакция',f'w:edit:{app_id}')]]
  elif sent:
   next_step='Продолжить интервью Giga' if a.get('giga_invitation') else 'Дождаться ответа или обновить чат HH'
   primary=[[('Продолжить Giga',f'activate:{giga["id"]}')]] if giga else []
   if not giga and a.get('giga_invitation'):primary.append([('Связать это приглашение с Giga',f'w:giga:{app_id}')])
   primary.append([('Обновить статусы и открытые чаты HH','w:menu:sync')])
  elif w['state'] in ('sending','approved','uncertain'):
   next_step='Проверить результат на HH; повторная отправка не выполняется'
   primary=[[('Обновить статусы HH','w:menu:sync'),('Обновить карточку',f'w:open:{app_id}')]]
  elif w['form']:
   next_step='Проверить точный текст и ответы перед разрешением'
   primary=([[('Ответить на вопросы анкеты',f'w:fields:{app_id}@0')]] if any(f.get('purpose')!='cover' for f in w['form']['fields']) else [])+[[('Проверить и разрешить отправку',f'w:preview:{app_id}')],[('Изменить письмо · API',f'w:talk:{app_id}'),('Изменить без API',f'w:offline:{app_id}')],[('Вставить свою редакцию',f'w:edit:{app_id}')]]
  else:
   next_step='Подготовить форму HH' if w['draft'] else 'Составить письмо'
   primary=([[( 'Подготовить форму HH',f'w:prepare:{app_id}')]] if w['draft'] else [])+[[('Письмо / обсуждение · API',f'w:talk:{app_id}'),('Письмо без API',f'w:offline:{app_id}')],[('Своя редакция / из ChatGPT',f'w:edit:{app_id}')]]
  if not sent and w['state'] not in ('sending','approved','uncertain','fill_approved','filling'):
   primary=[[('🚀 Разбор + письмо + форма · API',f'w:papi:{app_id}')],[('📋 Подготовить без API',f'w:poff:{app_id}')],[('🔎 Соответствие · Luna',f'w:analysis:{app_id}')]]+primary
  if c['channel']=='career' and not w['form']:primary.append([('Открыть вакансию компании ↗',c['vacancy']['link'])])
  controls=primary+[[('План, этапы и история',f'w:plan:{app_id}')],[('К списку откликов','w:menu:apps')]]
  text='💼 '+c['vacancy']['title']+' · '+c['vacancy']['company']+'\nCV: '+c['resume_title']+'\nCRM: '+CRM_STAGES[a['crm']['stage']]+' · '+WORK_STATUSES[a['crm']['work_status']]+'\n'+('HH: ' if c['channel']=='hh' else 'Статус: ')+TITLES.get(a['status'],a['status'])+'\nСледующее действие: '+next_step+'\n'+c['vacancy']['link']
  if not sent:text+='\n\nПисьмо #'+str(w['revision'])+':\n'+(w['draft'] or 'Пока нет. Выберите режим создания ниже.')
  if c['channel']=='career':
   if w['state'] in ('fill_approved','filling'):text+='\n\nРазрешённый перенос ждёт исходную вкладку Chrome. Оставьте её открытой. Повторное разрешение не нужно.'
   elif w['state']=='fields_filled':text+='\n\nТексты перенесены. Проверьте выбранное резюме, файлы, списки и согласия на сайте компании, затем отправьте отклик вручную.'
   else:text+='\n\nСохраните ответы → проверьте точный состав → разрешите перенос в открытую вкладку компании. Финальная отправка пока на сайте; согласия и файлы проверяются отдельно.'
  if a.get('giga_invitation'):text+='\n\nПриглашение Giga сохранено из HH. Запуск: выбрать диалог → /start_recruiter → проверить и подтвердить. Каждый ответ редактируется и отправляется отдельно.'
  await self.operator.send(text,controls)
  for meeting in a['appointments'][:5]:await self.operator.send(meeting['title']+' · '+meeting['status']+'\n'+datetime.fromisoformat(meeting['start_at']).astimezone(ZoneInfo(meeting['time_zone'])).strftime('%d.%m.%Y %H:%M')+' · '+meeting['time_zone']+'\n'+meeting['location']+'\n'+meeting['notes'])
 async def delivery_list(self):
  rows=self.store.deliveries()
  await self.operator.send('Доставка уведомлений: '+str(len(rows))+' требуют доставки или проверки. Сверьте личный чат перед повтором. /deliveries — обновить.')
  for item in rows:
   if item['state']!='uncertain':continue
   ref=hashed([item['key'],item['revision']])[:20];self.store.setting('delivery-review:'+ref,packed({'key':item['key'],'revision':item['revision']}))
   await self.operator.send('Доставка не подтверждена: '+item['key']+'\n'+((item['payload'] or {}).get('text') or 'Старое уведомление; текст будет восстановлен из события.')[:2200],[[('Проверил: сообщение есть',f'w:delivery:{ref}@sent')],[('Проверил: сообщения нет, повторить',f'w:delivery:{ref}@retry')]])
 def clear_input(self):
  for key in ('workflow_waiting','awaiting_answer','awaiting_answer_preferences','awaiting_candidate_fact'):self.store.setting(key,'')
 async def main_menu(self):
  self.clear_input()
  from .journey import overview
  state=await asyncio.to_thread(overview,self.store)
  cv=state['cv']['title'] if state['cv'] else 'выберите в расширении'
  pending=json.loads(self.store.setting('pending_digest') or '{}')
  status='\nПоиск: '+self.task('search:'+pending['discovery_id'])['label'] if pending.get('discovery_id') else '\n«Топ-10 без откликов» — сохранённый рейтинг. Внутри можно запустить поиск новых вакансий.'
  await self.operator.send('🎯 Рабочий поиск\nCV: '+cv+status+'\n\nПодборки: 10:00 и 19:00, Москва. Подготовлю письмо и анкету; отправка — после отдельного согласования. /tasks — очередь и прогресс.\n\nПоиск → выбор вакансии → разбор → письмо → форма → проверка.\nНапример: «Проверь новые вакансии в Яндексе, Сбере и Авито. Интересуют исследовательские позиции».',[[('🎯 Топ-10 без откликов','w:menu:top')],[('Мои отклики и письма','w:menu:apps')],[('🧭 Навыки и обучение','w:menu:skills')],[('Система и настройки','w:menu:system')]])

 async def app_list(self,page=0):
  self.clear_input()
  apps=[a for a in self.store.list() if a['context']['channel'] in ('hh','career') and a['status']!='superseded']
  page=max(0,min(page,(len(apps)-1)//8 if apps else 0));rows=[[(a['context']['vacancy']['title'][:45],f'w:open:{a["id"]}')] for a in apps[page*8:(page+1)*8]]
  nav=[]
  if page:nav.append(('← Назад',f'w:apps:{page-1}'))
  if len(apps)>(page+1)*8:nav.append(('Ещё отклики →',f'w:apps:{page+1}'))
  if nav:rows.append(nav)
  rows.append([('Главное меню','w:menu:home')])
  await self.operator.send('Мои отклики · '+str(len(apps))+'\nВыберите вакансию. В карточке показано следующее действие.' if apps else 'Откликов пока нет. Выберите вакансию из подборки.',rows)
 async def request_today(self):
  raw=self.store.setting('pending_digest')
  if raw:
   pending=json.loads(raw)
   if pending.get('discovery_id'):
    task=self.task('search:'+pending['discovery_id']);await self.operator.send(task['label']+'\n'+(task['next_action'] or 'Поиск уже сохранён. Повторять запрос не нужно.')+'\n/tasks — состояние, пауза и отмена.',[[('Открыть задачи','w:menu:tasks')]])
   else:await self.operator.send('Чтение уже в очереди Chrome. /tasks — состояние и управление.')
  else:await self.begin_digest('manual:'+str(time.time_ns()))
 async def connection_status(self):
  browser=self.store.browser_status();workers=browser['workers'];giga=workers['giga']
  auto=browser['auto_sync'];auto_labels={'disabled':'выключена','waiting_chrome':'ждёт обновлённое расширение и подключение HH','queued':'в очереди','running':'чтение страниц','scheduled':'по расписанию','backoff':'пауза после ошибки'}
  auto_text='\nАвтосинхронизация HH: '+auto_labels.get(auto['state'],auto['state'])+' · каждые '+str(auto['interval_seconds']//60)+' мин.'+'\nПоследнее успешное чтение HH: '+(datetime.fromtimestamp(auto['last_success'],self.zone).strftime('%d.%m %H:%M') if auto['last_success'] else 'ещё не подтверждено')
  bump=browser['resume_bump'];auto_text+='\n⬆️ Автоподнятие резюме: '+('включено для '+str(len(bump['resume_ids'])) if bump['enabled'] else 'выключено')+(' · ожидает расширение 0.11.18 / Chrome' if bump['enabled'] and not bump['worker_ready'] else '')
  labels={'connected':'на связи (RPC подтверждён)','reconnecting':'переподключается','not_configured':'не настроен','unauthorized':'нужен вход','error':'ошибка соединения','stale':'нет свежего подтверждения','unknown':'не проверен'}
  await self.operator.send('Telegram-бот: работает\nTelethon/Giga: '+labels.get(giga['state'],giga['state'])+'\nChrome/HH: '+('свежий heartbeat' if browser['connected'] else 'нет связи')+'\nСбор вакансий: '+('на связи' if workers['collection']['connected'] else 'нет свежего heartbeat')+'\nСайты компаний: '+('на связи' if workers['career']['connected'] else 'нет свежего heartbeat')+'\nHH: в очереди '+str(browser['queued'])+'; выполняется '+str(browser['running'])+auto_text+('' if browser['connected'] else '\n\n'+CHROME_HELP))

 async def resume_bump_menu(self):
  from .resume_bump import status
  s=status(self.store);labels={'disabled':'выключено','waiting_chrome':'ждём Chrome','queued':'в очереди','running':'проверка HH','cooldown':'ждём доступность кнопки','scheduled':'запланировано','needs_input':'нужна проверка'}
  lines=['⬆️ Поднять резюме в поиске HH','Бесплатное поднятие выбранных CV, не чаще раза в 4 часа. Скрытые резюме не публикуются. Если Chrome спит — задача ждёт.']
  for r in s['resumes']:
   if r['selected']:lines.append(r['title']+' · '+labels[r['state']]+(' · '+r['note'] if r.get('note') else ''))
  buttons=[]
  if s['enabled']:buttons.append([('Приостановить автоподнятие',f'w:bumpoff:{s["revision"]}')])
  else:
   primary=self.archive.summary().get('primary_id');row=next((r for r in s['resumes'] if r['id']==primary),None)
   if row:
    import secrets
    ref=secrets.token_hex(10);self.store.setting('resume-bump-approval:'+ref,packed({'resume_id':primary,'revision':s['revision'],'expires':time.time()+900}))
    lines.append('Кнопка ниже разрешает автоподнятие только CV: '+row['title'])
    buttons.append([('Разрешить бесплатное автоподнятие этого CV',f'w:bumpon:{ref}')])
  lines.append('Выбор нескольких резюме: веб-сервис → Сегодня → Поднять резюме в поиске HH. Результаты придут сюда; платные услуги не подключаются.')
  buttons.extend([[('Обновить состояние','w:menu:bump')],[('Главное меню','w:menu:home')]])
  await self.operator.send('\n\n'.join(lines),buttons)

 def field_context(self,ref):
  data=json.loads(self.store.setting('field-review:'+ref) or '{}');a=self.store.workflow(data['app_id']);form=a['workflow']['form']
  if not form or form['fingerprint']!=data['fingerprint']:raise ValueError('Анкета изменилась. Откройте последнюю версию.')
  field=next((f for f in form['fields'] if f['id']==data['field_id']),None)
  if not field or a['form_answers']['revisions'][field['id']]!=data['revision']:raise ValueError('Ответ уже изменился. Откройте анкету заново.')
  return data,a,field
 async def form_fields(self,app_id,page=0):
  a=self.store.workflow(app_id);form=a['workflow']['form']
  if not form:raise ValueError('Сначала подготовьте форму в расширении.')
  fields=[f for f in form['fields'] if f.get('purpose')!='cover'];rows=[]
  for f in fields[page*8:(page+1)*8]:
   revision=a['form_answers']['revisions'][f['id']];ref=hashed([app_id,form['fingerprint'],f['id'],revision])[:20]
   self.store.setting('field-review:'+ref,packed({'app_id':app_id,'fingerprint':form['fingerprint'],'field_id':f['id'],'revision':revision}))
   value=a['form_answers']['values'][f['id']];mark='✓' if value else '○'
   rows.append([(mark+' '+f['label'][:48],f'w:field:{ref}')])
  if len(fields)>(page+1)*8:rows.append([('Ещё вопросы',f'w:fields:{app_id}@{page+1}')])
  if a['context']['channel']=='career':rows.append([('Общие данные для анкет',f'w:profile:{app_id}')])
  rows.append([('Проверить весь отклик',f'w:preview:{app_id}')])
  await self.operator.send('Анкета · '+a['context']['vacancy']['title']+'\nВопросов: '+str(len(fields))+'. Выберите вопрос. Ответы сохраняются в общей истории; на сайт не отправляются.',rows)
 async def show_field(self,ref):
  data,a,f=self.field_context(ref);value=a['form_answers']['values'][f['id']]
  rows=[]
  if f.get('manual_only') or f['type']=='file':
   await self.operator.send(f['label']+'\n'+('Вложение нужно выбрать на сайте компании. Содержимое файла не читалось.' if f['type']=='file' else 'Это поле нужно проверить и выбрать на сайте компании. Автоматический перенос его не меняет.'),[[('К вопросам',f'w:fields:{a["id"]}@0')]]);return
  if f['type'] in ('checkbox','radio'):rows=[[('Да',f'w:fchoice:{ref}@yes'),('Нет',f'w:fchoice:{ref}@no')]]
  elif f['type']=='select':rows=[[(o['text'][:55],f'w:fchoice:{ref}@{i}')] for i,o in enumerate(f.get('options',[]))]
  else:
   rows=[[('Написать / вставить ответ',f'w:fedit:{ref}')]]
   from .candidate_profile import field_key
   if not field_key(f) and f.get('purpose') not in ('contact','resume_url') and f['type'] not in ('email','tel'):rows.append([('Предложить ответ · API',f'w:fapi:{ref}'),('Ответ без API',f'w:foffline:{ref}')])
  rows.append([('К вопросам анкеты',f'w:fields:{a["id"]}@0')])
  await self.operator.send(f['label']+(' *' if f.get('required') else '')+'\n\nТекущий ответ:\n'+str(value or 'Пока нет')+'\n\nВыбор и текст сохранятся как черновик. Отправка — после общей проверки.',rows)
 async def profile_menu(self,app_id=''):
  from .candidate_profile import read
  p=read(self.store);rows=[]
  for key,label in p['labels'].items():
   ref=hashed([key,p['revisions'][key],app_id])[:20];self.store.setting('profile-review:'+ref,packed({'key':key,'revision':p['revisions'][key],'app_id':app_id}))
   rows.append([(label+': '+(p['values'][key] or 'не указано'),f'w:pedit:{ref}')])
  rows.append([('К анкете',f'w:fields:{app_id}@0')] if app_id else [('Главное меню','w:menu:home')])
  await self.operator.send('Данные для анкет\nКонтакты, город, соцсети и портфолио хранятся отдельно от CV и не отправляются модели. Используются только в пустых полях, после проверки переноса. Согласия и специфичные ответы работодателю не копируются между компаниями. Выберите поле для правки.',rows)
 async def career_fill_preview(self,app_id):
  a=self.store.workflow(app_id)
  try:intent=self.store.career_fill_intent(app_id)
  except ValueError as error:
   await self.operator.send(str(error),[[('К карточке',f'w:open:{app_id}')]]);return
  c=a['context'];form=intent['form_snapshot']
  await self.operator.send('ПРОВЕРКА ПЕРЕНОСА В ФОРМУ\n'+c['vacancy']['company']+' · '+c['vacancy']['title']+'\n'+intent['source_url']+'\nКонтекст CV: '+c['resume_title']+'\nЦель: '+(c['goal'] or 'не задана')+'\n\nБудут переданы только показанные сохранённые тексты. Сайт может сохранять данные сразу при вводе. Выбранное на сайте резюме проверьте отдельно.')
  for f in form['fields']:
   if f['id'] in intent['answers']:await self.operator.send(f['label']+':\n'+intent['answers'][f['id']])
  ref=hashed(intent)[:20];self.store.setting('career-fill-review:'+ref,packed(intent))
  await self.operator.send('Вручную на сайте: '+('; '.join(intent['manual_fields']) or 'файлы, согласия и нестандартные поля')+'\n'+'\n'.join(intent['limitations'])+'\n\nРазрешение действует 15 минут для этих текстов и этой версии формы. Кнопка отправки отклика не нажимается.',[[('Разрешаю заполнить поля',f'w:cfill_approve:{ref}')],[('Изменить ответы',f'w:fields:{app_id}@0'),('Изменить письмо',f'w:edit:{app_id}')],[('К карточке',f'w:open:{app_id}')]])
 async def preview(self,app_id):
  a=self.store.workflow(app_id)
  if a['context']['channel']=='career':return await self.career_fill_preview(app_id)
  form=a['workflow']['form']
  if not form:raise ValueError('Сначала подготовьте форму HH.')
  c=a['context'];values=a['form_answers']['values']
  await self.operator.send('ПРОВЕРКА ОТКЛИКА\n'+c['vacancy']['title']+'\nCV: '+c['resume_title']+'\n'+str(c.get('resume_url') or c['resume_id'])+'\nЦель: '+(c['goal'] or 'не задана')+'\nПисьмо #'+str(a['workflow']['revision'])+':\n'+a['workflow']['draft'])
  for f in form['fields']:
   if f.get('purpose')!='cover':await self.operator.send(f['label']+(' *' if f.get('required') else '')+':\n'+str(values[f['id']] or 'Не заполнено'))
  rows=[]
  if any(f.get('purpose')!='cover' for f in form['fields']):rows.append([('Ответить / изменить ответы',f'w:fields:{app_id}@0')])
  try:intent=self.store.intent(app_id)
  except ValueError as error:
   await self.operator.send(str(error),rows+[[('К карточке отклика',f'w:open:{app_id}')]]);return
  ref=hashed(intent)[:20];self.store.setting('intent:'+ref,packed(intent))
  rows.append([('Разрешаю «'+intent['submit_label']+'»',f'w:approve:{ref}')])
  rows.append([('Изменить письмо',f'w:edit:{app_id}')])
  await self.operator.send('Действие на HH: «'+intent['submit_label']+'». Разрешение действует 15 минут только для показанных CV, письма и ответов. Следующий шаг анкеты потребует нового согласования.',rows)
 async def update(self,update):
  cb=update.get('callback_query');m=update.get('message') or {};actor=(cb or m).get('from',{});chat=(cb.get('message',{}) if cb else m).get('chat',{})
  if actor.get('id')!=self.owner or chat.get('id')!=self.owner or chat.get('type')!='private':return True
  text=m.get('text','');waiting=self.store.setting('workflow_waiting')
  if cb and not cb.get('data','').startswith('w:'):return False
  if not cb and not waiting and not text.startswith('/') and any(self.store.setting(k) for k in ('awaiting_answer','awaiting_answer_preferences','awaiting_candidate_fact')):return False
  if not cb and not waiting and text=='/cancel' and any(self.store.setting(k) for k in ('awaiting_answer','awaiting_answer_preferences','awaiting_candidate_fact')):return False
  natural=not cb and not waiting and not text.startswith('/') and bool(text.strip())
  agent_command=not cb and (text=='/tasks' or any(text.startswith(c+' ') for c in ('/pause','/resume','/cancel')))
  if not cb and not (natural or agent_command or text.split('@')[0] in ('/start','/help','/status','/today','/hh','/sync_hh','/deliveries','/cancel') or (waiting and not text.startswith('/'))):return False
  async with self.lock:
   try:
    if cb:
     await self.operator.ack(cb['id']);_,op,id=cb['data'].split(':',2)
     self.store.setting('awaiting_answer','');self.store.setting('awaiting_answer_preferences','');self.store.setting('awaiting_candidate_fact','');self.store.setting('workflow_waiting','')
     if op=='task':
      action,task_id,revision=id.split('@');self.control_task(task_id,action,int(revision),'telegram:'+str(self.owner));await self.task_menu()
     elif op=='rank':
      from .telegram_ranking import show_page
      await show_page(self,id)
     elif op=='pick':
      app=self.select_recommendation(id);await self.show(app['id'])
     elif op=='nodate':
      from .discovery import read
      scope={**read(self.store,id)['payload'].get('scope',{}),'since_days':None}
      task=await self.search('nodate-'+cb['id'],scope);await self.operator.send('🔎 Запущен отбор без ограничения даты публикации. Компании и направления сохранены. Результат придёт сюда.');await self.task_menu(task)
     elif op=='why':
      data=json.loads(self.store.setting('recommendation:'+id) or '{}');e=data['explanation'];fit=e['qualification_fit'];align=e['career_alignment']
      await self.operator.send('🔎 Почему эта вакансия\n'+fit['meaning']+'\nБлизость к CV: '+str(fit['semantic_similarity'])+'\nК цели: '+str(align['semantic_similarity'])+'\n'+e['application_priority']['rule']+'\n'+(align.get('explanation') or 'Подробный разбор требований Luna пока не выполнен. Это предварительный семантический отбор.'),[[('Подробный разбор',f'w:rreview:{id}'),('Подготовить отклик',f'w:pick:{id}')]])
     elif op in ('rreview','rapi','roff','rimport','rpage'):
      from .telegram_analysis import recommendation_action
      await recommendation_action(self,op,id)
     elif op=='feedback':
      ref,choice=id.split('@');from .career_recommendations import feedback
      feedback(self,ref,choice);await self.operator.send('✅ Оценка сохранена. '+('Вакансия будет исключена из следующих подборок для этой версии CV.' if choice=='uninteresting' else 'Учту при следующих подборках.'),[[('К вакансиям','w:menu:results')]])
     elif op in ('papi','poff','pstart','pprompt','analysis','aapi','aoff','aimport'):
      await self.preparation_action(op,id,cb['id'])
     elif op=='menu':
      if id=='today':await self.request_today()
      elif id=='tasks':await self.task_menu()
      elif id=='top':
       from .telegram_ranking import show_top
       await show_top(self)
      elif id=='results':await self.results_menu()
      elif id=='apps':await self.app_list()
      elif id=='setup':await self.operator.send(CHROME_HELP)
      elif id=='skills':
       from .career_skills import telegram
       p=await asyncio.to_thread(self.skills_plan)
       await self.operator.send(telegram(p),[[('Главное меню','w:menu:home')]])
      elif id=='system':await self.operator.send('Система · служебные действия',[[('Задачи агента','w:menu:tasks')],[('⬆️ Поднятие резюме HH','w:menu:bump')],[('Проверить связь','w:menu:status'),('Подключить HH','w:menu:setup')],[('Обновить ответы и чаты HH','w:menu:sync')],[('Данные для анкет','w:menu:profile')],[('Проверить доставку уведомлений','w:menu:deliveries')],[('Главное меню','w:menu:home')]])
      elif id=='bump':await self.resume_bump_menu()
      elif id=='profile':await self.profile_menu()
      elif id=='deliveries':await self.delivery_list()
      elif id=='status':await self.connection_status()
      elif id=='sync':self.store.queue_command('sync');await self.operator.send('Синхронизация ответов HH в очереди Chrome.')
      else:await self.main_menu()
     elif op in ('bumpon','bumpoff'):
      from .resume_bump import configure,status,tick
      if op=='bumpon':
       approval=json.loads(self.store.setting('resume-bump-approval:'+id) or '{}')
       if approval.get('expires',0)<time.time():raise ValueError('Разрешение истекло. Откройте меню поднятия заново.')
       configure(self.store,{'enabled':True,'resume_ids':[approval['resume_id']]},approval['revision'],True)
      else:
       cfg=status(self.store);configure(self.store,{'enabled':False,'resume_ids':cfg['resume_ids']},int(id))
      tick(self.store);await self.resume_bump_menu()
     elif op=='delivery':
      ref,resolution=id.split('@');saved=json.loads(self.store.setting('delivery-review:'+ref) or '{}')
      self.store.resolve_delivery(saved['key'],saved['revision'],resolution,confirmed=True);await self.delivery_list()
     elif op=='giga':
      app=self.store.start_screening(id,confirmed=True)
      await self.operator.send('Связь Giga с этой вакансией и CV сохранена. Отправки рекрутеру не было. Выберите диалог ниже, затем /question для существующего общения.',[[('Выбрать связанный Giga-диалог',f'activate:{app["id"]}')]])
     elif op=='apps':await self.app_list(int(id))
     elif op=='open':await self.show(id)
     elif op=='plan':
      a=self.store.workflow(id)
      await self.operator.send('План · '+a['context']['vacancy']['title']+'\n'+CRM_STAGES[a['crm']['stage']]+' · '+WORK_STATUSES[a['crm']['work_status']]+'\n'+a['crm']['next_action'],[[('Этап отбора',f'w:stages:{id}'),('Что сейчас делаем',f'w:works:{id}')],[('Назначить интервью',f'w:meeting:{id}'),('Следующий шаг',f'w:nextstep:{id}')],[('История ответов',f'w:history:{id}')],[('Назад к отклику',f'w:open:{id}')]])
     elif op=='history':
      a=self.store.workflow(id);history=a['field_history'][:20]
      if not history and not a['field_suggestions']:await self.operator.send('Сохранённых ответов анкеты пока нет.')
      for v in reversed(a['field_suggestions'][:10]):await self.operator.send(v['question']+' · предложение '+v['result'].get('model','модели')+'\n'+v['result']['answer'])
      for v in reversed(history):await self.operator.send(v['question']+' · версия '+str(v['revision'])+' · '+v['actor']+'\n'+str(v['value']))
      await self.operator.send('История хранится с версией формы и контекстом CV/вакансии.',[[('Назад',f'w:open:{id}')]])
     elif op=='fields':
      app_id,page=id.split('@');await self.form_fields(app_id,int(page))
     elif op=='profile':await self.profile_menu('' if id=='home' else id)
     elif op=='pedit':
      from .candidate_profile import LABELS
      data=json.loads(self.store.setting('profile-review:'+id) or '{}');self.store.setting('workflow_waiting',packed({**data,'mode':'profile'}));await self.operator.send('Пришлите поле «'+LABELS[data['key']]+'» одним сообщением. Оно будет сохранено для анкет разных компаний. /cancel — отмена.')
     elif op=='field':await self.show_field(id)
     elif op=='fchoice':
      ref,choice=id.split('@');data,a,f=self.field_context(ref)
      value=choice=='yes' if f['type'] in ('checkbox','radio') else f['options'][int(choice)]['value']
      self.store.save_field_answer(a['id'],f['id'],value,data['fingerprint'],data['revision'],'telegram_user');await self.form_fields(a['id'])
     elif op in ('fedit','foffline','fapi'):
      data,a,f=self.field_context(id)
      if f['type'] in ('checkbox','radio','select'):raise ValueError('Выберите один из вариантов формы.')
      if f.get('manual_only') or f['type']=='file':raise ValueError('Это поле заполняется на сайте компании.')
      if op in ('foffline','fapi'):self.store.answerable_field(a['id'],f['id'],data['fingerprint'],data['revision'])
      if op=='fapi':
       await self.operator.send('Предлагаю ответ с Luna. Это черновик, он не отправится работодателю.')
       from .recruiter_answers import draft_answer
       from .candidate_facts import answer_context
       result=await asyncio.to_thread(draft_answer,answer_context(self.store,a['context']),f['label'],'luna',Path(__file__).resolve().parents[1]/'.cache/recruiter_answers')
       data,a,f=self.field_context(id)
       self.store.record_field_suggestion(a['id'],f['id'],{**result,'model':'luna'},data['fingerprint'],data['revision'])
       await self.operator.send(result['answer']+'\n\n'+('Нужно уточнить: '+'; '.join(result['missing']) if result['needs_user'] else result['review_note']))
       self.store.setting('workflow_waiting',packed({'mode':'field','app_id':a['id'],'ref':id}))
       await self.operator.send('Отредактируйте предложение и пришлите окончательный ответ одним сообщением. Он сохранится в анкете; отправка будет согласована отдельно. /cancel — оставить прежний ответ.')
      else:
       if op=='foffline':
        from .external_prompt import build_prompt
        from .candidate_facts import answer_context
        prompt=build_prompt(answer_context(self.store,a['context']),'answer',question=f['label'],draft=str(a['form_answers']['values'][f['id']]))
        if hasattr(self.operator,'send_prompt'):await self.operator.send_prompt(prompt)
        else:await self.operator.send(prompt)
       self.store.setting('workflow_waiting',packed({'mode':'field','app_id':a['id'],'ref':id}))
       await self.operator.send('Пришлите готовый ответ на вопрос: '+f['label']+'\nОн сохранится без отправки работодателю. /cancel — отмена.')
     elif op=='stages':await self.operator.send('Выберите этап CRM. HH-статус сохранится отдельно.',[[(label,f'w:stage:{id}@{key}')] for key,label in CRM_STAGES.items()]+[[('Назад к плану',f'w:plan:{id}')]])
     elif op=='stage':
      app_id,stage=id.split('@');self.store.set_crm(app_id,stage,actor='telegram_user');await self.show(app_id)
     elif op=='works':await self.operator.send('Этап отбора не меняется. Что сейчас делаем?', [[(label,f'w:work:{id}@{key}')] for key,label in WORK_STATUSES.items()]+[[('Назад к плану',f'w:plan:{id}')]])
     elif op=='work':
      app_id,state=id.split('@');a=self.store.workflow(app_id);self.store.set_crm(app_id,a['crm']['stage'],actor='telegram_user',work_status=state,revision=a['crm']['revision']);await self.show(app_id)
     elif op in ('meeting','nextstep','offline'):
      self.store.get(id);self.store.setting('workflow_waiting',packed({'app_id':id,'mode':op}))
      await self.operator.send({'meeting':'Пришлите: ГГГГ-ММ-ДД ЧЧ:ММ | длительность в минутах | название | адрес или ссылка (необязательно). Время — Москва. Например: 2026-11-02 14:00 | 60 | Техническое интервью | https://meet.google.com/… . /cancel — отмена.', 'nextstep':'Пришлите следующий шаг. Можно добавить срок после |: Ждём приглашения | 2026-11-02 10:00. Время — Москва. /cancel — отмена.', 'offline':'Напишите пожелания редактору и нужную длину письма, например: «Составь письмо на 3 предложения, подчеркни исследовательский проект». Я подготовлю промпт с CV, вакансией, целью, письмом и историей. API модели не вызывается. /cancel — отмена.'}[op])
     elif op in ('talk','edit'):

      self.store.get(id);self.store.setting('workflow_waiting',packed({'app_id':id,'mode':op}));await self.operator.send('Напишите пожелания и попросите составить/изменить письмо. Обсуждение с Luna платное; контекст CV и вакансии будет передан в OpenAI. /cancel — отмена.' if op=='talk' else 'Пришлите полный текст письма. Он сохранится без вызова модели и без отправки на HH. /cancel — отмена.')
     elif op=='cfill_approve':
      intent=json.loads(self.store.setting('career-fill-review:'+id) or '{}');self.store.approve_career_fill(intent['app_id'],intent['intent_hash'],confirmed=True);await self.operator.send('Разрешение на перенос сохранено на 15 минут. Исходная вкладка компании должна оставаться открытой. Отправки отклика и выбора согласий не будет.');await self.show(intent['app_id'])
     elif op=='prepare':
      self.prepare_form(id);await self.operator.send('Подготовка поставлена в очередь Chrome. Отправка только после отдельного разрешения.')
     elif op=='preview':await self.preview(id)
     elif op=='approve':
      intent=json.loads(self.store.setting('intent:'+id) or '{}');self.store.approve(intent['app_id'],intent['intent_hash'],intent['answers'],confirmed=True);await self.operator.send('Разрешение сохранено. Подключённая вкладка HH выполнит это действие один раз. Жду подтверждения от сайта.')
     else:raise ValueError('Кнопка устарела.')
    elif natural or agent_command:
     result=await self.converse(text,'telegram:'+str(update.get('update_id',m.get('message_id'))),'telegram:'+str(self.owner))
     if 'tasks' not in result:await self.operator.send(result['message'])
     if result.get('application_id'):await self.show(result['application_id'])
     elif result.get('application_ids'):
      for app_id in result['application_ids']:await self.show(app_id)
     elif 'tasks' in result or 'task' in result:await self.task_menu(result.get('task'))
     elif 'state' in result:await self.connection_status()
    elif text.startswith('/start'):await self.main_menu()
    elif text=='/help':
     await self.main_menu();await self.operator.send('/today — активные вакансии\n/hh — отклики и CRM\n/sync_hh — ответы HH\n/status — состояние\n/applications — выбрать Giga-отклик\n/question — текущий вопрос Giga\n/tasks — задачи агента\n/pause search:ID, /resume search:ID, /cancel search:ID — управление задачей\n/cancel — завершить ввод')
    elif text=='/deliveries':await self.delivery_list()
    elif text=='/status':await self.connection_status()
    elif text=='/today':await self.request_today()
    elif text=='/hh':await self.app_list()
    elif text=='/sync_hh':self.store.queue_command('sync');await self.operator.send('Синхронизация HH в очереди Chrome. Прочитаю доступные страницы и чаты; отсутствие записи не означает отказ.')
    elif text=='/cancel':
     self.store.setting('workflow_waiting','');await self.operator.send('Ввод отменён.',[[('Вернуться к отклику',f'w:open:{json.loads(waiting)["app_id"]}')]] if waiting and json.loads(waiting).get('app_id') else [[('Главное меню','w:menu:home')]])
    elif waiting:
     p=json.loads(waiting)
     if p['mode']=='profile':
      from .candidate_profile import save
      save(self.store,{p['key']:text},{p['key']:p['revision']},'telegram_owner');self.store.setting('workflow_waiting','');await self.profile_menu(p.get('app_id',''));return True
     if p['mode']=='recommendation_analysis_import':
      from .telegram_analysis import import_result
      await import_result(self,p,text);return True
     a=self.store.workflow(p['app_id'])
     if p['mode']=='analysis_import':
      from .external_analysis import import_review
      imported=import_review(self.archive,p['export_id'],text);self.store.setting('workflow_waiting','');await self.analysis_card(a['id'],imported)
     elif p['mode']=='edit':self.store.save_letter(a['id'],text,a['workflow']['revision']);self.store.setting('workflow_waiting','');await self.show(a['id'])
     elif p['mode']=='meeting':
      fields=[v.strip() for v in text.split('|')]
      if len(fields) not in (3,4):raise ValueError('Формат: ГГГГ-ММ-ДД ЧЧ:ММ | минуты | название | ссылка.')
      start=datetime.strptime(fields[0],'%Y-%m-%d %H:%M').replace(tzinfo=self.zone);duration=int(fields[1])
      self.store.save_appointment(a['id'],{'stage':a['crm']['stage'],'title':fields[2],'start_at':start.isoformat(),'end_at':(start+timedelta(minutes=duration)).isoformat(),'time_zone':str(self.zone),'location':fields[3] if len(fields)==4 else ''},actor='telegram_user');self.store.setting('workflow_waiting','');await self.show(a['id'])
     elif p['mode']=='nextstep':
      fields=text.split('|',1);due=datetime.strptime(fields[1].strip(),'%Y-%m-%d %H:%M').replace(tzinfo=self.zone).isoformat() if len(fields)>1 else None
      self.store.set_crm(a['id'],a['crm']['stage'],actor='telegram_user',next_action=fields[0].strip(),follow_up_at=due,clear_follow_up=not due,revision=a['crm']['revision']);self.store.setting('workflow_waiting','');await self.show(a['id'])
     elif p['mode']=='field':
      data,a,f=self.field_context(p['ref']);self.store.save_field_answer(a['id'],f['id'],text,data['fingerprint'],data['revision'],'telegram_user');self.store.setting('workflow_waiting','');await self.form_fields(a['id'])
     elif p['mode']=='offline':
      from .external_prompt import build_prompt
      prompt=build_prompt(a['context'],'discuss',comments=text,draft=a['workflow']['draft'],history=a['discussion']);self.store.setting('workflow_waiting','')
      if hasattr(self.operator,'send_prompt'):await self.operator.send_prompt(prompt)
      else:await self.operator.send(prompt)
      await self.operator.send('Откройте файл, скопируйте промпт в ChatGPT. Готовое письмо вставьте кнопкой ниже. Вызовов API модели: 0.',[[('Вставить письмо из ChatGPT',f'w:edit:{a["id"]}')]])
     else:
      await self.operator.send('Редактор готовит ответ. Письмо рекрутеру не отправляется.')
      result=await asyncio.to_thread(self.drafter,self.store,a['id'],text,'tg-'+hashed([m.get('message_id'),text])[:24], 'luna');await self.operator.send(result['reply']+ ('\nУточнения: '+'; '.join(result['missing']) if result['needs_user'] else ''));await self.show(a['id'])
   except (ValueError,KeyError,TypeError,IndexError) as error:await self.operator.send(str(error) if isinstance(error,ValueError) else 'Контекст устарел. Откройте отклик заново.',[[('Мои отклики','w:menu:apps')],[('Главное меню','w:menu:home')]])
  return True

 async def task_menu(self,only=None):
  tasks=[only] if only else self.tasks();active=[t for t in tasks if t['actions'] or t['state'].endswith('_requested')]
  if not only:await self.operator.send('⏳ Задачи агента · '+str(len(active))+' активных.\nСостояние хранится в сервисе; закрытие Telegram не отменяет задачу. /tasks — обновить.',[[('Последние вакансии','w:menu:results'),('Новый поиск','w:menu:today')]] if not active else None)
  for task in active[:8]:
   buttons=[[( {'pause':'Пауза','resume':'Продолжить','cancel':'Отменить'}[a],f'w:task:{a}@{task["id"]}@{task["revision"]}')] for a in task['actions']]
   from .agent_progress import text as progress_text
   await self.operator.send(progress_text(task) if task['kind']=='search' else ('🔬 Luna · '+task['label']+'\n'+str(task['progress']['done'])+' из '+str(task['progress']['total'])+' · ошибок '+str(task['progress']['failed'])+'\n'+task['note']) if task['kind']=='analysis' else '🌐 Chrome · '+task['label']+'\n'+task['next_action'],buttons)
 async def refresh_progress(self):
  """Edit existing owner messages, never resend an ambiguous/missing progress card."""
  if not hasattr(self.operator,'edit') or self.progress_lock.locked():return
  from .agent_progress import text as progress_text,EditRetry
  async with self.progress_lock:
   with self.store.connect() as db:
    rows=[dict(r) for r in db.execute("SELECT r.id,r.payload,d.message_ids FROM discovery_runs r JOIN workflow_delivery d ON d.key=r.digest_key||':progress' WHERE d.state='sent' ORDER BY r.updated DESC LIMIT 20")]
   for row in rows:
    receipts=json.loads(row['message_ids'] or '[]')
    if len(receipts)!=1 or type(receipts[0]) is not int:continue
    key='telegram-progress:'+row['id'];previous=json.loads(self.store.setting(key) or '{}')
    if previous.get('disabled') or time.time()<previous.get('next_at',0):continue
    task=self.task('search:'+row['id']);text=progress_text(task)+'\nAPI: '+('включён в сохранённых настройках поиска.' if json.loads(row['payload'])['config']['allow_api'] else 'выключен.')
    fingerprint=hashed(text)
    if fingerprint==previous.get('hash'):continue
    try:exists=await self.operator.edit(receipts[0],text,[[('Задачи и управление','w:menu:tasks')]])
    except EditRetry as error:self.store.setting(key,packed({**previous,'next_at':time.time()+error.after}));continue
    except Exception:self.store.setting(key,packed({**previous,'next_at':time.time()+30}));continue
    self.store.setting(key,packed({'message_id':receipts[0],'hash':fingerprint,'next_at':time.time()+10,'disabled':exists is False}))
 async def progress_updates(self):
  while True:
   try:await self.refresh_progress()
   except Exception:pass  # Progress must not interrupt answer handling/durable delivery.
   await asyncio.sleep(5)

 async def results_menu(self):
  saved=json.loads(self.store.setting('last-selection') or self.store.setting('last-recommendations') or self.store.setting('last-collected') or '{}');rows=[]
  for ref in saved.get('refs',[]):
   data=json.loads(self.store.setting('recommendation:'+ref) or '{}')
   if not data:continue
   try:job=self.archive.detail('vacancy',data['vacancy_id'])['payload']
   except ValueError:continue
   rows.append([(job['title'][:50],f'w:pick:{ref}')])
  await self.operator.send(('📚 Прочитанные вакансии вне подтверждённой подборки' if any(json.loads(self.store.setting('recommendation:'+ref) or '{}').get('unranked') for ref in saved.get('refs',[])) else '🎯 Последняя подборка')+'\nВыберите вакансию → режим разбора и письма → форма в Chrome → проверка.' if rows else '🔎 Подборка пока не готова. Можно запустить поиск или проверить его прогресс.',rows+[[('🎯 Топ-10 без откликов','w:menu:top'),('Полный рейтинг','w:rank:0')],[('Найти вакансии','w:menu:today'),('Очередь и прогресс','w:menu:tasks')]])
 async def analysis_card(self,app_id,analysis=None):
  a=self.store.get(app_id);c=a['context']
  if analysis is None:analysis=self.analyze(c['resume_id'],c['vacancy']['id'],c.get('goal',''))['analysis']
  text='🔎 Соответствие вакансии\n'
  if analysis:
   metric=analysis.get('metrics',{}).get('overall',{});text+='Подтверждение требований: '+str(metric.get('percent'))+'% по рубрике разбора, не вероятность найма.\n'+analysis.get('recommendation_reason','')+'\nЦель: '+analysis.get('goal_alignment','')
  else:text+='Сохранённого разбора для этих CV, вакансии и цели нет. Выберите режим.'
  await self.operator.send(text,[[('Разобрать · Luna API',f'w:aapi:{app_id}'),('Без API',f'w:aoff:{app_id}')],[('Продолжить к письму',f'w:open:{app_id}')]])
 async def preparation_action(self,op,app_id,request):
  version=None
  if '@' in app_id:app_id,version=app_id.split('@',1);version=int(version)
  a=self.store.workflow(app_id);c=a['context']
  if op=='analysis':return await self.analysis_card(app_id)
  if op=='papi':
   await self.operator.send('✍️ Подготовить отклик через API\n'+c['vacancy']['title']+'\nCV: '+c['resume_title']+'\nДо двух запросов: разбор Luna и письмо. Профессиональный текст CV, вакансия, цель и история обсуждения будут переданы модели; готовый разбор берётся из кэша. После подготовки HH откроет форму в Chrome; отправка потребует отдельной проверки. На сайте компании перенос полей согласуется отдельно.',[[('Запустить подготовку · API',f'w:pstart:{app_id}@{a["workflow"]["revision"]}')],[('Без API',f'w:poff:{app_id}'),('Назад',f'w:open:{app_id}')]])
  elif op in ('pstart','poff'):
   if op=='pstart' and version is None:raise ValueError('Откройте новую карточку отклика и подтвердите режим API.')
   task=self.queue_preparation(app_id,'telegram-prep:'+hashed([app_id,version if version is not None else a['workflow']['revision'],op,c])[:32],'api' if op=='pstart' else 'offline',version)
   await self.operator.send(('✅ Подготовка уже сохранена' if task['state'] not in ('queued','analyzing','drafting') else '⏳ Подготовка сохранена')+'\n'+('Разбор и письмо выполнятся в сервисе. Если Chrome спит, форма дождётся подключения.' if op=='pstart' else 'Готовлю промпт без API. Откройте карточку и нажмите «Получить промпт», затем вставьте письмо.'),[[('Получить промпт',f'w:pprompt:{app_id}')] if op=='poff' else [('Открыть отклик',f'w:open:{app_id}')]])
  elif op=='pprompt':
   from .external_prompt import build_prompt
   prompt=build_prompt(c,'discuss',comments='Подготовь короткое письмо по фактам CV, укажи пробелы и необходимые уточнения.',draft=a['workflow']['draft'],history=a['discussion'])
   if hasattr(self.operator,'send_prompt'):await self.operator.send_prompt(prompt)
   else:await self.operator.send(prompt)
   await self.operator.send('📋 Следующий шаг\nСкопируйте промпт в ChatGPT, затем вставьте готовое письмо. После сохранения можно подготовить форму HH или передать анкету компании.',[[('Вставить письмо',f'w:edit:{app_id}')]])
  elif op=='aapi':
   from .skill_analysis import analyze
   await self.operator.send('🔎 Выполняю разбор Luna. Результат сохранится; отправки отклика не будет.')
   result=await asyncio.to_thread(self.analyze_owned,app_id);await self.analysis_card(app_id,result)
  elif op=='aoff':
   from .external_analysis import export_review
   data=export_review(self.archive,c['resume_id'],c['vacancy']['id'],c.get('goal',''));self.store.setting('analysis-export:'+app_id,data['export_id'])
   if hasattr(self.operator,'send_prompt'):await self.operator.send_prompt(data['prompt'])
   else:await self.operator.send(data['prompt'])
   await self.operator.send('📋 Разбор без API\nПолучите JSON в ChatGPT по промпту, затем вставьте его. Цитаты будут проверены перед сохранением.',[[('Вставить JSON разбора',f'w:aimport:{app_id}')],[('К отклику',f'w:open:{app_id}')]])
  elif op=='aimport':
   export_id=self.store.setting('analysis-export:'+app_id)
   if not export_id:raise ValueError('Сначала получите промпт разбора без API.')
   self.store.setting('workflow_waiting',packed({'mode':'analysis_import','app_id':app_id,'export_id':export_id}));await self.operator.send('Пришлите JSON результата разбора. /cancel — отмена.')
