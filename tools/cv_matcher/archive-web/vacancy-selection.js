'use strict';
const VacancySelection=(()=>{
 function install(){
  const root=make('details','intakePanel collectionTools');root.id='vacancySelection';root.hidden=!['vacancy','ranking'].includes(tab);
  root.append(make('summary','','Отбор с помощью LLM · без API'));
  const controls=make('div','journeyActions'),copy=make('button','secondary','Скопировать запрос на отбор вакансий · без API');controls.append(copy);root.append(controls);
  root.append(make('p','muted','Выбранное CV + цель + краткие карточки из текущей выборки. Вставьте запрос в ChatGPT, Gemini или другую LLM. Полные описания не требуются; расходы API сервиса — 0.'));
  const allLabel=make('label','','Все вакансии из архива · одним запросом'),includeAll=make('input');includeAll.type='checkbox';includeAll.checked=false;allLabel.prepend(includeAll);root.append(allLabel);
  root.append(make('p','muted','С этим флажком включается весь архив без фильтров списка и без разбиения на пакеты. Подтверждённо закрытые вакансии исключаются.'));
  const options=make('details');options.append(make('summary','','Настроить пакет и пожелания'));
  function field(label,tag='input'){const l=make('label','flowLabel',label),i=make(tag);l.append(i);options.append(l);return i;}
  const goal=field('Цель отбора','textarea');goal.rows=2;goal.maxLength=2000;goal.placeholder='Пусто — цель выбранного списка / поиска';
  const comments=field('Что учитывать при отборе','textarea');comments.rows=2;comments.maxLength=4000;comments.placeholder='Например: приоритет исследовательских задач, DiT, Flow Matching; готов к смежным ролям';
  const size=field('Карточек в пакете','select');for(const n of [25,50,100]){const option=make('option','',String(n));option.value=String(n);size.append(option);}size.value='50';
  const packet=field('Номер пакета');packet.type='number';packet.min='1';packet.max='10000';packet.value='1';
  const length=field('Длина краткого описания','select');for(const n of [400,600,1200]){const option=make('option','',n+' символов');option.value=String(n);length.append(option);}length.value='600';
  const top=field('Сколько рекомендаций запросить');top.type='number';top.min='1';top.max='30';top.value='10';
  const all=make('button','secondary','Включить короткие карточки: статус «Все записи»');all.onclick=()=>{$('filter').value='';packet.value='1';loadList(true).catch(e=>notice(e.message));};options.append(all);
  options.append(make('p','muted','Учитываются поиск, компании, статус и CV. На экране рейтинга — только сохранённый рейтинг. Закрытые вакансии исключаются, непроверенные помечаются. Большая выборка делится на пакеты; это не отбор из всей базы сразу.'));
  root.append(options);const status=make('p','muted');status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
  const preview=make('details');preview.append(make('summary','','Текст запроса · просмотр и ручное копирование'));const text=make('textarea');text.rows=10;text.readOnly=true;text.setAttribute('aria-label','Запрос на отбор рекомендуемых вакансий');preview.append(text);root.append(preview);
  const next=make('button','secondary','Следующий пакет');next.hidden=true;controls.append(next);
  includeAll.onchange=()=>{size.disabled=packet.disabled=includeAll.checked;next.hidden=true;text.value='';packet.value='1';status.textContent=includeAll.checked?'Будет скопирован весь архив с краткими описаниями. Размер запроса покажем после подготовки.':'Включён отбор по текущим фильтрам и пакетам.';};
  let request=0,lastContext='';
  const context=()=>({resume_id:$('analysisCV').value,goal:goal.value.trim()||(tab==='ranking'?$('rankingGoal').value:summaryData?.goal||''),comments:comments.value,
   companies:includeAll.checked?null:companyPicker.value,q:includeAll.checked?'':$('search').value,status:includeAll.checked?'':$('filter').value,model:$('embeddingModel').value,
   ranked_only:!includeAll.checked&&tab==='ranking',all_vacancies:includeAll.checked,description_chars:Number(length.value),limit:Number(size.value),top:Number(top.value)});
  async function build(){
   const token=++request,value=context(),key=JSON.stringify(value),view=tab;
   if(lastContext&&lastContext!==key)packet.value='1';lastContext=key;
   copy.disabled=true;next.disabled=true;status.textContent='Собираю локальный контекст выбранного CV и карточки вакансий…';
   try{
    const data=await api('workflow',{op:'vacancy_selection_prompt',...value,packet:Number(packet.value)});
    if(token!==request)return;
    if(view!==tab||key!==JSON.stringify(context())){text.value='';next.hidden=true;status.textContent='CV или фильтры изменились. Скопируйте запрос заново для текущего выбора.';return;}
    text.value=data.prompt;next.hidden=data.all_vacancies||data.packet>=data.packets;
    let copied=false;try{await navigator.clipboard.writeText(data.prompt);copied=true;}catch{preview.open=true;text.focus();text.select();}
    status.textContent=(copied?'Запрос скопирован. ':'Запрос готов. Нажмите Cmd+C / Ctrl+C в поле ниже. ')+
     'CV: '+data.resume_title+' · '+(data.all_vacancies?'весь архив':'пакет '+data.packet+' из '+data.packets)+' · карточек '+data.included+' из '+data.total+
     ' · '+data.characters.toLocaleString('ru-RU')+' символов · API: 0.'+
     (data.unknown_activity?' Активность не подтверждена у '+data.unknown_activity+' карточек.':'')+
     (data.fragments?' Неполных описаний: '+data.fragments+'.':'')+
     (data.skipped?' Пропущено карточек с некорректной ссылкой: '+data.skipped+'.':'')+
     (data.large_prompt?' Большой запрос: проверьте, помещается ли он в выбранную LLM. При необходимости уменьшите длину описаний.':'');
   }catch(error){text.value='';next.hidden=true;status.textContent=error.message;}
   finally{if(token===request){copy.disabled=false;next.disabled=false;}}
  }
  copy.onclick=build;next.onclick=()=>{packet.value=String(Number(packet.value)+1);return build();};
  $('rankingIntro').after(root);
 }
 return {install};
})();
VacancySelection.install();
