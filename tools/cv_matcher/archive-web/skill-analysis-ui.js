(function(root){
 'use strict';
 const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
 const labels={confirmed:'Подтверждено',partial:'Частично',studying:'Изучение / учебная практика',not_evidenced:'Не подтверждено в CV',explicit_gap:'В CV явно указан пробел'},importance={must:'Обязательное',nice:'Будет плюсом',unclear:'Важность не уточнена'};
 function render(report,target){
  target.replaceChildren();
  const intro=el('div','skillVerdict');intro.append(el('strong','',({apply:'Стоит откликнуться',clarify:'Стоит уточнить условия и требования',low_priority:'Низкий приоритет отклика'})[report.recommendation]),el('p','',report.recommendation_reason));target.append(intro);
  target.append(el('h4','','Покрытие требований подтверждениями в CV'));
  const metrics=el('div','skillMetrics');
  for(const dimension of [{label:'Все выделенные требования',...report.metrics.overall},{label:'Обязательные требования',...report.metrics.must},...report.metrics.dimensions]){
   const row=el('div','skillMetric'),name=el('span','',dimension.label),score=el('strong','',dimension.percent===null?'Нет явных требований':dimension.percent+'%'),bar=el('meter');bar.min=0;bar.max=100;bar.value=dimension.percent||0;bar.setAttribute('aria-label',dimension.label);
   row.append(name,score);if(dimension.percent!==null)row.append(bar);row.append(el('small','',`Требований: ${dimension.requirements} · подтверждено ${dimension.statuses.confirmed} · частично ${dimension.statuses.partial} · изучение ${dimension.statuses.studying} · без подтверждения ${dimension.statuses.not_evidenced} · явных пробелов ${dimension.statuses.explicit_gap}`));metrics.append(row);
  }
  target.append(metrics,el('p','muted',report.rubric));
  if(report.goal_alignment)target.append(el('h4','','Соответствие вашей цели'),el('p','',report.goal_alignment));
  target.append(el('h4','','Требования, подтверждения и пробелы'));
  for(const row of report.requirements){
   const detail=el('details','requirement'),summary=el('summary');summary.append(el('span','tag '+(row.status==='confirmed'?'active':'missing'),labels[row.status]),document.createTextNode(' '+row.requirement));detail.append(summary,el('p','muted',importance[row.importance]),el('p','',row.explanation),el('strong','','Вакансия'),el('blockquote','',row.job_quote));
   if(row.resume_quotes.length){detail.append(el('strong','','Выбранное резюме'));for(const quote of row.resume_quotes)detail.append(el('blockquote','',quote));}else detail.append(el('p','muted','Подтверждающий фрагмент в CV не найден. Это не доказывает отсутствие навыка.'));
   detail.append(el('p','skillAction',row.action));target.append(detail);
  }
  for(const [heading,rows] of [['Что уточнить у себя или рекрутера',report.questions],['Ограничения разбора',report.limitations]])if(rows.length){target.append(el('h4','',heading));const list=el('ul');for(const text of rows)list.append(el('li','',text));target.append(list);}
  target.append(el('p','muted',`${report.model} · ${new Date(report.created_at).toLocaleString('ru-RU')} · ${report.source==='user_pasted'?'Вставленный ответ ChatGPT, без API; проверены формат и ссылки на источники':report.cached?'Сохранённый результат, без вызова API':'Результат сохранён в SQLite'}. Проверяйте интерпретацию цитат: она может быть неточной.`));
 }
 function attach(parent,{api,context,isCurrent,onHistory}){
  const section=el('section','skillAnalysis'),button=el('button','','Разобрать требования · Luna'),status=el('p','muted'),output=el('div');status.setAttribute('role','status');section.append(el('h3','','Подробный разбор соответствия'),el('p','muted','Luna сопоставит требования с опытом, покажет пробелы и объяснит оценку по направлениям. По кнопке профессиональный текст выбранного CV, вакансия и цель отправляются в OpenAI. Повторный просмотр сохранённого результата бесплатный.'),button,status,output);parent.append(section);if(onHistory){const history=el('button','secondary','История разборов вакансий (для выбранных CV)');history.onclick=onHistory;section.append(history);}
  if(!context.resume_id){button.disabled=true;status.textContent='Выберите резюме над списком.';return;}
  const show=result=>{render(result,output);button.disabled=true;button.textContent='Разбор сохранён';status.textContent='Учитываются именно выбранное CV, текст вакансии и цель поиска.';};
  button.onclick=async()=>{if(!isCurrent())return;button.disabled=true;status.textContent='Luna читает CV и требования… Обычно это занимает до двух минут. Можно вернуться к сохранённому результату позже.';
   try{const result=await api('skill-analysis',context,150000);if(isCurrent())show(result);}catch(e){if(isCurrent()){status.textContent=e.message;button.disabled=false;}}
  };
  const offline=el('button','secondary','ChatGPT без API'),box=el('div','externalAnalysis');box.hidden=true;
  const prompt=el('textarea'),answer=el('textarea'),info=el('p','muted'),copy=el('button','secondary','1. Скопировать промпт с CV и вакансией'),save=el('button','','2. Проверить и показать разбор');
  prompt.rows=10;prompt.readOnly=true;prompt.hidden=true;prompt.setAttribute('aria-label','Промпт для разбора навыков без API');
  answer.rows=8;answer.maxLength=150000;answer.placeholder='Вставьте сюда полный JSON из ответа ChatGPT';answer.setAttribute('aria-label','Ответ ChatGPT для разбора навыков');
  info.setAttribute('role','status');box.append(el('p','','Скопируйте промпт → вставьте в ChatGPT → вставьте полученный JSON сюда. Сервис проверит цитаты, рассчитает покрытие и сохранит разбор с исходными версиями документов.'),copy,prompt,answer,save,info);section.append(offline,box);
  let exported=null;offline.onclick=()=>{box.hidden=!box.hidden;};
  copy.onclick=async()=>{if(!isCurrent())return;copy.disabled=true;try{
    exported=await api('skill-external',{op:'export',...context});if(!isCurrent())return;prompt.value=exported.prompt;
    try{await navigator.clipboard.writeText(exported.prompt);info.textContent='Промпт скопирован. Попросите ChatGPT вернуть JSON по указанной схеме.';}catch{prompt.hidden=false;prompt.focus();prompt.select();info.textContent='Промпт выделен: Cmd+C / Ctrl+C.';}
  }catch(e){info.textContent=e.message;}finally{copy.disabled=false;}};
  save.onclick=async()=>{if(!isCurrent())return;save.disabled=true;try{
    let exportId=exported?.export_id;if(!exportId){try{exportId=JSON.parse(answer.value.trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'')).export_id;}catch{throw Error('Вставьте полный JSON-ответ с export_id и analysis.');}}
    const result=await api('skill-external',{op:'import',export_id:exportId,answer:answer.value});if(!isCurrent())return;
    if(result.resume_id!==context.resume_id||result.vacancy_id!==context.vacancy_id||result.goal!==context.goal){info.textContent='Ответ сохранён в истории исходной пары CV–вакансия. Выбрана другая пара.';return;}
    const saved=await api('skill-analysis?'+new URLSearchParams(context));if(!isCurrent())return;
    if(saved.analysis?.resume_hash===result.resume_hash&&saved.analysis?.vacancy_hash===result.vacancy_hash){show(result);info.textContent='Разбор сохранён в SQLite и показан выше. Вызовов API: 0.';}
    else info.textContent='Разбор сохранён в истории. Тексты CV или вакансии уже изменились: для текущей версии скопируйте новый промпт.';
  }catch(e){info.textContent=e.message;}finally{save.disabled=false;}};
  button.disabled=true;status.textContent='Проверяю сохранённый разбор…';
  api('skill-analysis?'+new URLSearchParams(context)).then(data=>{if(!isCurrent())return;if(data.analysis)show(data.analysis);else{button.disabled=false;status.textContent='Для этой версии документов сохранённого разбора пока нет.';}}).catch(e=>{if(isCurrent()){button.disabled=false;status.textContent=e.message;}});
 }
 root.SkillAnalysis={attach,render};
})(globalThis);
