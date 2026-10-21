'use strict';
const VacancyIntake=(()=>{
 const call=(op,data={})=>api('workflow',{op,...data});
 function field(parent,label,tag='input'){const l=make('label','flowLabel',label),i=make(tag);l.append(i);parent.append(l);return i;}
 function action(parent,label,fn){const b=make('button','secondary',label);b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}};parent.append(b);return b;}
 function install(){
  installResume();
  installBackfill();
  const root=$('vacancyIntake'),box=make('details','intakePanel');box.append(make('summary','','Добавить одну вакансию · ссылка или текст'));root.append(box);
  const url=field(box,'Ссылка на полную вакансию');url.type='url';const title=field(box,'Название'),company=field(box,'Компания'),body=field(box,'Полный текст: обязанности и требования','textarea');body.rows=7;
  const label=make('label'),full=make('input');full.type='checkbox';label.append(full,document.createTextNode('Я вставил полное описание вакансии'));box.append(label);
  const status=make('p','muted');status.setAttribute('role','status');box.append(status);
  box.append(make('p','muted','Для чтения ссылки достаточно её адреса; остальные поля нужны только для ручной вставки. Chrome проверяет очередь раз в минуту.'));
  action(box,'Настроить чтение сайтов в расширении',()=>Journey.connect());
  action(box,'Сохранить текст и подготовить письмо',async()=>{const saved=await call('vacancy_import',{url:url.value,title:title.value,company:company.value,text:body.value,confirmed_full:full.checked});await showVacancy(saved.vacancy_id,true);});
  action(box,'Загрузить полное описание',async()=>{const saved=await call('collect_one',{url:url.value});status.textContent='Задача сохранена. Сервис выберет способ чтения по настройкам источника.';await poll(saved.command_id,status);});
 }
 function installBackfill(){
  const root=$('vacancyIntake'),box=make('details','intakePanel backfillPanel'),summary=make('summary','','Полные описания · дозагрузка архива');box.append(summary);root.append(box);
  const overview=make('div','backfillOverview'),heading=make('strong'),meter=make('progress'),metrics=make('div','backfillMetrics'),updated=make('p','muted');
  overview.hidden=true;meter.max=100;meter.setAttribute('aria-label','Обработано вакансий в дозагрузке');overview.append(heading,meter,metrics,updated);root.insertBefore(overview,box);
  box.append(make('p','muted','Последовательно прочитать сохранённые ссылки без полного описания. Прогресс сохраняется после перезапуска. Только сбор текста, без платных API. Для HH требуется Chrome с расширением 0.11.22 или новее.'));
  const line=make('p','muted','Откройте блок, чтобы посмотреть состояние.');line.setAttribute('role','status');box.append(line);
  const sources=make('div'),issues=make('div');box.append(sources,issues);let latest,busy=false,restored=false;
  const labels={pending:'ожидают',retry:'повтор отложен',reading:'читаются',complete:'загружены',closed:'закрыты',needs_input:'нужна проверка',failed:'ошибка',cancelled:'отменены'};
  const reasons={access_required:'Требуется проверка доступа на сайте',login_required:'Войдите на сайт',unsupported_layout:'Разметка не распознана',incomplete_descriptions:'Полный текст не подтверждён',unverified_empty:'Не удалось подтвердить содержимое',chrome_interrupted:'Chrome перестал отвечать',transport_failed:'Чтение не завершено',python_error:'Ошибка чтения через Python',unsupported_transport:'Способ сбора не поддерживает источник'};
  const render=value=>{latest=value;const run=value.run;
   const counts=value.counts||{},total=value.total||0,done=['complete','closed','needs_input','failed','cancelled'].reduce((n,key)=>n+(counts[key]||0),0),percent=total?Math.floor(100*done/total):run?.state==='complete'?100:0;
   const stateLabels={running:'Дозагрузка выполняется',paused:'Дозагрузка на паузе',complete:'Дозагрузка завершена',needs_input:'Дозагрузка: нужна проверка',cancelled:'Дозагрузка остановлена'},title=stateLabels[run?.state]||'Дозагрузка';
   overview.hidden=!run;heading.textContent=title+' · '+done+' из '+total+' · '+percent+'%';meter.value=percent;
   meter.setAttribute('aria-valuetext',done+' из '+total+' обработано; полных описаний загружено: '+(counts.complete||0));
   metrics.replaceChildren();for(const [key,label] of [['complete','Полных описаний'],['reading','Сейчас читаются'],['pending','В очереди'],['retry','Отложенный повтор'],['needs_input','Нужна проверка'],['closed','Закрыты'],['failed','Ошибки'],['cancelled','Отменены']]){if(!counts[key]&&key!=='complete')continue;const item=make('span');item.append(make('strong','',String(counts[key]||0)),document.createTextNode(' '+label));metrics.append(item);}
   updated.textContent='Обновлено: '+new Date().toLocaleTimeString('ru-RU')+'. Прогресс обновляется каждые 5 секунд. Проверки и закрытые вакансии учитываются как обработанные, но не как загруженные описания.';
   summary.textContent=run?'Подробности дозагрузки · '+title+' · '+done+'/'+total:'Полные описания · дозагрузка архива';
   line.textContent=run?Object.entries(counts).map(([key,count])=>(labels[key]||key)+': '+count).join(' · ')+(value.chrome_requires_update?' · Перезагрузите расширение Chrome 0.11.22+.':''):'Дозагрузка ещё не запускалась.';
   if(!restored){restored=true;if(run&&['running','paused'].includes(run.state))box.open=true;}
   start.hidden=!!run&&['running','paused'].includes(run.state);pause.hidden=!run||!['running','paused'].includes(run.state);pause.textContent=run?.state==='paused'?'Продолжить':'Пауза';cancel.hidden=pause.hidden;
   sources.replaceChildren();for(const source of value.sources||[])sources.append(make('p','muted',source.host+' — '+Object.entries(source.counts).map(([key,count])=>(labels[key]||key)+': '+count).join(', ')));
   issues.replaceChildren();for(const item of (value.issues||[]).slice(0,8)){const p=make('p','muted');p.append(external(item.source_url,item.vacancy_id),document.createTextNode(' — '+(reasons[item.reason]||item.reason||'Нужна проверка')));issues.append(p);}
  };
  const refresh=async()=>{if(busy)return;busy=true;try{render(await call('collection_backfill'));}finally{busy=false;}};
  const start=action(box,'Дозагрузить полные описания',async()=>{box.open=true;heading.textContent='Запускаем дозагрузку…';overview.hidden=false;render(await call('collection_backfill_start'));});
  const pause=action(box,'Пауза',async()=>{render(await call('collection_backfill_control',{run_id:latest.run.id,action:latest.run.state==='paused'?'resume':'pause'}));});pause.hidden=true;
  const cancel=action(box,'Остановить дозагрузку',async()=>{render(await call('collection_backfill_control',{run_id:latest.run.id,action:'cancel'}));});cancel.hidden=true;
  action(box,'Обновить прогресс дозагрузки',refresh);
  const reportError=e=>{line.textContent='Не удалось обновить прогресс: '+e.message;updated.textContent='Связь с сервисом потеряна. Показан последний полученный прогресс; повтор через 5 секунд.';};
  box.ontoggle=()=>{if(box.open)refresh().catch(reportError);};
  refresh().catch(reportError);
  setInterval(()=>{if(tab==='vacancy'&&(box.open||!latest||['running','paused'].includes(latest.run?.state)))refresh().catch(reportError);},5000);
 }
 function installResume(){
  const root=make('details','intakePanel');root.id='resumeIntake';root.hidden=tab!=='resume';$('collection').prepend(root);
  root.append(make('summary','','Добавить резюме · ссылка HH'),make('p','muted','Подойдёт ваше резюме или резюме знакомого. Ссылка должна открывать полный текст в Chrome. Сохраняются профессиональные разделы, выбранное основное CV не меняется. Без вызовов API.'));
  const url=field(root,'Прямая ссылка на резюме HH');url.type='url';url.placeholder='https://hh.ru/resume/…';url.autocomplete='off';
  const status=make('p','muted');status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
  const result=make('div','journeyActions');root.append(result);let pending='',polling=false;
  const restore=()=>{try{return sessionStorage.getItem('cv-resume-import')||'';}catch{return '';}};
  const remember=id=>{pending=id;try{if(id)sessionStorage.setItem('cv-resume-import',id);else sessionStorage.removeItem('cv-resume-import');}catch{}};
  async function watch(){
   if(!pending||polling)return;polling=true;
   try{for(let n=0;n<90;n++){
    const value=await call('resume_import_status',{command_id:pending});
    if(!['queued','running'].includes(value.state)){
     status.textContent=value.result.note||(value.state==='complete'?'Резюме сохранено.':'Импорт не завершён. Проверьте доступ к резюме и повторите.');remember('');result.replaceChildren();
     if(value.state==='complete'){action(result,'Открыть сохранённое резюме',async()=>{setTab('resume');selection='resume:'+value.resume_id;$('search').value='';await reload();await openDetail('resume',value.resume_id);});if(tab==='resume')await reload();}
     return;
    }
    status.textContent=value.state==='running'?'Chrome читает резюме и сохраняет его в сервисе…':'Ожидаю расширение Chrome 0.11.6 или новее. Очередь проверяется раз в минуту; разрешите чтение HH в параметрах расширения.';
    await new Promise(resolve=>setTimeout(resolve,2000));
   }status.textContent='Задача сохранена, но чтение пока не подтверждено. Проверьте расширение и нажмите «Обновить состояние импорта».';
   }finally{polling=false;}
  }
  action(root,'Добавить через Chrome',async()=>{if(pending){status.textContent='Уже есть задача импорта. Дождитесь результата или обновите её состояние.';await watch();return;}const saved=await call('resume_import',{url:url.value});result.replaceChildren();remember(saved.command_id);await watch();});
  action(root,'Обновить состояние импорта',async()=>{if(!pending){status.textContent='Активной задачи импорта нет. Вставьте ссылку и нажмите «Добавить через Chrome».';return;}await watch();});
  action(root,'Открыть параметры расширения',()=>Journey.connect());
  const saved=restore();if(saved){remember(saved);watch().catch(e=>{status.textContent=e.message;});}
 }
 async function showVacancy(id,prepare=false){await reload();setTab('vacancy');await openDetail('vacancy',id);if(prepare&&$('analysisCV').value)await Flow.create({id});else notice('Описание сохранено. Выберите CV и нажмите «Сопроводительное письмо / подготовить отклик».');}
 async function poll(id,status){
  for(let n=0;n<90;n++){
   const r=await call('collection_status',{command_id:id});
   if(!['queued','running'].includes(r.state)){status.textContent=r.result.note||'Чтение завершено.';if(r.state==='complete')await showVacancy(r.vacancy_id,true);else notice(status.textContent);return;}
   status.textContent=r.state==='running'?(r.transport==='python'?'Сервис читает страницу: HTML / Playwright…':'Chrome читает описание вакансии…'):(r.transport==='python'?'Ожидаю свободный сборщик сервиса…':'Ожидаю расширение Chrome. Проверьте подключение и разрешение чтения этого сайта.');
   await new Promise(resolve=>setTimeout(resolve,2000));
  }
  status.textContent='Чтение ещё не подтверждено. Задача сохранена; проверьте подключение HH и разрешения компаний.';
 }
 async function discovery(root){
  const saved=await call('discovery_config'),box=make('details','intakePanel');box.append(make('summary','','Поиск по расписанию · источники и расходы'));
  box.append(make('p','muted','В 10:00 и 19:00: обновить выбранное CV → собрать страницы и полные описания → проверить кэш → пересчитать рейтинг → отправить подборку. Компьютер, Chrome, сервис и Telegram-бот должны работать.'));
  const sources=field(box,'Адреса выдачи, по одному на строку. Пусто — рекомендации HH для выбранного CV.','textarea');sources.rows=4;sources.value=saved.sources.join('\n');
  const l=make('label'),paid=make('input');paid.type='checkbox';paid.checked=saved.allow_api;l.append(paid,document.createTextNode('Разрешаю автоматические платные запросы embeddings для новых/изменённых текстов в пределах лимита описаний'));box.append(l);
  const model=field(box,'Embedding-модель','select');for(const m of ['text-embedding-3-small','text-embedding-3-large']){const o=make('option','',m);o.value=m;model.append(o);}model.value=saved.model;
  const pages=field(box,'Страниц за одну порцию'),details=field(box,'Полных описаний за одну порцию');pages.type=details.type='number';pages.min=details.min=1;pages.max=5;details.max=100;pages.value=saved.pages;details.value=saved.details;
  const maxPages=field(box,'Всего страниц на источник'),maxDetails=field(box,'Всего описаний на источник');maxPages.type=maxDetails.type='number';maxPages.min=maxDetails.min=1;maxPages.max=100;maxDetails.max=2000;maxPages.value=saved.max_pages??(saved.allow_api?saved.pages:20);maxDetails.value=saved.max_details??(saved.allow_api?saved.details:1000);
  const transport=field(box,'Способ сбора и резервный путь','select');for(const [value,label] of [['python_first','Python → Chrome при сбое'],['chrome_first','Chrome → Python при сбое'],['python_only','Только Python'],['chrome_only','Только Chrome']]){const o=make('option','',label);o.value=value;transport.append(o);}transport.value=saved.transport||'chrome_only';
  box.append(make('p','muted','Гибридный режим меняет только чтение вакансий. Данные сохраняются в одном архиве; платный анализ настраивается отдельно. Для HH используется Chrome, для Google/Meta пока только Python.'));
  const luna=field(box,'Разобрать Luna перед подборкой: 0 — выключено; до 10 запросов на запуск, только с разрешённым API');luna.type='number';luna.min=0;luna.max=10;luna.value=saved.luna_top??0;
  const filters=field(box,'Фильтры T-Bank: названия флажков, по одному на строку. Пусто — не менять фильтры источника.','textarea');filters.rows=2;filters.value=(saved.tbank_filters||[]).join('\n');
  action(box,'T-Bank: IT-разработка → Машинное обучение',async()=>{filters.value='IT-разработка\nМашинное обучение';notice('Профиль IT + ML подготовлен. Нажмите «Сохранить настройки поиска».');});
  const save=async()=>{await call('discovery_config_save',{config:{transport:transport.value,sources:sources.value.split('\n').map(s=>s.trim()).filter(Boolean),allow_api:paid.checked,model:model.value,pages:Number(pages.value),details:Number(details.value),max_pages:Number(maxPages.value),max_details:Number(maxDetails.value),luna_top:Number(luna.value),tbank_filters:filters.value.split('\n').map(s=>s.trim()).filter(Boolean)}});};
  action(box,'Сохранить настройки поиска',async()=>{await save();notice('Сохранено. Без разрешения API новые embeddings не оплачиваются; недостающие будут показаны отдельно.');});
  action(box,'Запустить свежий поиск сейчас',async()=>{await save();const run=await call('discovery_start');notice('Поиск запущен. Результат придёт в Telegram. Идентификатор: '+run.id);});root.append(box);
 }
 return {install,discovery};
})();
VacancyIntake.install();
