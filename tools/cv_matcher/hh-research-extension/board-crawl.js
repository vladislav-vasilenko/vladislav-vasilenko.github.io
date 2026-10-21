/* Bounded source-tab traversal. Same-origin activeTab access, no hidden HTTP scraping. */
const boardCrawls=new Map();
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id||!['crawl_board','stop_board_crawl'].includes(message.type))return;
 if(message.type==='stop_board_crawl'){const run=boardCrawls.get(message.tabId);if(run)run.stop=true;reply({ok:true});return;}
 (async()=>{
  if(activeJobs.size)throw Error('Дождитесь завершения текущего сбора или обновления резюме.');
  if(typeof loadCompanyCatalog==='function')try{await loadCompanyCatalog();}catch{}
  const tab=await chrome.tabs.get(message.tabId),adapter=JobBoardAdapters.resolve(tab.url);
  if(!adapter)throw Error('Для пакетного сбора откройте Avito, Ozon.Tech, T-Bank, Yandex или Sber. Другие сайты можно сохранить вручную.');
  const limits=HHCrawl.limits(message.options);
  if(adapter.id==='tbank')limits.tbank_filters=(await LocalResumeService.request('/archive/workflow',{op:'discovery_config'})).tbank_filters||[];
  const sink=typeof createCollectionStorage==='function'?await createCollectionStorage({optional:true}):null;
  const run={stop:false,...sink,...(sink?{onProgress:state=>collectionStatusWrite('board_crawl_status',{...state,storage_target:'sqlite'})}:{})};boardCrawls.set(tab.id,run);activeJobs.add(tab.id);runBoardCrawl(tab.id,tab.url,adapter,limits,run).catch(()=>{});return {ok:true};
 })().then(reply,e=>reply({ok:false,error:e.message}));return true;
});
async function runBoardCrawl(tabId,start,adapter,limits,run){
 const state={state:'running',tab_id:tabId,adapter:adapter.id,started_at:new Date().toISOString(),phase:'listing',pages:0,discovered:0,loaded:0,review:0,skipped_closed:0,failed:0,failures:[],start_url:start};
 const deadline=Date.now()+4*60*1000,seen=new Set(),queue=[],visited=new Set();let next=start,last=start,finished=false;
 const stopped=()=>run.stop||Date.now()>=deadline;
 const persist=async()=>{if(!run.saveVacancies)await chrome.storage.local.set({board_crawl_status:{...state,updated_at:new Date().toISOString()}});if(run.onProgress)await run.onProgress({...state});};
 async function read(){
  for(let n=0;n<8;n++){
   if(stopped())throw Error('Сбор остановлен или достигнут лимит времени.');
   const tab=await chrome.tabs.get(tabId);if(!JobBoardAdapters.sameSource(tab.url,start)||JobBoardAdapters.resolve(tab.url)?.id!==adapter.id)throw Error('Источник изменился. Сбор остановлен; откройте нужную вкладку заново.');
   const savedCatalog=(await chrome.storage.local.get('company_catalog')).company_catalog;
   if(savedCatalog){await chrome.scripting.executeScript({target:{tabId},files:['board-core.js','board-adapters.js']});await chrome.scripting.executeScript({target:{tabId},func:catalog=>{JobBoardAdapters.configure(catalog.companies);globalThis.__jobBoardConfig={};},args:[savedCatalog]});}
   const result=(await chrome.scripting.executeScript({target:{tabId},files:savedCatalog?['board-content.js']:['board-core.js','board-adapters.js','board-content.js']}))[0]?.result;
   if(result?.blocked)throw Error(result.warning||'Источник ограничил доступ.');
   if(result?.vacancies?.length||result?.empty===true)return result;
   if(n===7)throw Error(result?.warning||'Вакансии ещё не загружены или структура источника изменилась.');
   await new Promise(resolve=>setTimeout(resolve,500));
  }
 }
 async function save(rows){rows=await JobBoards.canonicalRows(rows);if(run.saveVacancies)return run.saveVacancies(rows.map(r=>({...r,search_page:start})));const {vacancies=[]}=await chrome.storage.local.get('vacancies');await chrome.storage.local.set({vacancies:ResearchSearch.mergeVacancies(vacancies,rows.map(r=>({...r,search_page:start})))});}
 try{
  await persist();
  if(adapter.id==='tbank'&&limits.tbank_filters?.length){
   // Establish the parent direction first: professions depend on it.
   // Apply and verify the entire profile, including ML, in the live DOM.
   const filtered=JobBoardAdapters.filterURL(start,limits.tbank_filters);
   if(filtered!==start)await navigate(tabId,filtered,{readReady:true});
   await chrome.scripting.executeScript({target:{tabId},func:values=>{globalThis.__boardFilterValues=values;},args:[limits.tbank_filters]});
   const applied=(await chrome.scripting.executeScript({target:{tabId},files:['board-core.js','board-adapters.js','board-filter-core.js','board-filter-content.js']}))[0]?.result;
   if(!applied?.ok)throw Error(applied?.error||'Не удалось подтвердить фильтры T-Bank. Сбор не начат.');
   if(!JobBoardAdapters.sameSource(start,applied.url)||JobBoards.identity(applied.url))throw Error('Источник изменился при настройке фильтров.');
   start=applied.url;next=last=start;state.start_url=start;state.filters=applied.checked;
  }
  const searches=JobBoardAdapters.searchURLs(start,limits.search_terms||[]),listingBudget=Math.max(1,Math.min(100,limits.listing_budget||limits.pages*searches.length));
  state.search_terms=searches.length>1?(limits.search_terms||[]):[];state.queries_planned=searches.length;state.queries_done=0;
  for(const search of searches){
   if(stopped()||state.pages>=listingBudget)break;
   next=search;
   let queryPages=0;
   while(next&&queryPages<limits.pages&&state.pages<listingBudget&&!stopped()){
   if(visited.has(next))throw Error('Источник вернул уже прочитанную страницу.');
   if(state.pages||next!==start)await navigate(tabId,next,{readReady:true});last=next;visited.add(next);const result=await read();state.pages++;queryPages++;result.vacancies=await JobBoards.canonicalRows(result.vacancies);await save(result.vacancies.map(v=>({...v,listing_verified_at:new Date().toISOString()})));
   if(result.page_kind==='detail'){
    for(const r of result.vacancies)seen.add(r.id);state.discovered=result.vacancies.length;state.loaded+=result.vacancies.filter(r=>r.description_quality==='full').length;state.review+=result.vacancies.filter(r=>r.description_quality==='needs_review').length;finished=true;next=null;break;
   }
   for(const row of result.vacancies){if(!JobBoardAdapters.sameSource(row.link,start)||JobBoardAdapters.resolve(row.link)?.id!==adapter.id||seen.has(row.id))continue;seen.add(row.id);queue.push(row);}
   state.discovered=seen.size;next=(result.next_pages||[]).map(url=>JobBoardAdapters.nextURL(last,url)).find(Boolean)||null;
   // Dynamic/load-more boards may expose only the currently rendered subset.
   finished=false;await persist();
  }

   state.queries_done++;await persist();
  }
  const vacancies=run.loadVacancies?await run.loadVacancies():(await chrome.storage.local.get('vacancies')).vacancies||[],fresh=new Set(vacancies.filter(r=>ResearchSearch.detailFresh(r,{force:limits.force_details})).map(r=>r.id));
  const current=new Map(vacancies.map(r=>[r.id,r])),eligible=queue.filter(r=>!(limits.skip_closed!==false&&HHCrawl.isClosed(current.get(r.id)||r)));
  state.skipped_closed=queue.length-eligible.length;
  const pending=eligible.filter(r=>!fresh.has(r.id));state.reused=eligible.length-pending.length;state.phase='descriptions';state.planned=state.loaded+Math.min(pending.length,limits.details);await persist();
  for(const row of pending.slice(0,limits.details)){
   if(stopped())break;state.current_title=row.title;await persist();
   try{await navigate(tabId,row.link,{readReady:true});const result=await read();result.vacancies=await JobBoards.canonicalRows(result.vacancies);const found=result.vacancies.filter(r=>r.id===row.id&&['full','needs_review'].includes(r.description_quality));if(!found.length)throw Error('Полный текст этой вакансии не распознан.');await save(found.map(r=>({...r,listing_snapshot:ResearchSearch.listingStamp(row)})));state.loaded+=found.filter(r=>r.description_quality==='full').length;state.review+=found.filter(r=>r.description_quality==='needs_review').length;}
   catch(e){state.failed++;state.failures.push({id:row.id,error:e.message});if(/ограничил|Источник изменился|captcha|капч|авторизац|403/i.test(e.message))throw e;}
   await persist();
  }
  state.remaining=Math.max(0,pending.length-state.loaded-state.review-state.failed);
  state.state=run.stop?'stopped':finished&&!state.failed?'complete':'partial';state.next_page=next;
  state.note='Сохранены доступные загруженные карточки. Для «Показать ещё» или бесконечной ленты загрузите следующую порцию на сайте и повторите сбор. Отсутствие вакансии здесь не означает закрытие.';
  if(!run.stop&&queue.length)await navigate(tabId,next||last,{readReady:true});
 }catch(e){state.state=run.stop?'stopped':'failed';state.error=e.message;}
 finally{delete state.current_title;state.completed_at=new Date().toISOString();try{await persist();}finally{boardCrawls.delete(tabId);if(run.ownsTabLock!==false)activeJobs.delete(tabId);}}
 return {...state,ids:[...seen]};
}
