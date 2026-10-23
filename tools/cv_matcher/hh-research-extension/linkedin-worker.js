/* Active-session executor. Durable commands live in SQLite; a temporary IDB receipt
   survives MV3 suspension without repeating writes or filling chrome.storage. */
(()=>{
 'use strict';
 if(!chrome.alarms?.get||!chrome.alarms?.create||!chrome.permissions?.contains)return;
 let busy=false;
 const call=data=>LocalResumeService.request('/archive/linkedin',data,30000),pause=ms=>new Promise(r=>setTimeout(r,ms));
 async function receipt(op,value,key='result'){const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('linkedin-receipts-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('pending');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});try{return await new Promise((resolve,reject)=>{const t=db.transaction('pending',op==='get'?'readonly':'readwrite'),s=t.objectStore('pending'),r=op==='get'?s.get(key):op==='put'?s.put(value,key):s.delete(key);let result;r.onsuccess=()=>result=r.result;t.oncomplete=()=>resolve(result);t.onerror=()=>reject(t.error);});}finally{db.close();}}
 async function worker(){let id=await receipt('get',null,'worker_id');if(!id){id='linkedin-'+crypto.randomUUID();await receipt('put',id,'worker_id');}return id;}
 async function dom(id,op,p){await chrome.scripting.executeScript({target:{tabId:id},files:['linkedin-core.js','linkedin-content.js']});const r=await chrome.scripting.executeScript({target:{tabId:id},func:async(operation,params)=>{try{return {ok:true,data:await LinkedInSession.handle(operation,params)};}catch(e){return {ok:false,error:e.message};}},args:[op,p]});if(!r[0]?.result?.ok)throw Error(r[0]?.result?.error||'Не удалось прочитать страницу LinkedIn.');return r[0].result.data;}
 async function ready(id,url){const until=Date.now()+30000;while(Date.now()<until){const t=await chrome.tabs.get(id);if(t.url&&/authwall|checkpoint|login/.test(new URL(t.url).pathname))throw Error('LinkedIn требует вход или ручную проверку.');if(t.url&&!t.pendingUrl&&t.status==='complete'){LinkedInCore.url(t.url);return;}await pause(500);}throw Error('Страница не загрузилась за 30 секунд.');}
 async function managed(url,slot='linkedin_tab_id'){LinkedInCore.url(url);let id=await receipt('get',null,slot);let t;try{if(id)t=await chrome.tabs.get(id);}catch{}if(!t||!t.url?.startsWith('https://www.linkedin.com/')){t=await chrome.tabs.create({url,active:false});id=t.id;await receipt('put',id,slot);}else if(t.url!==url)await chrome.tabs.update(id,{url});await ready(id,url);return id;}
 async function current(p){if(p.snapshot?.tab_id){const t=await chrome.tabs.get(p.snapshot.tab_id);if(!LinkedInCore.url(t.url).startsWith(p.account))throw Error('Форма в другой вкладке или на другом аккаунте.');return t.id;}const tabs=await chrome.tabs.query({active:true,lastFocusedWindow:true});const t=tabs.find(t=>{try{return LinkedInCore.url(t.url).startsWith(p.account);}catch{return false;}});if(!t)throw Error('Откройте форму редактирования своего LinkedIn в активной вкладке Chrome.');return t.id;}
 async function assertOwner(p,id){const r=await dom(id,'owner',p);if(!r.verified)throw Error('Собственный профиль не подтверждён: проверьте аккаунт и ссылку в настройках.');}
 async function perform(cmd,w){
  const op=cmd.kind.slice(9),p=cmd.payload;
  if(p.expires&&Date.now()/1000>p.expires)throw Error('Предпросмотр устарел. Прочитайте страницу снова.');
  if(op.startsWith('profile.')&&op!=='profile.read'){
   const id=await current(p);await assertOwner(p,id);let data=await dom(id,op,p);
   if(op==='profile.save'){await pause(1200);const status=await dom(id,'mutation.status',p);return {state:status.dialog_open?'needs_input':'completed',message:status.dialog_open?'Форма осталась открыта. Проверьте ошибки LinkedIn.':'LinkedIn закрыл форму. Перечитайте профиль для проверки сохранённых полей.',data:status};}
   return {state:'completed',message:op==='profile.fill'?'Поля перенесены. Проверьте их перед отдельным сохранением.':'Форма прочитана.',data:{...data,tab_id:id}};
  }
  // Validate that the configured owner is editable in the current authenticated session.
  const owner=await managed(p.account,'linkedin_owner_tab_id');await assertOwner(p,owner);
  if(op==='profile.read'){
   const data=await dom(owner,op,p);let unchanged=0,previous='';
   for(let pass=0;pass<18;pass++){
    await dom(owner,'scroll',p);await pause(650);const next=await dom(owner,op,p);
    if(next.headline)data.headline=next.headline;
    for(const [key,section]of Object.entries(next.sections)){if(section.text)data.sections[key]=section;}
    data.observed_headings=next.observed_headings;if(next.about_edit_url)data.about_edit_url=next.about_edit_url;
    const signature=Object.values(data.sections).map(s=>s.text.length).join(',');unchanged=signature===previous?unchanged+1:0;previous=signature;
    const control=await call({op:'progress',id:cmd.id,worker_id:w,count:Object.values(data.sections).filter(s=>s.text).length,message:'Читаю секции профиля · проход '+(pass+1)});if(!control.continue||unchanged>=6)break;
   }
   if(!data.sections.about.text&&data.about_edit_url){try{const id=await managed(data.about_edit_url),editor=await dom(id,'profile.form',p),fields=editor.fields.filter(f=>f.type==='textarea'&&/about|о себе|summary/i.test(f.label));if(fields.length===1)data.sections.about={text:fields[0].value,coverage:fields[0].value?'editor_read':'empty',links:[]};}catch(e){data.sections.about.warning=e.message;}}
   for(const section of Object.values(data.sections)){const detail=section.links.find(a=>/\/details\//.test(a.url));if(detail){try{const id=await managed(detail.url);section.detail=await dom(id,'profile.detail',p);}catch(e){section.warning=e.message;}}}
   const found=Object.values(data.sections).filter(s=>s.text).length;for(const section of Object.values(data.sections))if(!section.text&&section.coverage!=='empty')section.coverage='not_found';
   data.coverage=found===5&&data.headline?'visible_sections':'partial';return {state:data.headline&&found?'completed':'needs_input',message:'Прочитано секций: '+found+' из 5. '+(data.headline?'Заголовок распознан. ':'Заголовок требует проверки. ')+(found<5?'Непрочитанные секции требуют отдельной проверки.':'Развёрнутые блоки отмечены отдельно.'),data};
  }
  if(op==='network.prepare'){
   const path=['accept','ignore'].includes(p.network_action)?'https://www.linkedin.com/mynetwork/invitation-manager/':p.network_action==='withdraw'?'https://www.linkedin.com/mynetwork/invitation-manager/sent/':p.url;
   const id=await managed(path),data=await dom(id,op,p);return {state:'completed',message:'Проверьте контакт и действие.',data:{...data,tab_id:id}};
  }
  if(op==='network.execute'){
   const id=p.snapshot.tab_id;await dom(id,op,p);await pause(1200);const status=await dom(id,'mutation.status',p);
   return {state:'needs_input',message:status.dialog_open?'LinkedIn открыл подтверждение. Завершите действие в этой вкладке после проверки.':'Кнопка нажата один раз. Обновите список контактов или приглашений, чтобы проверить результат.',data:status};
  }
  const id=await managed(p.url);
  if(['jobs.list','network.list','messages.list'].includes(op)){
   const collected=new Map();let unchanged=0,reason='Достигнут лимит проходов';
   for(let pass=0;pass<20;pass++){
    const r=await dom(id,op,p),before=collected.size;for(const item of r.items)collected.set(item.link||item.url,item);
    if(r.items.length)await call({op:'checkpoint',id:cmd.id,worker_id:w,outcome:{state:'completed',message:'Сохраняю промежуточную порцию',data:{items:r.items,reason:'Промежуточный снимок'}}});
    const progress=await call({op:'progress',id:cmd.id,worker_id:w,count:collected.size,message:'Читаю доступную выдачу · проход '+(pass+1)});
    if(!progress.continue){reason='Остановлено пользователем';break;}if(collected.size>=p.limit){reason='Достигнут выбранный лимит';break;}
    unchanged=before===collected.size?unchanged+1:0;if(unchanged>=3){reason='Новых карточек в загруженной части нет';break;}
    await dom(id,'scroll',p);await pause(900);
   }
   const items=[...collected.values()].slice(0,p.limit);return {state:items.length?'completed':'needs_input',message:items.length?'Сохранено '+items.length+' записей.':'Карточки не распознаны. Проверьте открытую страницу.',data:{items,reason}};
  }
  if(op==='jobs.detail'||op==='messages.thread'){
   let data,error;for(let i=0;i<5;i++){try{data=await dom(id,op,p);break;}catch(e){error=e;await pause(700);}}if(!data)throw error;
   return {state:'completed',message:op==='jobs.detail'?'Полное описание сохранено.':'Загруженная часть выбранного диалога сохранена.',data};
  }
  throw Error('Операция не поддерживается этой версией расширения.');
 }
 async function tick(){if(busy)return {ok:true,busy:true};busy=true;try{
  if(!await chrome.permissions.contains({origins:['https://www.linkedin.com/*']}))throw Error('Разрешите LinkedIn в настройках расширения.');
  const enabled=await receipt('get',null,'enabled')||(await chrome.storage.local.get('linkedin_enabled')).linkedin_enabled;if(!enabled)throw Error('Адаптеры LinkedIn выключены.');
  const pending=await receipt('get');if(pending){await call(pending);await receipt('delete');}
  const w=await worker(),{command}=await call({op:'claim',worker_id:w,version:chrome.runtime.getManifest().version});if(!command)return {ok:true,message:'Связь с локальным сервисом проверена. Новых задач нет.'};
  let outcome;try{outcome=await perform(command,w);}catch(e){outcome={state:['profile.fill','profile.save','network.execute'].includes(command.kind.slice(9))?'uncertain':'needs_input',message:e.message,data:{}};}
  const report={op:'result',id:command.id,worker_id:w,outcome};await receipt('put',report);await call(report);await receipt('delete');return {ok:true,message:outcome.message};
 }catch(e){console.warn('LinkedIn workspace: '+String(e.message).slice(0,300));return {ok:false,error:String(e.message).slice(0,500)};}finally{busy=false;}}
 void chrome.alarms.get('linkedin-workspace').then(a=>{if(!a)return chrome.alarms.create('linkedin-workspace',{periodInMinutes:1});});chrome.alarms.onAlarm.addListener(a=>{if(a.name==='linkedin-workspace')void tick();});
 chrome.runtime.onMessage.addListener((m,s,reply)=>{if(!['linkedin_wake','linkedin_enable'].includes(m.type)||s.id!==chrome.runtime.id)return;(async()=>{if(m.type==='linkedin_enable')await receipt('put',true,'enabled');return tick();})().then(reply,e=>reply({ok:false,error:e.message}));return true;});
 void tick();
})();
