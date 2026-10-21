'use strict';
const $=id=>document.getElementById(id),params=new URL(location.href).searchParams;
let context=null,application=null;
let formState=null,fieldInputs=new Map(),submitPending=false,formDirty=false;
const status=t=>$('status').textContent=t;
function showActions(){
 $('actions').hidden=false;$('applicationId').textContent='Отклик: '+application.id+' · '+application.status;
 $('channel').value=application.context.channel;$('channel').disabled=true;$('create').disabled=true;
 $('openHH').hidden=application.context.channel!=='hh';$('telegramInstructions').hidden=application.context.channel!=='telegram';
}
(async()=>{
 const {resume_bundle:bundle,vacancies=[]}=await chrome.storage.local.get(['resume_bundle','vacancies']);
 const resume=bundle?.resumes?.find(r=>r.id===params.get('resume')&&r.quality==='full');
 const vacancy=vacancies.find(v=>v.id===params.get('vacancy')&&v.description_quality==='full'&&!v.archived);
 if(!resume||!vacancy||resume.content_hash!==params.get('hash'))throw new Error('CV изменилось или полная вакансия недоступна. Вернитесь в рейтинг и выберите актуальный контекст.');
 context={resume_id:resume.id,bundle:{...bundle,primary_id:resume.id,resumes:[resume]},vacancy,goal:params.get('goal')||''};
 $('context').textContent=vacancy.title+' · '+vacancy.company+'\nCV: '+resume.title;
 $('goal').textContent='Карьерная цель: '+(context.goal||'не указана');
 if((resume.source_type||'hh')!=='hh')$('channel').value='telegram';
 if(params.get('continue')){
  const {pending_hh_application:app,hh_application_form:form,hh_application_submission:submission}=await chrome.storage.local.get(['pending_hh_application','hh_application_form','hh_application_submission']);
  if(!app||app.id!==params.get('continue')||app.context.resume_hash!==resume.content_hash||form?.application_id!==app.id)throw new Error('Контекст формы изменился. Прочитайте форму через popup заново.');
  application=app;formState=form;submitPending=submission?.application_id===app.id&&submission.state==='sending'&&submission.fingerprint===form.snapshot.fingerprint;showActions();paintForm();
 }
})().catch(e=>{$('create').disabled=true;status(e.message);});
$('create').onclick=async()=>{
 if(!context)return;$('create').disabled=true;
 try {
  application=await LocalResumeService.request('/applications',{...context,channel:$('channel').value});
  showActions();
  status(application.context.channel==='telegram'?'Отклик добавлен в локальную очередь управляющего Telegram-бота. Сообщения рекрутеру ещё не отправлялись.':'Контекст отклика сохранён. Продолжите в HH с выбранным резюме.');
 }catch(e){status(e.message);$('create').disabled=false;}
};
$('openHH').onclick=async()=>{
 await chrome.storage.local.set({pending_hh_application:application});
 await chrome.tabs.create({url:application.context.vacancy.link});
 status('В HH откройте форму отклика, затем нажмите значок расширения → «Продолжить отклик HH в открытой форме».');
};
$('draft').onclick=async()=>{
 if(!application)return;$('draft').disabled=true;
 try {
  const result=await LocalResumeService.request('/answer-draft',{application_id:application.id,question:$('question').value,model:$('qaModel').value,comments:$('qaComments').value},90000);
  $('answer').value=result.answer;$('evidence').replaceChildren(...result.evidence.map(item=>{const q=document.createElement('blockquote');q.textContent=item.quote;return q;}));
  status((result.needs_user?'Нужны уточнения: '+result.missing.join('; ')+'. ':'')+result.review_note+(result.cached?' Из кэша.':''));
 }catch(e){status(e.message);}finally{$('draft').disabled=false;}
};
async function copyAnswerPrompt(question,draft=''){
 if(!application)throw Error('Сначала создайте отклик с выбранным CV.');const packet=ChatGPTExport.buildAnswerPackage({context:application.context,question,comments:$('qaComments').value,draft});
 try{await navigator.clipboard.writeText(packet);status('Промпт скопирован. Вставьте в ChatGPT, затем вставьте готовый ответ в нужное поле. Вызовов API: 0.');}
 catch{const field=$('qaPrompt');field.value=packet;field.hidden=false;field.focus();field.select();status('Промпт выделен: Cmd+C / Ctrl+C.');}
}
$('draftOffline').onclick=()=>copyAnswerPrompt($('question').value,$('answer').value).catch(e=>status(e.message));
$('copy').onclick=async()=>{try{await navigator.clipboard.writeText($('answer').value);status('Ваш ответ скопирован.');}catch{status('Скопируйте ответ из поля вручную.');}};
async function hh(action,answers){
 const config={action,vacancy_id:application.context.vacancy.id,resume_id:application.context.resume_id,fingerprint:formState.snapshot.fingerprint,answers};
 await chrome.scripting.executeScript({target:{tabId:formState.tab_id},func:c=>{globalThis.__hhApplyAction=c;},args:[config]});
 return (await chrome.scripting.executeScript({target:{tabId:formState.tab_id},files:['hh-apply-core.js','hh-apply-content.js']}))[0]?.result;
}
function paintForm(){
 $('hhForm').hidden=false;const snapshot=formState.snapshot;fieldInputs=new Map();$('hhFields').replaceChildren();
 if(snapshot.state==='submitted'){$('fillHH').disabled=true;$('submitHH').disabled=true;status('HH показывает уже отправленный отклик. Повтор не выполняется.');return;}
 for(const field of snapshot.fields){
  const article=document.createElement('article'),label=document.createElement('label'),input=document.createElement(field.type==='select'?'select':['checkbox','radio'].includes(field.type)?'input':'textarea');
  label.textContent=field.label+(field.required?' *':'');
  if(['checkbox','radio'].includes(field.type)){input.type=field.type;input.name=field.group;input.checked=!!field.value;}
  else if(field.type==='select'){
   for(const option of field.options){const o=document.createElement('option');o.value=option.value;o.textContent=option.text;input.append(o);}input.value=field.value;
  }else{input.value=field.value||'';input.rows=3;}
  const dirty=()=>{formDirty=true;$('submitHH').disabled=true;};input.addEventListener('input',dirty);input.addEventListener('change',dirty);
  label.append(input);article.append(label);fieldInputs.set(field.id,{field,input});
  if(!['select','checkbox','radio'].includes(field.type)){
   const button=document.createElement('button');button.textContent='Предложить ответ на этот вопрос';button.className='secondary';
   button.onclick=async()=>{button.disabled=true;try{const result=await LocalResumeService.request('/answer-draft',{application_id:application.id,question:field.label,model:$('qaModel').value,comments:$('qaComments').value},90000);input.value=result.answer;dirty();status(result.needs_user?'Нужны уточнения: '+result.missing.join('; '):result.review_note);}catch(e){status(e.message);}finally{button.disabled=false;}};const offline=document.createElement('button');offline.className='secondary';offline.textContent='Ответ без API';offline.onclick=()=>copyAnswerPrompt(field.label,input.value).catch(e=>status(e.message));article.append(button,offline);
  }
  $('hhFields').append(article);
 }
 $('fillHH').disabled=false;$('submitHH').disabled=submitPending||snapshot.selected_resume_id!==application.context.resume_id;
}
$('refreshHH').onclick=async()=>{
 try {
  const next=await hh('inspect');if(next.fingerprint!==formState.snapshot.fingerprint)submitPending=false;
  formState={...formState,snapshot:next};formDirty=false;await chrome.storage.local.set({hh_application_form:formState});
  if(next.state==='submitted')await chrome.storage.local.set({hh_application_submission:{application_id:application.id,state:'submitted'}});
  paintForm();
 }catch(e){status(e.message);}
};
$('fillHH').onclick=async()=>{
 try{
  if(submitPending)throw new Error('Сначала проверьте результат отправки на HH.');
  const answers=Object.fromEntries([...fieldInputs].map(([id,{field,input}])=>[id,['checkbox','radio'].includes(field.type)?input.checked:input.value]));
  await hh('fill',answers);await $('refreshHH').onclick();status('Ответы перенесены в HH. Проверьте форму перед отправкой.');
 }catch(e){status(e.message);}
};
$('submitHH').textContent='Согласовать отклик в рабочем месте';
$('submitHH').onclick=async()=>{
 try{
  const opened=await LocalResumeService.request('/archive/open',{resume_id:application.context.resume_id,goal:application.context.goal});
  const url=new URL(opened.url);url.searchParams.set('application',application.id);await chrome.tabs.create({url:url.href});
  status('Обсуждение письма и разрешение на конкретную отправку — в разделе «Отклики». Подключите вкладку HH через popup расширения.');
 }catch(e){status(e.message);}
};
