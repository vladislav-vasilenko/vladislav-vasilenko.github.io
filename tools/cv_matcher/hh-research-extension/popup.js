"use strict";
// popup.html is an extension UI; opening it as file:// cannot access its storage or scripting APIs.
if (!globalThis.chrome?.runtime?.id) {
  const help = document.createElement("p");
  help.textContent = "Это интерфейс расширения Chrome. Открой chrome://extensions, загрузи папку hh-research-extension и запускай его кнопкой на панели Chrome. Открытие popup.html как файла не подключает сбор и анализ.";
  document.body.replaceChildren(help);
  throw new Error("Open this popup from the installed Chrome extension.");
}
let profile;
let resumePolicy;
let lastCapture = [];
const $ = (id) => document.getElementById(id);
const selections = () => ({tier: $("tier").value, company: $("company").value,
  track: $("track").value, location: $("location").value, daily: $("daily").checked});
function fillSelect(id, rows) {
  $(id).replaceChildren(...rows.map(([value, label]) => {
    const option = document.createElement("option");
    option.value = value; option.textContent = label; return option;
  }));
}
function fillCompanies() {
  fillSelect("company", [["", "Все компании уровня"], ...profile.companies
    .filter((company) => company.tier === $("tier").value)
    .map((company) => [company.id, company.label])]);
  refreshCareerLink();
}
function refreshCareerLink() {
  const company = profile?.companies.find(c=>c.id === $("company").value);
  $("companyCareer").disabled = !company?.career_url;
}
$("company").addEventListener("change", refreshCareerLink);
$("companyCareer").addEventListener("click", async () => {
  try {
    const company = profile.companies.find(c=>c.id === $("company").value);
    const url = new URL(company?.career_url);
    if (url.protocol !== "https:") throw new Error("Карьерная ссылка не задана.");
    await chrome.tabs.create({url: url.href});
  } catch(error) {status(error.message);}
});
async function refreshCount() {
  const {vacancies = []} = await chrome.storage.local.get("vacancies");
  const full = vacancies.filter((v) => v.description_quality === "full").length;
  $("count").textContent = `Сохранено: ${vacancies.length}. Полных описаний: ${full}.`;
  $("export").disabled = !vacancies.length;
  const {resume_bundle} = await chrome.storage.local.get("resume_bundle");
  const snapshots = resume_bundle?.resumes || [];
  const primaryId=resume_bundle?.primary_id||resumePolicy?.primary_id;
  resumePolicy={...resumePolicy,primary_id:primaryId};
  const primary=snapshots.find(r=>r.id===primaryId&&r.quality==="full");
  const {resume_sync_status:sync,resume_catalog:catalog,last_ranking:ranking}=await chrome.storage.local.get(["resume_sync_status","resume_catalog","hh_crawl_status","board_crawl_status","last_ranking"]);
  const crawl=await collectionStatusRead('hh_crawl_status'),boardCrawl=await collectionStatusRead('board_crawl_status');
  $("exportResumes").disabled=!primary||sync?.state==="running";
  $("resumeStatus").textContent=primary?`Основное: ${primary.title}. Проверено: ${new Date(primary.checked_at).toLocaleString("ru-RU")}. Сохранено резюме: ${snapshots.length}.`:"Выберите загруженное основное резюме в управлении резюме.";
  if(sync?.state==="running") $("resumeStatus").textContent="Обновление резюме выполняется. Можно закрыть popup.";
  if(sync?.state==="failed") $("resumeStatus").textContent+=` Ошибка обновления HH: ${sync.error}`;
  if(sync?.failures?.length) $("resumeStatus").textContent+=` Не обновлено: ${sync.failures.length}.`;
  $("catalogStatus").textContent=catalog?`В каталоге HH: ${catalog.resumes.length}. Успешно загружено HH: ${snapshots.filter(r=>(r.source_type||"hh")==="hh"&&r.quality==="full").length}.`:"Каталог ещё не прочитан.";
  const definitions=new Map((resumePolicy.resumes||[]).map(r=>[r.id,r]));
  for(const r of catalog?.resumes||[]) definitions.set(r.id,r);
  for(const r of snapshots) definitions.set(r.id,{id:r.id,url:r.source_url,title:r.title,source_type:r.source_type||"hh"});
  resumePolicy.resumes=[...definitions.values()];
  const selected=$("resume").value;
  fillSelect("resume",resumePolicy.resumes.map(r=>[r.id,`${r.id===primaryId?'Основное':'Резервное'}: ${r.title||r.label}`]));
  $("resume").value=definitions.has(selected)?selected:primaryId;
  $("openResume").disabled=!definitions.size;
  const selectedCV=snapshots.find(r=>r.id===$("resume").value&&r.quality==="full");
  const hhSelected=selectedCV&&(selectedCV.source_type||"hh")==="hh";
  $("openRecommendations").disabled=!hhSelected;
  $("rankRecommendations").disabled=!hhSelected||!vacancies.some(v=>v.description_quality==="full"&&v.recommended_for?.includes(selectedCV.id));
  const running=crawl?.state==="running"&&Date.now()-Date.parse(crawl.updated_at)<60000;
  $("crawlHH").disabled=running;$("collect").disabled=running;$("stopCrawl").disabled=!running;
  const [active]=await chrome.tabs.query({active:true,currentWindow:true});
  $("crawlRecommendations").disabled=running||!hhSelected||ResearchSearch.recommendationResume(active?.url)!==selectedCV.id;
  const crawlLabel=running?'Сбор идёт':({complete:'Сбор завершён',partial:'Сохранена часть результатов',stopped:'Сбор остановлен',failed:'Сбор прерван ошибкой'})[crawl?.state]||'Состояние сбора';
  $("crawlStatus").textContent=crawl?`${crawlLabel}. Сохранено полных описаний: ${crawl.loaded||0}; найдено карточек: ${crawl.discovered||0}; прочитано страниц: ${crawl.pages||0}. Из кэша: ${crawl.reused||0}; закрытых пропущено: ${crawl.skipped_closed||0}; ошибок: ${crawl.failed||0}. ${crawl.current_title||crawl.error||crawl.note||''}`:"Сбор с пагинацией ещё не запускался.";
  if(crawl?.storage_target==="sqlite")$("crawlStatus").textContent+=" Полные тексты сохраняются в SQLite веб-сервиса, без заполнения кэша расширения.";
  if(crawl?.return_warning) $("crawlStatus").textContent+=" "+crawl.return_warning;
  if(running&&crawl.phase==="returning") $("crawlStatus").textContent+=" Возвращаюсь к выдаче.";
  if(crawl?.state==="running"&&!running) $("crawlStatus").textContent+=" Фоновый процесс прерван. Открой выдачу и запусти сбор снова.";
  const boardRunning=boardCrawl?.state==='running'&&Date.now()-Date.parse(boardCrawl.updated_at)<60000;
  $('crawlBoard').disabled=boardRunning||running;$('stopBoard').disabled=!boardRunning;
  $('boardCrawlStatus').textContent=boardCrawl?`${boardCrawl.state}: страниц ${boardCrawl.pages}; найдено ${boardCrawl.discovered}; полных ${boardCrawl.loaded}; требуют проверки ${boardCrawl.review||0}; закрытых ${boardCrawl.skipped_closed||0}; ошибок ${boardCrawl.failed}. ${boardCrawl.error||boardCrawl.note||''}`:'Сбор источника ещё не запускался.';
  globalThis.SearchPipeline?.update({selectedCV,full,total:vacancies.length,ranking:ranking?.resume_id===selectedCV?.id&&ranking?.resume_hash===selectedCV?.content_hash?ranking:null});

}
function status(message) { $("status").textContent = message; }
chrome.storage.onChanged.addListener((changes,area)=>{
  if(["local","session"].includes(area)&&resumePolicy&&["resume_bundle","resume_catalog","resume_sync_status","hh_crawl_status","board_crawl_status","last_ranking","vacancies"].some(k=>k in changes)) refreshCount().catch(error=>status(error.message));
});

