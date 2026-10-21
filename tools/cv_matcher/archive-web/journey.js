'use strict';
const Journey=(()=>{
 const button=(label,fn,cls='secondary')=>{const b=make('button',cls,label);b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;};
 function browserIssue(note){return /Frame.*showing error page/i.test(note)?'Страница HH не загрузилась: Chrome показал страницу ошибки. Откройте служебную вкладку HH, проверьте доступ к сайту и при необходимости обновите её. Эта запись относится к прошлой попытке; текущее состояние показано выше.':'Не удалось завершить предыдущее чтение HH. Проверьте доступ к сайту в служебной вкладке; подробности сохранены ниже.';}
 function autoSync(root,status){
  if(!status)return;
  const labels={disabled:'Выключена',waiting_chrome:'Ожидает подключение HH в обновлённом расширении',queued:'Ожидает свободный Chrome',running:'Читаю страницы HH',backoff:'Пауза после ошибки',scheduled:'По расписанию'};
  const panel=make('section','journeyContext');panel.append(make('h3','','Автосинхронизация откликов HH'),make('p','',labels[status.state]||status.state),make('p','muted','Проверка каждые '+status.interval_seconds/60+' мин. Последнее успешное чтение: '+(status.last_success?date(new Date(status.last_success*1000).toISOString()):'ещё не подтверждено')+'. Chrome, расширение и сервис должны работать.'));
  if(status.last_error){const issue=make('div','todayPastIssue'),details=make('details');issue.append(make('p','todayLabel','ПОСЛЕДНЯЯ НЕУДАЧНАЯ ПОПЫТКА'+(status.last_error_at?' · '+date(new Date(status.last_error_at*1000).toISOString()):'')),make('p','',browserIssue(status.last_error)));details.append(make('summary','','Технические подробности'),make('pre','flowText',status.last_error));issue.append(details);panel.append(issue);}
  panel.append(make('p','muted','Читаем доступные страницы откликов и по очереди чаты. При первом чтении переписка сохраняется без рассылки старых сообщений. Новые сообщения и изменения статусов приходят в Telegram.'));
  panel.append(button(status.enabled?'Приостановить синхронизацию':'Включить синхронизацию',async()=>{await api('workflow',{op:'hh_auto_sync_save',config:{enabled:!status.enabled,interval_seconds:status.interval_seconds}});await enter();}),button('Обновить состояние',enter));root.append(panel);
 }
 function resumeBump(root,status,primary){
  if(!status)return;
  const panel=make('section','journeyContext'),labels={disabled:'выключено',waiting_chrome:'ожидает Chrome / расширение 0.11.18',queued:'в очереди Chrome',running:'проверяю HH',cooldown:'ждём доступность кнопки HH',scheduled:'запланировано',needs_input:'нужна ваша проверка'};
  panel.append(make('h3','','⬆️ Поднять резюме в поиске HH'),make('p','',status.enabled?'Автоподнятие включено для выбранных резюме.':'Автоподнятие выключено.'),make('p','muted','Только бесплатная кнопка «Поднять в поиске», не чаще раза в 4 часа после подтверждённого поднятия. Скрытые резюме не публикуются, платные услуги не подключаются. При сне ноутбука задача ждёт Chrome; пропущенные интервалы не накапливаются.'));
  const selected=[];
  for(const r of status.resumes){
   const row=make('div'),label=make('label'),check=make('input');check.type='checkbox';check.checked=r.selected||!status.resume_ids.length&&r.id===primary;check.style.width='auto';label.append(check,document.createTextNode(' '+r.title));row.append(label,make('p','muted',labels[r.state]+(r.last_success?' · поднято '+date(new Date(r.last_success*1000).toISOString()):'')+(r.next_at?' · проверка после '+date(new Date(r.next_at*1000).toISOString()):'')));
   if(r.note)row.append(make('p','muted',r.note));
   if(r.blocked)row.append(button('Проверил результат на HH — разрешить новую проверку',async()=>{await api('workflow',{op:'resume_bump_retry',resume_id:r.id,confirmed:true});await enter();}));
   selected.push({id:r.id,check});panel.append(row);
  }
  panel.append(button(status.enabled?'Сохранить выбранные резюме':'Разрешить бесплатное автоподнятие выбранных',async()=>{await api('workflow',{op:'resume_bump_save',config:{enabled:true,resume_ids:selected.filter(r=>r.check.checked).map(r=>r.id)},revision:status.revision,confirmed:true});await enter();}));
  if(status.enabled)panel.append(button('Приостановить автоподнятие',async()=>{await api('workflow',{op:'resume_bump_save',config:{enabled:false,resume_ids:status.resume_ids},revision:status.revision});await enter();}));
  panel.append(button('Обновить состояние',enter),external('https://hh.ru/applicant/profile/me','Проверить резюме на HH ↗'));root.append(panel);
 }
 async function agentPanel(root){
  const state=await api('agent'),panel=make('section','journeyContext');panel.append(make('h3','','Пульт агента'),make('p','muted','Задачи и контекст общие для Telegram, веба и MCP. Чтение останавливается на безопасной границе; отправленный отклик отменить здесь нельзя.'));
  const form=make('form','journeyActions'),input=make('input');input.type='text';input.maxLength=2000;input.placeholder='Найди вакансии · мои задачи · подготовь отклик hh_123';input.setAttribute('aria-label','Запрос карьерному агенту');input.style.flex='1';
  const send=make('button','','Выполнить'),reply=make('p','muted');reply.setAttribute('role','status');form.append(input,send);panel.append(form,reply);
  form.onsubmit=async e=>{e.preventDefault();if(!input.value.trim())return;send.disabled=true;const request_id=crypto.randomUUID();try{const result=await api('agent',{op:'converse',text:input.value,request_id});reply.textContent=result.message;if(result.review_url)reply.append(' ',external(result.review_url,'Открыть карточку ↗'));await showTasks();}catch(err){reply.textContent=err.message;}finally{send.disabled=false;}};
  const tasks=make('div');panel.append(tasks,button('Обновить задачи',async()=>showTasks()));root.append(panel);
  async function showTasks(items){
   const data=items||((await api('agent')).tasks);tasks.replaceChildren();
   const active=data.filter(t=>t.actions.length||t.state.endsWith('_requested')); if(!active.length){tasks.append(make('p','muted','Активных задач нет.'));return;}
   for(const task of active.slice(0,12)){
    const row=make('article','journeyApplication'),body=make('div'),controls=make('div','journeyActions');body.append(make('strong','',task.label||task.state),make('p','muted',task.next_action),make('p','muted',task.id+' · собрано '+task.progress.collected+' · ранжировано '+task.progress.ranked));
    for(const action of task.actions)controls.append(button({pause:'Пауза',resume:'Продолжить',cancel:'Отменить'}[action],async()=>{await api('agent',{op:'control_task',task_id:task.id,action,revision:task.revision});await showTasks();}));row.append(body,controls);tasks.append(row);
   }
  }
  await showTasks(state.tasks);
 }
 async function connect(){
  if(document.documentElement.dataset.cvMatcherConnected!=='true'){notice('В Chrome: значок ML Research Vacancy Search → 5. Отклик → «Подключить HH один раз». Или Chrome → Расширения → ML Research Vacancy Search → Параметры.');return;}
  const id=crypto.randomUUID();await new Promise(resolve=>{const handler=e=>{if(e.origin!==location.origin||e.source!==window||e.data?.channel!=='cv-workspace-response'||e.data.id!==id)return;window.removeEventListener('message',handler);clearTimeout(timer);if(!e.data.ok)notice('Не удалось открыть параметры. Откройте их через меню расширения в Chrome.');resolve();};const timer=setTimeout(()=>{window.removeEventListener('message',handler);notice('Откройте параметры расширения в Google Chrome.');resolve();},3000);window.addEventListener('message',handler);window.postMessage({channel:'cv-workspace-request',id,action:'open_setup'},location.origin);});
 }
 let request=0;const opened=new Set();
 function relevant(data){return (data.items||[]).filter(i=>i.resume_id===data.cv?.id);}
 function focus(data){
  const items=relevant(data),attention=items.find(i=>i.needs_attention);
  if(attention)return {title:attention.state==='uncertain'?'Проверьте результат отклика':'Отклик ждёт вашей проверки',hint:'Проверьте письмо, ответы и следующее действие перед отправкой.',label:'Открыть проверку',item:attention};
  if(!data.cv)return {title:'Начните с резюме',hint:'Выберите резюме и карьерную цель. На их основе появятся персональные рекомендации.',label:'Выбрать резюме',tab:'resume'};
  if(data.cv.quality!=='full')return {title:'Проверьте резюме',hint:'Для сравнения вакансий нужен полный и проверенный текст.',label:'Открыть резюме',tab:'resume'};
  if(!data.summary.full_descriptions)return {title:'Соберите первые вакансии',hint:'Подключите Chrome и выберите источники. Результаты сохранятся в вашем архиве.',label:'Настроить сбор',setup:true};
  if(!data.ranked)return {title:'Найдите подходящие вакансии',hint:'Описания уже собраны. Откройте рейтинг, чтобы сравнить их с выбранным резюме.',label:'Открыть рейтинг',tab:'ranking'};
  const preparation=items.find(i=>i.stage_key==='preparing'&&!['approved','sending'].includes(i.state)&&!['submitted','viewed','invited','rejected','withdrawn'].includes(i.status));
  if(preparation)return {title:'Продолжите подготовку отклика',hint:preparation.next,label:'Продолжить отклик',item:preparation};
  return {title:'Выберите следующий отклик',hint:'Сравните лучшие вакансии и выберите, куда хотите двигаться дальше.',label:'Выбрать вакансию',tab:'ranking'};
 }
 function openApplication(item){setTab('applications');return Flow.enter(item.id);}
 function disclosure(parent,key,title,hint,load){
  const box=make('details','todayDisclosure'),head=make('summary'),body=make('div','todayDisclosureBody');head.append(make('strong','',title),make('span','muted',hint));box.append(head,body);box.open=opened.has(key);let loaded=false,loading=false;
  async function reveal(){if(!box.open||loaded||loading)return;loading=true;body.textContent='Загружаю…';try{body.replaceChildren();await load(body);loaded=true;}catch(e){body.replaceChildren(make('p','muted',e.message),button('Повторить',reveal));}finally{loading=false;}}
  box.ontoggle=()=>{if(box.open)opened.add(key);else opened.delete(key);reveal();};parent.append(box);if(box.open)reveal();return box;
 }
 async function enter(){
  const n=++request,data=await api('journey');if(tab!=='today'||n!==request)return;
  const root=$('journeyContent');root.replaceChildren();root.className='todayShell';document.querySelector('.stats').hidden=true;
  const top=make('div','todayContext'),cv=make('div');cv.append(make('span','todayLabel','ФОКУС ПОИСКА'),make('strong','',data.cv?.title||'Резюме не выбрано'));top.append(cv,button('Изменить',()=>setTab('resume'),'todayTextButton'));root.append(top);
  const f=focus(data),layout=make('div','todayOverview'),hero=make('section','todayFocus');hero.append(make('p','eyebrow','СЕЙЧАС'),make('h2','',f.title));
  if(f.item)hero.append(make('h3','todayRole',f.item.title),make('p','todayCompany',f.item.company));
  hero.append(make('p','todayHint',f.hint));const actions=make('div','journeyActions');actions.append(button(f.label,()=>f.item?openApplication(f.item):f.setup?connect():setTab(f.tab),'todayPrimary'));hero.append(actions,make('p','todayFootnote','Отправка отклика — после вашего отдельного подтверждения.'));
  const summary=make('aside','todaySummary');summary.append(make('h2','','Ваш поиск'));const metrics=make('div','todayMetrics');
  for(const [count,label,dest] of [[data.summary.full_descriptions,'полных описаний','vacancy'],[data.ranked,'в сохранённом рейтинге','ranking'],[(data.items||[]).filter(i=>i.needs_attention).length,'ожидают вашей проверки','applications']]){const b=button('',()=>setTab(dest),'todayMetric');b.append(make('strong','',String(count)),make('span','',label));metrics.append(b);}summary.append(metrics);
  const connection=make('p','todayConnection');connection.append(make('span',data.browser.connected?'todayDot':'todayDot offline'),document.createTextNode(data.browser.connected?'Chrome на связи':'Chrome недоступен — задачи ждут подключения'));summary.append(connection);
  if(data.browser.queued||data.browser.running)summary.append(make('p','todayFootnote','В очереди: '+data.browser.queued+' · выполняется: '+data.browser.running));
  layout.append(hero,summary);root.append(layout);
  const queue=relevant(data).filter(i=>i.id!==f.item?.id&&!['rejected','withdrawn'].includes(i.status)).slice(0,3);
  if(data.appointments?.length){const section=make('section','todayList');section.append(make('h2','','Ближайшие встречи'));for(const item of data.appointments.slice(0,2)){const row=make('article','todayRow'),body=make('div');body.append(make('h3','',item.title+' · '+item.company),make('p','muted',CRMPlanning.when(item.start_at,item.time_zone)));row.append(body,button('Подготовиться',()=>openApplication({id:item.app_id})));section.append(row);}root.append(section);}
  if(queue.length){const section=make('section','todayList'),heading=make('div','todaySectionHeading');heading.append(make('h2','','Дальше по плану'),button('Все отклики',()=>setTab('applications'),'todayTextButton'));section.append(heading);for(const item of queue){const row=make('article','todayRow'),body=make('div');body.append(make('h3','',item.title),make('p','muted',item.company+' · '+item.next));row.append(body,button('Открыть →',()=>openApplication(item),'todayTextButton'));section.append(row);}root.append(section);}
  const shortcuts=make('nav','todayShortcuts');shortcuts.setAttribute('aria-label','Разделы поиска');shortcuts.append(button('Карта возможностей →',()=>setTab('analytics'),'todayTextButton'),external('https://t.me/baniartbot','Продолжить в Telegram ↗'));root.append(shortcuts);
  const advanced=make('section','todayTools');advanced.append(make('h2','','Управление поиском'),make('p','muted','Настройки и служебные задачи — когда они нужны.'));
  disclosure(advanced,'agent','Задачи и команды агенту',data.browser.running?'Есть выполняемые задачи':'Посмотреть очередь, приостановить или продолжить',agentPanel);
  const sync=data.browser.auto_sync,bump=data.browser.resume_bump;
  disclosure(advanced,'automation','Автоматизация HH',[(sync?.enabled?'Ответы: включено':'Ответы: выключено'),(bump?.resumes?.some(r=>r.blocked)?'Поднятие: нужна проверка':bump?.enabled?'Поднятие резюме: включено':'Поднятие резюме: выключено')].join(' · '),body=>{autoSync(body,sync);resumeBump(body,bump,data.cv?.id);});
  disclosure(advanced,'sources','Источники и расписание','Где искать, сколько читать и разрешены ли расходы API',async body=>{await VacancyIntake.discovery(body);const settings=body.querySelector('details');if(settings)settings.open=true;});
  disclosure(advanced,'connection','Подключение и диагностика',data.browser.connected?'Chrome подключён':'Проверить связь с Chrome',body=>{const workers=data.browser.workers||{};body.append(make('p','muted','Сбор: '+(workers.collection?.connected?'на связи':'ожидает Chrome')+' · Компании: '+(workers.career?.connected?'на связи':'нет свежего подключения')+' · Giga: '+(workers.giga?.connected?'на связи':'не проверен')),button('Подключить HH',connect));});
  disclosure(advanced,'context','Резюме и цель',data.goal||'Цель поиска не задана',body=>{body.append(make('h3','',data.cv?.title||'Резюме не выбрано'),make('p','',data.goal||'Укажите карьерную цель в резюме.'),make('p','muted','Проверено: '+date(data.cv?.checked_at)),button('Открыть резюме',()=>setTab('resume')));});root.append(advanced);
 }
 return {enter,connect,focus,browserIssue};
})();
