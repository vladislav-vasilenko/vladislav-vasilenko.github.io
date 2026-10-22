'use strict';
const PortfolioPublication=(()=>{
 async function mount(root){
  const state=await api('portfolio-publication');root.replaceChildren();
  root.append(make('p','muted','Источник — основное полное HH-резюме. Публикуются только введение «Обо мне», компании, роли, даты, описания опыта и подтверждённые навыки со ссылками на публичные GitHub-проекты. Контакты и внутренние факты не переносятся.'));
  const label=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';check.checked=!!state.enabled;
  label.append(check,document.createTextNode(' Обновлять сайт автоматически при изменении основного HH-резюме / введения / подтверждений'));
  check.onchange=async()=>{check.disabled=true;try{await api('portfolio-publication',{op:'configure',enabled:check.checked});}catch(e){check.checked=!check.checked;notice(e.message);}finally{check.disabled=false;}};
  root.append(label);
  if(state.published_at)root.append(make('p','muted','Опубликовано: '+date(state.published_at)+' · блоков опыта '+state.experience_count+' · навыков '+state.skill_count));
  if(state.error)root.append(make('p','githubImportWarning',state.error));
  const actions=make('div','githubImportActions'),preview=make('button','secondary','Предпросмотр и редактирование'),publish=make('button','secondary','Обновить сайт сейчас'),body=make('div');
  preview.type=publish.type='button';
  preview.onclick=async()=>{preview.disabled=true;try{const data=await api('portfolio-publication',{op:'preview'});body.replaceChildren();body.append(make('h3','',data.resume_title),make('p','muted','Из основного HH: '+data.payload.experience.length+' блоков. Язык источника: '+data.payload.source.language.toUpperCase()+'. Для другого языка — «Ожидается перевод», оригинал доступен отдельно.'));
   await aboutEditor(body,data);
   visualEditor(body).catch(e=>notice(e.message));
   const experienceTitle=make('h3','','Опыт из основного HH-резюме');body.append(experienceTitle);
   for(const item of data.payload.experience){const card=make('details');card.append(make('summary','',item.company+' · '+item.role+' · '+item.period),make('pre','flowText',item.description));body.append(card);}
   const title=make('h3','','Подтверждённые навыки · для HH и портфолио');body.append(title);
   if(!data.payload.confirmed_skills.length)body.append(make('p','muted','Пока нет подтверждённых практических навыков со ссылками на GitHub. Добавьте проект/лабораторную и отметьте подтверждение в карьерной траектории. Само упоминание в CV не засчитывается.'));
   else for(const skill of data.payload.confirmed_skills){const line=make('p');line.append(make('strong','',skill.label+' '));for(const link of skill.links)line.append(external(link.url,link.label+' ↗'),' ');body.append(line);}
   const copy=make('button','secondary','Скопировать блок навыков для HH');copy.onclick=()=>navigator.clipboard.writeText(data.skills_text).then(()=>notice('Блок навыков скопирован.'));copy.disabled=!data.payload.confirmed_skills.length;body.append(copy);
  }catch(e){notice(e.message);}finally{preview.disabled=false;}};
  publish.onclick=async()=>{publish.disabled=true;publish.textContent='Публикую…';try{const result=await api('portfolio-publication',{op:'publish'},180000);if(result.phase==='error')throw Error(result.error);notice(result.phase==='publishing'?'Публикация уже выполняется.':result.phase==='up_to_date'?'Публичный опыт уже актуален.':'JSON опубликован. GitHub Actions собирает обновление сайта.');await mount(root);}catch(e){notice(e.message);}finally{publish.disabled=false;publish.textContent='Обновить сайт сейчас';}};
  actions.append(preview,publish);root.append(actions,body,external('https://vladislav-vasilenko.github.io/','Открыть публичное портфолио ↗'));
 }
 async function aboutEditor(host,data){
  const box=make('section','portfolioAboutEditor');box.append(make('h3','','Введение под шапкой резюме'));
  if(data.payload.source.url)box.append(external(data.payload.source.url,'Исходное HH-резюме ↗'));
  box.append(make('p','muted','По умолчанию синхронизируется «Обо мне» из HH. Здесь можно сохранить проверенную редакцию для сайта. HH меняется отдельно: скопируйте текст, обновите его на HH и импортируйте свежий снимок через расширение.'));
  if(data.about_needs_review)box.append(make('p','githubImportWarning','Источник HH или основное резюме изменилось. Прежнюю редакцию нужно сверить; сейчас используется свежий текст HH.'));
  const label=make('label','','Текст введения · без заголовка «Обо мне»'),text=make('textarea');text.rows=9;text.maxLength=6000;text.value=data.payload.about?.text||'';label.append(text);box.append(label);
  const language=make('select');for(const code of ['ru','en']){const option=make('option','',code.toUpperCase());option.value=code;language.append(option);}language.value=data.payload.about?.language||data.payload.source.language;language.onchange=()=>{text.value=data.payload.about?.translations?.[language.value]||(language.value===data.payload.about?.language?data.payload.about.text:'');check.checked=false;};
  const languageLabel=make('label','','Язык текста ');languageLabel.append(language);box.append(languageLabel);
  const review=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';review.append(check,document.createTextNode(' Я проверил формулировки и разрешаю использовать их на публичном сайте'));box.append(review);
  const actions=make('div','githubImportActions'),save=make('button','secondary','Сохранить редакцию для сайта'),copy=make('button','secondary','Скопировать для HH'),reset=make('button','secondary','Использовать текст HH');
  save.onclick=async()=>{save.disabled=true;try{await api('portfolio-publication',{op:'save_about',text:text.value,language:language.value,basis:data.about_basis,reviewed:check.checked});notice('Редакция сохранена. Используйте «Обновить сайт сейчас» или автопубликацию.');}catch(e){notice(e.message);}finally{save.disabled=false;}};
  copy.onclick=()=>navigator.clipboard.writeText(text.value).then(()=>notice('Введение скопировано для HH.'));
  reset.onclick=async()=>{await api('portfolio-publication',{op:'save_about',reset:true});text.value=data.about_source;check.checked=false;notice('Сайт снова использует исходное введение HH.');};
  actions.append(save,copy,reset);box.append(actions);
  const tools=make('details');tools.append(make('summary','','Обсудить введение: траектория, текущий опыт и GitHub'));
  const activity=make('button','secondary','Обновить публичную активность GitHub'),prompt=make('button','secondary','Скопировать контекст для LLM · без API'),results=make('div');
  activity.onclick=async()=>{activity.disabled=true;activity.textContent='Читаю GitHub…';try{const value=await api('portfolio-publication',{op:'github_activity'},240000);results.replaceChildren(make('p','muted','Проверено: '+date(value.checked_at)+'. Активность репозитория не подтверждает личное авторство или владение навыком.'));for(const item of value.items){results.append(external(item.url,item.url.split('/').pop()+' ↗'));for(const commit of item.commits)results.append(make('p','muted',date(commit.date)+' · '+commit.message));}}catch(e){notice(e.message);}finally{activity.disabled=false;activity.textContent='Обновить публичную активность GitHub';}};
  prompt.onclick=async()=>{const context=await api('portfolio-publication',{op:'context'});context.current_draft=text.value;await navigator.clipboard.writeText(context.instruction+'\n\n'+JSON.stringify(context,null,2));notice('Контекст для обсуждения скопирован. API модели не вызывается.');};
  const toolActions=make('div','githubImportActions');toolActions.append(activity,prompt);tools.append(make('p','muted','Только публичные репозитории, найденные в описании опыта HH, до 6 проектов и 3 последних коммитов. Приватные репозитории и секреты не включаются. Карьерная цель и этот контекст остаются в локальном сервисе до вашего копирования.'),toolActions,results);box.append(tools);host.append(box);
 }
 async function visualEditor(host){
  const details=make('details');details.append(make('summary','','Публичные визуализации · выборка и предпросмотр JSON'));const body=make('div');details.append(body);host.append(details);let ready=false;
  details.ontoggle=async()=>{if(!details.open||ready)return;ready=true;try{
   const data=await api('portfolio-publication',{op:'visual_choices'}),cfg=data.settings||{};
   body.append(make('p','muted','SQLite остаётся на этом компьютере. На сайт передаются только выбранное направление, этапы, названия навыков, публичные лаборатории и обезличенная сводка рынка. История откликов, оценки Luna, цитаты, контакты и заметки исключены.'));
   const fields={};for(const [key,title] of [['enabled','Синхронизировать публичные визуализации'],['trajectory','Направление исследований и этапы'],['market','Карта и потоки обезличенной выборки']]){const row=make('label'),input=make('input');input.type='checkbox';input.style.width='auto';input.checked=!!cfg[key];fields[key]=input;row.append(input,document.createTextNode(' '+title));body.append(row);}
   const path=make('select');for(const item of data.paths){const option=make('option','',item.label);option.value=item.id;path.append(option);}path.value=cfg.trajectory_id||data.active||'';const pathLabel=make('label','','Публичное направление · выбранная траектория');pathLabel.append(path);body.append(pathLabel);
   const sample=make('select');for(const [id,title] of [['research','Обучение моделей / Generative AI / Research / Infrastructure'],['all','Все наблюдаемые направления']]){const option=make('option','',title);option.value=id;sample.append(option);}sample.value=cfg.sample||'research';const sampleLabel=make('label','','Обезличенная выборка');sampleLabel.append(sample);body.append(sampleLabel);
   const review=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';review.append(check,document.createTextNode(' Я проверил публичную выборку и разрешаю её публикацию'));body.append(review);
   const collect=()=>({...Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.checked])),trajectory_id:path.value,sample:sample.value,reviewed:check.checked});
   for(const input of [...Object.values(fields),path,sample])input.onchange=()=>{check.checked=false;};
   const actions=make('div','githubImportActions'),preview=make('button','secondary','Предпросмотр публичного JSON'),save=make('button','secondary','Сохранить выбор публикации'),download=make('button','secondary','Скачать публичный JSON'),output=make('pre','flowText');let projected=null;download.disabled=true;
   preview.onclick=async()=>{preview.disabled=true;try{const value=await api('portfolio-publication',{op:'visual_preview',settings:collect()},180000);projected=value.payload;output.textContent=JSON.stringify(projected,null,2);download.disabled=!projected;}catch(e){notice(e.message);}finally{preview.disabled=false;}};
   save.onclick=async()=>{save.disabled=true;try{await api('portfolio-publication',{op:'visual_settings',settings:collect()});notice('Выбор сохранён. Автопубликация использует только этот публичный срез.');}catch(e){notice(e.message);}finally{save.disabled=false;}};
   download.onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(projected,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='portfolio-public-visuals.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
   actions.append(preview,save,download);body.append(actions,output);
  }catch(e){ready=false;body.textContent=e.message;}};
 }
 function enter(){const host=$('portfolioPublication');if(!host)return;host.hidden=tab!=='resume';if(!host.hidden&&!host.dataset.ready){host.dataset.ready='true';mount($('portfolioPublicationBody')).catch(e=>{host.dataset.ready='';$('portfolioPublicationBody').textContent=e.message;});}}
 return {enter,mount};
})();