$("tier").addEventListener("change", fillCompanies);
$("resume").addEventListener("change",()=>refreshCount().catch(e=>status(e.message)));
$("search").addEventListener("click", async () => {
  $("search").disabled = true;
  try {
    const options = selections();
    await chrome.storage.local.set({search_options: options});
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    status("Читаю каталог HH и актуальное основное резюме, затем открою поиск…");
    const result = await chrome.runtime.sendMessage({type: "sync_and_search", tabId: tab.id, options});
    if (!result?.ok) throw new Error(result?.error || "Обновление резюме не выполнено.");
    await refreshCount();
    status(result.changed ? "Резюме изменилось. Поиск открыт с новой версией профиля." : "Резюме проверено, изменений нет. Поиск открыт.");
  } catch (error) { status(error.message); }
  finally { $("search").disabled = false; }
});
$("openResume").addEventListener("click", async () => {
  try {
    const resume = resumePolicy.resumes.find((r) => r.id === $("resume").value);
    await chrome.tabs.create({url: resume?.url || chrome.runtime.getURL("resumes.html")});
  } catch (error) { status(error.message); }
});
$("saveResume").addEventListener("click", async () => {
  $("saveResume").disabled = true;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    status("Читаю профессиональные разделы резюме…");
    const result = await chrome.runtime.sendMessage({type: "capture_resume", tabId: tab.id});
    if (!result?.ok) throw new Error(result?.error || "Резюме не прочитано.");
    await refreshCount();
    status(result.changed ? "Сохранена новая версия резюме." : "Резюме проверено. Текст не изменился.");
  } catch (error) { status(error.message); }
  finally { $("saveResume").disabled = false; }
});
$("exportResumes").addEventListener("click", async () => {
  try {
    const {resume_bundle} = await chrome.storage.local.get("resume_bundle");
    downloadJSON({...resume_bundle, exported_at: new Date().toISOString()}, "resumes.json");
    status("Снимки резюме экспортированы для Python. Контакты в них не включены.");
  } catch (error) { status(error.message); }
});
function downloadJSON(data, filename) {
  const blobUrl = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = blobUrl; link.download = filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
}
$("openCatalog").addEventListener("click",()=>chrome.tabs.create({url:ResumeCatalog.CATALOG_URL}));
$("syncCatalog").addEventListener("click",async()=>{
  $("syncCatalog").disabled=true;
  try {
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    status("Читаю каталог и загружаю тексты резюме. Процесс продолжится, если закрыть popup…");
    const result=await chrome.runtime.sendMessage({type:"sync_catalog",tabId:tab.id});
    if(!result?.ok) throw new Error(result?.error||"Каталог не прочитан.");
    await refreshCount();
    status(`Найдено резюме: ${result.catalog_count}. Загружено: ${result.loaded.length}.`+(result.failures.length?` Не удалось обновить резервных: ${result.failures.length}.`:""));
  } catch(error) {status(error.message);}
  finally {$("syncCatalog").disabled=false;}
});
$("collect").addEventListener("click", async () => {
  $("collect").disabled = true;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const url = new URL(tab?.url || "about:blank");
    if (url.protocol !== "https:") {
      throw new Error("Открой страницу вакансий по HTTPS.");
    }
    const isHH = url.hostname === "hh.ru" || url.hostname.endsWith(".hh.ru");
    const config = {mode: $("boardMode").value, company: $("boardCompany").value.trim(),
      link_selector: $("linkSelector").value.trim(), description_selector: $("descriptionSelector").value.trim()};
    if (!isHH) {
      await chrome.storage.local.set({["board_recipe:" + url.hostname]: config});
      await chrome.scripting.executeScript({target: {tabId: tab.id}, func: settings => {globalThis.__jobBoardConfig = settings;}, args: [config]});
    }
    const results = await chrome.scripting.executeScript({target: {tabId: tab.id}, files: isHH ? ["content.js"] : ["board-core.js", "board-adapters.js", "board-content.js"]});
    const result = results[0]?.result;
    if(result?.vacancies?.length&&!isHH)result.vacancies=await JobBoards.canonicalRows(result.vacancies);
    if (!result?.vacancies?.length) throw new Error(result?.warning || "Карточки не найдены. Проверь загрузку страницы и вход в HH.");
    const {vacancies = []} = await chrome.storage.local.get("vacancies");
    const merged = ResearchSearch.mergeVacancies(vacancies, ResearchSearch.markSearchSource(result.vacancies,tab.url));
    lastCapture = result.vacancies;
    $("capturePreview").textContent = lastCapture.map(v => `${v.title}\n${v.link}\n${v.description_quality} — ${v.description.length} символов\n${v.description}`).join("\n\n");
    $("confirmDescriptions").disabled = !lastCapture.some(v=>v.description_quality === "needs_review");
    const sink=await createCollectionStorage({optional:true});
    if(sink)await sink.saveVacancies(ResearchSearch.markSearchSource(result.vacancies,tab.url));
    else await chrome.storage.local.set({vacancies: merged});
    await refreshCount();
    status(`Прочитано ${result.vacancies.length}. ${result.warning || "Полный текст сохранён."}`);
  } catch (error) { status(error.message); }
  finally { $("collect").disabled = false; }
});
$("confirmDescriptions").addEventListener("click", async () => {
  const checked = lastCapture.filter(v=>v.description_quality === "needs_review" && v.description.length > 150)
    .map(v=>({...v, description_quality:"full", reviewed_at:new Date().toISOString(), review_method:"user_confirmed_preview"}));
  const {vacancies=[]} = await chrome.storage.local.get("vacancies");
  await chrome.storage.local.set({vacancies:ResearchSearch.mergeVacancies(vacancies,checked)});
  $("confirmDescriptions").disabled = true;
  await refreshCount(); status(`Подтверждено описаний: ${checked.length}.`);
});
$("export").addEventListener("click", async () => {
  try {
    const {vacancies = []} = await chrome.storage.local.get("vacancies");
    const blobUrl = URL.createObjectURL(new Blob([JSON.stringify(vacancies, null, 2)], {type: "application/json"}));
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = `job-boards-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
    status("JSON подготовлен для загрузки. Его можно открыть в viewer CV Matcher.");
  } catch (error) { status(error.message); }
});

(async () => {
  try {
    // Board collection works even if the private HH resume profile is not configured.
    $("collect").disabled = false;
    const [active] = await chrome.tabs.query({active: true, currentWindow: true});
    if (active?.url?.startsWith("https://")) {
      const host = new URL(active.url).hostname;
      const stored = await chrome.storage.local.get("board_recipe:" + host);
      const recipe = stored["board_recipe:" + host];
      if (recipe) {$("boardMode").value = recipe.mode; $("boardCompany").value = recipe.company; $("linkSelector").value = recipe.link_selector; $("descriptionSelector").value = recipe.description_selector;}
    }
    const response = await fetch(chrome.runtime.getURL("search-profile.json"));
    if (!response.ok) throw new Error("Профиль поиска недоступен.");
    profile = await response.json();
    try{const catalog=await loadCompanyCatalog();profile.companies=catalog.companies;if(active?.url){const configured=JobBoardAdapters.resolve(active.url);if(configured&&JobBoardAdapters.registry.some(a=>a.id===configured.id))SearchPipeline.source(configured.id,false);if(configured&&!JobBoardAdapters.registry.some(a=>a.id===configured.id)){SearchPipeline.source('custom',false);$('boardUrl').value=active.url;}}const currentRecipe=active?.url?JobBoardAdapters.recipe(active.url):null;if(currentRecipe){const b=currentRecipe.board;const recipe={mode:'auto',company:currentRecipe.company.label,link_selector:b.link_selector||'',description_selector:b.description_selector||''};await chrome.storage.local.set({['board_recipe:'+new URL(active.url).hostname]:recipe});$('boardCompany').value=recipe.company;$('linkSelector').value=recipe.link_selector;$('descriptionSelector').value=recipe.description_selector;}}catch{}
    $("openSearch").disabled=false;
    resumePolicy={primary_id:null,resumes:[]};
    try {const resumeResponse=await fetch(chrome.runtime.getURL("resume-profile.local.json"));if(resumeResponse.ok) resumePolicy=await resumeResponse.json();} catch{}
    fillSelect("resume", resumePolicy.resumes.map((r) => [r.id, r.label]));
    $("resume").value = resumePolicy.primary_id;
    fillSelect("tier", Object.entries(profile.tier_labels));
    fillSelect("track", profile.tracks.map((track) => [track.id, track.label]));
    fillSelect("location", profile.locations.map((location) => [location.id, location.label]));
    const {search_options: saved,ranking_goal,last_ranking} = await chrome.storage.local.get(["search_options","ranking_goal","last_ranking"]);
    $("searchGoal").value=ranking_goal??last_ranking?.goal??"Generative Modelling / DiT / Transformer pre-training и post-training";
    if (saved) {
      for (const id of ["tier", "track", "location"]) {
        if ([...$(id).options].some((option) => option.value === saved[id])) $(id).value = saved[id];
      }
      $("daily").checked = Boolean(saved.daily);
    }
    fillCompanies();
    if (saved && [...$("company").options].some((option) => option.value === saved.company)) $("company").value = saved.company;
    refreshCareerLink();
    await refreshCount();
    $("search").disabled = false; $("collect").disabled = false;
    $("openResume").disabled = false; $("saveResume").disabled = false;
    $("syncCatalog").disabled = false;
    status("Пройдите шаги сверху. Сохранённые CV и вакансии доступны при повторном открытии.");
  } catch (error) { status(error.message); }
})();
$("openBoard").addEventListener("click", async () => {
  try { const url = new URL($("boardUrl").value); if (url.protocol !== "https:") throw new Error("Нужен адрес HTTPS."); await chrome.tabs.create({url: url.href}); }
  catch (error) { status(error.message); }
});

$("manageResumes").onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL("resumes.html")});
async function openRanking(source="all") {
  const goal=$("searchGoal").value.trim();await chrome.storage.local.set({ranking_goal:goal});
  const params=new URLSearchParams({resume:$("resume").value,source,goal});
  const known=new Set(['avito','ozon','tbank','yandex','sber','huawei','samsung']),board=$('pipelineSource')?.value,company=known.has(board)?board:$('company').value;
  if(known.has(company))params.set('company',company);
  await chrome.tabs.create({url:chrome.runtime.getURL("ranking.html")+"?"+params});
}
$("searchGoal").addEventListener("change",()=>chrome.storage.local.set({ranking_goal:$("searchGoal").value.trim()}));
$("openRanking").onclick=()=>openRanking();
$("rankRecommendations").onclick=()=>openRanking("hh_recommended");
$("continueHH").onclick=async()=>{
  try {
    const {pending_hh_application:app}=await chrome.storage.local.get('pending_hh_application');
    if(!app)throw new Error('Сначала нажмите «Откликнуться» в рейтинге, создайте HH-отклик и откройте вакансию.');
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    const config={action:'inspect',vacancy_id:app.context.vacancy.id,resume_id:app.context.resume_id};
    await chrome.scripting.executeScript({target:{tabId:tab.id},func:config=>{globalThis.__hhApplyAction=config;},args:[config]});
    const data=(await chrome.scripting.executeScript({target:{tabId:tab.id},files:['hh-apply-core.js','hh-apply-content.js']}))[0]?.result;
    if(!data)throw new Error('Форма не прочитана.');
    await chrome.storage.local.set({hh_application_form:{application_id:app.id,tab_id:tab.id,snapshot:data}});
    const params=new URLSearchParams({resume:app.context.resume_id,hash:app.context.resume_hash,vacancy:app.context.vacancy.id,goal:app.context.goal,continue:app.id});
    await chrome.tabs.create({url:chrome.runtime.getURL('application.html')+'?'+params});
  }catch(error){status(error.message);}
};
$("openRecommendations").onclick=async()=>{try{await chrome.tabs.create({url:ResearchSearch.recommendationUrl($("resume").value)});}catch(e){status(e.message);}};
$("openSearch").onclick=async()=>{try{const options=selections();await chrome.storage.local.set({search_options:options});await chrome.tabs.create({url:ResearchSearch.buildUrl(profile,options)});}catch(e){status(e.message);}};
$("captureGoogle").onclick=async()=>{
  try {
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});ResumeImports.googleDoc(tab.url);
    const granted=await chrome.permissions.request({origins:["https://docs.google.com/*","https://*.googleusercontent.com/*"]});
    if(!granted) throw new Error("Доступ к экспорту Google Docs не предоставлен. Можно скачать TXT/DOCX и загрузить файл.");
    status("Читаю текстовый экспорт Google Docs…");
    const result=await chrome.runtime.sendMessage({type:"capture_google_doc",tabId:tab.id});
    if(!result?.ok) throw new Error(result?.error||"Документ не прочитан.");
    await chrome.tabs.create({url:chrome.runtime.getURL("resumes.html")});
  }catch(e){status(e.message);}
};
$("crawlHH").onclick=async()=>{
  try {
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    const result=await chrome.runtime.sendMessage({type:"crawl_hh",tabId:tab.id,options:{pages:$("crawlPages").value,details:$("crawlDetails").value,skip_closed:$("skipClosed").checked!==false,force_details:$("forceDetails").checked===true}});
    if(!result?.ok) throw new Error(result?.error||"Сбор не запущен.");
    status("Сбор начат. Можно закрыть popup; прогресс появится при повторном открытии.");await refreshCount();
  }catch(e){status(e.message);}
};
$("crawlRecommendations").onclick=async()=>{
  try {
    const resumeId=$("resume").value;
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    if(ResearchSearch.recommendationResume(tab?.url)!==resumeId) throw new Error("Откройте рекомендации для выбранного CV и нажмите расширение в этой вкладке.");
    const result=await chrome.runtime.sendMessage({type:"crawl_hh",tabId:tab.id,recommended_resume_id:resumeId,options:{pages:$("crawlPages").value,details:$("crawlDetails").value,skip_closed:$("skipClosed").checked!==false,force_details:$("forceDetails").checked===true}});
    if(!result?.ok) throw new Error(result?.error||"Сбор рекомендаций не запущен.");
    status("Собираю страницы рекомендаций и полные описания. После завершения сравните их с этим CV и карьерной целью.");await refreshCount();
  }catch(e){status(e.message);}
};
$("stopCrawl").onclick=async()=>{
  const hh_crawl_status=await collectionStatusRead("hh_crawl_status");
  await chrome.runtime.sendMessage({type:"stop_hh_crawl",tabId:hh_crawl_status?.tab_id});
  status("Остановка после текущего чтения. Собранные данные сохранятся.");
};

$('openArchive').onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL('archive.html')});
$('crawlBoard').onclick=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});const reply=await chrome.runtime.sendMessage({type:'crawl_board',tabId:tab.id,options:{pages:5,details:50,skip_closed:$('skipClosed').checked!==false,force_details:$('forceDetails').checked===true}});if(!reply?.ok)throw Error(reply?.error||'Сбор не запущен.');status('Собираю источник. Можно закрыть popup; прогресс сохраняется.');await refreshCount();}catch(e){status(e.message);}};
$('stopBoard').onclick=async()=>{const board_crawl_status=await collectionStatusRead('board_crawl_status');await chrome.runtime.sendMessage({type:'stop_board_crawl',tabId:board_crawl_status?.tab_id});status('Остановка после текущего чтения. Данные сохранятся.');};

const activateJobWidgets=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});const reply=await chrome.runtime.sendMessage({type:'hh_badges_activate',tabId:tab.id,resume_id:$('resume').value,goal:$('searchGoal').value.trim()});if(!reply?.ok)throw Error(reply?.error||'Не удалось показать отметки.');status('Панель включена для выбранного CV на этой вкладке. '+(reply.note?'Синхронизация: '+reply.note:'Сохранённые результаты — без вызова API.'));}catch(e){status(e.message);}};

for(const [id,type] of [['enableHHWorker','hh_workflow_enable'],['syncHHResponses','hh_sync_current'],['pollHHWorker','hh_workflow_poll']])$(id).onclick=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});const reply=await chrome.runtime.sendMessage({type,tabId:tab.id});if(!reply?.ok)throw Error(reply?.error||'Не удалось выполнить действие.');$('workflowStatus').textContent=type==='hh_workflow_enable'?'Вкладка подключена. Задачи из сайта и Telegram будут выполняться здесь после согласования.':type==='hh_sync_current'?`Сохранено новых наблюдений: ${reply.observations_added}; сообщений: ${reply.messages_added}.`:'Проверяю очередь…';}catch(e){$('workflowStatus').textContent=e.message;}};

chrome.storage.local.get('cover_model').then(data=>{$('coverModel').value=['luna','terra','sol'].includes(data.cover_model)?data.cover_model:'luna';});
$('coverModel').onchange=()=>chrome.storage.local.set({cover_model:$('coverModel').value});



$('showHHBadges').onclick=activateJobWidgets;
$('showBoardBadges').onclick=activateJobWidgets;

$('openCompanySettings').onclick=async()=>{try{const result=await chrome.runtime.sendMessage({type:'archive_open',view:'settings'});if(!result?.ok)throw Error(result?.error||'Подключите локальный сервис.');}catch(e){status(e.message);}};

$("cleanupHH").onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL("hh-cleanup.html")});
