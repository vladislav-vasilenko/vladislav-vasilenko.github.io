/* Shared native-field transfer, with explicit semantics for each company.
   Never uploads, chooses consents, submits, navigates or sends network requests. */
(function(root){
 const version='career-fields-v2';
 const adapters={yandex:{cover:/сопроводительное письмо|cover letter/i},sber:{cover:/сопроводительное письмо|cover letter/i},tbank:{cover:/сопроводительное письмо|cover letter/i},avito:{cover:/^комментарий$|сопроводительное письмо|cover letter/i},ozon:{cover:/сопроводительное письмо|cover letter/i}};
 const clean=t=>String(t||'').replace(/\s+/g,' ').trim();
 const visible=n=>{const r=n.getBoundingClientRect(),s=getComputedStyle(n);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
 const shape=fields=>JSON.stringify(fields.map(({value,...f})=>f));
 const sameValue=(field,a,b)=>a===b||/^(?:номер телефона|телефон|phone(?: number)?)(?:\s|[*:]|$)/i.test(field.label)&&typeof a==='string'&&typeof b==='string'&&a.replace(/\D/g,'').length>=7&&a.replace(/\D/g,'')===b.replace(/\D/g,'');
 function inspect(doc,url,isVisible=visible){
  const provider=BoardWidgets.provider(url),job=JobBoards.identity(url),adapter=adapters[provider];
  if(!adapter||!job||!BoardWidgets.valid(job.id,provider))throw Error('Откройте полную вакансию компании и её анкету.');
  if(/вакансия (?:в архиве|закрыта|неактуальна)|при[её]м откликов (?:заверш[её]н|закрыт)/i.test(clean(doc.body?.innerText)))throw Error('На странице есть признак закрытой вакансии. Заполнение остановлено.');
  const outside=n=>!n.closest?.('[data-cv-matcher-badges]');
  const candidates=[...doc.querySelectorAll('form,[role="dialog"]')].filter(isVisible).filter(outside).filter(n=>n.querySelector('textarea,input[type="file"],input[type="email"],input[type="tel"],input[autocomplete="email"],input[autocomplete="tel"]'));
  // Boards may use a plain container instead of <form>. Only an exact native
  // send label plus contact fields identifies such a container; no button click.
  if(!candidates.length)for(const b of doc.querySelectorAll('button,input[type="submit"]')){
   if(!isVisible(b)||!outside(b)||!(/^(?:отправить (?:отклик|заявку|анкету))$/i.test(clean(b.innerText||b.value))||provider==='tbank'&&/^отправить$/i.test(clean(b.innerText||b.value))))continue;
   for(let n=b.parentElement;n&&!/^(BODY|HTML)$/.test(n.tagName);n=n.parentElement){
    const standard=n.querySelector('input[type="email"],input[type="tel"]')&&n.querySelector('textarea');
    const tbank=provider==='tbank'&&n.querySelector('input[type="tel"]')&&n.querySelector('input[type="file"]')&&/фамилия и имя/i.test(clean(n.innerText))&&/почта/i.test(clean(n.innerText));
    if(standard||tbank){candidates.push(n);break;}
   }
  }
  const roots=[...new Set(candidates)].filter(n=>!candidates.some(other=>other!==n&&n.contains(other)));
  if(roots.length!==1){
   const frames=[...doc.querySelectorAll('iframe')].filter(isVisible);
   const login=/войти и откликнуться|войдите.{0,40}(?:отклик|анкет)/i.test(clean(doc.body?.innerText));
   const code=roots.length?'ambiguous_form':login?'login_required':frames.length?'embedded_form':'form_not_open';
   const message=roots.length?'Найдено несколько анкет. Оставьте одну форму этой вакансии.':login?'Сначала войдите в аккаунт на сайте компании и откройте анкету кнопкой «Откликнуться».':frames.length?'На странице встроенная iframe-форма. Этот адаптер пока не читает её поля: заполните анкету на сайте. Простое обновление или разрешение переноса это ограничение не устраняет.':'Откройте форму отклика кнопкой «Откликнуться» на сайте и повторите чтение в веб-сервисе.';
   throw Object.assign(Error(message),{code,retryable:code==='form_not_open'});
  }
  const form=roots[0],fields=[],nodes=new Map();
  for(const n of form.querySelectorAll('input,textarea,select')){
   const type=n.tagName==='TEXTAREA'?'textarea':n.tagName==='SELECT'?'select':n.type||'text';
   if(['hidden','password','submit','button','reset'].includes(type)||!isVisible(n)||n.disabled||/captcha|csrf|token/i.test(n.name||''))continue;
   const labelled=(n.getAttribute('aria-labelledby')||'').split(/\s+/).filter(Boolean).map(id=>doc.getElementById?.(id)?.innerText||'').join(' ');
   const label=clean([...(n.labels||[])].map(l=>l.innerText).join(' ')||n.getAttribute('aria-label')||labelled||n.closest?.('label')?.innerText||n.parentElement?.querySelector?.('label')?.innerText||n.placeholder||n.name);
   if(!label)throw Error('Не распознан вопрос поля. Продолжите на сайте вручную.');
   const id='f'+fields.length,purpose=/^(?:ссылка на резюме|ссылка на ваше резюме|resume (?:url|link)|cv (?:url|link))[*:]?$/i.test(label)&&['text','url'].includes(type)?'resume_url':adapter.cover.test(label)?'cover':/о себе|about you/i.test(label)?'about':/^(?:имя|фамилия|фио|e-?mail|телефон|номер телефона|phone|first.?name|last.?name)(?:\s|[*:]|$)/i.test(label)||['email','tel'].includes(type)?'contact':'question';
   const customCity=n.getAttribute('role')==='combobox'&&/^город(?:\s|[*:]|$)/i.test(label),supportedCity=customCity&&provider==='tbank';
   fields.push({id,label:label.slice(0,2000),type,group:n.name||'',required:!!n.required||n.getAttribute('aria-required')==='true',value:type==='file'?'':['checkbox','radio'].includes(type)?!!n.checked:n.value||'',purpose:supportedCity||/^(?:ссылки на соцсети|вконтакте, телеграм и другие|ссылка на портфолио|портфолио)$/i.test(label)?'contact':purpose,options:type==='select'?[...n.options].map(o=>({value:o.value,text:clean(o.textContent)})):[],...(supportedCity?{control:'tbank_city'}:{}),manual_only:type==='file'||['checkbox','radio'].includes(type)||!!n.readOnly&&!supportedCity||customCity&&!supportedCity});nodes.set(id,n);
   if(fields.length>80)throw Error('Слишком много полей. Продолжите вручную.');
  }
  if(!fields.length)throw Error('Нет распознанных полей.');
  const limitations=['Файлы, согласия, переключатели и нестандартные списки проверьте на сайте. Отправка отклика — вручную.'];
  if([...doc.querySelectorAll('iframe')].some(isVisible))limitations.unshift('Часть анкеты находится во встроенной форме. Её поля пока заполняются на сайте вручную.');
  return {snapshot:{state:'questionnaire',adapter_version:version,provider,vacancy_id:job.id,source_url:url,fields,submit_label:'',fingerprint:JSON.stringify([provider,job.id,fields]),execution_supported:false,limitations},nodes,form};
 }
 function fill(doc,url,config,isVisible=visible){
  if(config.source_url!==url)throw Error('Открыта другая страница. Прочитайте анкету заново.');
  const before=inspect(doc,url,isVisible),snap=before.snapshot;
  if(config.fingerprint!==snap.fingerprint||config.vacancy_id!==snap.vacancy_id)throw Error('Анкета или значения изменились. Нужно новое согласование.');
  if(!config.answers||!Object.keys(config.answers).length)throw Error('Нет согласованных текстов.');
  for(const [id,value] of Object.entries(config.answers)){
   const f=snap.fields.find(f=>f.id===id);
   if(!f||f.manual_only||f.control||!['text','email','tel','url','number','date','textarea','select'].includes(f.type)||typeof value!=='string'||value.length>16000||(f.type==='select'&&!f.options.some(o=>o.value===value)))throw Error('Поле не поддерживает согласованный перенос.');
  }
  for(const [id,value] of Object.entries(config.answers)){
   const now=inspect(doc,url,isVisible);
   if(shape(now.snapshot.fields)!==shape(snap.fields))throw Error('Сайт изменил вопросы во время заполнения. Проверьте форму вручную.');
   const n=now.nodes.get(id);if(n.value===value)continue;
   const proto=n.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:n.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;
   const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;if(!setter)throw Error('Не найден стандартный ввод поля.');
   setter.call(n,value);n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}));
  }
  const after=inspect(doc,url,isVisible);
  if(shape(after.snapshot.fields)!==shape(snap.fields)||after.snapshot.fields.some(f=>!sameValue(f,f.value,Object.hasOwn(config.answers,f.id)?config.answers[f.id]:snap.fields.find(o=>o.id===f.id).value)))throw Error('Значения не совпали после заполнения. Проверьте анкету вручную.');
  return {state:'fields_filled',source_url:url,values:Object.fromEntries(Object.keys(config.answers).map(id=>[id,after.snapshot.fields.find(f=>f.id===id).value])),note:'Согласованные тексты перенесены. Проверьте резюме, файлы, списки и согласия; отклик ещё не отправлен.'};
 }
 async function fillApproved(doc,url,config,isVisible=visible,pause=ms=>new Promise(r=>setTimeout(r,ms))){
  const before=inspect(doc,url,isVisible),snap=before.snapshot;
  if(!snap.fields.some(f=>f.control==='tbank_city'&&Object.hasOwn(config.answers||{},f.id)))return fill(doc,url,config,isVisible);
  if(config.source_url!==url||config.vacancy_id!==snap.vacancy_id||config.fingerprint!==snap.fingerprint)throw Error('Анкета или значения изменились. Нужно новое согласование.');
  for(const [id,value] of Object.entries(config.answers||{})){
   const f=snap.fields.find(f=>f.id===id);
   if(!f||f.manual_only||typeof value!=='string'||value.length>16000||!['text','email','tel','url','number','date','textarea','select'].includes(f.type)||f.control&&f.control!=='tbank_city'||f.type==='select'&&!f.options.some(o=>o.value===value))throw Error('Поле не поддерживает согласованный перенос.');
  }
  const selected=new Set();
  for(const f of snap.fields.filter(f=>f.control==='tbank_city'&&Object.hasOwn(config.answers,f.id))){
   const value=config.answers[f.id],input=before.nodes.get(f.id);
   // An arbitrary typed word is insufficient: click an exact actual option.
   input.click();
   if(!input.readOnly){const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set;if(!setter)throw Error('Не найден поиск города.');setter.call(input,value.replace(/^Россия,\s*г\s+/,'').trim());input.dispatchEvent(new Event('input',{bubbles:true}));}
   let chosen=false;
   for(let attempt=0;attempt<25;attempt++){
    await pause(100);
    const current=inspect(doc,url,isVisible);if(shape(current.snapshot.fields)!==shape(snap.fields))throw Error('Анкета изменилась при выборе города.');
    const node=current.nodes.get(f.id),controls=node.getAttribute('aria-controls')||node.getAttribute('aria-owns');
    const linked=controls?.split(/\s+/).map(id=>doc.getElementById(id)).filter(n=>n&&isVisible(n));
    const lists=linked?.length?linked:[...doc.querySelectorAll('[role="listbox"]')].filter(isVisible);
    if(lists.length>1)throw Error('Найдено несколько списков городов. Выберите город на сайте.');
    const options=lists.flatMap(list=>[...list.querySelectorAll('[role="option"],tui-option')]).filter(n=>isVisible(n)&&clean(n.innerText||n.textContent)===value&&n.getAttribute('aria-disabled')!=='true');
    if(options.length>1)throw Error('Город неоднозначен. Выберите точный вариант на сайте.');
    if(options.length===1){options[0].click();chosen=true;break;}
   }
   if(!chosen)throw Error('В списке не найден точный город «'+value+'». Введённый поисковый текст не считается выбранным городом.');
   let accepted=false;
   for(let n=0;n<20;n++){await pause(100);const current=inspect(doc,url,isVisible);if(shape(current.snapshot.fields)!==shape(snap.fields))throw Error('Анкета изменилась при выборе города.');if(current.nodes.get(f.id).value===value){accepted=true;break;}}
   if(!accepted)throw Error('Сайт не подтвердил выбранный город.');selected.add(f.id);
  }
  const current=inspect(doc,url,isVisible);
  if(current.snapshot.fields.some(f=>!sameValue(f,f.value,selected.has(f.id)?config.answers[f.id]:snap.fields.find(o=>o.id===f.id).value)))throw Error('При выборе города изменились другие значения. Проверьте форму.');
  const native=Object.fromEntries(Object.entries(config.answers).filter(([id])=>!selected.has(id)));
  if(Object.keys(native).length)fill(doc,url,{...config,fingerprint:current.snapshot.fingerprint,answers:native},isVisible);
  const after=inspect(doc,url,isVisible);
  if(shape(after.snapshot.fields)!==shape(snap.fields)||after.snapshot.fields.some(f=>!sameValue(f,f.value,Object.hasOwn(config.answers,f.id)?config.answers[f.id]:snap.fields.find(o=>o.id===f.id).value)))throw Error('Значения не совпали после заполнения.');
  return {state:'fields_filled',source_url:url,values:Object.fromEntries(Object.keys(config.answers).map(id=>[id,after.snapshot.fields.find(f=>f.id===id).value])),note:'Город выбран из списка, согласованные поля перенесены. Отклик ещё не отправлен.'};
 }
 // This only reveals an empty URL input. Personal data is still transferred
 // by fill after the exact-value approval. Never replace an attached file.
 async function prepareResumeLink(doc,url,isVisible=visible){
  const before=inspect(doc,url,isVisible);
  if(before.snapshot.fields.some(f=>f.purpose==='resume_url')||before.snapshot.provider!=='avito')return before.snapshot;
  if([...before.form.querySelectorAll('input[type="file"]')].some(n=>!!n.value))return before.snapshot;
  const radios=before.snapshot.fields.filter(f=>f.type==='radio'),links=radios.filter(f=>/^ссылка$/i.test(f.label)),files=radios.filter(f=>/^файл$/i.test(f.label));
  if(links.length!==1||files.length!==1||!links[0].group||links[0].group!==files[0].group)return before.snapshot;
  before.nodes.get(links[0].id).click();
  for(let n=0;n<15;n++){await new Promise(resolve=>setTimeout(resolve,100));const after=inspect(doc,url,isVisible);if(after.snapshot.fields.some(f=>f.purpose==='resume_url'))return after.snapshot;}
  throw Error('Поле ссылки не появилось. Переключите «Файл / Ссылка» на сайте и повторите чтение.');
 }
 async function prepareProfile(doc,url,{resume=false,portfolio=false}={},isVisible=visible){
  let snapshot=resume?await prepareResumeLink(doc,url,isVisible):inspect(doc,url,isVisible).snapshot;
  if(!portfolio||snapshot.provider!=='tbank'||snapshot.fields.some(f=>/^(?:ссылка на портфолио|портфолио)$/i.test(f.label)))return snapshot;
  const current=inspect(doc,url,isVisible),buttons=[...current.form.querySelectorAll('button,a,[role="button"]')].filter(n=>isVisible(n)&&/^\+?\s*Добавить портфолио$/i.test(clean(n.innerText||n.textContent)));
  if(buttons.length!==1)return snapshot;
  buttons[0].click();
  for(let n=0;n<15;n++){await new Promise(r=>setTimeout(r,100));snapshot=inspect(doc,url,isVisible).snapshot;if(snapshot.fields.some(f=>/^(?:ссылка на портфолио|портфолио)$/i.test(f.label)))return snapshot;}
  throw Error('Поле портфолио не появилось. Раскройте его на сайте и повторите чтение.');
 }
 root.CareerForms={version,adapters,inspect,fill,fillApproved,prepareResumeLink,prepareProfile};
})(globalThis);
