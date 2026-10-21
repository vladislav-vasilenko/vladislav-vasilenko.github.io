"""Deterministic top-K skills intelligence. Reuses current ranking and cached Luna only."""
import copy,math,re,time
from .career_skills_catalog import SKILLS,RESOURCES,VERSION,ACTION_LABELS
from . import career_skills_store as storage,skill_analysis
from .career_skill_requirements import extract,EXTRACTOR
from .career_skill_evidence import collect
from .archive_store import digest
from .career_analytics import snapshot,TAXONOMY
from .luna_batch import selected

ENGINE='skills-priority-3'
METHOD='Спрос: один навык на вакансию; required=1, preferred=0,45, mentioned=0. Вес позиции = 1/log2(rank+2). Приоритет = 100 × доля взвешенного спроса × важность трека/3 × потребность действия / sqrt(max(1, часы/4)). Часы — оценка одного упражнения, не освоения профессии. Это эвристика, не вероятность найма.'
STATES={'confirmed':'Подтверждение есть','unknown':'Данных недостаточно','explicit_gap':'Пробел указан явно','studying':'В процессе обучения','partial':'Частичное подтверждение','conflict':'Противоречивые данные'}

def catalog(store):return {'version':VERSION,'directions':[{'id':k,'label':label} for k,label,_ in TAXONOMY],'tracks':storage.tracks(store),'skills':[{k:v for k,v in s.items() if k!='pattern'} for s in SKILLS.values()],'actions':ACTION_LABELS}

def action(evidence):
 f=evidence['flags'];state=evidence['state']
 if state in ('unknown','conflict'):return 'validate'
 if state=='confirmed':
  if not f['cv_mention']:return 'document_in_cv'
  if (f['project'] or f['research']) and not f['published'] and not f['professional']:return 'publish_project'
  return None
 if f['learning_completed'] or state=='partial':return 'practice'
 return 'learn'

def prerequisites(key,evidence):
 result=[];seen=set()
 def visit(k):
  for p in SKILLS[k]['prerequisites']:
   if p in seen:continue
   seen.add(p);visit(p);e=evidence[p]
   if e['state']!='confirmed':result.append({'skill_id':p,'label':SKILLS[p]['label'],'state':e['state'],'action':'learn' if e['state'] in ('explicit_gap','studying') else 'practice' if e['state']=='partial' else 'validate'})
 visit(key);return result

def learning(key,evidence):
 before=prerequisites(key,evidence);resources=[]
 for rid in SKILLS[key]['resource_ids']:
  r=RESOURCES[rid]
  if key not in r['topics']:continue
  missing=[p for p in r['prerequisites'] if evidence[p]['state']!='confirmed']
  resources.append({**r,'blocked':bool(missing),'missing_prerequisites':missing})
 return {'prerequisites':before,'resources':resources,'resource_gap':not bool(resources),'exercise':'Выполнить одно ограниченное упражнение по теме, сохранить код, результаты и ограничения. После проверки добавить подтверждение.'}

