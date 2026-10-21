'use strict';
const $=id=>document.getElementById(id),make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const date=value=>value?new Date(value).toLocaleString('ru-RU'):'не указано';
let tab='today',offset=0,eventOffset=0,selection=null,listRequest=0,detailRequest=0,summaryData=null,searchTimer,historyOffset=0,historyRequest=0,historyDetailRequest=0,companyOptions=[];
const companyPicker=CompanyPicker.create({container:$('companyFilter'),list:$('companyOptions'),search:$('companySearch'),summary:$('companySummary'),selected:$('companySelected'),onChange:()=>loadList(true).catch(e=>notice(e.message))});
const labels={added:'Добавлена запись',changed:'Изменён текст',closed:'Закрытие подтверждено на HH',reopened:'Позиция снова активна',missing:'Не найдена при полном сборе',returned:'Снова найдена'};
let lastDiagnostic;
function notice(text){$('notice').textContent=text;if(lastDiagnostic?.message===text)showDiagnostic(lastDiagnostic,'Не удалось завершить операцию');}
function showDiagnostic(error,operation='Работа веб-сервиса',target=$('notice')){
 const e=error instanceof Error?error:new Error(String(error));lastDiagnostic=e;for(const old of [...target.querySelectorAll('.diagnostic')].slice(0,-3))old.remove();const box=make('section','diagnostic');box.setAttribute('role','alert');
 const safe=value=>String(value||'').replace(/([?&#](?:token|code|connect|key|authorization)=)[^\s&#]*/gi,'$1[скрыто]').replace(/(Bearer\s+)\S+/gi,'$1[скрыто]');
 e.message=safe(e.message);box.append(make('p','',operation+': '+e.message));const details=make('details');details.append(make('summary','','Техническая диагностика'));
 const report=JSON.stringify({operation,message:safe(e.message),endpoint:e.endpoint,status:e.status,request_id:e.diagnosticId,type:e.name,stack:safe(e.stack),time:new Date().toISOString()},null,2);
 details.append(make('pre','',report));const copy=make('button','secondary','Скопировать диагностику');copy.onclick=async()=>{try{await navigator.clipboard.writeText(report);copy.textContent='Скопировано';}catch{copy.textContent='Выделите текст диагностики для копирования';}};details.append(copy);box.append(details);target.append(box);
}
async function api(path,body,timeout=30000){
 const endpoint='/archive/'+path.split('?')[0];let response;
 try{
  response=await fetch('/archive/'+path,{credentials:'same-origin',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(timeout)});
  let data;try{data=await response.json();}catch{throw new Error('Сервис вернул ответ, который не является JSON.');}
  if(!response.ok){if(response.status===401){$('login').hidden=false;$('app').hidden=true;}throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||'Не удалось прочитать локальный архив.'));}return data;
 }catch(original){const e=original instanceof Error?original:new Error(String(original));e.endpoint=endpoint;e.status=response?.status;e.diagnosticId=response?.headers.get('X-Career-Request-Id');if(e.name==='TimeoutError')e.message='Сервис не ответил за '+Math.round(timeout/1000)+' секунд. Проверьте состояние задачи перед повторным запуском.';showDiagnostic(e,'Запрос к сервису');throw e;}
}
const manualApplicationState=new Map();
function manualApplicationButton(row,onChanged){
 const id=row.id,initial=row.manual_application||{marked:false,revision:0};manualApplicationState.set(id,initial);
 const b=make('button','secondary manualApplication');b.type='button';b.dataset.manualVacancy=id;
 const render=()=>{const state=manualApplicationState.get(id);b.textContent=state.marked?'✓ Отклик сделан · отменить':'Отклик сделан';b.setAttribute('aria-pressed',String(state.marked));b.title=state.marked?'Отмечено вами '+date(state.marked_at)+'. Нажмите, чтобы отменить только ручную отметку.':'Отметить, что вы уже откликнулись. Ничего не отправляет работодателю.';};render();
 b.onclick=async event=>{event.stopPropagation();b.disabled=true;try{const state=manualApplicationState.get(id),updated=await api('workflow',{op:'manual_application',vacancy_id:id,marked:!state.marked,revision:state.revision});manualApplicationState.set(id,updated);for(const item of document.querySelectorAll('[data-manual-vacancy]'))if(item.dataset.manualVacancy===id){item.textContent=updated.marked?'✓ Отклик сделан · отменить':'Отклик сделан';item.setAttribute('aria-pressed',String(updated.marked));}notice(updated.marked?'Отклик отмечен вами. Эта вакансия исключена из подборки без откликов.':'Ручная отметка снята. Подтверждённые статусы площадки сохранены.');if(onChanged)await onChanged(updated);}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;
}
function external(url,label){const a=make('a','',label);try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))return make('span','muted',label);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}catch{return make('span','muted',label);}return a;}
function applicationEntry(job){
 const prior=job.application,entry=make('button','',prior?.id?'Продолжить отклик →':'Подготовить отклик →');entry.type='button';
 if(job.availability==='closed'){entry.disabled=true;entry.textContent='Вакансия закрыта';return entry;}
 if(!prior?.id&&(job.manual_application?.marked||prior&&['submitted','viewed','invited','rejected','withdrawn','completed'].includes(prior.status))){entry.disabled=true;entry.textContent='Отклик уже сделан';return entry;}
 entry.onclick=async()=>{entry.disabled=true;try{if(prior?.id){setTab('applications');await Flow.enter(prior.id);}else if(job.payload?.description_quality!=='full'){const task=await api('workflow',{op:'collect_one',url:job.payload.link});notice('Чтение полного описания в очереди сбора. После завершения обновите карточку и подготовьте отклик.');}else await Flow.create(job);}catch(e){notice(e.message);}finally{entry.disabled=false;}};return entry;
}
const embeddingLabels={generated:'Embeddings рассчитаны',not_generated:'Embeddings не рассчитаны',stale:'Embeddings требуют обновления',partial:'Embeddings частично рассчитаны',needs_description:'Embeddings: нужно полное описание'};
function analysisParams(){return new URLSearchParams({resume_id:$('analysisCV').value,goal:tab==='ranking'?$('rankingGoal').value:summaryData?.goal||'',model:$('embeddingModel').value});}
function tags(row){
 const div=make('div','tags');
 if(row.kind==='vacancy')div.append(make('span','tag '+row.availability,row.availability==='closed'?'Закрыта на HH':row.availability==='active'?'Проверена на странице':'Активность не проверена'));
 if(row.quality==='full')div.append(make('span','tag tagTechnical','Полное описание'));
 if(row.kind==='vacancy'&&row.quality&&row.quality!=='full')div.append(make('span','tag missing',row.quality==='needs_review'?'Текст требует проверки':'Краткая карточка'));
 if(row.missing_scopes)div.append(make('span','tag missing','Не найдена в одном из поисков'));
 if(row.versions>1)div.append(make('span','tag version tagTechnical',row.versions+' версий'));
 if(row.embedding){const badge=make('span','tag '+(row.embedding.status==='generated'?'active tagTechnical':'missing'),embeddingLabels[row.embedding.status]);badge.title=row.embedding.model+' · фрагментов '+row.embedding.chunks_ready+'/'+row.embedding.chunks_total;div.append(badge);}
 if(row.ranking)div.append(make('span','tag version','Близость '+row.ranking.score.toFixed(3)));
 if(row.ranking_stale)div.append(make('span','tag missing','Рейтинг требует обновления'));
 if(row.manual_application?.marked)div.append(make('span','tag active tagManual','Отклик сделан · отмечено вами'));
 if(row.application)div.append(make('span','tag active',({'queued':'Отклик подготовлен','active':'Диалог с рекрутером','completed':'Диалог завершён','submitted':'Отклик отправлен','paused':'Диалог на паузе'})[row.application.status]||'Есть отклик · '+row.application.status));
 return div;
}
async function reload(){
 summaryData=await api('summary');if(new URL(location.href).searchParams.has('goal'))summaryData.goal=new URL(location.href).searchParams.get('goal');$('statJobs').textContent=summaryData.vacancies;$('statFull').textContent=summaryData.full_descriptions;$('statClosed').textContent=summaryData.closed;$('statMissing').textContent=summaryData.missing_in_search;
 $('navJobs').textContent=summaryData.vacancies;$('navResumes').textContent=summaryData.resumes;$('lastSync').textContent='Последняя синхронизация: '+date(summaryData.last_sync);
 const selected=$('analysisCV').value||new URL(location.href).searchParams.get('resume_id'),resumes=await api('entities?kind=resume&limit=200');
 const placeholder=make('option','','Выберите CV');placeholder.value='';$('analysisCV').replaceChildren(placeholder);
 for(const row of resumes.items){const option=make('option','',row.title);option.value=row.id;$('analysisCV').append(option);}
 if(selected&&resumes.items.some(r=>r.id===selected))$('analysisCV').value=selected;
 else if(summaryData.primary_id&&resumes.items.some(r=>r.id===summaryData.primary_id))$('analysisCV').value=summaryData.primary_id;
 else $('analysisCV').selectedIndex=resumes.items.length?1:0;
 if(!$('rankingGoal').dataset.edited)$('rankingGoal').value=summaryData.goal||'';
 const companies=await api('companies');companyOptions=companies.items;fillCompanies();
 const historyCV=$('historyResume').value,allCV=make('option','','Все резюме');allCV.value='';$('historyResume').replaceChildren(allCV);for(const row of resumes.items){const option=make('option','',row.title);option.value=row.id;$('historyResume').append(option);}$('historyResume').value=historyCV;
 if(tab==='learning'){await CareerSkills.enterPage();return;}if(tab==='analytics'){await CareerAnalytics.enter();return;}if(tab==='about')return;else if(tab==='settings')await CompanySettings.enter();else if(tab==='today')await Journey.enter();else if(tab==='applications')await Flow.enter(chosenApplication());else if(tab==='reviews')await loadReviews(true);else if(tab==='changes')await loadChanges(true);else{await loadList(true);if(selection){const [kind,...id]=selection.split(':');await openDetail(kind,id.join(':'));}if(tab==='resume')await ResumeCompare.openRequested();}
}
async function loadList(reset=false){
 const request=++listRequest;if(reset){offset=0;$('list').replaceChildren();}
 const params=new URLSearchParams({...Object.fromEntries(analysisParams()),kind:tab==='ranking'?'vacancy':tab,...(companyPicker.value===null?{}:{companies:JSON.stringify(companyPicker.value)}),ranked_only:String(tab==='ranking'),exclude_closed:String(tab==='ranking'),q:$('search').value,status:tab==='resume'&&$('filter').value!=='missing'?'':$('filter').value,offset:String(offset),limit:'50'});
 const data=await api('entities?'+params);if(request!==listRequest)return;
 let rankPosition=offset;for(const row of data.items){
  const button=make('button','record'+(selection===row.kind+':'+row.id?' selected':''));button.dataset.key=row.kind+':'+row.id;button.title=[row.title,row.company,row.quality==='full'?'Полное описание':'',row.embedding?embeddingLabels[row.embedding.status]:'',row.versions>1?row.versions+' версий':''].filter(Boolean).join(' · ');button.append(make('h3','',tab==='ranking'?(++rankPosition)+'. '+row.title:row.title),make('p','company',row.kind==='resume'?'Сохранённое резюме':row.company||'Компания не указана'),tags(row));button.onclick=()=>openDetail(row.kind,row.id).catch(e=>notice(e.message));if(row.kind==='vacancy'){const card=make('article','recordCard');card.dataset.key=row.kind+':'+row.id;const quick=make('div','recordQuick');quick.append(manualApplicationButton(row,async()=>{if(selection==='vacancy:'+row.id)await openDetail('vacancy',row.id);}));card.append(button,quick);$('list').append(card);}else $('list').append(button);
 }
 if(reset&&tab==='resume'&&!selection&&data.items.length){const preferred=new URL(location.href).searchParams.get('resume_id')||summaryData?.primary_id;await openDetail('resume',data.items.find(r=>r.id===preferred)?.id||data.items[0].id);}
 if(reset&&tab==='resume')await ResumeCompare.openRequested();
 offset+=data.items.length;$('more').hidden=offset>=data.total;$('listCount').textContent=`Показано ${offset} из ${data.total}`;
 if(!data.total&&tab==='ranking')$('list').append(make('p','muted','Сохранённого рейтинга для этой версии CV, цели, компании и модели нет. Выберите компанию и запустите расчёт; готовые векторы будут использованы повторно.'));
 else if(!data.total)$('list').append(make('p','muted',summaryData?.vacancies||summaryData?.resumes?'Нет записей по выбранным фильтрам.':'Откройте «Локальный архив» в расширении и выполните первую синхронизацию.'));if(reset&&globalThis.VacancyMap)VacancyMap.refresh();
}
function setTab(value){
 document.documentElement.dataset.workspaceView=value;
 if(typeof window!=='undefined')window.scrollTo?.({top:0,behavior:'auto'});
 $('analytics').hidden=value!=='analytics';$('learning').hidden=value!=='learning';
 if(value==='learning'){tab=value;selection=null;detailRequest++;for(const id of ['today','collection','changes','reviews','applications','settings','about'])$(id).hidden=true;document.querySelector('.stats').hidden=true;$('pageTitle').textContent='Карьерная траектория';$('pageHint').textContent='Цель, этапы перехода и подтверждённые результаты.';const u=new URL(location.href);u.searchParams.set('view','learning');u.searchParams.delete('application');u.searchParams.delete('compare');history.replaceState(null,'',u.pathname+u.search);document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));CareerSkills.enterPage().catch(e=>showDiagnostic(e,'Навыки и обучение',$('learning')));return;}

 if(value==='analytics'){tab=value;selection=null;detailRequest++;for(const id of ['today','collection','changes','reviews','applications','settings','about'])$(id).hidden=true;document.querySelector('.stats').hidden=true;$('pageTitle').textContent='Карта возможностей';$('pageHint').textContent='От наблюдаемого рынка к вашим исследованиям и откликам.';const u=new URL(location.href);u.searchParams.set('view','analytics');u.searchParams.delete('application');history.replaceState(null,'',u.pathname+u.search);document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));CareerAnalytics.enter().catch(e=>notice(e.message));return;}

 if($('vacancySelection'))$('vacancySelection').hidden=!['vacancy','ranking'].includes(value);
 for(const id of ['resumeIntake','resumeSources','resumeCompare'])if($(id))$(id).hidden=value!=='resume';
 $('vacancyIntake').hidden=value!=='vacancy';if($('vacancyMap'))$('vacancyMap').hidden=value!=='vacancy';
 document.querySelectorAll('.resumeReading').forEach(el=>el.classList.remove('resumeReading'));
 const navigationURL=new URL(location.href);navigationURL.searchParams.set('view',value);if(value!=='applications')navigationURL.searchParams.delete('application');history.replaceState(null,'',navigationURL.pathname+navigationURL.search);
 $('about').hidden=value!=='about';
 if(value==='about'){tab=value;selection=null;for(const id of ['today','collection','changes','reviews','applications','settings'])$(id).hidden=true;document.querySelector('.stats').hidden=true;$('pageTitle').textContent='О сервисе';$('pageHint').textContent='Руководство, возможности и устройство «Рабочего поиска».';document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));return;}

 $('settings').hidden=value!=='settings';
 if(value==='settings'){tab=value;selection=null;for(const id of ['today','collection','changes','reviews','applications'])$(id).hidden=true;document.querySelector('.stats').hidden=true;$('pageTitle').textContent='Настройки';$('pageHint').textContent='Данные для автозаполнения, приоритеты компаний и адаптеры Chrome.';document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));CompanySettings.enter().catch(e=>notice(e.message));return;}

 if(value!=='applications'&&new URL(location.href).searchParams.has('application')){const u=new URL(location.href);u.searchParams.delete('application');history.replaceState(null,'',u.pathname+u.search);}
 $('today').hidden=value!=='today';$('rankingIntro').hidden=value!=='ranking';
 if(value==='today'){tab=value;selection=null;$('collection').hidden=true;$('changes').hidden=true;$('reviews').hidden=true;$('applications').hidden=true;document.querySelector('.stats').hidden=true;$('pageTitle').textContent='Сегодня';$('pageHint').textContent='Один следующий шаг — всё остальное под рукой.';document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));Journey.enter().catch(e=>notice(e.message));return;}
 document.querySelector('.stats').hidden=['applications','resume','vacancy','ranking'].includes(value);$('applications').hidden=value!=='applications';
 if(value==='applications'){tab=value;selection=null;$('collection').hidden=true;$('changes').hidden=true;$('reviews').hidden=true;$('pageTitle').textContent='Отклики';$('pageHint').textContent='Продолжайте с текущего этапа. Отправка — после вашей проверки.';document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));Flow.enter(new URL(location.href).searchParams.get('application')).catch(e=>notice(e.message));return;}
 tab=value;selection=null;detailRequest++;historyDetailRequest++;historyRequest++;if(value==='reviews'){
  $('pageTitle').textContent='История разборов вакансий (для выбранных CV)';$('pageHint').textContent='Каждый вывод связан с версиями CV и вакансии.';$('collection').hidden=true;$('changes').hidden=true;$('reviews').hidden=false;document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));loadReviews(true).catch(e=>notice(e.message));return;
 }$('reviews').hidden=true;$('pageTitle').textContent=value==='resume'?'Резюме':value==='changes'?'Изменения':value==='ranking'?'Рейтинг по резюме':'Вакансии';$('pageHint').textContent=value==='resume'?'Профессиональный профиль и история его развития.':value==='changes'?'Что появилось, изменилось и перестало встречаться.':'От находки до осмысленного отклика.';
 $('collection').hidden=value==='changes';$('changes').hidden=value!=='changes';document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));
 $('search').value='';$('filter').value=['vacancy','ranking'].includes(value)?'full':'';for(const id of ['embeddingModel','analysisCV'])$(id).parentElement.hidden=!['vacancy','ranking'].includes(value);
 $('companyFilter').hidden=!['vacancy','ranking'].includes(value);document.querySelector('.collectionFieldLabel').textContent=value==='resume'?'Поиск резюме':'Поиск вакансий';$('search').placeholder=value==='resume'?'Название или текст резюме…':'Компания, роль или технология…';
 $('detail').className='detail empty';$('detail').replaceChildren(make('span','emptyIcon','↗'),make('h2','',value==='resume'?'Выберите резюме':'Выберите вакансию'),make('p','','Полный текст, история версий и сравнение изменений.'));
 (value==='changes'?loadChanges(true):loadList(true)).catch(e=>notice(e.message));
}
async function openDetail(kind,id){
 const request=++detailRequest,data=await api('entity/'+kind+'/'+encodeURIComponent(id)+'?'+analysisParams());if(request!==detailRequest)return;
 document.querySelectorAll('.resumeReading').forEach(el=>el.classList.remove('resumeReading'));selection=kind+':'+id;if(kind==='resume'){const u=new URL(location.href);u.searchParams.set('resume_id',id);window.history.replaceState(null,'',u.pathname+u.search);}for(const item of $('list').children)item.classList.toggle('selected',item.dataset.key===selection);const panel=$('detail');panel.className='detail'+(kind==='vacancy'?' vacancyReader':'');panel.replaceChildren();
 panel.append(make('p','eyebrow',kind==='resume'?'РЕЗЮМЕ · СОХРАНЁННАЯ ВЕРСИЯ':data.payload.company||'ВАКАНСИЯ'),make('h2','',data.title),tags({...data,versions:data.versions.length,missing_scopes:data.membership.filter(m=>!m.present).length,quality:data.payload.description_quality}));
 const actions=make('div','detailActions'),url=kind==='resume'?data.payload.source_url:data.payload.link;if(kind==='vacancy'){const primary=applicationEntry(data);if(!primary.disabled)actions.append(primary);}if(url)actions.append(external(url,'Открыть источник ↗'));if(kind==='vacancy'){const more=make('details','vacancyActionMenu'),mark=manualApplicationButton(data,()=>openDetail(kind,id));mark.textContent=data.manual_application?.marked?'Снять ручную отметку отклика':'Отметить, что отклик уже сделан';more.append(make('summary','','Ещё'),mark);if(data.payload.description_quality==='full'){const path=make('button','secondary','Построить траекторию под вакансию');path.onclick=()=>CareerTrajectory.fromVacancy(data.id);more.append(path);}actions.append(more);}panel.append(actions);if(kind==='vacancy'&&data.payload.description_quality==='needs_review'){const confirm=make('button','secondary','Я проверил текст: описание полное');actions.append(confirm);confirm.onclick=async()=>{confirm.disabled=true;try{await api('confirm-description',{vacancy_id:data.id,content_hash:data.content_hash});await openDetail(kind,id);loadList(true).catch(e=>notice(e.message));}catch(e){notice(e.message);confirm.disabled=false;}};panel.append(make('p','muted','Сначала сравните сохранённый текст с оригиналом вакансии. Подтверждайте полноту после проверки требований и обязанностей.'));}
 panel.append(make('p','meta',`Источник проверен: ${date(data.source_at)}\nВ архиве с: ${date(data.first_seen)} · Синхронизация: ${date(data.last_seen)}`));
 if(data.payload.collector)panel.append(make('p','meta','Сбор: '+({chrome_extension:'Chrome Extension',playwright:'Playwright'})[data.payload.collector]+' · адаптер '+data.payload.adapter_id+' · '+data.payload.adapter_version));
 if(data.embedding)panel.append(make('p','meta',data.embedding.model+' · фрагментов '+data.embedding.chunks_ready+' из '+data.embedding.chunks_total));
 if(data.ranking)panel.append(make('p','meta','Сохранённый рейтинг: '+date(data.ranking.generated_at)+' · близость '+data.ranking.score.toFixed(3)+' · '+data.ranking.model+'\nСемантическая близость, не процент соответствия. Цель: '+(data.ranking.goal||'не указана')));
 if(kind==='vacancy'){buildAnalysis(panel,data);if(data.payload.description_quality==='full'){const selectedCV=$('analysisCV').value;SkillAnalysis.attach(panel,{api,onHistory:()=>setTab('reviews'),context:{resume_id:selectedCV,vacancy_id:data.id,goal:tab==='ranking'?$('rankingGoal').value:summaryData.goal||''},isCurrent:()=>request===detailRequest&&$('analysisCV').value===selectedCV});}}
 if(kind==='resume'){const provenance=make('details');provenance.append(make('summary','','Источник, синхронизация и embeddings'));provenance.append(...panel.children);ResumeProfile.render(panel,data,{api,goal:summaryData?.goal||'',isCurrent:()=>request===detailRequest&&tab==='resume'});panel.append(provenance);}
 const content=make('details'),contentTitle=make('summary','',kind==='vacancy'&&data.payload.description_quality!=='full'?'Сохранённый фрагмент · полного описания ещё нет':'Полный сохранённый текст');content.open=kind!=='resume';content.append(contentTitle);if(kind==='vacancy'&&globalThis.VacancyDocument)VacancyDocument.render(content,data);else content.append(make('div','text',data.text));panel.append(content);
 const history=make('details');history.append(make('summary','','История и сравнение версий · '+data.versions.length));
 if(data.versions.length>1){
  const controls=make('div','diffControls'),before=make('select'),after=make('select'),run=make('button','','Показать изменения'),output=make('div','diffText');before.setAttribute('aria-label','Предыдущая версия');after.setAttribute('aria-label','Следующая версия');
  for(const version of data.versions){for(const select of [before,after]){const option=make('option','',date(version.source_at)+' · #'+version.id);option.value=String(version.id);select.append(option);}}
  after.value=String(data.version_id);const previous=data.versions.find(v=>v.id!==data.version_id&&v.source_at<=data.source_at);before.value=String(previous?.id||data.versions.find(v=>v.id!==data.version_id).id);
  run.onclick=async()=>{run.disabled=true;try{const diff=await api('diff?'+new URLSearchParams({kind,id,before:before.value,after:after.value}));output.replaceChildren(...diff.segments.map(s=>make(s.type==='insert'?'ins':s.type==='delete'?'del':'span','',s.text)));}catch(e){notice(e.message);}finally{run.disabled=false;}};
  controls.append(before,after,run);history.append(make('p','muted','Зелёным выделено добавленное, красным — удалённое. Даты относятся к снимкам источника.'),controls,output);
 }else history.append(make('p','muted','Это первая сохранённая версия. Сравнение появится после следующего изменения текста.'));
 panel.append(history);
 if(data.membership.length){const sightings=make('details');sightings.append(make('summary','','Где встречалась запись'));
  for(const item of data.membership){const box=make('div','scope');box.append(make('strong','',item.present?'Найдена в этом источнике':'Не найдена при полном сборе этого источника'),make('p','',date(item.checked_at)),external(item.scope,'Открыть исходный поиск HH ↗'));sightings.append(box);}panel.append(sightings);
 }
 if(kind==='vacancy'){vacancyReader(panel,content);if(data.payload.description_quality==='full')CareerSkills.mountVacancy(content,{resume_id:$('analysisCV').value,vacancy_id:data.id,goal:tab==='ranking'?$('rankingGoal').value:summaryData.goal||'',model:$('embeddingModel').value},()=>request===detailRequest);}
}
function vacancyReader(panel,content){
 const header=make('div','vacancyReaderHeader'),nav=make('div','vacancyReaderTabs'),body=make('div','vacancyReaderBody'),reading=make('section','vacancyReaderPage'),analysis=make('section','vacancyReaderPage'),sources=make('section','vacancyReaderPage');
 const children=[...panel.children];for(const child of children){if(child===content)reading.append(child);else if(child.matches('.analysis,.skillAnalysis'))analysis.append(child);else if(child.matches('.meta,details'))sources.append(child);else header.append(child);}
 const bar=make('div','vacancyReaderControls'),toggle=make('button','secondary');toggle.type='button';const workspace=panel.closest('.workspace');const setList=hidden=>{workspace.classList.toggle('vacancyListHidden',hidden);toggle.textContent=hidden?'Показать список вакансий':'Скрыть список вакансий';toggle.setAttribute('aria-expanded',String(!hidden));try{localStorage.setItem('vacancy-list-hidden',String(hidden));}catch{}};let hidden=false;try{hidden=localStorage.getItem('vacancy-list-hidden')==='true';}catch{}setList(hidden);toggle.onclick=()=>setList(!workspace.classList.contains('vacancyListHidden'));bar.append(toggle);
 const buttons=[];nav.setAttribute('role','tablist');nav.setAttribute('aria-label','Карточка вакансии');for(const [i,label,page] of [[0,'Описание',reading],[1,'Соответствие CV',analysis],[2,'Источники и версии',sources]]){const b=make('button','secondary',label);b.type='button';b.id='vacancy-reader-tab-'+i;b.setAttribute('role','tab');page.id='vacancy-reader-page-'+i;page.setAttribute('role','tabpanel');page.setAttribute('aria-labelledby',b.id);b.setAttribute('aria-controls',page.id);buttons.push(b);nav.append(b);body.append(page);b.onclick=()=>select(i);b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;select(next);buttons[next].focus();}};}function select(index){for(const [i,page] of [reading,analysis,sources].entries()){page.hidden=i!==index;buttons[i].setAttribute('aria-selected',String(i===index));buttons[i].tabIndex=i===index?0:-1;}}
 panel.replaceChildren(bar,header,nav,body);select(0);
}
function buildAnalysis(panel,job){
 const section=make('section','analysis'),actions=make('div','actions'),compare=make('button','','Сравнить с выбранным CV'),copy=make('button','secondary','Скопировать CV + вакансию для ChatGPT'),output=make('div'),preview=make('textarea');preview.hidden=true;preview.readOnly=true;preview.rows=12;preview.setAttribute('aria-label','Пакет для ChatGPT');
 section.append(make('h3','','Сверка с выбранным резюме'),make('p','muted','Упоминания технологий и контекст для анализа. Подготовить письмо можно основной кнопкой вверху карточки.'),actions,output,preview);actions.append(compare,copy);panel.append(section);
 if(job.payload.description_quality!=='full'){compare.disabled=true;copy.disabled=true;output.append(make('p','muted','Для анализа сначала загрузите полное описание через расширение.'));}
 compare.onclick=async()=>{if(!$('analysisCV').value){notice('Выберите CV над списком.');return;}compare.disabled=true;
  try{const result=await api('compare',{resume_id:$('analysisCV').value,vacancy_id:job.id});output.replaceChildren(make('p','muted',result.note));const table=make('table'),head=make('tr');head.append(make('th','','Термин вакансии'),make('th','','Выбранный CV'));table.append(head);
   for(const item of result.items){const row=make('tr'),cell=make('td');cell.append(make('span','tag '+(item.mentioned_in_cv?'active':'missing'),item.mentioned_in_cv?'Упоминается':'Не подтверждено в CV'));if(item.cv_excerpt)cell.append(make('blockquote','',item.cv_excerpt));row.append(make('td','',item.skill),cell);table.append(row);}output.append(table);if(!result.items.length)output.append(make('p','muted','Словарь не выявил терминов. Это не оценка соответствия: используйте полный текст и анализ в ChatGPT.'));
  }catch(e){notice(e.message);}finally{compare.disabled=false;}
 };
 copy.onclick=async()=>{if(!$('analysisCV').value){notice('Выберите CV над списком.');return;}copy.disabled=true;
  try{const resume=await api('entity/resume/'+encodeURIComponent($('analysisCV').value)),data=resume.payload;
   const packet=ChatGPTExport.buildPackage({ranking:{resume_id:resume.id,resume_hash:data.content_hash||resume.content_hash,goal:tab==='ranking'?$('rankingGoal').value:summaryData.goal||''},bundle:{resumes:[{...data,content_hash:data.content_hash||resume.content_hash}]},vacancies:[job.payload],jobId:job.id});preview.value=packet;
   try{await navigator.clipboard.writeText(packet);notice('CV, полная вакансия и промпт скопированы. Вставьте в ChatGPT App.');}catch{preview.hidden=false;preview.focus();preview.select();notice('Пакет выделен. Нажмите Cmd+C / Ctrl+C.');}
  }catch(e){notice(e.message);}finally{copy.disabled=false;}
 };
}
async function loadReviews(reset=false){
 const request=++historyRequest;if(reset){historyOffset=0;$('historyList').replaceChildren();}
 const data=await api('skill-history?'+new URLSearchParams({resume_id:$('historyResume').value,offset:historyOffset}));if(request!==historyRequest||tab!=='reviews')return;
 for(const item of data.items){const button=make('button','record');button.append(make('p','eyebrow',date(item.created_at)+' · '+item.model),make('h3','',item.vacancy_title),make('p','company',item.company||''),make('p','',item.resume_title),make('p','meta',`CV #${item.resume_version_id??'?'} · вакансия #${item.vacancy_version_id??'?'} · покрытие ${item.metrics.overall.percent??'—'}%`),make('p','muted','Цель: '+(item.goal||'не указана')));button.onclick=()=>openReview(item.key).catch(e=>notice(e.message));$('historyList').append(button);}
 historyOffset+=data.items.length;$('historyCount').textContent=`Показано ${historyOffset} из ${data.total}`;$('moreReviews').hidden=historyOffset>=data.total;if(!data.total)$('historyList').append(make('p','muted','Разборов пока нет. Откройте вакансию, выберите CV и нажмите «Разобрать требования · Luna».'));
}
async function openReview(key){
 const request=++historyDetailRequest,data=await api('skill-history/'+encodeURIComponent(key));if(request!==historyDetailRequest||tab!=='reviews')return;
 const panel=$('historyDetail');panel.className='detail';panel.replaceChildren(make('p','eyebrow','СОХРАНЁННЫЙ РАЗБОР · БЕЗ ВЫЗОВА API'),make('h2','',data.sources.vacancy.payload?.title||data.sources.vacancy.id),make('p','meta',date(data.analysis.created_at)+' · '+data.analysis.model+' · '+data.analysis.prompt_version),make('p','','Цель: '+(data.analysis.goal||'не указана')));
 for(const [kind,label] of [['resume','Резюме'],['vacancy','Вакансия']]){const source=data.sources[kind],box=make('details','analysisSource');box.append(make('summary','',label+' · версия #'+(source.version_id??'?')+' · '+(source.matches_current?'текст совпадает с текущим':'сохранённый исторический текст')));box.append(make('p','',source.payload?.title||source.id),make('p','meta','Снимок источника: '+date(source.source_at)),make('p','meta','SHA-256 текста для Luna: '+source.text_hash));const url=source.payload?.source_url||source.payload?.link;if(url)box.append(external(url,'Открыть текущий оригинал ↗'));box.append(make('div','text',source.text??'Исходная версия старого разбора не найдена. Не подменяем её актуальным текстом.'));panel.append(box);}
 const output=make('section');SkillAnalysis.render(data.analysis,output);panel.append(output);
}
async function loadChanges(reset=false){
 if(reset){eventOffset=0;$('events').replaceChildren();}
 const result=await api('events?offset='+eventOffset);eventOffset+=result.items.length;$('moreEvents').hidden=result.items.length<100;
 for(const event of result.items){const row=make('article','timelineRow'),body=make('div'),open=make('button','secondary','Открыть');body.append(make('h3','',(labels[event.event]||event.event)+' · '+(event.title||event.entity_id)));if(event.details.scope)body.append(make('p','',event.details.scope));if(event.company)body.append(make('p','',event.company));
  open.onclick=async()=>{setTab(event.kind);try{await openDetail(event.kind,event.entity_id);}catch(e){notice(e.message);}};row.append(make('time','',date(event.at)),body,open);$('events').append(row);
 }
 if(!eventOffset)$('events').append(make('p','muted','Исходный набор сохранён. Изменений после первой синхронизации пока нет; прошлые версии появятся при следующих сборах.'));
 if(reset){const history=await api('rankings');$('rankingHistory').replaceChildren();for(const run of history.items){const item=make('div','scanRow');item.append(make('strong','',run.resume_title||run.resume_id),make('p','',date(run.generated_at)+' · '+run.model+' · вакансий '+run.all.length),make('p','muted','Цель: '+(run.goal||'не указана')));$('rankingHistory').append(item);}if(!history.items.length)$('rankingHistory').append(make('p','muted','Синхронизируйте сохранённый рейтинг через расширение.'));const data=await api('scans');$('scans').replaceChildren();for(const scan of data.items){const row=make('div','scanRow');row.append(make('strong','',scan.kind==='resume'?'Каталог резюме':'Поиск вакансий'),make('span','tag '+(scan.complete?'active':'missing'),scan.complete?'Полный сбор':'Частичное наблюдение'),make('p','',date(scan.completed_at)+' · записей '+(scan.payload.ids||[]).length+' · страниц '+(scan.payload.pages||0)),external(scan.scope,scan.kind==='resume'?'Открыть каталог резюме HH ↗':'Открыть исходный поиск HH ↗'));if(!scan.complete)row.append(make('p','muted','Отсутствие записей в этом запуске не используется для вывода об исчезновении.'));if(scan.payload.error)row.append(make('p','muted',scan.payload.error));$('scans').append(row);}}
}
async function start(){
 const hash=new URLSearchParams(location.hash.slice(1)),code=hash.get('connect');if(code){history.replaceState(null,'',location.pathname+location.search);await api('login',{code});}
 await reload();const requested=new URL(location.href).searchParams.get('view');if(chosenApplication())setTab('applications');else if(['learning','analytics','about','settings','vacancy','ranking','resume','reviews','changes','applications'].includes(requested))setTab(requested);$('login').hidden=true;$('app').hidden=false;notice('');
}
$('connect').onclick=async()=>{const token=$('token').value.trim();try{const response=await fetch('/archive/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Resume-Import-Token':token},body:'{}'});const data=await response.json();$('token').value='';if(!response.ok)throw new Error(data.detail);await start();}catch(e){$('loginStatus').textContent=e.message;}};
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>setTab(button.dataset.tab));
$('historyResume').onchange=()=>loadReviews(true).catch(e=>notice(e.message));$('moreReviews').onclick=()=>loadReviews().catch(e=>notice(e.message));
$('refresh').onclick=()=>reload().catch(e=>notice(e.message));$('more').onclick=()=>loadList().catch(e=>notice(e.message));$('moreEvents').onclick=()=>loadChanges().catch(e=>notice(e.message));
$('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadList(true).catch(e=>notice(e.message)),250);};$('filter').onchange=()=>loadList(true).catch(e=>notice(e.message));
$('analysisCV').onchange=$('embeddingModel').onchange=()=>{loadList(true).catch(e=>notice(e.message));if(selection?.startsWith('vacancy:'))openDetail('vacancy',selection.slice(8)).catch(e=>notice(e.message));};
$('backup').onclick=async()=>{try{const data=await api('export'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),link=make('a');link.href=url;link.download='cv-matcher-archive-'+new Date().toISOString().slice(0,10)+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notice(e.message);}};
start().catch(e=>{if(e.status===401){$('loginStatus').textContent=e.message;$('login').hidden=false;}else{$('app').hidden=false;showDiagnostic(e,'Загрузка интерфейса');}});
window.addEventListener('error',event=>{if(event.error)showDiagnostic(event.error,'Ошибка интерфейса');else if(event.target?.tagName==='SCRIPT')showDiagnostic(new Error('Не загружен скрипт '+new URL(event.target.src).pathname),'Загрузка компонентов');},true);
window.addEventListener('unhandledrejection',event=>showDiagnostic(event.reason,'Незавершённая операция интерфейса'));

function chosenApplication(){return new URL(location.href).searchParams.get("application")||null;}


$('rankingGoal').oninput=()=>{$('rankingGoal').dataset.edited='true';$('rankingStatus').textContent='Цель изменена. Показываю только сохранённый рейтинг для новой цели.';detailRequest++;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{loadList(true).catch(e=>notice(e.message));if(selection?.startsWith('vacancy:'))openDetail('vacancy',selection.slice(8)).catch(e=>notice(e.message));},250);};
$('viewRanking').onclick=()=>{loadList(true).catch(e=>notice(e.message));if(selection?.startsWith('vacancy:'))openDetail('vacancy',selection.slice(8)).catch(e=>notice(e.message));};
async function calculateRanking(allowAPI){
 const b=allowAPI?$('runRanking'):$('rankOffline'),context={resume_id:$('analysisCV').value,companies:companyPicker.value,model:$('embeddingModel').value,goal:$('rankingGoal').value,allow_api:allowAPI};
 if(!context.resume_id){notice('Выберите резюме.');return;}for(const id of ['analysisCV','companyFilter','companySearch','embeddingModel','rankingGoal'])$(id).disabled=true;b.disabled=true;$('runRanking').disabled=true;$('rankOffline').disabled=true;$('rankingStatus').textContent='Сравниваю выбранный CV с вакансиями выбранных компаний. Сначала проверяю кэш…';
 try{const result=await api('rank',context,240000);$('rankingStatus').textContent='Сохранено: '+result.ranked_count+' вакансий · из кэша '+result.cache_reused+' · новых сравнений '+result.new_compared+' · API-запросов '+result.api_requests+'.';if(tab==='ranking')await loadList(true);}
 catch(e){$('rankingStatus').textContent=e.message;}finally{for(const id of ['analysisCV','companyFilter','companySearch','embeddingModel','rankingGoal'])$(id).disabled=false;$('runRanking').disabled=false;$('rankOffline').disabled=false;}
}
$('runRanking').onclick=()=>calculateRanking(true);$('rankOffline').onclick=()=>calculateRanking(false);

function fillCompanies(){companyPicker.setOptions(companyOptions);}

document.querySelectorAll('[data-about-target]').forEach(button=>button.onclick=()=>setTab(button.dataset.aboutTarget));

// Layout preferences only; no workflow or account settings are changed.
(()=>{const b=$('sidebarToggle');function apply(hidden){document.documentElement.classList.toggle('sidebarCollapsed',hidden);b.textContent=hidden?'☰ Показать меню':'☰ Скрыть меню';b.setAttribute('aria-expanded',String(!hidden));}let hidden=false;try{hidden=localStorage.getItem('workspace-sidebar-hidden')==='true';}catch{}apply(hidden);b.onclick=()=>{hidden=!document.documentElement.classList.contains('sidebarCollapsed');apply(hidden);try{localStorage.setItem('workspace-sidebar-hidden',String(hidden));}catch{}};})();
