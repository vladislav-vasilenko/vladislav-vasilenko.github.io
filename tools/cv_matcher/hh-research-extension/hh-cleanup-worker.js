/* User-confirmed cleanup. Never runs from an alarm, content script, or Telegram. */
let hhCleanupBusy=false,hhCleanupStop=false;
const cleanupSave=data=>chrome.storage.local.set({hh_cleanup_status:{...data,updated_at:new Date().toISOString()}});
async function cleanupScript(tabId,action){
 const work=(async()=>{
  await chrome.scripting.executeScript({target:{tabId},func:value=>{globalThis.__hhCleanupAction=value;},args:[action]});
  return wfScript(tabId,['hh-sync-core.js','hh-cleanup-core.js','hh-cleanup-content.js']);
 })();let timer;
 try{return await Promise.race([work,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('HH не ответил на очистку за 15 секунд. Проверьте вкладку вручную.')),15000);})]);}
 finally{clearTimeout(timer);}
}
function cleanupLock(){
 if(hhCleanupBusy||activeJobs.size||hhWorkflowBusy||collectionBusy||careerWorkflowBusy)throw Error('Дождитесь текущей задачи расширения.');
 hhCleanupBusy=true;hhCleanupStop=false;activeJobs.add('hh-cleanup');
}
async function cleanupScan(){
 const status={state:'scanning',pages:0,found:0,unknown:0};let tab;
 try{
  await chrome.storage.session.remove('hh_cleanup_plan');await cleanupSave(status);
  tab=await chrome.tabs.create({url:'about:blank',active:false});
  let url='https://hh.ru/applicant/negotiations',complete=false;const visited=new Set(),items=[],deadline=Date.now()+5*60*1000;
  while(url&&status.pages<100&&Date.now()<deadline&&!hhCleanupStop){
   if(visited.has(url))throw Error('HH повторил страницу. Предпросмотр остановлен.');visited.add(url);
   await navigate(tab.id,url,{shouldStop:()=>hhCleanupStop||Date.now()>=deadline});
   let snap;
   for(let n=0;n<10;n++){snap=await cleanupScript(tab.id,{action:'scan'});if(snap?.items?.length||snap?.empty)break;if(hhCleanupStop)throw Error('Проверка остановлена.');await new Promise(r=>setTimeout(r,400));}
   if(!snap?.items?.length&&!snap?.empty)throw Error('Не удалось распознать отклики HH. Предпросмотр не готов; удаление недоступно.');
   if(!HHCleanup.page(snap.source_url)||HHCleanup.page(snap.source_url).searchParams.get('page')!==HHCleanup.page(url).searchParams.get('page'))throw Error('Страница HH изменилась.');
   status.pages++;status.unknown+=snap.unknown||0;items.push(...snap.items.filter(HHCleanup.rejected));status.found=HHCleanup.unique(items).length;await cleanupSave(status);
   url=snap.next_page?HHCleanup.next(snap.source_url,snap.next_page):null;complete=!snap.next_page&&!snap.more_available;
  }
  const plan={id:crypto.randomUUID(),state:'preview',tab_id:tab.id,created_at:Date.now(),expires_at:Date.now()+10*60*1000,items:HHCleanup.unique(items),pages:status.pages,unknown:status.unknown,complete:complete&&!hhCleanupStop};
  await chrome.storage.session.set({hh_cleanup_plan:plan});
  await cleanupSave({...status,state:'preview',found:plan.items.length,complete:plan.complete,note:plan.complete?'Прочитаны все страницы, на которые HH дал ссылки.':'Прочитана часть списка. В подтверждение войдут только показанные отклики.'});
 }catch(error){await cleanupSave({...status,state:hhCleanupStop?'stopped':'failed',note:error.message});}
 finally{hhCleanupBusy=false;activeJobs.delete('hh-cleanup');}
}
async function cleanupExecute(plan,selected){
 const run={id:crypto.randomUUID(),plan_id:plan.id,state:'running',total:selected.length,removed:0,skipped:0,items:[],started_at:new Date().toISOString()},tabId=plan.tab_id;
 const save=async()=>{await chrome.storage.local.set({hh_cleanup_run:run});await cleanupSave(run);};
 try{
  await save();
  // Descending page order prevents earlier removals from shifting later pages.
  selected.sort((a,b)=>Number(new URL(b.page_url).searchParams.get('page')||0)-Number(new URL(a.page_url).searchParams.get('page')||0));
  let current='';
  for(const target of selected){
   if(hhCleanupStop)break;
   if(!HHCleanup.page(target.page_url))throw Error('Неподдерживаемый адрес отклика.');
   if(current!==target.page_url){await navigate(tabId,target.page_url,{shouldStop:()=>hhCleanupStop});current=target.page_url;}
   const currentTab=await chrome.tabs.get(tabId);if(!HHCleanup.page(currentTab.url)||HHCleanup.page(currentTab.url).searchParams.get('page')!==HHCleanup.page(current).searchParams.get('page'))throw Error('Вкладка HH изменена.');
   const before=await cleanupScript(tabId,{action:'scan'});
   try{HHCleanup.target(before?.items||[],target);}catch(error){run.skipped++;run.items.push({vacancy_id:target.vacancy_id,title:target.title,state:'skipped',note:error.message});await save();continue;}
   // Save the actual refusal to SQLite before removing anything from HH.
   const snapshot=await wfScript(tabId,['hh-sync-core.js','hh-sync-content.js']);
   if(!snapshot?.records?.some(r=>r.vacancy_id===target.vacancy_id&&r.status==='rejected'))throw Error('Отказ не подтверждён для сохранения в CRM.');
   await LocalResumeService.request('/archive/workflow',{op:'observe',snapshot},15000);
   const receipt={vacancy_id:target.vacancy_id,title:target.title,state:'started',at:new Date().toISOString()};run.items.push(receipt);await save();
   // Persist the attempt before clicking. A lost response never causes a retry.
   const click=await cleanupScript(tabId,{action:'remove',target});if(click?.state!=='clicked')throw Error('Нет подтверждения начала удаления. Не повторяем клик.');
   let result,confirmed=false;
   for(let n=0;n<20;n++){
    await new Promise(r=>setTimeout(r,400));
    if(!confirmed){const confirmation=await cleanupScript(tabId,{action:'confirm',target});if(!['confirmed','already_confirmed','no_dialog'].includes(confirmation?.state))throw Error('Не распознано подтверждение HH.');confirmed=confirmation.state!=='no_dialog';}
    result=await cleanupScript(tabId,{action:'verify',target});if(result?.state==='removed')break;
   }
   if(result?.state!=='removed')throw Error('Удаление не подтверждено. Проверьте HH вручную; автоматического повтора не будет.');
   receipt.state='removed';receipt.evidence=result.evidence;run.removed++;await save();
  }
  run.state=hhCleanupStop?'stopped':run.skipped?'partial':'complete';run.note=`Удалено на HH: ${run.removed} из ${run.total}. Пропущено изменившихся: ${run.skipped}. История CRM сохранена.`;
 }catch(error){for(const item of run.items)if(item.state==='started')item.state='uncertain';run.state='needs_input';run.note=error.message;}
 finally{run.completed_at=new Date().toISOString();try{await save();}finally{hhCleanupBusy=false;activeJobs.delete('hh-cleanup');}}
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id||sender.url!==chrome.runtime.getURL('hh-cleanup.html')||!['hh_cleanup_status','hh_cleanup_scan','hh_cleanup_execute','hh_cleanup_stop','hh_cleanup_open'].includes(message.type))return;
 (async()=>{
  if(message.type==='hh_cleanup_status'){
   const data=await chrome.storage.local.get(['hh_cleanup_status','hh_cleanup_run']);
   if(!hhCleanupBusy&&['running','scanning'].includes(data.hh_cleanup_status?.state)){
    const run=data.hh_cleanup_run;if(run?.state==='running'){run.state='needs_input';for(const item of run.items)if(item.state==='started')item.state='uncertain';await chrome.storage.local.set({hh_cleanup_run:run});}
    await cleanupSave({...data.hh_cleanup_status,state:'needs_input',note:'Фоновый процесс прерван. Незавершённые удаления не повторяются. Проверьте HH и найдите отказы заново.'});data.hh_cleanup_status=(await chrome.storage.local.get('hh_cleanup_status')).hh_cleanup_status;
   }
   return {ok:true,status:data.hh_cleanup_status,run:data.hh_cleanup_run,plan:(await chrome.storage.session.get('hh_cleanup_plan')).hh_cleanup_plan,busy:hhCleanupBusy};
  }
  if(message.type==='hh_cleanup_stop'){hhCleanupStop=true;return {ok:true};}
  if(message.type==='hh_cleanup_open'){const plan=(await chrome.storage.session.get('hh_cleanup_plan')).hh_cleanup_plan;if(!plan)throw Error('Сначала найдите отказы.');await chrome.tabs.update(plan.tab_id,{active:true});return {ok:true};}
  if(!await chrome.permissions.contains({origins:['https://hh.ru/*']}))throw Error('Разрешите чтение HH в настройках подключения.');
  if(message.type==='hh_cleanup_scan'){cleanupLock();void cleanupScan();return {ok:true};}
  const plan=(await chrome.storage.session.get('hh_cleanup_plan')).hh_cleanup_plan;
  if(message.confirm!==true||plan?.id!==message.plan_id)throw Error('Нужно подтверждение списка пользователем.');
  const selected=HHCleanup.selection(plan,message.keys);cleanupLock();
  try{await chrome.storage.session.set({hh_cleanup_plan:{...plan,state:'consumed'}});}catch(error){hhCleanupBusy=false;activeJobs.delete('hh-cleanup');throw error;}
  void cleanupExecute(plan,selected);return {ok:true};
 })().then(reply,error=>reply({ok:false,error:error.message}));return true;
});
