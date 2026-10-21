/* Only DOM reads in authorized Chrome sessions. No API key or generative call. */
const collectionHosts=new Set(['hh.ru','career.avito.com','ozon.tech','career.ozon.ru','yandex.ru','yandex.com','rabota.sber.ru','tbank.ru','www.tbank.ru']);
function collectionURL(value){const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||!collectionHosts.has(u.hostname)||u.port)throw Error('Источник сбора не поддерживается.');return u;}
async function captureOne(tabId,url){
 const expected=JobBoards.identity(url);if(!expected)throw Error('Нужна полная страница вакансии.');
 const hh=new URL(url).hostname==='hh.ru';let data,row;
 for(let n=0;n<8;n++){
  const currentURL=(await chrome.tabs.get(tabId)).url;
  if(JobBoards.identity(currentURL)?.id!==expected.id||!JobBoardAdapters.sameSource(currentURL,url))throw Error('Адрес вакансии изменился. Чтение остановлено.');
  data=await collectionReadWithin(()=>wfScript(tabId,hh?['content.js']:['board-core.js','board-adapters.js','board-content.js']));
  if(data?.blocked)throw Error(data.warning||'Проверьте вход или CAPTCHA в Chrome.');
  row=data?.vacancies?.find(v=>v.id===expected.id&&(v.description_quality==='full'||v.description_quality==='needs_review'||v.archived));
  if(row)break;await new Promise(resolve=>setTimeout(resolve,300));
 }
 if(!row)throw Error('Полное описание не распознано. Вставьте текст вакансии в веб-сервис вручную.');
 if(!hh)row=(await JobBoards.canonicalRows([row]))[0];
 const saved=await LocalResumeService.request('/archive/sync',{client_id:'single-vacancy-capture',records:[await ArchiveSyncCore.record('vacancy',row.id,row)]});
 if(saved.rejected?.length)throw Error('Вакансия не сохранена в SQLite.');
 return {state:row.description_quality==='full'&&!row.archived?'complete':'needs_input',ids:[row.id],note:row.archived?'Вакансия закрыта.':row.description_quality==='full'?'Полное описание сохранено. Можно подготовить письмо.':'Проверьте полноту текста в веб-сервисе.'};
}
async function wfCollect(hhTab,command){
 const p=command.payload,u=collectionURL(p.source_url);let tabId=hhTab,temporary=false,retain=false,reuse=false,readURL=u.href;
 const job={stop:false,ownsTabLock:false,...await createCollectionStorage()};
 let checking=false,latestProgress,sequence=0,lastReport=0,reporting=false;
 const fields=['discovered','planned','loaded','reused','failed','skipped_closed','archived','review','pages'];
 const report=async(force=false)=>{if(!latestProgress||reporting||!force&&Date.now()-lastReport<3000)return;reporting=true;try{await workflowCall({op:'task_progress',command_id:command.id,worker_id:command.worker_id,sequence:++sequence,progress:latestProgress});lastReport=Date.now();}catch{}finally{reporting=false;}};
 job.onProgress=async state=>{latestProgress={phase:state.phase||'listing'};for(const field of fields)latestProgress[field]=Number.isInteger(state[field])?state[field]:field==='planned'?null:0;await report();};
 const check=async()=>{if(checking)return;checking=true;try{const status=await workflowCall({op:'task_control_status',command_id:command.id,worker_id:command.worker_id});job.stop=job.stop||status.stop;await report();}catch{job.stop=true;}finally{checking=false;}};
 await check();const timer=setInterval(check,1500);
 try{
  if(job.stop)return {state:'complete',ids:[],note:'Чтение остановлено по запросу управления.'};
  if((u.hostname==='hh.ru'||command.kind==='discover'&&p.refresh_cv&&/^[a-f0-9]{38}$/i.test(p.resume_id||''))&&!hhTab)throw Error('Подключите HH в настройках расширения для чтения выбранного HH-резюме или выдачи.');
  if(command.kind==='discover'&&p.refresh_cv&&/^[a-f0-9]{38}$/i.test(p.resume_id||'')){
   await navigate(hhTab,'https://hh.ru/resume/'+p.resume_id);const saved=await capture(hhTab,await loadPolicy(),p.resume_id,{persist:false});const cv=saved.bundle.resumes.find(r=>r.id===p.resume_id);
   if(!cv)throw Error('Выбранное CV не прочитано.');
   const ack=await LocalResumeService.request('/archive/sync',{client_id:'discovery-selected-cv',records:[await ArchiveSyncCore.record('resume',cv.id,cv)]});if(ack.rejected?.length)throw Error('Обновлённое CV не сохранено.');
  }
  if(u.hostname!=='hh.ru'){
   if(!await chrome.permissions.contains({origins:[u.origin+'/*']}))return {state:'needs_input',ids:[],note:'Разрешите сбор '+u.hostname+' в настройках расширения → Источники компаний. Затем повторите поиск.'};
   if(command.kind==='collect'&&chrome.tabs.query){
    const expected=JobBoards.identity(u.href),origins=['tbank.ru','www.tbank.ru'].includes(u.hostname)?['https://tbank.ru/*','https://www.tbank.ru/*']:[u.origin+'/*'];
    const open=(await chrome.tabs.query({url:origins})).find(t=>t.status==='complete'&&JobBoardAdapters.sameSource(t.url,u.href)&&JobBoards.identity(t.url)?.id===expected?.id);
    if(open){tabId=open.id;readURL=open.url;reuse=true;}
   }
   if(!reuse){const tab=await chrome.tabs.create({url:'about:blank',active:false});tabId=tab.id;temporary=true;activeJobs.add(tabId);}
  }
  if(job.stop)return {state:'complete',ids:[],note:'Чтение остановлено.'};
  if(!reuse)await navigate(tabId,u.href,{readReady:true,shouldStop:()=>job.stop});
  if(job.stop)return {state:'complete',ids:[],note:'Чтение остановлено.'};
  if(command.kind==='collect'){const result=await captureOne(tabId,readURL);await job.onProgress({phase:'complete',discovered:1,planned:1,loaded:result.state==='complete'?1:0,review:result.state==='needs_input'?1:0});return {...result,progress:latestProgress};}
  const limits={...HHCrawl.limits(p.options),tbank_filters:p.options?.tbank_filters||[],attempted_ids:p.options?.attempted_ids||[],search_terms:p.options?.search_terms||[],listing_budget:p.options?.listing_budget||20};
  const state=u.hostname==='hh.ru'?await runHHCrawl(tabId,u.href,limits,job):await runBoardCrawl(tabId,u.href,JobBoardAdapters.resolve(u.href),limits,job);
  await job.onProgress({...state,phase:['complete','failed','stopped'].includes(state.state)?state.state:'saving'});
  activeJobs.add(tabId);retain=state.state==='failed';
  // Persist full source versions before telling the service that ranking may start.
  const vacancies=await job.loadVacancies(),ids=state.ids||[],selected=vacancies.filter(v=>ids.includes(v.id));
  for(let n=0;n<selected.length;n+=50){const result=await LocalResumeService.request('/archive/sync',{client_id:'scheduled-discovery',records:await Promise.all(selected.slice(n,n+50).map(v=>ArchiveSyncCore.record('vacancy',v.id,v)))});if(result.rejected?.length)throw Error('Часть вакансий не сохранена в архиве.');}
  return {state:state.state==='failed'?'failed':'complete',ids,listing_ids:state.listing_ids||ids,reused_ids:state.reused_ids||[],attempted_ids:state.attempted_ids||[],continuation:state.continuation||null,progress:latestProgress,diagnostics:state.dom_diagnostics||null,reason:state.state==='failed'?collectionErrorReason(state.error||state.note):state.review?'incomplete_descriptions':'',coverage:state.state,note:state.error||state.note,warnings:state.state==='complete'?[]:[state.error||state.note||'Прочитана доступная часть выдачи.']};
 }catch(e){retain=/captcha|капч|авторизац|вход|ограничил|не загрузилась|не готова|error page/i.test(e.message);if(temporary&&retain)return {state:'needs_input',ids:[],reason:collectionErrorReason(e),note:e.message+' Служебная вкладка оставлена открытой. Проверьте её в Chrome и повторите чтение.'};throw e;}finally{clearInterval(timer);await report(true);if(temporary){activeJobs.delete(tabId);if(!retain)await chrome.tabs.remove(tabId).catch(()=>{});}}
}

