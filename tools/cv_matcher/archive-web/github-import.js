'use strict';
const GitHubImport = (() => {
 const views = new Map();
 const phases = {idle:'Ещё не запускался',checking:'Проверяю запуски GitHub',downloading:'Загружаю результат',importing:'Сохраняю в локальный архив',complete:'Импорт завершён',up_to_date:'Новых запусков нет',error:'Нужна проверка',interrupted:'Импорт прерван — можно продолжить'};
 const labels = {added:'Новые',updated:'Изменённые',unchanged:'Без изменений',protected:'Сохранён более полный / свежий текст',rejected:'Отклонены',duplicates:'Объединены повторы'};
 const action = (text, fn) => {const b=make('button','secondary',text);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;};
 function model(state) {
  const last=state.last_import;
  const active=state.running||(state.pending_key&&state.pending_key!==state.cursor&&state.counts);
  return {phase:phases[state.phase]||state.phase,counts:active?state.counts:last?.counts,
   progress:active&&state.total!==undefined?(state.offset||0)+' / '+state.total:'',
   sources:active?state.sources:last?.sources,warnings:active?state.warnings:last?.warnings};
 }
 function render(root,state) {
  const m=model(state),runs=root.querySelector('[data-github-control]');root.replaceChildren();
  root.append(make('p','githubImportState',m.phase));
  if(m.progress){const bar=make('progress');bar.max=state.total||1;bar.value=state.offset||0;bar.setAttribute('aria-label','Обработано вакансий');root.append(bar,make('p','muted',m.progress));}
  const controls=make('div','githubImportActions');
  const start=action(state.running?'Импорт выполняется…':'Проверить и импортировать',async()=>{await api('github-import',{op:'start'});await refresh();});start.disabled=state.running;
  const automatic=make('label'),check=make('input');check.type='checkbox';check.checked=!!state.enabled;
  check.onchange=async()=>{check.disabled=true;try{await api('github-import',{op:'configure',enabled:check.checked});await refresh();}catch(e){check.checked=!check.checked;notice(e.message);}finally{check.disabled=false;}};
  automatic.append(check,document.createTextNode(' Автопроверка каждый час, пока сервис работает'));
  controls.append(start,automatic);root.append(controls);
  if(state.last_checked_at)root.append(make('p','muted','Последняя проверка: '+date(state.last_checked_at)));
  const last=state.last_import;
  if(last){root.append(make('p','muted','Последний импорт: '+date(last.imported_at)+' · данные от '+date(last.exported_at)));
   root.append(external('https://github.com/'+state.repository+'/actions/runs/'+last.run.id,'Запуск #'+last.run.run_number+' · '+(last.run.conclusion==='success'?'успешный':'завершился с ошибкой')+' ↗'));
  }
  if(m.counts){const stats=make('dl','githubImportCounts');for(const [key,label] of Object.entries(labels)){const item=make('div');item.append(make('dt','',label),make('dd','',String(m.counts[key]||0)));stats.append(item);}root.append(stats);}
  for(const source of m.sources||[])root.append(make('p',source.errors?'githubImportWarning':'muted',source.source+': '+(source.errors?'ошибок сбора '+source.errors:'ошибок в отчёте нет; полнота выдачи не гарантирована')));
  for(const warning of m.warnings||[])root.append(make('p','githubImportWarning',warning));
  if(state.error){const error=make('p','githubImportWarning',state.error);error.setAttribute('role','alert');root.append(error);}
  if(state.invalid_examples?.length){const details=make('details');details.append(make('summary','','Причины отклонения записей'));for(const text of state.invalid_examples)details.append(make('p','muted',text));root.append(details);}
  const controlsHost=runs||make('div');controlsHost.dataset.githubControl='true';root.append(controlsHost);if(!runs)GitHubRuns.mount(controlsHost);
  root.append(make('p','muted','Только вакансии → локальная SQLite. Резюме не отправляются в GitHub. Импорт не подтверждает активность вакансии и не запускает модели. Доступ используется из gh auth login на этом компьютере.'));
 }
 let timer, refreshing=false, wasRunning=false;
 async function refresh() {
  if(refreshing)return;
  refreshing=true;
  try {
   const state=await api('github-import');
   for(const [root,summary] of views){if(!root.isConnected){views.delete(root);continue;}render(root,state);if(summary)summary.textContent='GitHub Actions · '+(state.running?model(state).phase:state.last_import?'импорт '+date(state.last_import.imported_at):'импорт вакансий');}
   if(state.running&&views.size)timer=setTimeout(()=>refresh().catch(e=>notice(e.message)),1500);
   if(wasRunning&&!state.running&&state.phase==='complete'&&['vacancy','ranking'].includes(tab))reload().catch(e=>notice(e.message));
   wasRunning=state.running;
  } finally {refreshing=false;}
 }
 async function mount(root,summary) {views.set(root,summary);await refresh();}
 function enter() {
  const host=$('githubCollection');if(!host)return;
  host.hidden=!['vacancy','ranking'].includes(tab);
  if(!host.hidden&&!host.dataset.ready){host.dataset.ready='true';mount($('githubCollectionBody'),$('githubCollectionSummary')).catch(e=>{host.dataset.ready='';$('githubCollectionBody').textContent=e.message;});}
  else if(!host.hidden)refresh().catch(e=>notice(e.message));
 }
 return {enter,mount,model};
})();
