'use strict';
const GitHubRuns=(()=>{
 const statuses={queued:'В очереди',in_progress:'Выполняется',completed:'Завершён',waiting:'Ожидает',requested:'Запрошен',pending:'Ожидает',success:'Успешно',failure:'Ошибка',cancelled:'Отменён',skipped:'Пропущен',action_required:'Требуется проверка',timed_out:'Истекло время'};
 const word=x=>statuses[x]||x||'—';
 const button=(name,fn)=>{const b=make('button','secondary',name);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;};
 function mount(host){
  const details=make('details'),body=make('div');details.append(make('summary','','Автономный сбор · запуски, источники и настройки'),body);host.append(details);
  let timer,busy=false;
  async function load(){
   if(busy||!host.isConnected)return;busy=true;clearTimeout(timer);
   try{
    const data=await api('github-import',{op:'runs'},120000),active=data.runs.some(r=>r.status!=='completed'),expanded=new Set([...body.querySelectorAll('details[open][data-state-key]')].map(d=>d.dataset.stateKey));body.replaceChildren();
    body.append(make('p','muted','Сбор работает в GitHub Actions независимо от локального сервиса. Импорт в SQLite выполняется отдельно. Ручной запуск запускает только парсеры и подготовку JSON, без моделей и embeddings.'));
    if(data.settings.dispatched_at)body.append(make('p','muted','Последняя команда запуска: '+date(data.settings.dispatched_at)+' · '+(data.settings.dispatch_status==='accepted'?'GitHub принял команду':data.settings.dispatch_status)));
    const settings=make('details');settings.dataset.stateKey='settings';settings.open=expanded.has('settings');settings.append(make('summary','','Источники и лимит следующего ручного запуска'));
    const choices=[];for(const adapter of data.adapters.filter(a=>a.github_actions)){const label=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';check.value=adapter.id;check.checked=data.settings.sources.includes(adapter.id);check.disabled=active;choices.push(check);label.append(check,document.createTextNode(' '+adapter.id+' · '+adapter.note));settings.append(label);}
    const limit=make('input');limit.type='number';limit.min=1;limit.max=500;limit.value=data.settings.limit;limit.disabled=active;const label=make('label','','Лимит на запрос источника · 1–500');label.append(limit);settings.append(label);
    settings.append(button('Сохранить настройки',async()=>{await api('github-import',{op:'settings',sources:choices.filter(c=>c.checked).map(c=>c.value),limit:Number(limit.value)});notice('Настройки следующего ручного запуска сохранены.');await loadAfter();}),make('p','muted','Расписание на GitHub: '+data.schedule+'. Здесь настраивается ручной запуск; расписание меняется в workflow и не зависит от флажка автопроверки импорта.'));
    body.append(settings);
    const actions=make('div','githubImportActions'),start=button(active?'Сбор уже выполняется':'Запустить сбор в GitHub',async()=>{await api('github-import',{op:'dispatch'},120000);notice('GitHub принял команду. Запуск появится в истории.');await loadAfter();});start.disabled=active;
    actions.append(start,button('Обновить историю',loadAfter));body.append(actions);
    const history=make('div');for(const run of data.runs){const row=make('details');row.dataset.stateKey='run-'+run.id;row.open=expanded.has(row.dataset.stateKey);row.append(make('summary','','#'+run.run_number+' · '+date(run.created_at)+' · '+word(run.conclusion||run.status)),external('https://github.com/vladislav-vasilenko/vladislav-vasilenko.github.io/actions/runs/'+run.id,'Открыть GitHub Run ↗'));
     const content=make('div');row.append(content);let loaded=false;row.ontoggle=async()=>{if(!row.open||loaded)return;loaded=true;try{const value=await api('github-import',{op:'run',run_id:run.id},120000);for(const job of value.jobs){content.append(make('h4','',job.name+' · '+word(job.conclusion||job.status)));for(const step of job.steps)content.append(make('p',step.conclusion==='failure'?'githubImportWarning':'muted',word(step.conclusion||step.status)+' · '+step.name));}}catch(e){loaded=false;content.textContent=e.message;}};
     if(run.status!=='completed')row.append(button('Остановить этот сбор',async()=>{await api('github-import',{op:'cancel',run_id:run.id},120000);notice('Запрошена остановка GitHub Run.');await loadAfter();}));history.append(row);}
    body.append(history);
    const adapters=make('details');adapters.dataset.stateKey='adapters';adapters.open=expanded.has('adapters');adapters.append(make('summary','','Все Python-адаптеры · '+data.adapters.length));for(const a of data.adapters)adapters.append(make('p','muted',a.id+' · '+a.adapter+' · '+(a.github_actions?'GitHub Actions / локально':'Локальный сбор')+' · '+a.note));body.append(adapters);
    const recent=data.settings.dispatched_epoch&&Date.now()/1000-data.settings.dispatched_epoch<90;
    if((active||recent)&&details.open)timer=setTimeout(()=>load().catch(e=>notice(e.message)),10000);
   }finally{busy=false;}
  }
  async function loadAfter(){busy=false;await load();}
  details.ontoggle=()=>{if(details.open)load().catch(e=>{body.textContent=e.message;});else clearTimeout(timer);};
 }
 return {mount};
})();
