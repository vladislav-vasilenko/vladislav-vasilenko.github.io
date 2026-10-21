/* Batch actions only run on explicit owner clicks. */
const CareerBatch=(()=>{
 let root,onRefresh,context,current,timer,finished=false;
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const button=(label,fn,secondary=true)=>{const b=make('button',secondary?'secondary':'',label);b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){fail(e,label);}finally{b.disabled=false;}};return b;};
 function mount(element,refresh){root=element;onRefresh=refresh;if(current)poll();}
 function fail(error,operation){if(root)showDiagnostic(error,operation,root);}
 function panel(title){root.replaceChildren();const box=make('section','acPanel');box.append(make('h2','',title));root.append(box);return box;}
 function payload(data,filters){return {resume_id:data.resume.id,goal:data.resume.goal,model:data.resume.model,filters,limit:50};}
 async function getPlan(data,filters){if(!root)throw Error('Панель пакетного разбора ещё не загружена. Обновите страницу.');clearTimeout(timer);context=payload(data,filters);const p=panel('Подготавливаю топ-50 из сохранённого рейтинга…');p.append(make('p','muted','Модели не вызываются. Проверяю версии CV, вакансий и готовые разборы.'));return await api('analytics-batch',{op:'preview',...context},60000);}
 async function preview(data,filters){try{
  const plan=await getPlan(data,filters);const p=panel('Luna · предварительный просмотр'),info=plan.summary;
  p.append(make('p','',info.resume_title+' · '+info.model),make('p','',info.selected+' вакансий · готовых разборов: '+info.cached+' · до '+info.api_needed+' новых платных запросов.'),make('p','muted','Выбраны лучшие по итоговому embedding-рейтингу среди текущих фильтров. Закрытые и неполные описания исключены. В OpenAI будут переданы профессиональный текст CV, цель и описания выбранных вакансий. Список и версии закреплены на 15 минут. Отправки откликов не будет.'));
  const list=make('details');list.append(make('summary','','Выбранные вакансии ('+info.selected+')'));for(const j of plan.items)list.append(make('p','',j.title+' · '+j.score));p.append(list);
  p.append(button('Подтверждаю: запустить Luna',async()=>{const result=await api('analytics-batch',{op:'start',plan_id:plan.id});current=result.id;finished=false;try{localStorage.setItem('career-luna-batch-id',current);}catch{}await poll();},false),button('Отмена',()=>{root.replaceChildren();}));root.scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){fail(e,'Предпросмотр топ-50');}}
 async function exportPrompt(data,filters){try{
  const p=await getPlan(data,filters),exported=await api('analytics-batch',{op:'export',plan_id:p.id},90000),box=panel('Топ-50 + CV · без API');
  box.append(make('p','',exported.count+' вакансий · '+exported.prompt.length.toLocaleString('ru-RU')+' символов. Полные описания и источники включены. Если пакет не помещается в модель, сузьте фильтры выборки и скопируйте заново.'));
  const text=make('textarea');text.rows=8;text.readOnly=true;text.value=exported.prompt;text.setAttribute('aria-label','Запрос для подробного разбора вакансий без API');box.append(text);
  box.append(button('Скопировать запрос',async()=>{await navigator.clipboard.writeText(text.value);status.textContent='Запрос скопирован. API сервиса не вызывался.';}),button('Скачать .txt',()=>{const url=URL.createObjectURL(new Blob([text.value],{type:'text/plain;charset=utf-8'}));const a=make('a');a.href=url;a.download='career-top-50-review.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
  const status=make('p','muted');status.setAttribute('role','status');box.append(status);
  const input=make('textarea');input.rows=5;input.placeholder='JSON с results из внешней модели';input.setAttribute('aria-label','Результат пакетного разбора без API');box.append(input,button('Импортировать разборы',async()=>{const result=await api('analytics-batch',{op:'import',plan_id:p.id,answer:input.value},90000);status.textContent='Сохранено: '+result.imported+'; ошибок: '+result.errors.length+'. '+result.errors.join('; ');await onRefresh();}));
  try{await navigator.clipboard.writeText(exported.prompt);status.textContent='Запрос скопирован. API сервиса не вызывался.';}catch{status.textContent='Автоматическое копирование недоступно. Используйте кнопку, выделите текст вручную или скачайте файл.';}
  root.scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){fail(e,'Экспорт топ-50 без API');}}
 async function poll(){clearTimeout(timer);if(!root||!current||document.getElementById('analytics')?.hidden)return;try{
  const task=await api('analytics-batch/'+encodeURIComponent(current)),p=panel('Luna · '+task.label);p.append(make('p','',task.progress.done+' из '+task.progress.total+' · из кэша '+task.progress.cached+' · API-запросов '+task.progress.api_requests+' · ошибок '+task.progress.failed),make('p','muted',task.note||'Состояние хранится в сервисе. Закрытие страницы не отменяет задачу. Если ноутбук спит, выполнение продолжится после пробуждения.'));
  const meter=make('progress');meter.max=Math.max(1,task.progress.total);meter.value=task.progress.done;p.append(meter);
  for(const action of task.actions)p.append(button(({pause:'Пауза',resume:'Продолжить оставшиеся',cancel:'Отменить'})[action],async()=>{await api('analytics-batch',{op:'control',batch_id:current,action,revision:task.revision});finished=false;await poll();}));
  if(['complete','cancelled','needs_input'].includes(task.state)&&!finished){finished=true;await onRefresh();}
  if(!['complete','cancelled'].includes(task.state))timer=setTimeout(poll,5000);
 }catch(e){fail(e,'Состояние пакетного разбора');if(e.status===404){current=null;try{localStorage.removeItem('career-luna-batch-id');}catch{}}else timer=setTimeout(poll,15000);}}
 try{current=localStorage.getItem('career-luna-batch-id');}catch{}
 return {mount,preview,exportPrompt};
})();

/* Local, linked career analytics. All labels/data are rendered as text. */
const CareerAnalytics=(()=>{
 'use strict';
 let data,request=0,root,controls={},selected=null,mapMode='embeddings',mapScale='data';
 try{if(localStorage.getItem('career-opportunity-mode')==='luna')mapMode='luna';}catch{}
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
 const svg=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
 const colors=CareerCharts.categoryColors;
 function color(key){return colors[key==='other'?colors.length-1:Math.max(0,data.taxonomy.findIndex(c=>c.id===key))%colors.length];}
 function select(label,values,initial=''){
  const wrap=el('label','acField',label),input=el('select');for(const [value,text] of values){const o=el('option','',text);o.value=value;input.append(o);}input.value=initial;wrap.append(input);input.onchange=()=>{selected=null;render();};controls.bar.append(wrap);return input;
 }
 function dateInput(label){const wrap=el('label','acField',label),input=el('input');input.type='date';wrap.append(input);input.onchange=()=>{selected=null;render();};controls.bar.append(wrap);return input;}
 function options(){return {company:controls.company.value,category:controls.category.value,workFormat:controls.workFormat?.value||'',region:controls.region?.value||'',from:controls.from.value,to:controls.to.value,availability:controls.availability.value,fit:controls.fit.value,fitThreshold:Number(controls.threshold.value),alignmentThreshold:Number(controls.alignment.value),focus:controls.focus.checked,focusCategories:controls.focusCategories.filter(c=>c.input.checked).map(c=>c.id)};}
 function panel(title,hint){const p=el('section','acPanel');p.append(el('h2','',title),el('p','muted',hint));return p;}
 function activate(node,label,ids){node.setAttribute('tabindex','0');node.setAttribute('role','button');node.setAttribute('aria-label',label);node.append(svg('title',{},label));const run=()=>{selected={label,ids};skillsScope();drill();controls.drill.scrollIntoView({behavior:'smooth',block:'start'});};node.onclick=run;node.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();run();}};return node;}
 function chart(w,h,label){const s=svg('svg',{viewBox:`0 0 ${w} ${h}`,role:'group','aria-label':label});s.append(svg('title',{},label));return s;}
 function saveFocus(){
  for(const c of controls.focusCategories)c.input.disabled=!controls.focus.checked;
  try{localStorage.setItem('career-analytics-focus-v1',JSON.stringify({enabled:controls.focus.checked,categories:controls.focusCategories.filter(c=>c.input.checked).map(c=>c.id)}));}catch{}
 }
 function selectCategory(key){controls.category.value=key;if(key&&controls.focus.checked&&!controls.focusCategories.some(c=>c.id===key&&c.input.checked)){controls.focus.checked=false;saveFocus();}selected=null;render();}
 function focusControls(){
  let saved={enabled:true,categories:['pretraining','post_training','diffusion','cuda','apple','research']};
  try{const old=JSON.parse(localStorage.getItem('career-analytics-focus-v1'));if(old&&typeof old.enabled==='boolean'&&Array.isArray(old.categories))saved=old;}catch{}
  saved.categories=[...new Set(saved.categories.map(id=>id==='bureau1440'?'space':id))];
  const field=el('fieldset','acFocus'),legend=el('legend','','Мой фокус');field.append(legend);
  const master=el('label','acFocusMaster'),input=el('input');input.type='checkbox';input.checked=saved.enabled;master.append(input,el('span','','Фокус на моих направлениях'));controls.focus=input;field.append(master);
  const list=el('div','acFocusOptions');controls.focusCategories=[];
  for(const c of data.taxonomy){const label=el('label'),check=el('input');check.type='checkbox';check.checked=saved.categories.includes(c.id);check.disabled=!input.checked;label.append(check,el('span','',c.label));list.append(label);controls.focusCategories.push({id:c.id,input:check});check.onchange=()=>{saveFocus();selected=null;render();};}
  input.onchange=()=>{saveFocus();selected=null;render();};field.append(list,el('p','muted','Включаем вакансию, если совпал хотя бы один отмеченный тег — даже когда основная категория другая. Состав архива и рейтинг не изменяются.'));root.append(field);
 }
 function mount(){
  root=document.getElementById('analytics');root.replaceChildren();const hero=el('div','acHero');hero.append(el('p','eyebrow','CAREER INTELLIGENCE'),el('h2','','От обнаруженной вакансии — к следующему шагу'),el('p','','Воронка, карьерная карта и история вашей выборки. Нажмите на поток или точку, чтобы увидеть вакансии.'));root.append(hero);
  focusControls();
  controls.bar=el('div','acFilters');root.append(controls.bar);
  controls.cv=select('Резюме',data.resumes.map(r=>[r.id,r.title]),data.resume.id);
  controls.cv.onchange=()=>enter(controls.cv.value).catch(error);
  controls.company=select('Компания',[['','Все компании'],...[...new Set(data.rows.map(r=>r.company))].sort().map(c=>[c,c||'Не указана'])]);
  controls.category=select('Направление / тег',[['','Все направления'],...data.taxonomy.map(c=>[c.id,c.label])]);controls.category.onchange=()=>selectCategory(controls.category.value);
  controls.workFormat=select('Формат работы',[['','Все форматы'],['remote','Удалёнка'],['hybrid','Гибрид'],['onsite','Офис']]);
  controls.region=select('Регион',[['','Все локации'],['moscow','Москва'],['spb','Санкт-Петербург'],['rf','Регионы РФ'],['global','Global / Зарубеж']]);
  controls.availability=select('Активность',[['','Все наблюдения'],['active','Проверена активность'],['unknown','Не проверена'],['closed','Закрытие подтверждено']]);
  controls.from=dateInput('Впервые обнаружены с');controls.to=dateInput('По');
  controls.fit=select('Подтверждения в CV',[['','Любой разбор'],['known','Есть Luna-разбор'],['high','Выше порога'],['unknown','Разбора нет']]);
  controls.threshold=select('Порог требований',[['40','40%'],['60','60%'],['80','80%']],'60');
  controls.alignment=select('Порог близости к цели',[['0.3','0,3'],['0.4','0,4'],['0.5','0,5']],'0.4');
  const salary=select('Зарплата',[['','Нет структурированных данных']]);salary.disabled=true;
  const reset=el('button','secondary','Сбросить фильтры');reset.onclick=()=>{for(const k of ['company','category','workFormat','region','availability','from','to','fit'])controls[k].value='';controls.focus.checked=false;saveFocus();selected=null;render();};controls.bar.append(reset);
  controls.unclassified=el('p','acUnclassified');root.append(controls.unclassified);
  controls.status=el('p','acStatus');controls.status.setAttribute('role','status');root.append(controls.status);const learning=el('button','secondary','Навыки и обучение → по текущей выборке');learning.onclick=()=>{skillsScope();setTab('learning');};root.append(learning);
  const tabs=el('div','acModes');controls.mode=el('select');controls.mode.setAttribute('aria-label','Режим аналитики');for(const [v,t] of [['funnel','Market → Candidate Funnel'],['evolution','Market Evolution']]){const o=el('option','',t);o.value=v;controls.mode.append(o);}controls.mode.onchange=render;tabs.append(controls.mode);controls.share=el('select');controls.share.setAttribute('aria-label','Количество или доля');for(const [v,t] of [['count','Количество'],['share','Доля, %']]){const o=el('option','',t);o.value=v;controls.share.append(o);}controls.share.onchange=render;tabs.append(controls.share);root.append(tabs);
  controls.main=el('div');controls.map=el('div');controls.batch=el('div');controls.batch.id='analyticsBatch';controls.skills=el('div');controls.intelligence=el('div');controls.drill=el('section','acPanel');controls.drill.id='analyticsVacancies';root.append(controls.main,controls.map,controls.batch,controls.skills,controls.intelligence,controls.drill);CareerBatch.mount(controls.batch,()=>refreshRows());mountSkills(controls.intelligence);
  const method=el('details','acMethod');method.append(el('summary','','Как читать данные и оценки'));const list=el('ul');for(const text of data.methodology)list.append(el('li','',text));method.append(list);root.append(method);
 }
 let skillsLoading;
 async function mountSkills(element){
  try{
   if(typeof CareerSkills==='undefined'){
    if(!skillsLoading)skillsLoading=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/assets/career-skills.js?v=1';script.onload=()=>typeof CareerSkills==='undefined'?reject(Error('Модуль навыков не инициализирован. Обновите страницу.')):resolve();script.onerror=()=>{script.remove();reject(Error('Модуль навыков не загружен. Проверьте, что локальный сервис обновлён, затем повторите.'));};document.head.append(script);}).catch(e=>{skillsLoading=null;throw e;});
    await skillsLoading;
   }
   if(!element.isConnected)return;
   await CareerSkills.mount(element);skillsScope();
  }catch(e){if(element.isConnected){showDiagnostic(e,'Загрузка модуля навыков',element);const retry=el('button','secondary','Повторить загрузку навыков');retry.onclick=()=>{element.replaceChildren();mountSkills(element);};element.append(retry);}}
 }
 function skillsScope(){if(typeof CareerSkills==='undefined')return;CareerSkills.update({resume_id:data.resume.id,goal:data.resume.goal,model:data.resume.model,filters:options(),available_vacancies:CareerCharts.filters(data.rows,options()),vacancy_ids:selected?selected.ids:null});}
 function render(){
  if(!data)return;const f=options(),rows=CareerCharts.filters(data.rows,f);controls.status.textContent=(f.focus?'Фокус · ':'')+rows.length+' из '+data.rows.length+' вакансий · '+data.resume.title+' · '+data.resume.model+' · данные на '+new Date(data.as_of).toLocaleString('ru-RU');
  const unknown=data.rows.filter(r=>r.category==='other'),short=unknown.filter(r=>r.quality!=='full').length;controls.unclassified.textContent='Не классифицировано: '+unknown.length+' (из них '+short+' без полного описания). По названию и доступному тексту направление пока не определено; это не оценка соответствия вашему CV. Снимите «Фокус», чтобы увидеть весь архив.';
  controls.share.hidden=controls.mode.value!=='evolution';controls.main.replaceChildren();controls.main.append(controls.mode.value==='evolution'?evolution(f):funnel(rows,f));map(rows,f);skills(rows);skillsScope();drill(rows);
 }
 function filterCaption(f){const parts=[];if(f.company)parts.push('Компания: '+f.company);if(f.category)parts.push('Направление: '+(data.taxonomy.find(c=>c.id===f.category)?.label||f.category));if(f.focus)parts.push('Фокус: '+f.focusCategories.map(k=>data.taxonomy.find(c=>c.id===k)?.label||k).join(', '));if(f.availability)parts.push('Активность: '+f.availability);if(f.workFormat)parts.push('Формат: '+f.workFormat);if(f.region)parts.push('Регион: '+f.region);if(f.fit)parts.push('Luna: '+f.fit+' · порог '+f.fitThreshold+'%');if(f.from||f.to)parts.push('Период: '+(f.from||'…')+' — '+(f.to||'…'));return parts.length?parts.join(' · '):'Все вакансии текущей выборки';}
 async function downloadFunnelPNG(source,count,meta={}){
  const cloned=source.cloneNode(true),view=source.viewBox.baseVal,legend=meta.legend||[],notes=meta.notes||[],footer=notes.length*22+Math.ceil(legend.length/3)*25+(legend.length?35:15),header=138,geometry=CareerCharts.exportGeometry(view.width,view.height+footer+header-90);
  // Presentation attributes make the SVG independent of the page's CSS.
  const originals=[source,...source.querySelectorAll('*')],copies=[cloned,...cloned.querySelectorAll('*')];
  for(let i=0;i<originals.length;i++){const style=getComputedStyle(originals[i]);for(const property of ['fill','stroke','stroke-width','fill-opacity','stroke-opacity','font-family','font-size','font-weight','text-anchor']){const value=style.getPropertyValue(property);if(value)copies[i].setAttribute(property,value);}for(const name of ['tabindex','role','class'])copies[i].removeAttribute(name);}
  cloned.setAttribute('xmlns','http://www.w3.org/2000/svg');cloned.setAttribute('width',view.width);cloned.setAttribute('height',view.height);
  const serialized=new XMLSerializer().serializeToString(cloned),img=new Image();
  await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('Не удалось преобразовать SVG в PNG.'));img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(serialized);});
  const canvas=document.createElement('canvas');canvas.width=geometry.width;canvas.height=geometry.height;const ctx=canvas.getContext('2d');if(!ctx)throw Error('Браузер не поддерживает экспорт Canvas.');
  ctx.scale(geometry.scale,geometry.scale);ctx.fillStyle='#fff';ctx.fillRect(0,0,view.width,view.height+footer+header);ctx.fillStyle='#23483b';ctx.font='bold 25px sans-serif';ctx.fillText(meta.title||'Воронка возможностей',25,34);ctx.font='14px sans-serif';
  const subtitle=meta.subtitle||(data.resume.title+' · '+count+' записей');const wrapped=(text,max)=>{const lines=[];let line='';for(const word of String(text).split(/\s+/)){if(line&&ctx.measureText(line+' '+word).width>max){lines.push(line);line=word;}else line+=(line?' ':'')+word;}if(line)lines.push(line);return lines;};
  for(const [i,line] of wrapped(subtitle,view.width-50).slice(0,3).entries())ctx.fillText(line,25,59+i*18);ctx.fillStyle='#718477';ctx.font='12px sans-serif';ctx.fillText('Сохранённая выборка · '+new Date().toLocaleString('ru-RU'),25,123);ctx.drawImage(img,0,header,view.width,view.height);
  let lineY=header+view.height+22;ctx.font='12px sans-serif';for(const note of notes){ctx.fillStyle='#62776a';ctx.fillText(note,25,lineY,view.width-50);lineY+=22;}
  if(legend.length){ctx.fillStyle='#496252';ctx.fillText('Цвет — основная специализация',25,lineY+3);lineY+=24;for(const [i,item] of legend.entries()){const x=25+(i%3)*(view.width-50)/3,y=lineY+Math.floor(i/3)*25;ctx.fillStyle=item.color;ctx.fillRect(x,y-10,10,10);ctx.fillStyle='#3b5947';ctx.fillText(item.label+' · '+item.count,x+17,y,(view.width-90)/3);}}

  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('Браузер не создал PNG.');
  const url=URL.createObjectURL(blob),link=el('a'),now=new Date(),date=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');link.href=url;link.download=(meta.prefix||'career-funnel')+'-'+date+'.png';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return {preview:canvas.toDataURL('image/png'),name:link.download,width:canvas.width,height:canvas.height};
 }
 function showPNGPreview(panel,result){let box=panel.querySelector('.acPNGPreview');if(!box){box=el('details','acPNGPreview');panel.append(box);}box.replaceChildren(el('summary','','PNG готов · '+result.width+' × '+result.height+' · предпросмотр'));const image=el('img');image.src=result.preview;image.alt='Экспорт диаграммы с подписями и делениями осей';image.style.width='100%';image.style.height='auto';box.append(image);box.open=true;}
 function funnel(rows,f){
  const p=panel('Воронка возможностей','Ширина — число вакансий. Одна запись проходит через каждый столбец один раз. «Разбора нет» и «Нет отклика» — отдельные состояния, а не отказы.');
  if(!rows.length){p.append(el('p','acEmpty','Нет вакансий по выбранным фильтрам.'));return p;}
  let layout=CareerCharts.funnel(rows,data.taxonomy,f);const s=chart(1450,layout.height,'Интерактивная воронка вакансий');
  function draw(width=1450){layout=CareerCharts.funnel(rows,data.taxonomy,{...f,width});s.replaceChildren(svg('title',{},'Интерактивная воронка вакансий'));s.setAttribute('viewBox',`0 0 ${width} ${layout.height}`);
  ['Наблюдаемая выборка','Специализация','Требования CV','Карьерная цель','Отклики и этапы'].forEach((label,i)=>s.append(svg('text',{x:25+i*(width-318)/4,y:23,class:'acColumn'},label)));
  const nodes=new Map(layout.nodes.map(n=>[n.id,n]));
  for(const link of layout.links){const a=nodes.get(link.source),b=nodes.get(link.target),fill=a.layer===1?color(a.key):b.layer===1?color(b.key):'#80a598';const path=svg('path',{d:link.path,fill,'fill-opacity':.28,class:'acFlow'});s.append(activate(path,a.label+' → '+b.label+': '+link.value,link.ids));}
  for(const n of layout.nodes){const g=svg('g',{class:'acNode'});g.append(svg('rect',{x:n.x,y:n.y,width:20,height:Math.max(.5,n.h),rx:3,fill:n.layer===1?color(n.key):n.key==='unknown'?'#9aa7a3':'#285b4a'}));
   const label=svg('text',{x:n.x+28,y:n.y+n.h/2-2,class:'acNodeText'});label.append(svg('tspan',{x:n.x+28},n.label.length>33?n.label.slice(0,31)+'…':n.label),svg('tspan',{x:n.x+28,dy:17,class:'acNodeCount'},n.ids.length+' вакансий'));g.append(label);s.append(activate(g,n.label+': '+n.ids.length,n.ids));}}
  draw();
  const toolbar=el('div','acMapActions'),full=el('button','secondary','На весь экран'),png=el('button','secondary','Скачать PNG');
  full.onclick=async()=>{try{if(document.fullscreenElement===p)await document.exitFullscreen();else await p.requestFullscreen();}catch(e){showDiagnostic(e,'Полноэкранная воронка',p);}};
  png.onclick=async()=>{png.disabled=true;try{await downloadFunnelPNG(s,rows.length);}catch(e){showDiagnostic(e,'Экспорт воронки PNG',p);}finally{png.disabled=false;}};toolbar.append(full,png);p.append(toolbar);
  const zoomTools=el('div','acFunnelZoom'),out=el('button','secondary','−'),level=el('span','acZoomLevel','100%'),inside=el('button','secondary','+'),reset=el('button','secondary','Вписать'),wheelLabel=el('label','acWheelZoom'),wheelToggle=el('input');wheelToggle.type='checkbox';wheelLabel.append(wheelToggle,el('span','','Зум прокруткой'));out.setAttribute('aria-label','Уменьшить воронку');inside.setAttribute('aria-label','Увеличить воронку');level.setAttribute('aria-live','polite');zoomTools.append(out,level,inside,reset,wheelLabel,el('span','muted','Щипок — зум · два пальца — прокрутка · можно перетаскивать'));toolbar.append(zoomTools);
  const box=el('div','acSankey');box.append(s);p.append(box,el('a','acJump','Список вакансий ↓'));p.lastChild.href='#analyticsVacancies';
  const zoom=CareerCharts.funnelZoom(box,s,value=>{level.textContent=Math.round(value*100)+'%';out.disabled=value<=.5;inside.disabled=value>=4;});out.onclick=()=>zoom.zoomBy(1/1.25);inside.onclick=()=>zoom.zoomBy(1.25);reset.onclick=()=>zoom.reset();
  wheelToggle.onchange=()=>zoom.setWheelZoom(wheelToggle.checked);
  p.onfullscreenchange=()=>{const active=document.fullscreenElement===p;full.textContent=active?'Выйти из полного экрана · Esc':'На весь экран';draw(active?Math.max(1450,layout.height*box.clientWidth/Math.max(1,box.clientHeight)):1450);zoom.setActive(active);};return p;
 }
 function map(rows,f){
  controls.map.replaceChildren();const view=CareerCharts.opportunityMap(rows,mapMode,f),known=view.points;
  const p=panel('Career Opportunity Map',mapMode==='luna'?'X — подтверждение требований по сохранённому Luna-разбору. Y — близость к карьерной цели.':'X — семантическая близость к CV. Y — близость к карьерной цели. Обе оценки берутся из готовых embeddings; они не измеряют владение навыками.');
  const modes=el('div','acMapModes');modes.setAttribute('role','group');modes.setAttribute('aria-label','Оценки на карте');
  for(const [value,title] of [['embeddings','Обзор по embeddings'],['luna','Подробный разбор Luna']]){const b=el('button','secondary',title);b.setAttribute('aria-pressed',String(mapMode===value));b.onclick=()=>{mapMode=value;try{localStorage.setItem('career-opportunity-mode',value);}catch{}map(rows,f);};modes.append(b);}p.append(modes);
  const scales=el('div','acMapModes');scales.setAttribute('role','group');scales.setAttribute('aria-label','Масштаб карты');
  for(const [value,title] of [['data','По диапазону данных'],['full','Полная шкала']]){const b=el('button','secondary',title);b.setAttribute('aria-pressed',String(mapScale===value));b.onclick=()=>{mapScale=value;map(rows,f);};scales.append(b);}p.append(scales);
  const actions=el('div','acMapActions'),luna=el('button','','Luna: разобрать топ-50'),copy=el('button','secondary','Скопировать топ-50 + CV · без API');luna.onclick=()=>CareerBatch.preview(data,options());copy.onclick=()=>CareerBatch.exportPrompt(data,options());actions.append(luna,copy);p.append(actions);
  if(!known.length)p.append(el('p','acEmpty',mapMode==='luna'?'Нет вакансий с обеими актуальными оценками. Выберите обзор по embeddings или выполните разбор Luna.':'Нет актуальных оценок близости одновременно к CV и цели. Обновите рейтинг или выберите карьерную цель; просмотр карты API не вызывает.'));
  else{
   const bounds=CareerCharts.mapViewport(view,mapScale),s=chart(1000,430,'Карта: '+view.xLabel+' и близость к цели'),left=80,right=970,top=40,bottom=365,x=v=>left+(right-left)*(v-bounds.x.min)/(bounds.x.max-bounds.x.min),y=v=>bottom-(bottom-top)*(v-bounds.y.min)/(bounds.y.max-bounds.y.min);
   const tx=Math.max(left,Math.min(right,x(view.xThreshold))),ty=Math.max(top,Math.min(bottom,y(f.alignmentThreshold)));
   s.append(svg('rect',{x:left,y:top,width:right-left,height:bottom-top,fill:'#f7f9f6'}),svg('rect',{x:tx,y:top,width:right-tx,height:ty-top,fill:'#e3f1df'}));
   for(const v of bounds.xTicks){s.append(svg('line',{x1:x(v),y1:top,x2:x(v),y2:bottom,stroke:'#dce5df'}),svg('text',{x:x(v),y:bottom+23,'text-anchor':'middle',class:'acAxis'},view.formatX(v)));}
   for(const v of bounds.yTicks)s.append(svg('text',{x:left-12,y:y(v)+4,'text-anchor':'end',class:'acAxis'},v.toFixed(mapScale==='full'?1:2)));
   if(f.alignmentThreshold>=bounds.y.min&&f.alignmentThreshold<=bounds.y.max)s.append(svg('line',{x1:left,y1:y(f.alignmentThreshold),x2:right,y2:y(f.alignmentThreshold),stroke:'#9daf9e','stroke-dasharray':'5 5'}));
   s.append(svg('text',{x:650,y:30,class:'acAxis'},mapMode==='luna'?'Подтверждения + карьерная цель':'Близость к CV + карьерная цель'),svg('text',{x:500,y:415,'text-anchor':'middle',class:'acAxis'},view.xLabel),svg('text',{x:18,y:220,transform:'rotate(-90 18 220)','text-anchor':'middle',class:'acAxis'},'Близость к карьерной цели'));
   for(const r of known){const c=svg('circle',{cx:x(r.x),cy:y(r.y),r:3.5,fill:color(r.category),'fill-opacity':.68,stroke:'#fff','stroke-width':.7,class:'acPoint'});const fmt=r.work_format==='remote'?'Удалёнка':r.work_format==='hybrid'?'Гибрид':r.work_format==='onsite'?'Офис':'';const loc=r.location||(r.region==='moscow'?'Москва':r.region==='spb'?'СПб':r.region==='rf'?'РФ':r.region==='global'?'Global':'');const metaLoc=[fmt,loc].filter(Boolean).join(', ');s.append(activate(c,r.title+(metaLoc?' ('+metaLoc+')':'')+' · '+view.xLabel+': '+view.formatX(r.x)+' · цель '+r.y,[r.id]));}p.append(s);const png=el('button','secondary','Скачать PNG · с осями');png.onclick=async()=>{png.disabled=true;try{const legend=[...new Set(known.map(r=>r.category))].map(key=>({label:data.taxonomy.find(c=>c.id===key)?.label||key,color:color(key),count:known.filter(r=>r.category===key).length}));const result=await downloadFunnelPNG(s,known.length,{title:'Career Opportunity Map',prefix:'career-opportunity-map',subtitle:data.resume.title+' · '+(mapMode==='luna'?'Luna: подтверждения требований':'Embeddings: семантическая близость'),legend,notes:['На карте: '+known.length+' из '+view.total+' · не хватает одной или обеих оценок: '+view.missing+' · шкала: '+(mapScale==='data'?'диапазон данных':'полная'),filterCaption(f),'Семантическая близость не измеряет владение навыками. Данные на '+new Date(data.as_of).toLocaleString('ru-RU')]});showPNGPreview(p,result);}catch(e){showDiagnostic(e,'Экспорт карты PNG',p);}finally{png.disabled=false;}};actions.prepend(png);
  }
  const counts=el('p','muted','Цвет — основная специализация. На карте: '+known.length+' из '+view.total+'. Без одной или обеих оценок: '+view.missing+'. Размер точек одинаковый; зарплаты не сохранены. Линейный масштаб: '+(mapScale==='data'?'приближен по всем точкам выборки':'полный диапазон')+'. Значения и порядок рейтинга не меняются. Переключение не вызывает API.');counts.setAttribute('role','status');counts.setAttribute('aria-live','polite');p.append(counts);controls.map.append(p);
 }
 function evolution(f){
  const p=panel('Market Evolution','Обнаруженные вакансии без подтверждённого закрытия, по полученным снимкам. Это история нашей выборки, а не оценка всего рынка. Исчезновение из выдачи не считается закрытием.');
  const cohort=CareerCharts.filters(data.rows,{...f,category:''}),share=controls.share.value==='share',points=CareerCharts.evolution(data.history,cohort.map(r=>r.id),f.category,share);
  if(points.length<2){p.append(el('p','acEmpty','История начинается '+(data.first_observation?new Date(data.first_observation).toLocaleDateString('ru-RU'):'после первого сбора')+'. Для временной диаграммы нужны наблюдения хотя бы за два месяца. Прошлые значения не восстанавливаются из текущих вакансий.'));return p;}
  const s=chart(1000,380,'Динамика наблюдаемой структуры вакансий'),left=65,right=970,top=25,bottom=315,max=share?100:Math.max(1,...points.map(v=>v.total)),x=i=>left+(right-left)*i/(points.length-1),y=v=>bottom-(bottom-top)*v/max;let baseline=points.map(()=>0);
  for(const cat of data.taxonomy){const topLine=points.map((p,i)=>baseline[i]+(p.values[cat.id]||0));const path='M'+topLine.map((v,i)=>x(i)+','+y(v)).join(' L')+' L'+baseline.map((v,i)=>x(i)+','+y(v)).reverse().join(' L')+' Z';const ids=[...new Set(points.flatMap(p=>p.ids[cat.id]||[]))].filter(id=>cohort.some(r=>r.id===id));s.append(activate(svg('path',{d:path,fill:color(cat.id),'fill-opacity':.8,class:'acArea'}),cat.label,ids));baseline=topLine;}
  for(let i=0;i<points.length;i++)if(i%Math.ceil(points.length/6)===0||i===points.length-1)s.append(svg('text',{x:x(i),y:bottom+25,'text-anchor':'middle',class:'acAxis'},points[i].month));
  s.append(svg('text',{x:left-10,y:top+5,'text-anchor':'end',class:'acAxis'},max+(share?'%':'')),svg('text',{x:left-10,y:bottom,'text-anchor':'end',class:'acAxis'},'0'));p.append(s);
  const legend=el('div','acLegend');data.taxonomy.forEach((c,i)=>{const item=el('button','secondary acLegendItem acColor'+(c.id==='other'?colors.length-1:i%colors.length),c.label);item.onclick=()=>{selectCategory(c.id);};legend.append(item);});p.append(legend,el('p','muted','Последний месяц неполный. Изменения долей не означают переход вакансий между специализациями. Фильтры применяются к текущему составу выбранной когорты.'));return p;
 }
 function skills(rows){
  controls.skills.replaceChildren();const p=panel('Подтверждённые компетенции и исследования','Профиль по доказательствам из текущих разборов, а не оценка уровня Research Scientist. Учебные проекты и курсы учитываются отдельно от практики.');
  p.append(el('p','muted','Актуальных разборов в выборке: '+rows.filter(r=>r.analysis_key).length+'. Обновления CV требуют нового разбора; переход по ссылке GitHub не запускает аудит репозитория.'));
  for(const text of data.skills.learning_evidence)p.append(el('blockquote','acLearning','📚 Упоминание обучения в CV: '+text));
  if(!data.skills.learning_evidence.length)p.append(el('p','muted','Курс MIT 6.S184 / Flow Matching будет показан здесь, если он указан в выбранном CV или сохранённых уточнениях. Сам интерес к направлению не доказывает владение.'));
  const dims=new Map();for(const r of rows)for(const d of r.dimensions||[]){const item=dims.get(d.id)||{label:d.label,confirmed:0,partial:0,studying:0,total:0};item.total+=d.requirements;for(const key of ['confirmed','partial','studying'])item[key]+=d.statuses[key]||0;dims.set(d.id,item);}
  if(dims.size){const table=el('table','acSkillsTable'),head=el('tr');for(const text of ['Направление требований','Практика','Частично','Изучение','Всего'])head.append(el('th','',text));table.append(head);for(const d of dims.values()){const tr=el('tr');for(const text of [d.label,d.confirmed,d.partial,d.studying,d.total])tr.append(el('td','',text));table.append(tr);}p.append(table);}
  for(const link of data.skills.github_links)p.append(external(link,'Исследования на GitHub ↗'));
  const action=el('button','secondary','Открыть выбранное резюме');action.onclick=()=>{document.getElementById('analysisCV').value=data.resume.id;setTab('resume');};p.append(action);controls.skills.append(p);
 }
 function drill(rows=CareerCharts.filters(data.rows,options())){
  const p=controls.drill;p.replaceChildren();const selectedIds=selected?new Set(selected.ids):null;const items=rows.filter(r=>!selectedIds||selectedIds.has(r.id));p.append(el('h2','',selected?selected.label:'Вакансии в выборке'),el('p','muted',items.length+' записей · нажмите карточку для текста, цитат Luna и подготовки отклика.'));let count=0;
   const list=el('div','acVacancies'),more=el('button','secondary','Показать ещё');const append=()=>{for(const r of items.slice(count,count+30)){const row=el('article','acVacancy'),body=el('div');const fmt=r.work_format==='remote'?'Удалёнка':r.work_format==='hybrid'?'Гибрид':r.work_format==='onsite'?'Офис':'';const loc=r.location||(r.region==='moscow'?'Москва':r.region==='spb'?'СПб':r.region==='rf'?'РФ':r.region==='global'?'Global':'');const metaLoc=[fmt,loc].filter(Boolean).join(', ');body.append(el('h3','',r.title),el('p','muted',r.company+(metaLoc?' · '+metaLoc:'')+' · '+CareerCharts.stageLabels[r.stage]),el('p','acEvidence','Теги: '+r.tags.map(k=>data.taxonomy.find(c=>c.id===k)?.label||k).join(' / ')));for(const evidence of (r.classification_evidence||[]))body.append(el('p','acEvidence',(data.taxonomy.find(c=>c.id===evidence.category)?.label||evidence.category)+': «'+evidence.quote+'»'+(evidence.basis?' · '+evidence.basis:'')));row.append(body);const actions=el('div','acVacancyActions'),open=el('button','secondary','Карточка и разбор');open.onclick=()=>{document.getElementById('analysisCV').value=data.resume.id;setTab('vacancy');openDetail('vacancy',r.id).catch(error);};actions.append(manualApplicationButton(r,()=>refreshRows()),open,external(r.url,'Источник ↗'));row.append(actions);list.append(row);}count+=30;more.hidden=count>=items.length;};more.onclick=append;p.append(list,more);append();
 }
 async function refreshRows(){const context=data.resume;const updated=await api('analytics?'+new URLSearchParams({resume_id:context.id,goal:context.goal,model:context.model}),undefined,60000);if(data.resume.id===context.id&&data.resume.goal===context.goal&&data.resume.model===context.model){data={...updated,resumes:data.resumes};render();}}
 function error(e){showDiagnostic(e,'Карьерная аналитика',root||document.getElementById('notice'));}
 async function enter(resumeId){
  const n=++request,params=new URLSearchParams({resume_id:resumeId||document.getElementById('analysisCV').value,goal:summaryData?.goal||'',model:document.getElementById('embeddingModel').value});root=document.getElementById('analytics');root.textContent='Загружаю сохранённую аналитику…';
  try{const result=await api('analytics?'+params,undefined,60000);if(n!==request)return;const resumes=(await api('entities?kind=resume&limit=200')).items;if(n!==request)return;data={...result,resumes};selected=null;mount();render();}catch(e){if(n===request){root.replaceChildren();error(e);}}
 }
 return {enter,exportChartPNG:downloadFunnelPNG,showPNGPreview};
})();
