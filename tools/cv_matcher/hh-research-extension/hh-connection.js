/* One-time optional HH access. The Python service owns state; Chrome owns the logged-in tab. */
function hhAddress(value){try{const u=new URL(value);return u.origin==='https://hh.ru'?u:null;}catch{return null;}}
function hhPendingTab(tab,config){return !!hhAddress(tab.pendingUrl)||(!tab.url||tab.url==='about:blank')&&Date.now()-Number(config?.created_at||0)<15000;}
// Advertise/poll the queue without opening a page. Resolve a tab only for real work.
async function wfWorkerIdentity(){
 const saved=await chrome.storage.local.get(['hh_managed_enabled','hh_managed_worker_id']),session=await chrome.storage.session.get(['hh_workflow_worker','hh_managed_worker_id']);
 if(!saved.hh_managed_enabled)return session.hh_workflow_worker||null;
 if(!await chrome.permissions.contains({origins:['https://hh.ru/*']}))return null;
 const id=saved.hh_managed_worker_id||session.hh_workflow_worker?.id||session.hh_managed_worker_id||crypto.randomUUID();
 if(!saved.hh_managed_worker_id){try{await chrome.storage.local.set({hh_managed_worker_id:id});}catch{await chrome.storage.session.set({hh_managed_worker_id:id});}}
 return {id,managed:true,tab_id:session.hh_workflow_worker?.tab_id};
}
let hhWorkerResolution=null;
async function wfResolveWorker(){
 if(hhWorkerResolution)return hhWorkerResolution;
 hhWorkerResolution=(async()=>{
  const saved=await chrome.storage.local.get(['hh_managed_enabled','hh_managed_worker_id']),session=await chrome.storage.session.get('hh_workflow_worker');
  if(!saved.hh_managed_enabled)return session.hh_workflow_worker||null;
  if(!await chrome.permissions.contains({origins:['https://hh.ru/*']}))throw Error('Доступ к HH отключён. Откройте настройки подключения расширения.');
  if(session.hh_workflow_worker?.managed){try{const tab=await chrome.tabs.get(session.hh_workflow_worker.tab_id);if(!(tab.pendingUrl&&!hhAddress(tab.pendingUrl))&&(hhAddress(tab.url)||hhPendingTab(tab,session.hh_workflow_worker)))return session.hh_workflow_worker;}catch{}}
  const identity=await wfWorkerIdentity(),id=identity.id,tab=await chrome.tabs.create({url:'https://hh.ru/applicant/negotiations',active:false});
  const config={id,tab_id:tab.id,managed:true,created_at:Date.now()};await chrome.storage.local.set({hh_managed_worker_id:id});await chrome.storage.session.set({hh_workflow_worker:config});return config;
 })();
 try{return await hhWorkerResolution;}finally{hhWorkerResolution=null;}
}
async function waitForHHWorker(tabId){
 // A newly created tab may expose only pendingUrl, or no URL yet. Never claim a
 // server task until a real HH document has committed; do not reload a form.
 for(let n=0;n<60;n++){
  let tab;try{tab=await chrome.tabs.get(tabId);}catch{throw Error('Служебная вкладка закрыта. Восстановите подключение HH.');}
  if(hhAddress(tab.url)&&!tab.pendingUrl)return tab;
  if(tab.pendingUrl&&!hhAddress(tab.pendingUrl))throw Error('Служебная вкладка переходит на другой сайт. Восстановите подключение HH.');
  if(tab.url&&tab.url!=='about:blank'&&!hhAddress(tab.pendingUrl))throw Error('В служебной вкладке открыт другой сайт. Восстановите вкладку HH в настройках.');
  await new Promise(resolve=>setTimeout(resolve,250));
 }
 throw Error('Служебная вкладка HH ещё не получила адрес. Откройте её, проверьте загрузку и повторите проверку связи.');
}
async function inspectWorker(){
 const config=(await chrome.storage.session.get('hh_workflow_worker')).hh_workflow_worker;
 if(!config)return {exists:false};
 let tab;try{tab=await chrome.tabs.get(config.tab_id);}catch{return {exists:false};}
 if(tab.pendingUrl&&!hhAddress(tab.pendingUrl)||!hhAddress(tab.url)&&!hhPendingTab(tab,config))return {exists:false};
 const worker={exists:true,managed:!!config.managed,tab_id:tab.id,state:tab.status==='loading'||!hhAddress(tab.url)?'loading':'unknown'};
 if(hhAddress(tab.url)&&!tab.pendingUrl){
  let timer;
  try{
   const probe=(await Promise.race([chrome.scripting.executeScript({target:{tabId:tab.id},files:['hh-connection-probe.js']}),new Promise(resolve=>{timer=setTimeout(()=>resolve([]),1500);})]))[0]?.result;
   if(hhAddress(probe?.url)&&['login','captcha','authenticated','loading','unknown'].includes(probe?.state))worker.state=probe.state;
  }catch{}finally{clearTimeout(timer);}
 }
 const saved=(await chrome.storage.session.get('hh_worker_loading_since')).hh_worker_loading_since;
 if(worker.state==='loading'){
  const at=saved?.tab_id===tab.id?saved.at:Date.now();
  if(saved?.tab_id!==tab.id)await chrome.storage.session.set({hh_worker_loading_since:{tab_id:tab.id,at}});
  worker.loading_seconds=Math.max(0,Math.floor((Date.now()-at)/1000));
  if(worker.loading_seconds>=30)worker.state='loading_stalled';
 }else if(saved)await chrome.storage.session.remove('hh_worker_loading_since');
 return worker;
}
async function registerWorkspaceBridge(){
 if(!chrome.scripting.registerContentScripts||!await chrome.permissions.contains({origins:['http://127.0.0.1/*']}))return;
 const scripts=await chrome.scripting.getRegisteredContentScripts({ids:['cv-workspace']});
 if(!scripts.length)await chrome.scripting.registerContentScripts([{id:'cv-workspace',matches:['http://127.0.0.1/*'],js:['workspace-bridge.js'],runAt:'document_idle',persistAcrossSessions:true}]);
 for(const tab of await chrome.tabs.query({url:'http://127.0.0.1/*'})){try{if(new URL(tab.url).origin==='http://127.0.0.1:8788')await chrome.scripting.executeScript({target:{tabId:tab.id},files:['workspace-bridge.js']});}catch{}}
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id)return;
 if(message.type==='workspace_setup'){
  let source;try{source=new URL(sender.tab?.url);}catch{return;}if(source.origin!=='http://127.0.0.1:8788')return;
  chrome.tabs.create({url:chrome.runtime.getURL('setup.html')}).then(()=>reply({ok:true}),()=>reply({ok:false}));return true;
 }
 if(!['connection_status','managed_enable','managed_disable','managed_open','pairing_forget','workspace_bridge_register'].includes(message.type))return;
 if(sender.tab&&sender.url!==chrome.runtime.getURL('setup.html'))return;
 (async()=>{
  if(message.type==='workspace_bridge_register'){await registerWorkspaceBridge();return {ok:true};}
  if(message.type==='pairing_forget'){await chrome.storage.session.remove('resume_import_token');await chrome.storage.local.remove('remembered_resume_import_token');return {ok:true};}
  if(message.type==='managed_open'){const worker=await inspectWorker();if(!worker.exists)throw Error('Служебная вкладка закрыта. Восстановите подключение HH.');await chrome.tabs.update(worker.tab_id,{active:true});return {ok:true};}
  if(message.type==='managed_disable'){if(typeof hhWorkflowBusy!=='undefined'&&hhWorkflowBusy)throw Error('Дождитесь завершения текущей задачи HH, затем отключите автоматизацию.');await chrome.storage.local.set({hh_managed_enabled:false});await chrome.storage.session.remove('hh_workflow_worker');return {ok:true};}
  if(message.type==='managed_enable'){
   if(!await chrome.permissions.contains({origins:['https://hh.ru/*']}))throw Error('Разрешите доступ к HH кнопкой на этой странице.');
   const health=await LocalResumeService.request('/health',null,4000);if(health.service!=='cv-matcher-local'||health.workflow!==true)throw Error('Обновите локальный сервис: в нём ещё нет функций работы с откликами.');await chrome.storage.local.set({hh_managed_enabled:true});const worker=await wfResolveWorker();hhWorkflowPulse();return {ok:true,tab_id:worker.tab_id};
  }
  const saved=await chrome.storage.local.get(['hh_managed_enabled','hh_workflow_status','remembered_resume_import_token']);let health=null,error='';try{health=await LocalResumeService.request('/health',null,4000);}catch(e){error=e.message;}
  return {ok:true,remembered:!!saved.remembered_resume_import_token,worker:await inspectWorker(),busy:typeof hhWorkflowBusy!=='undefined'&&hhWorkflowBusy,enabled:!!saved.hh_managed_enabled,permission:await chrome.permissions.contains({origins:['https://hh.ru/*']}),health,error,status:saved.hh_workflow_status};
 })().then(reply,error=>reply({ok:false,error:error.message}));return true;
});
if(chrome.runtime.onStartup)chrome.runtime.onStartup.addListener(()=>{registerWorkspaceBridge().catch(()=>{});});
registerWorkspaceBridge().catch(()=>{});