def plan(store,archive,data=None,*,remember=True,vacancy_id=None):
 data=data or {};summary=archive.summary();rid=data.get('resume_id') or summary.get('primary_id')
 if not rid:raise ValueError('Сначала выберите основное резюме.')
 prior=(storage.selection(store,rid) or {}) if remember else {};scope={**prior,**data};limit=scope.get('limit',50)
 trajectory_revision=None;trajectory_stage=None
 if scope.get('trajectory_id'):
  from .career_trajectory import overview
  trajectory=overview(store,archive,scope['trajectory_id'])['path'];trajectory_revision=trajectory['revision']
  if scope.get('stage_id') not in {s['id'] for s in trajectory['stages']}:raise ValueError('Этап траектории не найден.')
  if scope.get('trajectory_revision') is not None and scope['trajectory_revision']!=trajectory_revision:raise ValueError('Траектория изменена. Обновите этап перед расчётом.')
  trajectory_stage=next(s for s in trajectory['stages'] if s['id']==scope['stage_id'])
  scope['goal']=trajectory['goal'];scope['track_id']=trajectory['track_id']
 if type(limit) is not int or not 1<=limit<=50:raise ValueError('Топ-K — от 1 до 50.')
 mode=scope.get('mode','track')
 if mode not in ('vacancies','directions','track'):raise ValueError('Выберите вакансии, направления или карьерный трек.')
 directions=scope.get('direction_ids',[])
 if not isinstance(directions,list) or any(not isinstance(k,str) or k not in {t[0] for t in TAXONOMY} for k in directions):raise ValueError('Некорректные направления воронки.')
 if mode=='directions' and not directions:raise ValueError('Выберите хотя бы одно направление воронки.')
 track=storage.track(store,scope.get('track_id','generative')) if mode=='track' else None
 if mode=='track' and not track:raise ValueError('Карьерный трек не найден.')
 filters=scope.get('filters',{});ids=scope.get('vacancy_ids')
 if not isinstance(filters,dict) or len(str(filters))>10000:raise ValueError('Некорректные фильтры карты.')
 if ids is not None and (not isinstance(ids,list) or len(ids)>10000 or any(not isinstance(i,str) for i in ids)):raise ValueError('Некорректный выбор вакансий.')
 goal=scope.get('goal',summary.get('goal',''));model=scope.get('model','text-embedding-3-small')
 snap=snapshot(archive,rid,goal,model);eligible={r['id'] for r in snap['rows'] if selected(r,filters)}
 if mode=='vacancies' and (not ids or len(ids)>50):raise ValueError('Выберите от 1 до 50 вакансий.')
 if mode=='directions':eligible.intersection_update(r['id'] for r in snap['rows'] if set(r['tags']).intersection(directions))
 if ids is not None:eligible.intersection_update(ids)
 ranked=archive.entities('vacancy',status='full',resume_id=rid,goal=goal,model=model,ranked_only=vacancy_id is None and trajectory_revision is None,exclude_closed=True,all_items=True,include_payload=True)['items']
 if trajectory_revision is not None and ids:
  order={key:i for i,key in enumerate(ids)};ranked.sort(key=lambda r:order.get(r['id'],len(order)))
 jobs=[r for r in ranked if (r['id']==vacancy_id if vacancy_id else r['id'] in eligible) and not r['payload'].get('archived')][:limit]
 if not jobs and vacancy_id:raise ValueError('Нужно полное сохранённое описание незакрытой вакансии.')
 if not jobs:raise ValueError('В выборке нет полных открытых вакансий с актуальным персональным рейтингом. Обновите рейтинг или измените фильтры карты.')
 requirements=[];analyses=[];vacancies=[];unmapped=[]
 for rank,row in enumerate(jobs,1):
  ctx=skill_analysis.context(archive,rid,row['id'],goal);analysis=skill_analysis.cached(archive,ctx)
  if analysis:analyses.append(analysis)
  cache_key='requirements:'+digest([EXTRACTOR,row['payload'],(analysis or {}).get('key')])
  with store.connect() as db:extraction=storage.get(db,cache_key)
  if extraction is None:
   extraction=extract(row['payload'],analysis)
   with store.connect() as db:storage.put(db,cache_key,extraction)
  requirements.extend(extraction['requirements']);unmapped.extend({'vacancy_id':row['id'],'quote':q} for q in extraction['unmapped'])
  vacancies.append({'id':row['id'],'title':row['title'],'company':row.get('company',''),'url':row['payload'].get('link') or row['payload'].get('url',''),'rank':rank,'score':(row.get('ranking') or {}).get('score'),'vacancy_hash':ctx['vacancy_hash'],'analysis_key':(analysis or {}).get('key')})
 evidence=collect(store,archive,rid,analyses);grouped=evidence['skills'];demand={};weight_total=sum(1/math.log2(r['rank']+2) for r in vacancies)
 ranks={r['id']:r['rank'] for r in vacancies}
 for req in requirements:
  if req['type']=='mentioned' or req['negated']:continue
  identity=(req['skill_id'],req['vacancy_id'])
  strict=req.get('strictness','standard')
  type_w=1.35 if strict=='hard' else 1.0 if req['type']=='required' else 0.45
  w=type_w*req['confidence']/math.log2(ranks[req['vacancy_id']]+2)
  if identity not in demand or w>demand[identity][0]:demand[identity]=(w,req)
 if mode!='track':
  demanded={k for k,_ in demand}
  if trajectory_stage:
   stage_keys={k for c in trajectory_stage['criteria'] for k in c['skill_ids']} or set(storage.track(store,trajectory['track_id'])['skills'])
   demanded.intersection_update(stage_keys)
  track={'id':'derived_'+mode,'label':'Выбранные вакансии' if mode=='vacancies' else 'Выбранные направления: '+', '.join(label for k,label,_ in TAXONOMY if k in directions),'revision':1,'source':'vacancy_requirements','skills':{k:{'importance':3,'effort_hours':SKILLS[k]['effort_hours']} for k in sorted(demanded)}}
 priorities=[]
 for key,config in track['skills'].items():
  entries=[v for (s,_),v in demand.items() if s==key]
  if not entries:continue
  e=grouped[key];a=action(e);hours=config['effort_hours'];effort={'validate':1,'document_in_cv':1.5,'publish_project':4,'practice':sum(hours)/2,'learn':sum(hours)/2,None:0}[a]
  need={'validate':.65,'document_in_cv':.85,'publish_project':.7,'practice':.8,'learn':1,None:0}[a]
  score=100*sum(v[0] for v in entries)/weight_total*config['importance']/3*need/math.sqrt(max(1,effort/4))
  priorities.append({'skill_id':key,'label':SKILLS[key]['label'],'state':e['state'],'state_label':STATES[e['state']],'action':a,'action_label':ACTION_LABELS.get(a,'Поддерживать подтверждения'),'priority':round(score,3),'importance':config['importance'],'effort_hours':hours,'action_effort_hours':effort,'vacancy_count':len(entries),'vacancy_ids':[v[1]['vacancy_id'] for v in entries],'requirements':[v[1] for v in entries],'evidence':e,**learning(key,grouped)})
 priorities.sort(key=lambda p:(-p['priority'],-p['vacancy_count'],p['skill_id']))
 fingerprint=digest([ENGINE,VERSION,mode,directions,track,evidence['versions'],evidence['github'],vacancies,goal,model,filters,ids,limit,scope.get('trajectory_id'),trajectory_revision,scope.get('stage_id')])
 coverage=[]
 for job in vacancies:
  job_reqs=[r for r in requirements if r['vacancy_id']==job['id'] and r['type']!='mentioned' and not r['negated']]
  keys={r['skill_id'] for r in job_reqs}
  hard_keys={r['skill_id'] for r in job_reqs if r.get('strictness')=='hard'}
  has_hard_gap=any(grouped[k]['state'] in ('explicit_gap','unknown') for k in hard_keys)
  job['has_hard_gap']=has_hard_gap
  coverage.append({'vacancy_id':job['id'],'requirements':len(keys),'hard_requirements':len(hard_keys),'has_hard_gap':has_hard_gap,'states':{s:sum(grouped[k]['state']==s for k in keys) for s in STATES},'skills':{k:grouped[k]['state'] for k in sorted(keys)}})
 value={'mode':mode,'direction_ids':directions,'career_path':career_path(track,grouped,priorities) if mode=='track' else None,'vacancy_evidence':coverage,'id':fingerprint,'fingerprint':fingerprint,'created':time.time(),'engine':ENGINE,'catalog_version':VERSION,'resume':{'id':rid,'title':snap['resume']['title'],'version_id':evidence['resume']['version_id']},'goal':goal,'model':model,'track':track,'vacancies':vacancies,'requirements':requirements,'unmapped_requirements':unmapped[:100],'skills':grouped,'priorities':priorities,'github':evidence['github'],'summary':{s:sum(e['state']==s for e in grouped.values()) for s in STATES},'methodology':METHOD,'api_requests':0,'limitations':['Локальный словарь ограничен. Нераспознанные требования показаны отдельно.','Уточнения опыта пересчитывают этот план и доказательства по вакансиям. Исходный embedding-рейтинг и Luna-оценки не переписываются.','GitHub-ссылки не означают проверку кода или качества исследований.'],'filters':filters,'limit':limit,'evidence_versions':evidence['versions'],'trajectory_id':scope.get('trajectory_id'),'trajectory_revision':trajectory_revision,'stage_id':scope.get('stage_id')}
 value=storage.save_plan(store,fingerprint,value)
 if remember and trajectory_revision is None:storage.save_selection(store,rid,{'resume_id':rid,'mode':mode,'direction_ids':directions,'track_id':scope.get('track_id','generative'),'filters':filters,'vacancy_ids':ids,'goal':goal,'model':model,'limit':limit})
 return value

