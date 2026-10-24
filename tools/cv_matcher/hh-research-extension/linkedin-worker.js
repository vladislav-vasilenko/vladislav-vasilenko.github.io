/* Active-session executor. Durable commands live in SQLite; a temporary IDB receipt
   survives MV3 suspension without repeating writes or filling chrome.storage. */
(()=>{
 'use strict';
 if(!chrome.alarms?.get||!chrome.alarms?.create||!chrome.permissions?.contains)return;
 let busy=false;
 const call=data=>LocalResumeService.request('/archive/linkedin',data,30000),pause=ms=>new Promise(r=>setTimeout(r,ms));
 async function receipt(op,value,key='result'){const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('linkedin-receipts-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('pending');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});try{return await new Promise((resolve,reject)=>{const t=db.transaction('pending',op==='get'?'readonly':'readwrite'),s=t.objectStore('pending'),r=op==='get'?s.get(key):op==='put'?s.put(value,key):s.delete(key);let result;r.onsuccess=()=>result=r.result;t.oncomplete=()=>resolve(result);t.onerror=()=>reject(t.error);});}finally{db.close();}}
 async function worker(){let id=await receipt('get',null,'worker_id');if(!id){id='linkedin-'+crypto.randomUUID();await receipt('put',id,'worker_id');}return id;}
 const adapterFiles=['linkedin-core.js','linkedin-content.js'];
 // The adapters (~45 KB) are injected once per page load. A later call re-injects only when the
 // tab lost them (navigation reset the isolated world) or they came from an older extension version.
 async function ensureAdapters(id){
  const version=chrome.runtime.getManifest().version;
  const [probe]=await chrome.scripting.executeScript({target:{tabId:id},func:()=>globalThis.LinkedInSession?globalThis.__linkedinAdapterVersion||null:null});
  if(probe?.result===version)return;
  await chrome.scripting.executeScript({target:{tabId:id},files:adapterFiles});
  await chrome.scripting.executeScript({target:{tabId:id},func:v=>{globalThis.__linkedinAdapterVersion=v;},args:[version]});
 }
 async function dom(id,op,p){await ensureAdapters(id);const r=await chrome.scripting.executeScript({target:{tabId:id},func:async(operation,params)=>{try{return {ok:true,data:await LinkedInSession.handle(operation,params)};}catch(e){return {ok:false,error:e.message};}},args:[op,p]});if(!r[0]?.result?.ok)throw Error(r[0]?.result?.error||'Не удалось прочитать страницу LinkedIn.');return r[0].result.data;}
 async function ready(id,url){const until=Date.now()+30000;while(Date.now()<until){const t=await chrome.tabs.get(id);if(t.url&&/^\/(?:authwall|checkpoint|login|challenge)(?:\/|$)/.test(new URL(t.url).pathname))throw Error('LinkedIn требует вход или ручную проверку.');if(t.url&&!t.pendingUrl&&t.status==='complete'){LinkedInCore.url(t.url);return;}await pause(500);}throw Error('Страница не загрузилась за 30 секунд.');}
 async function managed(url,slot='linkedin_tab_id'){LinkedInCore.url(url);let id=await receipt('get',null,slot);let t;try{if(id)t=await chrome.tabs.get(id);}catch{}if(!t||!t.url?.startsWith('https://www.linkedin.com/')){t=await chrome.tabs.create({url,active:false});id=t.id;await receipt('put',id,slot);}else if(t.url!==url)await chrome.tabs.update(id,{url});await ready(id,url);return id;}
 async function current(p){if(p.snapshot?.tab_id){const t=await chrome.tabs.get(p.snapshot.tab_id);if(!LinkedInCore.url(t.url).startsWith(p.account))throw Error('Форма в другой вкладке или на другом аккаунте.');return t.id;}const tabs=await chrome.tabs.query({active:true,lastFocusedWindow:true});const t=tabs.find(t=>{try{return LinkedInCore.url(t.url).startsWith(p.account);}catch{return false;}});if(!t)throw Error('Откройте форму редактирования своего LinkedIn в активной вкладке Chrome.');return t.id;}
 async function assertOwner(p,id){const r=await dom(id,'owner',p);if(!r.verified)throw Error('Собственный профиль не подтверждён: проверьте аккаунт и ссылку в настройках.');}
 async function activate(id){const tab=await chrome.tabs.get(id);if(chrome.windows?.get&&tab.windowId!==undefined){const window=await chrome.windows.get(tab.windowId);if(window.state==='minimized')await chrome.windows.update(tab.windowId,{state:'normal'});}await chrome.tabs.update(id,{active:true});}
 async function waitOwner(p,id){let error;for(let pass=0;pass<16;pass++){try{await assertOwner(p,id);return;}catch(e){error=e;if(/LinkedIn требует вход|ручную проверку/i.test(e.message))throw e;await pause(500);}}throw error;}
 async function chooseProfileLanguage(id,p){if(!p.profile_language||p.profile_language==='current')return;const changed=await dom(id,'profile.language',p);if(changed.changed){await pause(1500);await waitOwner(p,id);}}
 async function readTurn(cmd,w,count,message){
  let status=await call({op:'progress',id:cmd.id,worker_id:w,count,message});
  while(status.continue&&status.wait_ms>0){await pause(Math.min(status.wait_ms,10000));status=await call({op:'progress',id:cmd.id,worker_id:w,count,message});}
  return status;
 }
 async function perform(cmd,w){
  const op=cmd.kind.slice(9),p=cmd.payload;
  if(p.expires&&Date.now()/1000>p.expires)throw Error('Предпросмотр устарел. Прочитайте страницу снова.');
  if(op==='profile.open'){
   const id=await managed(p.account,'linkedin_owner_tab_id');let data,error;await activate(id);await waitOwner(p,id);await chooseProfileLanguage(id,p);if(p.url!==p.account)await chrome.tabs.update(id,{url:p.url});await ready(id,p.url);if(p.edit_label)await dom(id,'profile.editor.open',p);
   for(let pass=0;pass<16;pass++){try{await assertOwner(p,id);data=await dom(id,'profile.form',p);break;}catch(e){error=e;await pause(500);}}
   if(!data)throw error;if(p.profile_language&&p.profile_language!=='current'&&data.profile_language!==p.profile_language)throw Error('Язык редактора изменился. Выберите нужную версию профиля и прочитайте форму заново.');return {state:'completed',message:'Редактор выбранного блока открыт. Проверьте поля перед переносом.',data:{...data,tab_id:id}};
  }
  if(op.startsWith('profile.')&&op!=='profile.read'){
   const id=await current(p);await assertOwner(p,id);let data=await dom(id,op,p);
   if(op==='profile.save'){await pause(1200);const status=await dom(id,'mutation.status',p);return {state:status.dialog_open?'needs_input':'completed',message:status.dialog_open?'Форма осталась открыта. Проверьте ошибки LinkedIn.':'LinkedIn закрыл форму. Перечитайте профиль для проверки сохранённых полей.',data:status};}
   return {state:'completed',message:op==='profile.fill'?'Поля перенесены. Проверьте их перед отдельным сохранением.':'Форма прочитана.',data:{...data,tab_id:id}};
  }
  // Validate that the configured owner is editable in the current authenticated session.
  const owner=await managed(p.account,'linkedin_owner_tab_id');if(op==='profile.read')await activate(owner);await waitOwner(p,owner);
  if(op==='profile.read'){
   let previousProfileTab;const activeProfileTabs=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(activeProfileTabs[0]?.id!==owner){previousProfileTab=activeProfileTabs[0]?.id;await chrome.tabs.update(owner,{active:true});}try{
   await chooseProfileLanguage(owner,p);const data=await dom(owner,op,p);if(p.profile_language&&p.profile_language!=='current'&&data.profile_language!==p.profile_language)throw Error('Язык профиля не подтверждён. Выберите язык в LinkedIn и повторите чтение.');let unchanged=0,previous='';
   for(let pass=0;pass<18;pass++){
    await dom(owner,'scroll',p);await pause(650);const next=await dom(owner,op,p);
    if(next.headline)data.headline=next.headline;
    for(const [key,section]of Object.entries(next.sections)){if(section.text)data.sections[key]=section;}
    data.observed_headings=next.observed_headings;if(next.about_edit_url)data.about_edit_url=next.about_edit_url;
    const signature=Object.values(data.sections).map(s=>s.text.length).join(',');unchanged=signature===previous?unchanged+1:0;previous=signature;
    const control=await call({op:'progress',id:cmd.id,worker_id:w,count:Object.values(data.sections).filter(s=>s.text).length,message:'Читаю секции профиля · проход '+(pass+1)});if(!control.continue||unchanged>=6)break;
   }
   if(!data.sections.about.text&&data.about_edit_url){try{const id=await managed(data.about_edit_url);let editor;for(let retry=0;retry<12;retry++){try{editor=await dom(id,'profile.form',p);break;}catch(e){if(retry===11)throw e;await pause(650);}}const fields=editor.fields.filter(f=>f.type==='textarea'&&(/about|о себе|summary|description|описание/i.test(f.label)||/about|о себе|summary/i.test(editor.title)));if(fields.length===1)data.sections.about={text:fields[0].value,coverage:fields[0].value?'editor_read':'empty',links:[]};}catch(e){data.sections.about.warning=e.message;}}
   for(const [sectionKey,section] of Object.entries(data.sections)){const detail=section.links.find(a=>a.url.startsWith(p.account+'details/')&&new RegExp('/details/'+({certifications:'certifications'}[sectionKey]||sectionKey)+'/').test(a.url));if(detail){try{const id=await managed(detail.url);section.detail=await dom(id,'profile.detail',{...p,section:sectionKey});}catch(e){section.warning=e.message;}}}
   const found=Object.values(data.sections).filter(s=>s.text).length;for(const section of Object.values(data.sections))if(!section.text&&section.coverage!=='empty')section.coverage='not_found';
   data.coverage=found===5&&data.headline?'visible_sections':'partial';return {state:data.headline&&found?'completed':'needs_input',message:'Прочитано секций: '+found+' из 5. '+(data.headline?'Заголовок распознан. ':'Заголовок требует проверки. ')+(found<5?'Непрочитанные секции требуют отдельной проверки.':'Развёрнутые блоки отмечены отдельно.'),data};
   }finally{if(previousProfileTab){try{const active=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(active[0]?.id===owner)await chrome.tabs.update(previousProfileTab,{active:true});}catch{}}}
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
   let previousListingTab;try{
   if(op==='network.list'||op==='messages.list'){const active=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(active[0]?.id!==id){previousListingTab=active[0]?.id;await activate(id);}}
   if(op==='messages.list'){for(let turn=0;turn<6;turn++){const navigation=await dom(id,'messages.navigate',p);if(!navigation.navigated)break;await pause(700);if(p.scope!=='all')break;}}
   if(op==='jobs.list'){const navigation=await dom(id,'jobs.navigate',p);if(navigation.navigated){await pause(1000);await ready(id,p.url);}}
   const collected=new Map(),knownContacts=new Set(p.known_contacts||[]);let diagnostics,scroll;let expandedMore=false,page=1,cardStalls=0,readError=false;const seenKeys=new Set();let unchanged=0,atEnd=false,preferencesMissing=false,stopped=false,reason='Достигнут лимит проходов';
   for(let pass=0;pass<(['jobs.list','messages.list'].includes(op)?Math.max(150,p.limit*3):Math.min(2000,100+knownContacts.size));pass++){
    let r=await dom(id,op,op==='network.list'?{...p,limit:Math.max(1,p.limit-collected.size),skip_contacts:[...knownContacts,...collected.keys()]}:p);if(op==='messages.list'&&!r.card_count&&!r.items.length){for(let loading=0;loading<20&&!r.card_count&&!r.items.length;loading++){const waiting=await call({op:'progress',id:cmd.id,worker_id:w,count:collected.size,message:'Ожидаю загрузку списка диалогов LinkedIn'});if(!waiting.continue){stopped=true;break;}await pause(650);r=await dom(id,op,p);}if(stopped){reason='Остановлено пользователем';break;}if(!r.card_count&&!r.items.length)throw Error('Список диалогов LinkedIn не загрузился. Проверьте открытую вкладку и выбранную папку.');}const before=collected.size;if(op==='network.list'&&p.only_new)r.items=r.items.filter(item=>!knownContacts.has(item.url)&&!collected.has(item.url)).slice(0,p.limit-collected.size);if(r.diagnostics){diagnostics=r.diagnostics;if(op==='messages.list'&&p.diagnostics&&pass===0)await call({op:'checkpoint',id:cmd.id,worker_id:w,outcome:{state:'completed',message:'Метаданные списка диалогов',data:{items:[],diagnostics:r.diagnostics}}});}preferencesMissing=preferencesMissing||r.preferences_unconfigured;for(const item of r.items){const key=item.link||item.url,old=collected.get(key);collected.set(key,{...old,...item,...(op==='jobs.list'?{recommendation_sections:[...new Set([...(old?.recommendation_sections||[]),...(item.recommendation_sections||[])])]}:{})});}
    for(let offset=0;offset<r.items.length;offset+=50)await call({op:'checkpoint',id:cmd.id,worker_id:w,outcome:{state:'completed',message:'Сохраняю промежуточную порцию',data:{items:r.items.slice(offset,offset+50),reason:'Промежуточный снимок'}}});
    const progress=await call({op:'progress',id:cmd.id,worker_id:w,count:collected.size,message:(op==='jobs.list'?'Карточек: '+collected.size+' · страница '+page+' · прокрутка · ':'Читаю доступную выдачу · ')+(pass+1)});
    if(!progress.continue){reason='Остановлено пользователем';stopped=true;break;}if(collected.size>=p.limit){reason='Достигнут выбранный лимит';break;}
    if(op==='jobs.list'||op==='messages.list'){
     const turn=await readTurn(cmd,w,collected.size,'Ожидаю следующий переход');if(!turn.continue){reason='Остановлено пользователем';stopped=true;break;}
     const selected=await dom(id,op==='jobs.list'?'jobs.select':'messages.select',{...p,seen_keys:[...seenKeys]});
     if(selected.clicked){
      if(selected.loading){cardStalls++;if(cardStalls>=3){readError=true;reason='LinkedIn не открыл выбранную карточку. Сохранена прочитанная часть; откройте выдачу в Chrome и продолжите.';break;}}
      if(selected.item){cardStalls=0;seenKeys.add(selected.key);const item=selected.item,key=item.link||item.url,old=collected.get(key);collected.set(key,{...old,...item,...(op==='jobs.list'?{recommendation_sections:[...new Set([...(old?.recommendation_sections||[]),...(item.recommendation_sections||[])])]}:{})});await call({op:'checkpoint',id:cmd.id,worker_id:w,outcome:{state:'completed',message:'Сохраняю карточку',data:{items:[item]}}});await call({op:'progress',id:cmd.id,worker_id:w,count:collected.size,message:'Карточка сохранена',unit_id:item.link||item.url});}
      unchanged=0;if(collected.size>=p.limit){reason='Достигнут выбранный лимит';break;}await pause(p.interval_ms||3000);continue;
     }
    }
    unchanged=before===collected.size?unchanged+1:0;if(unchanged>=(5)&&atEnd){if(op==='jobs.list'&&p.collection==='all'&&!expandedMore){expandedMore=true;const next=await dom(id,'jobs.navigate',{...p,expand_more:true});if(next.navigated){unchanged=0;atEnd=false;await pause(1100);continue;}}reason='После прокрутки нижней границы новые карточки больше не появились';break;}
    if(op==='jobs.list'){scroll=await dom(id,'jobs.advance',p);atEnd=scroll.at_end;if(scroll.paginated){page=scroll.page||page+1;unchanged=0;seenKeys.clear();}}else if(op==='messages.list'){scroll=await dom(id,'messages.advance',p);atEnd=scroll.at_end;}else if(op==='network.list'){scroll=await dom(id,'network.advance',p);atEnd=scroll.at_end;}else await dom(id,'scroll',p);await pause(op==='jobs.list'?(p.interval_ms||3000):900);
   }
   if(p.diagnostics&&op==='jobs.list')diagnostics={links:diagnostics,document:await dom(id,'jobs.diagnostics',p)};
   const items=[...collected.values()].slice(0,p.limit);return {state:stopped?'cancelled':readError?'needs_input':items.length?'completed':'needs_input',message:items.length?'Сохранено '+items.length+' записей.':preferencesMissing&&p.collection==='preferences'?'Предпочтения LinkedIn не настроены: доступна кнопка Add job preferences.':'Карточки не распознаны. Проверьте открытую страницу.',data:{...(op==='jobs.list'?{items:[],collected_links:items.map(j=>j.link)}:op==='messages.list'?{items:[],collected_threads:items.map(j=>j.url)}:{items:[],collected_contacts:items.map(j=>j.url)}),...(diagnostics?{diagnostics,scroll}:{}),reason:reason+(preferencesMissing?' · Jobs based on your preferences: предпочтения пока не настроены.':'')}};
   }finally{if(previousListingTab){try{const active=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(active[0]?.id===id)await chrome.tabs.update(previousListingTab,{active:true});}catch{}}}
  }
  if(op==='messages.thread'){
   let item,error,unchanged=0,previous=0,coverage='scroll_limit',stopped=false,atStart=false;const ordered=[],messages=new Map(),limit=p.message_limit||200;
   for(let pass=0;pass<80;pass++){
    let result;try{result=await dom(id,op,p);}catch(e){error=e;if(/LinkedIn требует вход|ручную проверку/i.test(e.message))throw e;if(pass<10){await pause(700);continue;}throw e;}
    item=result.items[0];const fresh=[];for(const message of item.messages||[]){if(!messages.has(message.id))fresh.push(message.id);messages.set(message.id,message);}if(pass===0)ordered.push(...fresh);else ordered.unshift(...fresh);
    const chosen=ordered.slice(-limit).map(key=>messages.get(key));item={...item,messages:chosen,text:chosen.length?chosen.map(m=>[m.sender,m.sent_label,m.text].filter(Boolean).join(' · ')).join('\n\n').slice(-180000):item.text};
    if(chosen.length!==previous||pass===0)await call({op:'checkpoint',id:cmd.id,worker_id:w,outcome:{state:'completed',message:'Сохраняю сообщения',data:{items:[item],history_coverage:'loaded_only'}}});
    const control=await call({op:'progress',id:cmd.id,worker_id:w,count:chosen.length,message:'Сообщений: '+chosen.length+' · дозагрузка старой истории · '+(pass+1)});if(!control.continue){stopped=true;coverage='stopped';break;}
    if(chosen.length>=limit){coverage='message_limit';break;}
    unchanged=chosen.length===previous?unchanged+1:0;previous=chosen.length;if(atStart&&unchanged>=3){coverage='top_reached';break;}if(unchanged>=8){coverage='no_new_messages';break;}
    const scroll=await dom(id,'messages.history.advance',p);atStart=scroll.at_start;await pause(1200);
   }
   if(!item)throw error||Error('Сообщения не загружены.');return {state:stopped?'cancelled':'completed',message:'Сохранена доступная история диалога: '+item.messages.length+' сообщений.',data:{items:[item],history_coverage:coverage,reason:coverage==='top_reached'?'Достигнута верхняя граница доступной истории':'Сохранён доступный фрагмент; полнота всей переписки не подтверждена.'}};
  }
  if(op==='jobs.detail'||op==='team.read'){
   let data,error,previousTab;
   try{
    for(let i=0;i<24;i++){
     try{data=await dom(id,op,p);break;}
     catch(e){
      error=e;if(/LinkedIn требует вход|ручную проверку|ограничил доступ/i.test(e.message))throw e;
      if(op==='jobs.detail'||op==='team.read'){
       // LinkedIn defers parts of a job page while the tab is hidden.
       // Use a real tab activation once; never fake visibility or click Apply.
       if(i===5){const active=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(active[0]?.id!==id){previousTab=active[0]?.id;await chrome.tabs.update(id,{active:true});}}
       await dom(id,'scroll',p);
       const control=await call({op:'progress',id:cmd.id,worker_id:w,count:0,message:'Загружаю полный текст · проход '+(i+1)});
       if(!control.continue)return {state:'cancelled',message:'Дозагрузка остановлена.',data:{}};
      }
      await pause(700);
     }
    }
    if(!data){if(op==='jobs.detail')return {state:'needs_input',message:error.message,data:{diagnostics:await dom(id,'jobs.diagnostics',p)}};throw error;}
    return {state:'completed',message:op==='team.read'?'Участники, показанные для вакансии, сохранены.':op==='jobs.detail'?'Полное описание сохранено.':'Загруженная часть выбранного диалога сохранена.',data};
   }finally{
    if(previousTab){try{const active=await chrome.tabs.query({active:true,lastFocusedWindow:true});if(active[0]?.id===id)await chrome.tabs.update(previousTab,{active:true});}catch{}}
   }
  }
  throw Error('Операция не поддерживается этой версией расширения.');
 }
 async function tick(){if(busy)return {ok:true,busy:true};busy=true;try{
  if(!await chrome.permissions.contains({origins:['https://www.linkedin.com/*']}))throw Error('Разрешите LinkedIn в настройках расширения.');
  const enabled=await receipt('get',null,'enabled')||(await chrome.storage.local.get('linkedin_enabled')).linkedin_enabled;if(!enabled)throw Error('Адаптеры LinkedIn выключены.');
  const pending=await receipt('get');if(pending){await call(pending);await receipt('delete');}
  const w=await worker(),{command,retry_after_ms}=await call({op:'claim',worker_id:w,version:chrome.runtime.getManifest().version});if(!command){if(retry_after_ms>0)setTimeout(()=>void tick(),Math.min(retry_after_ms,25000));return {ok:true,message:retry_after_ms?'Перерыв очереди чтения.':'Связь с локальным сервисом проверена. Новых задач нет.'};}
  let outcome;try{outcome=await perform(command,w);}catch(e){outcome={state:['profile.fill','profile.save','network.execute'].includes(command.kind.slice(9))?'uncertain':'needs_input',message:e.message,data:{}};}
  const report={op:'result',id:command.id,worker_id:w,outcome};await receipt('put',report);await call(report);await receipt('delete');if(!['profile.fill','profile.save','network.execute'].includes(command.kind.slice(9)))setTimeout(()=>void tick(),800);return {ok:true,message:outcome.message};
 }catch(e){console.warn('LinkedIn workspace: '+String(e.message).slice(0,300));return {ok:false,error:String(e.message).slice(0,500)};}finally{busy=false;}}
 void chrome.alarms.get('linkedin-workspace').then(a=>{if(!a)return chrome.alarms.create('linkedin-workspace',{periodInMinutes:1});});chrome.alarms.onAlarm.addListener(a=>{if(a.name==='linkedin-workspace')void tick();});
 chrome.runtime.onMessage.addListener((m,s,reply)=>{if(!['linkedin_wake','linkedin_enable'].includes(m.type)||s.id!==chrome.runtime.id)return;(async()=>{if(m.type==='linkedin_enable')await receipt('put',true,'enabled');return tick();})().then(reply,e=>reply({ok:false,error:e.message}));return true;});
 void tick();
})();
