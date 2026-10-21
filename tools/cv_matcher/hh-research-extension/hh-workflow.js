/* Managed or explicitly enabled HH tab, server queue and single-use approval. No blind retries. */
let hhWorkflowBusy=false;
function wfHHAddress(value,{chat=false}={}){try{const u=new URL(value);if(u.origin==='https://hh.ru'||chat&&u.origin==='https://chat.hh.ru')return u;}catch{}throw Error('Не удалось определить адрес страницы HH. Откройте служебную вкладку и проверьте загрузку.');}
const workflowCall=(data,timeout=150000)=>LocalResumeService.request('/archive/workflow',data,timeout);
async function wfScript(tabId,files){
 const injected=(await chrome.scripting.executeScript({target:{tabId},files}))[0];
 if(injected?.error)throw Error(injected.error.message||String(injected.error));
 return injected?.result;
}
async function wfApply(tabId,config){await chrome.scripting.executeScript({target:{tabId},func:c=>{globalThis.__hhApplyAction=c;},args:[config]});const result=await wfScript(tabId,['hh-apply-core.js','hh-apply-content.js']);if(!result||typeof result!=='object'||typeof result.state!=='string')throw Error('Не удалось прочитать форму HH. Откройте нужную вакансию и форму отклика в служебной вкладке, затем повторите подготовку. Автоматического повтора отправки не будет.');return result;}
async function wfReadWithin(operation,milliseconds,note){
 let timer;
 try{return await Promise.race([Promise.resolve().then(operation),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(note)),milliseconds);})]);}
 finally{clearTimeout(timer);}
}
async function wfStatus(status){try{await chrome.storage.local.set({hh_workflow_status:status});}catch{try{await chrome.storage.session.set({hh_workflow_status:status});}catch{}}}
async function wfCurrentSync(tabId,walk=false,{automatic=false}={}){
 const original=wfHHAddress((await chrome.tabs.get(tabId)).url,{chat:true}).href,deadline=Date.now()+120000;let url=original,pages=0,threads=[],records=0,total={observations_added:0,messages_added:0,warnings:[],observed_statuses:[]};
 const timeLeft=()=>!automatic||Date.now()<deadline;
 async function read(targetId=tabId){const snapshot=await wfReadWithin(()=>wfScript(targetId,['hh-sync-core.js','hh-sync-content.js']),8000,'HH не ответил на чтение откликов за 8 секунд. Проверьте вход и доступность страницы.');if(snapshot?.blocked)throw Error(snapshot.warning);if(!snapshot)throw Error('Страница HH не прочитана.');if(snapshot.warning)total.warnings.push(snapshot.warning);records+=(snapshot.records||[]).length;total.observed_statuses.push(...(snapshot.records||[]).filter(r=>r.vacancy_id&&r.status&&r.status!=='unknown').map(r=>({vacancy_id:r.vacancy_id,status:r.status})));const result=await LocalResumeService.request('/archive/workflow',{op:'observe',snapshot},automatic?15000:150000);total.observations_added+=result.observations_added;total.messages_added+=result.messages_added;total.warnings.push(...(result.warnings||[]));return snapshot;}
 while(pages<5&&timeLeft()){const snap=await read();pages++;threads.push(...snap.thread_urls||[]);if(!walk||!snap.next_page||!timeLeft())break;const from=new URL(url),next=new URL(snap.next_page);if(next.origin!==from.origin||next.pathname!==from.pathname||Number(next.searchParams.get('page')||0)<=Number(from.searchParams.get('page')||0))break;const filters=u=>JSON.stringify([...u.searchParams].filter(([k])=>!['page','hhtmFrom','from','search_session_id'].includes(k)).sort());if(filters(from)!==filters(next))break;url=next.href;await navigate(tabId,url);}
 if(automatic&&timeLeft()){
  // HH now uses buttons for embedded chats in negotiations. Read the full directory too.
  await navigate(tabId,'https://hh.ru/chat');const chats=await read();threads.push(...chats.thread_urls||[]);
  const known=await LocalResumeService.request('/archive/workflow',{op:'hh_sync_targets'},15000);threads.push(...known.urls||[]);
 }
 const unique=[...new Set(threads.map(value=>{try{const u=new URL(value);return u.origin==='https://hh.ru'&&/^\/chat\/\d{1,25}\/?$/.test(u.pathname)?u.origin+u.pathname.replace(/\/$/,''):null;}catch{return null;}}).filter(Boolean))];let cursor=automatic?Number((await chrome.storage.local.get('hh_auto_sync_cursor')).hh_auto_sync_cursor||0):0,visited=0;
 if(walk)for(let n=0;n<Math.min(unique.length,automatic?6:10)&&timeLeft();n++){const thread=unique[(cursor+n)%unique.length];if(new URL(thread).origin!==new URL(original).origin||!/^\/chat\/\d+\/?$/.test(new URL(thread).pathname))continue;await navigate(tabId,thread);await read();visited++;if(automatic)await chrome.storage.local.set({hh_auto_sync_cursor:(cursor+n+1)%unique.length});}
 // Read already-open HH chats in place. Never navigate or send in the user's chat tabs.
 if(walk&&!automatic&&chrome.tabs.query)for(const tab of (await chrome.tabs.query({url:'https://hh.ru/chat/*'})).filter(t=>t.id!==tabId).slice(0,10)){try{await read(tab.id);}catch(e){total.warnings.push('Открытый чат HH не прочитан: '+e.message);}}
 if(walk&&!automatic&&wfHHAddress((await chrome.tabs.get(tabId)).url,{chat:true}).href!==original)await navigate(tabId,original);
 if(automatic&&!records)throw Error('Не распознаны отклики HH. Проверьте вход и разметку страницы в Chrome; статусы не изменены.');
 if(automatic&&!timeLeft())total.warnings.push('Достигнут лимит времени чтения; прочитанную часть сохранили.');
 return {...total,pages,threads_read:visited,partial:true};
}
async function wfAutomaticSync(){
 // Own disposable tab: never navigate a prepared response form or the user's chat.
 if(!await chrome.permissions.contains({origins:['https://hh.ru/*']}))throw Error('Разрешите доступ к HH в настройках расширения.');
 const tab=await chrome.tabs.create({url:'about:blank',active:false});activeJobs.add(tab.id);
 try{const result=await wfReadWithin(async()=>{await navigate(tab.id,'https://hh.ru/applicant/negotiations',{timeoutMs:20000});return wfCurrentSync(tab.id,true,{automatic:true});},110000,'Истекло время фоновой проверки откликов HH. Повтор будет отложен; сбор вакансий может продолжаться.');return {state:'complete',...result};}
 finally{activeJobs.delete(tab.id);try{if(!(await chrome.tabs.get(tab.id)).active)await chrome.tabs.remove(tab.id);}catch{}}
}
async function wfRefresh(tabId,ids,worker){
 for(const id of ids){if(!/^hh_\d{1,20}$/.test(id))continue;await navigate(tabId,'https://hh.ru/vacancy/'+id.slice(3));let data;
  for(let n=0;n<8;n++){data=await wfScript(tabId,['content.js']);if(data?.blocked)throw Error(data.warning);if(data?.vacancies?.some(v=>v.id===id&&(v.archived===true||v.description_quality==='full')))break;await new Promise(r=>setTimeout(r,350));}
  const job=data?.vacancies?.find(v=>v.id===id);if(!job||job.archived!==true&&job.description_quality!=='full')throw Error('Не удалось подтвердить активность '+id);job.availability_checked_at=new Date().toISOString();
  const {vacancies=[]}=await chrome.storage.local.get('vacancies');await chrome.storage.local.set({vacancies:ResearchSearch.mergeVacancies(vacancies,[job])});
  const row=await ArchiveSyncCore.record('vacancy',job.id,job),reply=await LocalResumeService.request('/archive/sync',{client_id:'workflow_'+worker,records:[row]});if(reply.rejected?.length)throw Error('Архив не принял проверку вакансии.');if(job.archived===true&&ids.length===1)throw Error('Вакансия закрыта. Отклик остановлен.');
 }
}
async function wfPrepare(tabId,command,worker){
 const app=command.application,ctx=app.context;
 let existing=null;try{if(HHApply.verifyURL((await chrome.tabs.get(tabId)).url,ctx.vacancy.id))existing=await wfApply(tabId,{action:'inspect',vacancy_id:ctx.vacancy.id,resume_id:ctx.resume_id});}catch{}
 if(!existing)await wfRefresh(tabId,[ctx.vacancy.id],worker);
 const observed=await wfCurrentSync(tabId,false),prior=observed.observed_statuses.find(r=>r.vacancy_id===ctx.vacancy.id&&['submitted','viewed','invited','rejected','withdrawn'].includes(r.status));
 if(prior)return {state:'complete',note:'HH: '+({submitted:'отклик уже отправлен',viewed:'отклик уже просмотрен',invited:'вас уже пригласили',rejected:'по отклику получен отказ',withdrawn:'отклик отозван'})[prior.status]+'. Статус сохранён в CRM; новый отклик не отправлялся.'};
 // Follow a rendered form link only. Never click an unapproved native response button.
 const link=(await chrome.scripting.executeScript({target:{tabId},func:()=>[...document.querySelectorAll('a[href*="/applicant/vacancy_response"]')].map(a=>a.href)}))[0]?.result?.find(href=>{try{const u=new URL(href);return u.origin==='https://hh.ru'&&u.searchParams.get('vacancyId')===ctx.vacancy.id.slice(3);}catch{return false;}});
 if(!existing&&link)await navigate(tabId,link);
 const config={action:'inspect',vacancy_id:ctx.vacancy.id,resume_id:ctx.resume_id};let snapshot=await wfApply(tabId,config);
 if(snapshot.state==='submitted')return {state:'submitted',source_url:snapshot.source_url,evidence:snapshot.evidence};
 if(snapshot.state!=='form')throw Error('Откройте форму отклика HH вручную.');
 const covers=snapshot.fields.filter(f=>f.purpose==='cover');if(covers.length!==1)throw Error('В HH не распознано поле сопроводительного письма. Откройте форму с этим полем вручную и повторите подготовку.');
 await wfApply(tabId,{...config,action:'fill',fingerprint:snapshot.fingerprint,answers:{[covers[0].id]:app.workflow.draft}});snapshot=await wfApply(tabId,config);
 await workflowCall({op:'prepared',command_id:command.id,worker_id:worker,snapshot});return {state:'complete',note:'Форма заполнена письмом. Жду разрешения пользователя.'};
}
async function wfExecute(tabId,command,worker){
 const app=command.application,ctx=app.context,config={action:'inspect',vacancy_id:ctx.vacancy.id,resume_id:ctx.resume_id};
 const current=wfHHAddress((await chrome.tabs.get(tabId)).url).href;if(!HHApply.verifyURL(current,ctx.vacancy.id))throw Error('В служебной вкладке открыта другая вакансия. Подготовьте форму заново.');
 const before=await wfApply(tabId,config);if(before.state==='submitted')return {state:'submitted',source_url:before.source_url,evidence:before.evidence};
 const intent=await workflowCall({op:'claim',command_id:command.id,worker_id:worker,fingerprint:before.fingerprint});
 await wfApply(tabId,{...config,action:'fill',fingerprint:before.fingerprint,answers:intent.answers});const after=await wfApply(tabId,config);HHApply.verifyApproved(intent,before,after);
 const {resume_bundle}=await chrome.storage.local.get('resume_bundle');if(resume_bundle?.resumes?.find(r=>r.id===ctx.resume_id)?.content_hash!==intent.resume_hash)throw Error('CV в расширении изменилось. Отправка остановлена.');
 // This is the only click that can submit. It is never retried after claim.
 await wfApply(tabId,{...config,action:'submit',fingerprint:after.fingerprint});
 for(let n=0;n<10;n++){await new Promise(r=>setTimeout(r,600));try{const observed=await wfApply(tabId,config);if(observed.state==='submitted')return {state:'submitted',source_url:observed.source_url,evidence:observed.evidence};if(observed.fingerprint!==after.fingerprint){await workflowCall({op:'prepared',command_id:command.id,worker_id:worker,snapshot:observed});return {state:'needs_input',note:'HH показал следующий шаг. Требуется проверка и новое разрешение.'};}}catch{}}
 return {state:'uncertain',note:'Нет однозначного подтверждения HH. Проверьте отклики; повторный клик запрещён.'};
}
// The receipt is persisted before HTTP. Replaying it never replays a browser action.
async function wfSaveReceipt(command,worker,result){
 const key='hh_receipt_'+command.id,receipt={command_id:command.id,worker_id:worker,result};let area=chrome.storage.local;
 try{await area.set({[key]:receipt});}catch(error){if(!chrome.storage.session)throw error;area=chrome.storage.session;await area.set({[key]:receipt});}
 await workflowCall({op:'result',...receipt},command.kind==='resume_bump'||command.kind==='sync'?15000:150000);
 await area.remove(key);
}
async function wfFlushReceipts(){
 for(const area of [chrome.storage.local,chrome.storage.session].filter(Boolean)){
  const all=await area.get(null);
  for(const [key,receipt] of Object.entries(all))if(key.startsWith('hh_receipt_')){
   await workflowCall({op:'result',...receipt},receipt.result?.outcome?15000:150000);await area.remove(key);
  }
 }
}
async function hhWorkflowPulse(){
 if(hhWorkflowBusy)return;
 hhWorkflowBusy=true;let config,command,finished=false,reserved=false;
 try{
  await wfFlushReceipts();
  config=typeof wfWorkerIdentity==='function'?await wfWorkerIdentity():typeof wfResolveWorker==='function'?await wfResolveWorker():(await chrome.storage.session.get('hh_workflow_worker')).hh_workflow_worker;
  if(!config||config.tab_id&&activeJobs.has(config.tab_id))return;
  if(config.tab_id&&!config.managed&&typeof waitForHHWorker==='function')await waitForHHWorker(config.tab_id);
  const isolatedSync=config.managed===true||!!(chrome.permissions?.contains&&await chrome.permissions.contains({origins:['https://hh.ru/*']}));
  const data=await workflowCall({op:'next',worker_id:config.id,auto_sync:isolatedSync,resume_bump_version:1,kinds:['prepare','execute','refresh','sync','resume_bump']});command=data.command;if(!command)return;let result;
  if(!(command.kind==='sync'&&command.payload.automatic===true)){
   config=typeof wfResolveWorker==='function'?await wfResolveWorker():config;
   if(!config)throw Error('Подключите служебную вкладку HH.');
   activeJobs.add(config.tab_id);reserved=true;
   const tab=typeof waitForHHWorker==='function'?await waitForHHWorker(config.tab_id):await chrome.tabs.get(config.tab_id);wfHHAddress(tab.url);
  }
  if(command.kind==='refresh'){if(command.payload.resume_id){const rid=command.payload.resume_id;if(!/^[a-f0-9]{38}$/i.test(rid))throw Error('Нужно HH-резюме.');await navigate(config.tab_id,'https://hh.ru/resume/'+rid);const saved=await capture(config.tab_id,await loadPolicy()),cv=saved.bundle.resumes.find(r=>r.id===rid);const row=await ArchiveSyncCore.record('resume',rid,cv);const result=await LocalResumeService.request('/archive/sync',{client_id:'workflow_'+config.id,records:[row]});if(result.rejected?.length)throw Error('CV не синхронизировано.');}await wfRefresh(config.tab_id,command.payload.ids||[],config.id);result={state:'complete'};}
  else if(command.kind==='sync'&&command.payload.automatic===true){if(!isolatedSync)throw Error('Для фоновой проверки разрешите чтение HH в настройках.');result=await wfAutomaticSync();}
  else if(command.kind==='sync'){const target=command.payload.source_url||'https://hh.ru/applicant/negotiations';const u=new URL(target);if(u.origin!=='https://hh.ru'||!(/^\/chat\/\d+\/?$/.test(u.pathname)||u.pathname==='/applicant/negotiations')||u.search||u.hash)throw Error('Неподдерживаемая страница синхронизации HH.');await navigate(config.tab_id,target);result={state:'complete',...await wfCurrentSync(config.tab_id,true)};}
  else if(command.kind==='prepare')result=await wfPrepare(config.tab_id,command,config.id);
  else if(command.kind==='resume_bump')result=await wfBumpResume(command,config.id);
  else result=await wfExecute(config.tab_id,command,config.id);
  finished=true;await wfSaveReceipt(command,config.id,result);await wfStatus({state:result.state,note:result.note||'Задача завершена',at:new Date().toISOString()});
 }catch(error){await wfStatus({state:'needs_input',note:error.message,at:new Date().toISOString()});if(command&&!finished)try{await wfSaveReceipt(command,config.id,{state:'failed',note:error.message});}catch{}}
 finally{if(reserved)activeJobs.delete(config.tab_id);hhWorkflowBusy=false;}
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id||sender.tab||!['hh_workflow_enable','hh_workflow_poll','hh_sync_current'].includes(message.type))return;
 (async()=>{
  if(message.type==='hh_workflow_poll'){const stored=await chrome.storage.session.get('hh_workflow_worker');if(!stored.hh_workflow_worker)throw Error('На открытой вкладке HH сначала нажмите «Подключить эту вкладку HH для откликов».');hhWorkflowPulse();return {ok:true};}
  const tab=await chrome.tabs.get(message.tabId);let origin;try{origin=new URL(tab.url).origin;}catch{throw Error('Адрес вкладки ещё не определён. Дождитесь страницы HH и повторите действие.');}
  if(message.type==='hh_sync_current'){if(!['https://hh.ru','https://chat.hh.ru'].includes(origin))throw Error('Откройте HH с откликами или чатом.');if(activeJobs.size)throw Error('Дождитесь текущего сбора.');activeJobs.add(tab.id);try{const result=await wfCurrentSync(tab.id,true);await chrome.storage.local.set({hh_workflow_status:{state:'complete',note:`Чтение HH завершено. Новых наблюдений: ${result.observations_added}; сообщений: ${result.messages_added}.`,at:new Date().toISOString()}});return {ok:true,...result};}finally{activeJobs.delete(tab.id);}}
  if(origin!=='https://hh.ru')throw Error('Подключите отдельную вкладку https://hh.ru для работы с откликами.');
  await LocalResumeService.request('/health');
  await chrome.storage.session.set({hh_workflow_worker:{id:crypto.randomUUID(),tab_id:tab.id}});hhWorkflowPulse();return {ok:true};
 })().then(reply,e=>reply({ok:false,error:e.message}));return true;
});
if(chrome.alarms?.create){
 // Recreating the same alarm on every MV3 wake postpones it indefinitely.
 (async()=>{if(!chrome.alarms.get||!await chrome.alarms.get('hh-workflow'))await chrome.alarms.create('hh-workflow',{periodInMinutes:1});})().catch(()=>{});
 chrome.alarms.onAlarm.addListener(a=>{if(a.name==='hh-workflow')hhWorkflowPulse();});
 hhWorkflowPulse();
}