def save_evidence(store,archive,data):
 source=storage.read_plan(store,data['plan_id']) if data.get('plan_id') else None
 if source and source['resume']['id']!=data['resume_id']:raise ValueError('Подтверждение относится к другому резюме.')
 saved=storage.save_evidence(store,archive,data)
 try:
  if source:
   scope={k:source[k] for k in ('mode','direction_ids','filters','goal','model','limit')};scope.update({'resume_id':data['resume_id'],'track_id':source['track']['id'],'vacancy_ids':[v['id'] for v in source['vacancies']]})
   scope.update({k:source[k] for k in ('trajectory_id','trajectory_revision','stage_id') if source.get(k) is not None})
   updated=vacancy_plan(store,archive,{**scope,'vacancy_id':scope['vacancy_ids'][0]}) if not source.get('trajectory_id') and source['mode']=='vacancies' and len(scope['vacancy_ids'])==1 else plan(store,archive,scope,remember=False)
  else:updated=plan(store,archive,{'resume_id':data['resume_id']})
 except ValueError as error:return {'evidence':saved,'plan':None,'note':str(error)}
 return {'evidence':saved,'plan':updated}

def career_path(track,evidence,priorities):
 """Evidence-based transition milestones, not an inferred employment history."""
 foundations={}
 for row in priorities:
  if row['action'] in ('validate','learn','practice'):
   for pre in row['prerequisites']:foundations.setdefault(pre['skill_id'],pre)
 stages=[{'id':'foundations','label':'Проверить и закрепить основы','tasks':list(foundations.values())},
         {'id':'target','label':'Подтвердить целевую практику','tasks':[{'skill_id':p['skill_id'],'label':p['label'],'action':p['action'],'state':p['state']} for p in priorities if p['action'] in ('validate','learn','practice')]},
         {'id':'evidence','label':'Оформить результаты для перехода','tasks':[{'skill_id':p['skill_id'],'label':p['label'],'action':p['action'],'state':p['state']} for p in priorities if p['action'] in ('document_in_cv','publish_project')]}]
 return {'from':'Текущий профиль по CV и подтверждениям','to':track['label'],'track_revision':track['revision'],'confirmed_target_skills':sum(evidence[k]['state']=='confirmed' for k in track['skills']),'target_skills':len(track['skills']),'milestones':stages,'note':'Последовательность развития компетенций, а не обещание трудоустройства. Неизвестные основы сначала проверяются; отсутствие данных не означает отсутствие навыка. Путь уточняется после новых подтверждений.'}