async function collectionJournal(key,receipt){
 try{await chrome.storage.local.set({[key]:receipt});return chrome.storage.local;}catch(error){if(!chrome.storage.session)throw error;await chrome.storage.session.set({[key]:receipt});return chrome.storage.session;}
}
let collectionBusy=false;
async function collectionPulse(){
 if(collectionBusy)return;collectionBusy=true;let command,worker,finished=false,hhTab,temporaryHH=false,retainHH=false;
 try{
  const saved=await chrome.storage.local.get(null);
  for(const area of [chrome.storage.local,chrome.storage.session].filter(Boolean)){const journal=area===chrome.storage.local?saved:await area.get(null);for(const [key,receipt] of Object.entries(journal))if(key.startsWith('collection_receipt_')){await workflowCall({op:'result',...receipt});await area.remove(key);}}
  worker=saved.collection_worker_id||crypto.randomUUID();if(!saved.collection_worker_id)try{await chrome.storage.local.set({collection_worker_id:worker});}catch{}
  command=(await workflowCall({op:'next',worker_id:worker,kinds:['discover','collect'],collection_version:2})).command;if(!command)return;
  const p=command.payload,needsHH=new URL(p.source_url).hostname==='hh.ru'||command.kind==='discover'&&p.refresh_cv&&/^[a-f0-9]{38}$/i.test(p.resume_id||'');
  if(needsHH){
   if(await chrome.permissions.contains({origins:['https://hh.ru/*']})){const taskTab=await chrome.tabs.create({url:'about:blank',active:false});hhTab=taskTab.id;temporaryHH=true;}
   else{const config=await wfResolveWorker();hhTab=config?.tab_id;if(hhTab&&activeJobs.has(hhTab))throw Error('Служебная вкладка HH занята. Дождитесь завершения текущей операции.');}
  }
  activeJobs.add(hhTab||'collection');
  const result=await wfCollect(hhTab,command);retainHH=result.state==='needs_input'&&['access_required','login_required'].includes(result.reason);finished=true;
  const key='collection_receipt_'+command.id,receipt={command_id:command.id,worker_id:worker,result};const area=await collectionJournal(key,receipt);await workflowCall({op:'result',...receipt});await area.remove(key);
 }catch(e){
  retainHH=/captcha|капч|требует вход|авторизац/i.test(e.message);
  if(command&&!finished){const key='collection_receipt_'+command.id,receipt={command_id:command.id,worker_id:worker,result:{state:'failed',reason:collectionErrorReason(e),note:e.message,ids:[]}};try{const area=await collectionJournal(key,receipt);await workflowCall({op:'result',...receipt});await area.remove(key);}catch{}}
 }finally{activeJobs.delete(hhTab||'collection');if(temporaryHH&&!retainHH)try{if(!(await chrome.tabs.get(hhTab)).active)await chrome.tabs.remove(hhTab);}catch{}collectionBusy=false;}
}
if(chrome.alarms?.create){
 (async()=>{if(!chrome.alarms.get||!await chrome.alarms.get('collection-pipeline'))await chrome.alarms.create('collection-pipeline',{periodInMinutes:1});})().catch(()=>{});
 chrome.alarms.onAlarm.addListener(a=>{if(a.name==='collection-pipeline')collectionPulse();});collectionPulse();
}
