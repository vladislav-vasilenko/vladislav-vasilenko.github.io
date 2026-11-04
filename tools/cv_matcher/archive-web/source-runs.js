'use strict';
/* Starts whole-source crawls in the local service and shows live progress. No model calls. */
const SourceRuns=(()=>{
 const states={queued:'В очереди',running:'Идёт сбор',complete:'Готово',partial:'Готово, были ошибки',failed:'Не удалось',stopped:'Остановлен',interrupted:'Прерван — можно запустить снова'};
 const reasons={python_timeout:'превышено время',python_process_failed:'сборщик завершился с ошибкой',python_output_limit:'слишком большой ответ',python_parser_error:'источник изменил формат или недоступен',access_required:'источник ограничил доступ',login_required:'нужен вход',http_rate_limited:'слишком много запросов',navigation_timeout:'страница не ответила'};
 let root,body,timer,wasRunning=false,request=0,shown=false;
 const active=state=>state==='queued'||state==='running';
 function result(progress){
  if(progress?.new===undefined)return '';
  const parts=['новых '+progress.new,'обновлено '+progress.updated,'просмотрено '+progress.listed];
  if(progress.seconds)parts.push('за '+Math.round(progress.seconds)+' с');
  return parts.join(' · ');
 }
 function row(item){
  const box=make('div','sourceRun'),head=make('div','sourceRunHead'),last=item.last,running=active(last?.state);
  head.append(make('strong','',item.label),make('span','muted','Python, без окна браузера'));
  const button=make('button',running?'secondary':'',running?'Остановить':'Запустить');button.type='button';button.dataset.source=item.source;
  button.onclick=()=>act(button,running?{op:'stop',source:item.source}:{op:'start',sources:[item.source]});head.append(button);box.append(head);
  if(running){
   const wait=Busy.create(states[last.state]);if(last.progress?.total)wait.update(states[last.state]+' · запрос '+Math.min(last.progress.done+1,last.progress.total)+' из '+last.progress.total+' · '+result(last.progress),last.progress.done,last.progress.total);box.append(wait);
  }else if(last){
   box.append(make('p','sourceRunResult '+(['failed','partial'].includes(last.state)?'sourceRunWarning':''),[states[last.state],result(last.progress),date(new Date(last.updated*1000).toISOString())].filter(Boolean).join(' · ')));
   if(last.state==='failed'&&!last.progress.reasons?.length)box.append(make('p','muted','Выдача пуста. Это не значит, что вакансий нет: источник мог измениться или ограничить доступ.'));
   if(last.progress.reasons?.length)box.append(make('p','muted','Причина: '+last.progress.reasons.map(reason=>reasons[reason]||reason).join(', ')));
  }else box.append(make('p','muted','Ещё не запускался.'));
  return box;
 }
 function render(data){
  body.replaceChildren();
  for(const item of data.items)body.append(row(item));
  const hh=make('div','sourceRun'),head=make('div','sourceRunHead');head.append(make('strong','','hh.ru'),make('span','muted','Через расширение Chrome'));hh.append(head,make('p','muted',(data.chrome_connected?'Chrome подключён. ':'Chrome не подключён. ')+'У hh.ru нет открытого API, а сбор идёт в вашей авторизованной сессии, поэтому он медленнее. Запуск — в расширении или в разделе «Сегодня → Управление поиском».'));body.append(hh);
  const all=make('button','secondary','Запустить все быстрые');all.type='button';all.disabled=data.running;all.onclick=()=>act(all,{op:'start',sources:data.items.map(item=>item.source)});body.append(all);
 }
 async function act(button,command){button.disabled=true;try{await api('source-runs',command);await refresh();}catch(e){notice(e.message);button.disabled=false;}}
 async function refresh(){
  clearTimeout(timer);const n=++request,data=await api('source-runs');if(n!==request||root.hidden)return;render(data);
  if(data.running)timer=setTimeout(()=>refresh().catch(e=>notice(e.message)),1500);
  const finished=wasRunning&&!data.running;wasRunning=data.running;
  if(finished){const summary=await api('summary');$('navJobs').textContent=summary.vacancies;await loadList(true);}
 }
 function install(){
  root=make('details','collectionTools sourceRuns');root.id='sourceRuns';root.open=true;root.append(make('summary','','Сбор вакансий · запуск источников'));body=make('div','sourceRunsBody');body.append(Busy.create('Проверяю источники…'));root.append(body);
  document.querySelector('.collectionToolbar').after(root);
 }
 function enter(){
  if(!root)install();root.hidden=tab!=='vacancy';if(root.hidden){clearTimeout(timer);shown=false;return;}
  if(!shown){shown=true;refresh().catch(e=>notice(e.message));}
 }
 return {enter};
})();
globalThis.SourceRuns=SourceRuns;