def telegram(plan):
 lines=['🧭 Навыки · '+plan['track']['label'],'Выборка: '+str(len(plan['vacancies']))+' вакансий из текущего персонального рейтинга. API: 0.']
 jobs={v['id']:v for v in plan['vacancies']}
 items=[p for p in plan['priorities'] if p['action']][:3]
 if not items:lines.append('Нет неподтверждённых требований выбранного трека. Расширьте выборку в карьерной карте; отсутствие рекомендаций не доказывает полную квалификацию.')
 for i,p in enumerate(items,1):
  lines+=['',str(i)+'. '+p['label']+' — '+p['action_label'],p['state_label']+' · вакансий: '+str(p['vacancy_count'])]
  if p['prerequisites']:lines.append('Сначала: '+', '.join(s['label']+' ('+ACTION_LABELS[s['action']]+')' for s in p['prerequisites'][:4]))
  if p['action'] in ('learn','practice'):
   ready=[r for r in p['resources'] if not r['blocked']]
   lines.append('Ресурс: '+ready[0]['url'] if ready else 'Ресурс следующего уровня — после проверки предпосылок.')
  req=p['requirements'][0];j=jobs[req['vacancy_id']]
  lines+=['Основание: '+j['title'][:90], '«'+req['quote'][:150]+'»',j['url']]
 lines+=['','Подробный план, цитаты и подтверждение опыта: веб → Карьерная аналитика → Навыки. Недостаток данных ≠ отсутствие навыка.']
 return '\n'.join(lines)[:3800]

def track_from_text(text,tracks):
 value=text.lower()
 for t in tracks:
  if any(re.search(r'(?<!\w)'+re.escape(alias.lower())+r'(?!\w)',value) for alias in [t['label'],t['id'],*t.get('aliases',[])]):return t['id']
 return None

def vacancy_plan(store,archive,data):
 """One explicit vacancy, independent of embeddings and saved map selection."""
 if not isinstance(data.get('vacancy_id'),str) or not data['vacancy_id']:raise ValueError('Выберите вакансию.')
 return plan(store,archive,{'resume_id':data.get('resume_id'),'goal':data.get('goal',''),'model':data.get('model','text-embedding-3-small'),'mode':'vacancies','vacancy_ids':[data['vacancy_id']],'direction_ids':[],'filters':{},'limit':1},remember=False,vacancy_id=data['vacancy_id'])
