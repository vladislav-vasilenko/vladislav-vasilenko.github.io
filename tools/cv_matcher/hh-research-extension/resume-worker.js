/* Resume catalog, snapshots and messages. Requires browser-navigation.js. */
async function loadPolicy() {
  let policy={primary_id:null,resumes:[],max_age_hours:24};
  try {const response=await fetch(chrome.runtime.getURL("resume-profile.local.json"));if(response.ok) policy=await response.json();} catch{}
  const {resume_bundle,resume_catalog}=await chrome.storage.local.get(["resume_bundle","resume_catalog"]);
  const primary=resume_bundle?.primary_id||policy.primary_id;
  const definitions=new Map(policy.resumes.map(r=>[r.id,r]));
  for(const entry of resume_catalog?.resumes||[]) definitions.set(entry.id,entry);
  for(const entry of resume_bundle?.resumes||[]) definitions.set(entry.id,{id:entry.id,url:entry.source_url,source_type:entry.source_type||"hh",label:entry.title});
  return {...policy,primary_id:primary,resumes:[...definitions.values()].map(r=>({...r,role:r.id===primary?"primary":"secondary"}))};
}
async function capture(tabId, policy, expectedId=null, {persist=true}={}) {
  for (let attempt = 0; attempt < 12; attempt++) {
    const result = await chrome.scripting.executeScript({target: {tabId}, files: ["resume-content.js"]});
    const data = result[0]?.result;
    if (data?.resume) {
      if(expectedId&&data.resume.id!==expectedId)throw Error('HH открыл другое резюме. Импорт остановлен, сохранённое CV не изменено.');
      if(expectedId)data.resume.import_origin='direct_link';
      const {resume_bundle} = await chrome.storage.local.get("resume_bundle");
      const saved = await ResumeSync.saveSnapshot(resume_bundle, data.resume, policy);
      if(persist)await chrome.storage.local.set({resume_bundle: saved.bundle});
      return saved;
    }
    if (attempt === 11) throw new Error(data?.error || "Резюме не загрузилось; поиск остановлен.");
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
}
async function readCatalog(tabId, policy) {
  await navigate(tabId, ResumeCatalog.CATALOG_URL);
  for(let attempt=0;attempt<12;attempt++) {
    const result=await chrome.scripting.executeScript({target:{tabId},files:["catalog-core.js","catalog-content.js"]});
    const data=result[0]?.result;
    if(data?.entries?.length) {
      const resumes=ResumeCatalog.cleanCatalog(data.entries,policy);
      const catalog={source_url:ResumeCatalog.CATALOG_URL,checked_at:data.checked_at,resumes,listing_complete:data.catalog_complete===true};
      await chrome.storage.local.set({resume_catalog:catalog});
      return catalog;
    }
    if(attempt===11) throw new Error(data?.error||"Каталог резюме не прочитан.");
    await new Promise(resolve=>setTimeout(resolve,350));
  }
}
async function syncCatalog(tabId, policy) {
  const catalog=await readCatalog(tabId,policy);
  policy={...policy,resumes:[...policy.resumes.filter(r=>(r.source_type||"hh")!=="hh"),...catalog.resumes]};
  const plan=ResumeCatalog.syncPlan(catalog.resumes,policy);
  const loaded=[],failures=[];
  for(const entry of plan) {
    try {
      await navigate(tabId,entry.url);
      const result=await capture(tabId,policy);
      loaded.push({id:entry.id,changed:result.changed});
    } catch(error) {
      failures.push({id:entry.id,error:error.message});
    }
  }
  // Catalog members that are no longer present must not be exported as current reserves.
  const {resume_bundle}=await chrome.storage.local.get("resume_bundle");
  const ids=new Set(catalog.resumes.map(r=>r.id));
  if(resume_bundle) await chrome.storage.local.set({resume_bundle:{...resume_bundle,
    catalog_checked_at:catalog.checked_at,catalog_source:catalog.source_url,
    catalog_resumes:catalog.resumes.map(r=>({id:r.id,url:r.url,title:r.title})),
    resumes:resume_bundle.resumes.filter(r=>(r.source_type||"hh")!=="hh"||r.import_origin==='direct_link'||ids.has(r.id))
      .map(r=>failures.some(f=>f.id===r.id)?{...r,quality:"unavailable"}:r)}});
  await navigate(tabId,ResumeCatalog.CATALOG_URL);
  return {catalog_count:catalog.resumes.length,loaded,failures,changed:loaded.find(r=>r.id===policy.primary_id)?.changed};
}
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !["capture_resume", "sync_and_search", "sync_catalog", "capture_google_doc"].includes(message.type)) return;
  (async () => {
    if (activeJobs.has(message.tabId)) throw new Error("Обновление уже выполняется.");
    activeJobs.add(message.tabId);
    try {
      if(message.type==="capture_google_doc") {
        const tab=await chrome.tabs.get(message.tabId);
        const source=ResumeImports.googleDoc(tab.url);
        const granted=await chrome.permissions.contains({origins:["https://docs.google.com/*","https://*.googleusercontent.com/*"]});
        let data;
        if(granted) {
          const response=await fetch(source.export_url,{credentials:"include",cache:"no-store",signal:AbortSignal.timeout(20000)});
          if(!response.ok) throw new Error(`Google Docs: HTTP ${response.status}. Проверь доступ к документу.`);
          if(!/text\/plain/i.test(response.headers.get("content-type")||"")) throw new Error("Google вернул страницу входа или запрет экспорта. Проверь аккаунт; можно загрузить скачанный TXT/DOCX.");
          const text=await response.text();if(text.length<100||text.length>250000) throw new Error("Текст документа имеет недопустимый размер.");
          const title=(await chrome.scripting.executeScript({target:{tabId:message.tabId},func:()=>document.title}))[0]?.result||"Google Docs CV";
          data={candidate:{...source,title:title.replace(/\s*[-–]\s*Google (?:Docs|Документы).*$/i,""),source_url:source.url,text:ResumeImports.redactContacts(text),captured_at:new Date().toISOString(),extraction_method:"google_docs_txt_export",warnings:[]}};
        } else {
          data=(await chrome.scripting.executeScript({target:{tabId:message.tabId},files:["resume-core.js","resume-import-core.js","docs-content.js"]}))[0]?.result;
        }
        if(!data?.candidate) throw new Error(data?.error||"Документ не прочитан.");
        await chrome.storage.local.set({resume_import_candidate:data.candidate});
        return {ok:true};
      }
      await chrome.storage.local.set({resume_sync_status:{state:"running",started_at:new Date().toISOString()}});
      const tab = await chrome.tabs.get(message.tabId);
      const url = new URL(tab.url || "about:blank");
      if (url.protocol !== "https:" || url.hostname !== "hh.ru") {
        throw new Error("Открой каталог резюме на hh.ru и нажми кнопку расширения в этой вкладке.");
      }
      const policy = await loadPolicy();
      // activeTab remains valid while this tab stays on https://hh.ru.
      const saved = message.type === "capture_resume" ? await capture(message.tabId, policy)
        : await syncCatalog(message.tabId,policy);
      if (message.type === "sync_and_search") {
        const {resume_bundle}=await chrome.storage.local.get("resume_bundle");
        const primary=resume_bundle?.resumes?.find(r=>r.id===policy.primary_id&&r.quality==="full");
        if(!primary) throw new Error("Основное резюме не загружено. Выбери проверенное резюме в разделе управления.");
        const response = await fetch(chrome.runtime.getURL("search-profile.json"));
        const profile = await response.json();
        await chrome.tabs.update(message.tabId, {url: ResearchSearch.buildUrl(profile, message.options)});
      }
      await chrome.storage.local.set({resume_sync_status:{state:"complete",completed_at:new Date().toISOString(),
        loaded_count:saved.loaded?.length||1,failures:saved.failures||[]}});
      return {ok: true,...saved};
    } catch(error) {
      if(message.type!=="capture_google_doc") await chrome.storage.local.set({resume_sync_status:{state:"failed",error:error.message,completed_at:new Date().toISOString()}});
      throw error;
    } finally { activeJobs.delete(message.tabId); }
  })().then(sendResponse, (error) => sendResponse({ok: false, error: error.message}));
  return true;
});
