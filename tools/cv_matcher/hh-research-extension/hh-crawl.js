/* Sequential, bounded reads in the HH tab to which the user grants activeTab. */
const hhCrawls=new Map();
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id||!["crawl_hh","stop_hh_crawl"].includes(message.type)) return;
  if(message.type==="stop_hh_crawl") {
    const job=hhCrawls.get(message.tabId);if(job) job.stop=true;
    reply({ok:true,stopping:!!job});return;
  }
  (async()=>{
    if(hhCrawls.size||activeJobs.has(message.tabId)) throw new Error("Дождись завершения текущего сбора или обновления резюме.");
    const tab=await chrome.tabs.get(message.tabId);
    const start=HHCrawl.hhURL(tab.url,"search");
    if(message.recommended_resume_id&&ResearchSearch.recommendationResume(start)!==message.recommended_resume_id)
      throw new Error("Откройте рекомендации HH для выбранного резюме и запустите сбор из этой вкладки.");
    const sink=typeof createCollectionStorage==='function'?await createCollectionStorage({optional:true}):null;
    const job={stop:false,...sink,...(sink?{onProgress:state=>collectionStatusWrite('hh_crawl_status',{...state,storage_target:'sqlite'})}:{})};hhCrawls.set(message.tabId,job);activeJobs.add(message.tabId);
    // A popup may close; the worker keeps progress and collected records in storage.
    runHHCrawl(message.tabId,start,HHCrawl.limits(message.options),job).catch(()=>{});
    return {ok:true,started:true};
  })().then(reply,error=>reply({ok:false,error:error.message}));
  return true;
});
async function runHHCrawl(tabId,start,limits,job) {
  const state={state:"running",run_id:crypto.randomUUID(),start_page:HHCrawl.pageNumber(start),listing_complete:false,tab_id:tabId,started_at:new Date().toISOString(),pages:0,discovered:0,loaded:0,skipped_closed:0,failed:0,failures:[],phase:"listing",start_url:start,recommended_resume_id:ResearchSearch.recommendationResume(start)};
  const deadline=Date.now()+4*60*1000, seen=new Set(), pages=new Set(),listingIds=new Set(),attempted=new Set(),returned=new Set(),reusedIds=new Set();
  let listing=start, next=start, finished=false;
  const persist=async()=>{if(!job.saveVacancies)await chrome.storage.local.set({hh_crawl_status:{...state,observed_ids:[...listingIds],updated_at:new Date().toISOString()}});if(job.onProgress)await job.onProgress({...state});};
  const shouldStop=()=>job.stop||Date.now()>=deadline;
  function readDocument() {
    return new Promise((resolve,reject)=>{
      let settled=false,poll;
      const end=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);clearTimeout(poll);error?reject(error):resolve(value);};
      const check=()=>{if(settled)return;if(shouldStop())end(new Error("Сбор остановлен или достигнут лимит времени."));else poll=setTimeout(check,400);};
      const timer=setTimeout(()=>end(new Error("HH не ответил на чтение страницы за 10 секунд.")),10000);
      check();
      if(!settled)chrome.scripting.executeScript({target:{tabId},files:["content.js"]}).then(value=>end(null,value),error=>end(error));
    });
  }
  async function read(kind) {
    for(let i=0;i<8;i++) {
      if(shouldStop()) throw new Error("Сбор остановлен или достигнут лимит времени.");
      const data=(await readDocument())[0]?.result;
      if(data?.blocked) throw new Error(data.warning||"HH ограничил доступ. Проверь открытую вкладку.");
      if(data?.diagnostics)state.dom_diagnostics=data.diagnostics;
      if(kind==='listing'&&data?.layout_unknown)throw new Error('Разметка выдачи HH не распознана: нет карточек и подтверждения пустой выдачи. Данные архива сохранены.');
      if(data?.page_kind===kind && (data.empty || (kind==="listing"?data.vacancies?.length:data.vacancies?.some(v=>v.description_quality==="full"||v.archived)))) return data;
      if(i===7) throw new Error(data?.warning||"Не удалось прочитать страницу HH.");
      await new Promise(resolve=>setTimeout(resolve,500));
    }
  }
  async function save(rows) {
    if(job.saveVacancies)return job.saveVacancies(ResearchSearch.markSearchSource(rows,start));
    const {vacancies=[]}=await chrome.storage.local.get("vacancies");
    await chrome.storage.local.set({vacancies:ResearchSearch.mergeVacancies(vacancies,ResearchSearch.markSearchSource(rows,start))});
  }
  try {
    await persist();
    const previous=job.loadVacancies?await job.loadVacancies():(await chrome.storage.local.get("vacancies")).vacancies||[];
    const queue=previous.filter(v=>v.id?.startsWith("hh_")&&v.description_quality!=="full"&&Date.now()-Date.parse(v.collected_at)<24*60*60*1000&&HHCrawl.sameSearch(start,v.source_page));
    for(const row of queue) seen.add(row.id);
    while(next && state.pages<limits.pages && !shouldStop()) {
      if(pages.has(next)) throw new Error("HH вернул уже прочитанную страницу; сбор остановлен.");
      if(state.pages) await navigate(tabId,next,{shouldStop});
      listing=next;pages.add(listing);
      const data=await read("listing");
      // Fail closed if navigation dropped the selected query or filters.
      if(!HHCrawl.samePage(data.page_url,listing)) throw new Error("HH изменил адрес поиска. Проверь фильтры в открытой вкладке и запусти сбор снова.");
      listing=HHCrawl.hhURL(data.page_url,"search");
      state.pages++;for(const row of data.vacancies)listingIds.add(row.id);await save(data.vacancies.map(v=>({...v,listing_verified_at:new Date().toISOString()})));
      for(const row of data.vacancies) if(!seen.has(row.id)) {seen.add(row.id);queue.push(row);}
      state.discovered=listingIds.size;state.backlog=Math.max(0,seen.size-listingIds.size);
      const candidates=data.next_pages?.length?data.next_pages:(data.next_page?[data.next_page]:[]);
      next=candidates.map(url=>HHCrawl.nextURL(listing,url)).find(Boolean)||null;
      finished=!candidates.length;
      if(candidates.length&&!next) {
        let changed=[];try {changed=HHCrawl.changedFilters(listing,candidates[0]);}catch{}
        state.pagination_warning=`Переход на следующую страницу остановлен${changed.length?' — меняются фильтры: '+changed.join(', '):' — ссылка не соответствует следующей странице'}. Загружаю описания уже найденных вакансий.`;
        state.pagination_diagnostic={page_url:listing,candidate_url:candidates[0],changed_filters:changed};
        await persist();break;
      }
      await persist();
    }
    state.listing_complete=finished&&state.start_page===0&&!state.pagination_warning&&!shouldStop();
    // Only a full comparable search justifies checking old positions absent from it.
    const missingToCheck=new Set();
    if(state.listing_complete){
      for(const row of previous.filter(v=>v.id?.startsWith('hh_')&&v.description_quality==='full'&&!ResearchSearch.detailFresh(v,{force:limits.force_details})&&!(limits.skip_closed!==false&&HHCrawl.isClosed(v))&&!listingIds.has(v.id)&&HHCrawl.sameSearch(start,v.search_page)).slice(0,20)){
        missingToCheck.add(row.id);if(!seen.has(row.id)){seen.add(row.id);queue.push(row);}
      }
    }
    state.absent_to_check=missingToCheck.size;
    state.next_page=next;
    state.phase="descriptions"; await persist();
    const vacancies=job.loadVacancies?await job.loadVacancies():(await chrome.storage.local.get("vacancies")).vacancies||[];
    const recent=new Set(vacancies.filter(v=>v.description_quality==="full"&&ResearchSearch.detailFresh(v,{force:limits.force_details})).map(v=>v.id));
    const current=new Map(vacancies.map(v=>[v.id,v]));
    const eligible=queue.filter(v=>!(limits.skip_closed!==false&&HHCrawl.isClosed(current.get(v.id)||v)));
    state.skipped_closed=queue.length-eligible.length;
    const excluded=new Set(limits.attempted_ids||[]);
    const pending=eligible.filter(v=>!excluded.has(v.id)).filter(v=>missingToCheck.has(v.id)||(limits.skip_closed===false&&HHCrawl.isClosed(current.get(v.id)||v))||!recent.has(v.id)).sort((a,b)=>Number(listingIds.has(b.id))-Number(listingIds.has(a.id))||Number(missingToCheck.has(b.id))-Number(missingToCheck.has(a.id)));state.reused=eligible.filter(v=>recent.has(v.id)&&!excluded.has(v.id)).length;
    for(const v of eligible)if(recent.has(v.id)&&!excluded.has(v.id)){returned.add(v.id);reusedIds.add(v.id);}
    state.pending_total=pending.length;state.planned=Math.min(pending.length,limits.details);await persist();
    for(const row of pending.slice(0,limits.details)) {
      if(shouldStop()) break;
      attempted.add(row.id);returned.add(row.id);state.current_title=row.title;state.current_url=row.link;await persist();
      try {
        await navigate(tabId,HHCrawl.hhURL(row.link,"detail"),{shouldStop});
        const data=await read("detail");
        const archived=data.vacancies.find(v=>v.id===row.id&&v.archived===true);
        if(archived){await save([{...archived,availability_checked_at:new Date().toISOString()}]);state.archived=(state.archived||0)+1;continue;}
        const full=data.vacancies.filter(v=>v.id===row.id&&v.description_quality==="full"&&!v.archived);
        if(!full.length) throw new Error("Описание недоступно или вакансия в архиве.");
        await save(full.map(v=>({...v,archived:false,availability_checked_at:new Date().toISOString(),listing_snapshot:ResearchSearch.listingStamp(row),origin_query:new URL(start).searchParams.get("text")||"",search_page:listing})));
        state.loaded++;
      } catch(error) {
        if(job.stop)break;
        state.failed++;state.failures.push({id:row.id,error:error.message});
        // Login, CAPTCHA or access denial must stop the entire run, not provoke retries.
        if(/HH ограничил|captcha|капч|вход|авторизац|403/i.test(error.message)) throw error;
      }
      await persist();
    }
    state.remaining_descriptions=Math.max(0,pending.length-state.loaded-state.failed-(state.archived||0));
    state.state=job.stop?"stopped":(Date.now()>=deadline||!finished||state.failed||state.remaining_descriptions||state.pagination_warning?"partial":"complete");
    state.note=state.state==="complete"?"Прочитаны страницы до конца найденной пагинации.":"Сохранён частичный результат. Для продолжения открой следующую страницу или повтори сбор: свежие полные описания будут пропущены.";
    if(state.pagination_warning) state.note=state.pagination_warning+" Сохранён частичный результат.";
    // Preserve an HH challenge on screen so the user can handle it.
    if(!shouldStop()){
      const resultState=state.state;state.state="running";state.phase="returning";await persist();
      try{await navigate(tabId,next||listing,{shouldStop,timeoutMs:10000});}
      catch(error){if(!job.stop)state.return_warning="Результаты сохранены. Не удалось вернуться к выдаче: "+error.message;}
      finally{state.state=resultState;}
    }
  } catch(error) {state.state=job.stop?"stopped":"failed";state.error=error.message;}
  finally {
    state.completed_at=new Date().toISOString();delete state.current_title;delete state.current_url;
    if(job.stop)state.state="stopped";
    try{
    if(job.saveScan)await job.saveScan({id:state.run_id,scan_kind:'vacancy_search',scope_url:start,started_at:state.started_at,completed_at:state.completed_at,ids:[...listingIds].sort(),listing_complete:state.listing_complete,state:state.state,pages:state.pages,start_page:state.start_page});
    if(!job.saveVacancies){
    const {hh_scan_runs=[]}=await chrome.storage.local.get('hh_scan_runs');
    await chrome.storage.local.set({hh_scan_runs:[...hh_scan_runs,{id:state.run_id,scan_kind:'vacancy_search',scope_url:start,started_at:state.started_at,completed_at:state.completed_at,ids:[...listingIds].sort(),listing_complete:state.listing_complete,state:state.state,pages:state.pages,start_page:state.start_page,...(state.error?{error:state.error}:{})}]});
    }
    await persist();
    }finally{hhCrawls.delete(tabId);if(job.ownsTabLock!==false)activeJobs.delete(tabId);}
  }
  return {...state,ids:[...new Set([...listingIds,...returned])],listing_ids:[...listingIds],reused_ids:[...reusedIds],attempted_ids:[...attempted],continuation:{next_url:state.next_page||null,remaining:state.remaining_descriptions||0,listing_pages:state.pages,start_page:state.start_page}};
}
