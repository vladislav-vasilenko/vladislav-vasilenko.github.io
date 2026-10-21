'use strict';
const ResumeProfile=(()=>{
 const areas={timeline:'Хронология работы',goal:'Соответствие цели',research:'Исследования и математика',models:'Модели и обучение',engineering:'Инженерия',production:'Продакшен и масштаб'};
 const states={confirmed:'Описана практика',partial:'Частичное подтверждение',studying:'Изучение / учебная практика',not_evidenced:'Не подтверждено текстом'};
 function paragraphs(host,value){
  let list=null;for(const line of String(value||'').split('\n')){if(!line.trim())continue;if(/^\s*[-•]\s/.test(line)){if(!list){list=make('ul');host.append(list);}list.append(make('li','',line.replace(/^\s*[-•]\s*/,'')));}else{list=null;host.append(make('p','',line));}}
 }
 function render(panel,data,options){
  const cv=data.payload,document=make('article','resumeDocument'),header=make('section','resumeHeader');
  header.append(make('p','eyebrow','ПРОФЕССИОНАЛЬНЫЙ ПРОФИЛЬ'),make('h2','',cv.title),make('p','meta','Снимок #'+data.version_id+' · сохранён '+date(data.source_at||cv.captured_at)));
  const nav=make('div','resumeHeaderActions'),toggle=make('button','secondary','Режим чтения');toggle.setAttribute('aria-pressed','false');toggle.onclick=()=>{panel.classList.toggle('resumeExpanded');const expanded=panel.classList.contains('resumeExpanded');panel.closest('.workspace').classList.toggle('resumeReading',expanded);toggle.textContent=expanded?'Вернуть список резюме':'Режим чтения';toggle.setAttribute('aria-pressed',String(expanded));};nav.append(toggle);
  const exports=make('details','resumeExportMenu');exports.append(make('summary','','Экспорт ▾'));
  const print=make('button','secondary','Печать / сохранить PDF');print.onclick=()=>{exports.open=false;window.print();};exports.append(print);
  if((cv.source_type||'hh')==='hh'){const u=new URL(cv.source_url);u.searchParams.set('print','true');exports.append(external(u.href,'Печатный вид на HH ↗'));}
  nav.append(exports);header.append(nav);document.append(header);
  for(const section of cv.sections||[]){const block=make('section','resumeSection');block.append(make('h3','',section.heading||section.key));
   if(section.key==='experience'){
    const parsed=ResumeProfileCore.experience(section.text);
    if(parsed.items.length){for(const item of parsed.items){const row=make('article','resumeJob'),period=make('div','resumePeriod');period.append(make('strong','',item.dates));if(item.duration)period.append(make('p','meta',item.duration));const role=make('div','resumeRole');role.append(make('h4','',item.company||'Организация в исходнике не выделена'),make('p','resumePosition',item.role));paragraphs(role,item.description);row.append(period,role);block.append(row);}if(parsed.unparsed)block.append(make('p','meta',parsed.unparsed));}
    else paragraphs(block,section.text);
   }else if(section.key==='skills'){const chips=make('div','tags');for(const skill of section.text.split(/[\n,;]+/).map(s=>s.trim()).filter(Boolean))chips.append(make('span','tag',skill));block.append(chips);}
   else paragraphs(block,section.text);
   document.append(block);
  }
  for(const note of data.supplements||[]){const block=make('section','resumeSection resumeSupplement');block.append(make('span','tag missing','Дополнение пользователя · ещё не внесено в HH'),make('h3','',note.company),make('p','meta',note.start+' — '+note.end+' · версия дополнения #'+note.version_id),make('p','resumePosition',note.role));paragraphs(block,note.description);const copy=make('button','secondary','Скопировать блок для HH');copy.onclick=()=>navigator.clipboard.writeText(note.company+'\n'+note.start+' — '+note.end+'\n'+note.role+'\n'+note.description);block.append(copy);document.append(block);}
  if(data.user_facts?.length){const block=make('section','resumeSection resumeSupplement');block.append(make('span','tag missing','Уточнения пользователя · отдельно от HH-резюме'),make('h3','','Практический опыт и дополнительные факты'));for(const fact of data.user_facts)paragraphs(block,fact.text);document.append(block);}
  panel.append(document);review(panel,data,options);
 }
 function review(panel,data,{api,goal,isCurrent}){
  const box=make('section','resumeReview'),heading=make('h3','','Карьерный разбор резюме');box.append(heading,make('p','muted','Хронология, цели, навыки и план развития. До 10 лучших вакансий из актуального сохранённого рейтинга. Изучение и планы не считаются выполненной работой.'));
  const label=make('label','flowLabel','Цель развития'),target=make('textarea');target.rows=2;target.value=goal||'';target.maxLength=2000;label.append(target);
  const modelLabel=make('label','flowLabel','Модель'),model=make('select');for(const name of ['luna','terra','sol']){const o=make('option','',name);o.value=name;model.append(o);}modelLabel.append(model);
  const actions=make('div','resumeActions'),status=make('p','muted'),output=make('div'),prompt=make('textarea');prompt.readOnly=true;prompt.hidden=true;prompt.rows=12;prompt.setAttribute('aria-label','Промпт карьерного разбора');
  const importBox=make('details'),incoming=make('textarea');incoming.rows=8;incoming.setAttribute('aria-label','JSON карьерного разбора из ChatGPT');importBox.append(make('summary','','Вставить разбор из ChatGPT без API'),make('p','muted','Скопируйте промпт выше. Вставьте сюда JSON-ответ целиком; ссылки и цитаты будут проверены.'),incoming);
  let context=null;
  async function prepare(){const result=await api('resume-review',{op:'prepare',resume_id:data.id,goal:target.value,model:model.value});if(!isCurrent())return null;context=result.context;status.textContent='Зафиксированы CV #'+context.resume_version_id+' и '+context.jobs.length+' из 10 вакансий. '+(context.jobs.length?'Только рейтинг для этой версии CV и цели.':'Сначала сохраните рейтинг для этого CV и цели, чтобы использовать вакансии.');if(result.analysis)renderReview(output,result.analysis,context);return result;}
  function button(label,action){const b=make('button','secondary',label);b.onclick=async()=>{b.disabled=true;try{await action();}catch(e){status.textContent=e.message;}finally{b.disabled=false;}};return b;}
  actions.append(button('Подготовить источники',prepare),button('Разобрать через API',async()=>{const result=await prepare();if(!result)return;if(result.analysis){status.textContent+=' Показан сохранённый разбор; вызовов API: 0.';return;}status.textContent+=' Модель готовит разбор…';const analysis=await api('resume-review',{op:'generate',context_key:context.key},150000);if(isCurrent())renderReview(output,analysis,context);}),button('ChatGPT без API · скопировать промпт',async()=>{if(!await prepare())return;const result=await api('resume-review',{op:'prompt',context_key:context.key});prompt.value=result.prompt;try{await navigator.clipboard.writeText(result.prompt);status.textContent+=' Промпт скопирован, API модели не вызывается.';}catch{prompt.hidden=false;prompt.focus();prompt.select();status.textContent+=' Нажмите Cmd+C / Ctrl+C.';}}));
  importBox.append(button('Проверить и сохранить разбор',async()=>{if(!context)throw Error('Сначала подготовьте источники и скопируйте промпт.');const raw=JSON.parse(incoming.value.replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));const analysis=await api('resume-review',{op:'import',context_key:context.key,analysis:raw});if(isCurrent())renderReview(output,analysis,context);status.textContent='Сохранено в SQLite вместе с точными версиями CV и вакансий. Вызовов API: 0.';}));
  target.oninput=model.onchange=()=>{context=null;output.replaceChildren();status.textContent='Цель или модель изменены. Подготовьте источники заново.';};box.append(label,modelLabel,actions,status,prompt,importBox,output);panel.append(box);
 }
 function renderReview(host,a,ctx){
  host.replaceChildren();host.append(make('p','meta',a.model+' · '+date(a.created_at)),make('p','',a.summary));
  const dimensions=make('div','resumeDimensions');for(const d of a.dimensions){const card=make('article','resumeDimension');card.append(make('h4','',areas[d.area]),make('span','tag '+(d.status==='confirmed'?'active':'missing'),states[d.status]),make('p','',d.comment));for(const e of d.evidence)card.append(make('blockquote','',e.quote));const ul=make('ul');for(const step of d.next_steps)ul.append(make('li','',step));card.append(ul);dimensions.append(card);}host.append(dimensions,make('h4','','Что исследовать и сделать самостоятельно'));
  for(const project of a.projects){const card=make('article','resumeDimension');card.append(make('h4','',project.title),make('span','tag version','Рекомендация на будущее'),make('p','',project.why),make('p','',project.deliverable));for(const q of project.job_quotes)card.append(make('blockquote','',q));host.append(card);}
  for(const [title,values] of [['Что уточнить',a.questions],['Ограничения разбора',a.limitations]]){host.append(make('h4','',title));const ul=make('ul');for(const v of values)ul.append(make('li','',v));host.append(ul);}
  const sources=make('details');sources.append(make('summary','','Источники: CV #'+ctx.resume_version_id+' · вакансий '+ctx.jobs.length));for(const job of ctx.jobs){sources.append(external(job.url,job.title+' · '+job.company+' · #'+job.version_id));}host.append(sources);
 }
 return {render};
})();
