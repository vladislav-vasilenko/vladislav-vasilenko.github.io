"use strict";
const $=id=>document.getElementById(id),status=t=>$("status").textContent=t;
let result=null,busy=false,initialized=false,companyInitialized=false;
const companyReady=fetch(chrome.runtime.getURL("company-groups.json")).then(r=>{if(!r.ok)throw Error("Список компаний недоступен.");return r.json();}).then(async defaults=>{try{if(typeof loadCompanyCatalog==='function'){const saved=await loadCompanyCatalog();return CompanyFilters.configure(saved.companies);}}catch{}return CompanyFilters.configure(defaults);});
const query=new URL(location.href).searchParams;
$("source").value=query.get("source")==="hh_recommended"?"hh_recommended":"all";
if(query.has("goal")) $("goal").value=query.get("goal");
function clear(){result=null;$("results").replaceChildren();$("resultsSummary").textContent="";$("showAll").disabled=true;$("export").disabled=true;status("Параметры изменены. Пересчитайте рейтинг.");}
for(const id of ["resume","model","goal","limit","source"]) $(id).addEventListener("change",()=>{clear();refresh();if(id==="goal")chrome.storage.local.set({ranking_goal:$("goal").value.trim()});});
const rankedRows=data=>Array.isArray(data?.all)?data.all:(data?.top||[]);
const visibleCount=()=>Math.max(1,Math.min(RankingBatch.maxVacancies,Math.floor(Number($("viewCount").value)||10)));
function show(data) {
  const rows=rankedRows(data),shown=rows.slice(0,visibleCount());
  $("resultsSummary").textContent=`Показано ${shown.length} из ${rows.length} рассчитанных вакансий.`;
  $("showAll").disabled=!rows.length||shown.length===rows.length;
  $("results").replaceChildren(...shown.map((row,index)=>{
    const article=document.createElement("article"),h=document.createElement("h2"),a=document.createElement("a"),metric=document.createElement("p"),details=document.createElement("details"),summary=document.createElement("summary");
    a.textContent=`${index+1}. ${row.title}`;a.href=row.link;a.target="_blank";a.rel="noopener noreferrer";h.append(a);
    metric.className="metric";metric.textContent=`${row.company} · Близость к CV: ${row.cv_similarity.toFixed(3)}${row.goal_similarity!==null?` · К цели: ${row.goal_similarity.toFixed(3)}`:''} · Итог: ${row.score.toFixed(3)}`;
    summary.textContent="Близкие фрагменты CV и вакансии";details.append(summary);
    for(const [name,value] of [["Из выбранного резюме",row.evidence.resume],["Из вакансии",row.evidence.vacancy]]){const label=document.createElement("p"),quote=document.createElement("blockquote");label.textContent=name;quote.textContent=value;details.append(label,quote);}
    const apply=document.createElement('button');apply.textContent='Подготовить отклик';apply.setAttribute('aria-label',`Подготовить отклик: ${row.title}`);
    apply.onclick=()=>{
      const selected=result;if(!selected)return;
      const params=new URLSearchParams({resume:selected.resume_id,hash:selected.resume_hash,vacancy:row.id,goal:selected.goal||''});
      return chrome.tabs.create({url:chrome.runtime.getURL('application.html')+'?'+params});
    };
    article.append(h,metric,details,apply);ChatGPTExport.attach(article,row,()=>result);CoverLetters.attach(article,row,()=>result);return article;
  }));
  $("export").disabled=false;
}
async function displayChanged() {
  if(result) show(result);
  await chrome.storage.local.set({ranking_view_count:visibleCount()});
}
$("viewCount").addEventListener("input",displayChanged);
$("viewCount").addEventListener("change",()=>{$("viewCount").value=String(visibleCount());displayChanged();});
$("showAll").onclick=()=>{if(result){$("viewCount").value=String(rankedRows(result).length);return displayChanged();}};
async function refresh() {
 await companyReady;
 const {resume_bundle:b,vacancies=[],ranking_company}=await chrome.storage.local.get(["resume_bundle","vacancies","ranking_company"]);
 const selected=initialized?$("resume").value:new URL(location.href).searchParams.get("resume")||b?.primary_id;initialized=true;
 const placeholder=document.createElement("option");placeholder.value="";placeholder.textContent="Выберите загруженное резюме";
 $("resume").replaceChildren(placeholder,...(b?.resumes||[]).filter(r=>r.quality==="full").map(r=>{const o=document.createElement("option");o.value=r.id;o.textContent=r.title+' · '+(r.source_type||'hh');return o;}));
 $("resume").value=[...$("resume").options].some(o=>o.value===selected)?selected:"";
 if(selected&&!$("resume").value) status("Выбранное резюме не загружено полностью. Обновите его или явно выберите другое.");
 const recommended=$("source").value==="hh_recommended";
 let full=vacancies.filter(r=>r.description_quality==="full"&&!r.archived&&(!recommended||r.recommended_for?.includes($("resume").value)));
 const selectedCompany=companyInitialized?$("companyFilter").value:query.get('company')??ranking_company??'';companyInitialized=true;
 const companies=new Map();for(const row of vacancies.filter(r=>r.description_quality==='full'&&!r.archived)){const key=CompanyFilters.key(row.company);companies.set(key,CompanyFilters.label(row.company));}
 if(selectedCompany&&!companies.has(selectedCompany))companies.set(selectedCompany,'Выбранная компания');
 const options=[["",`Все компании · ${full.length}`],...[...companies].sort((a,b)=>a[1].localeCompare(b[1],'ru')).map(([key,label])=>[key,`${label} · ${full.filter(r=>CompanyFilters.key(r.company)===key).length}`])];
 $("companyFilter").replaceChildren(...options.map(([value,label])=>{const option=document.createElement('option');option.value=value;option.textContent=label;return option;}));$("companyFilter").value=selectedCompany;
 if(selectedCompany)full=full.filter(r=>CompanyFilters.key(r.company)===selectedCompany);
 const limit=Math.max(1,Math.min(RankingBatch.maxVacancies,Math.floor(Number($("limit").value)||200)));
 $("limit").value=String(limit);
 full.sort((a,b)=>(Date.parse(b.collected_at)||0)-(Date.parse(a.collected_at)||0));
 $("count").textContent=`${recommended?'Рекомендации HH для выбранного CV. ':''}Полных сохранённых вакансий: ${full.length}. В расчёт войдёт ${Math.min(full.length,limit)} самых свежих; лимит можно изменить. API вызывается только кнопкой ниже.`;
 $("rank").disabled=$("rankOffline").disabled=busy||!$("resume").value||!full.length;
 return {bundle:b,vacancies:full.slice(0,limit)};
}
$("connect").onclick=async()=>{try{const data=await LocalResumeService.connect($("token").value);$("token").value="";status(data.openai_configured?"Сервис подключён, ключ OpenAI настроен.":"Сервис подключён. Задайте OPENAI_API_KEY в .env проекта и перезапустите сервис.");}catch(e){status(e.message);}};
async function calculate(allowAPI=true){
 if(busy)return;clear();busy=true;$("rank").disabled=$("rankOffline").disabled=true;
 for(const id of ["resume","model","goal","limit","source","companyFilter"]) $(id).disabled=true;
 try {
   const {bundle,vacancies}=await refresh(),resume_id=$("resume").value;
   // Only the selected CV crosses the local bridge; reserves are not sent or embedded.
   const chosen=bundle.resumes.find(r=>r.id===resume_id);
   const request={allow_api:allowAPI,resume_id,model:$("model").value,goal:$("goal").value.trim(),bundle:{...bundle,primary_id:resume_id,resumes:[chosen]},vacancies,company_filter:$("companyFilter").value};
   status(`Сравниваю ${vacancies.length} вакансий с «${chosen.title}». Оставьте вкладку открытой…`);
   result=await RankingBatch.run(request,packet=>LocalResumeService.request("/rank",packet,240000),p=>status(`Сравниваю ${p.total} вакансий с «${chosen.title}». Обработано ${p.processed} из ${p.total}; пакет ${p.batch} из ${p.batches} (до ${RankingBatch.batchSize} вакансий). Оставьте вкладку открытой…`));
   result.selection_source=$("source").value;result.company_filter=request.company_filter;
   await chrome.storage.local.set({ranking_goal:request.goal,ranking_company:request.company_filter});
   await chrome.storage.local.set({last_ranking:result});show(result);
   status(`Резюме: ${result.resume_title}. Сравнено: ${result.ranked_count}. Готовых сравнений из кэша: ${result.cache_reused||0}. Новых API-запросов: ${result.api_requests}; токенов: ${result.usage_tokens}.\n${result.score_warning}`);
 }catch(e){
   if(e.partial_ranking){result={...e.partial_ranking,selection_source:$("source").value,company_filter:$("companyFilter").value};await chrome.storage.local.set({last_ranking:result});show(result);status(`Расчёт выполнен частично: обработано ${result.processed_count} из ${result.requested_count}. ${e.message} Автоматического повтора нет; готовые пакеты и векторы сохранены.`);}
   else status(e.message);
 }finally{busy=false;for(const id of ["resume","model","goal","limit","source","companyFilter"])$(id).disabled=false;await refresh();}
}
$("rank").onclick=()=>calculate(true);$("rankOffline").onclick=()=>calculate(false);
$("export").onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=u;a.download="vacancy-ranking.json";a.click();setTimeout(()=>URL.revokeObjectURL(u),30000);};
chrome.storage.onChanged.addListener((changes,area)=>{if(area==="local"&&(changes.resume_bundle||changes.vacancies)&&!busy){clear();refresh();}});
(async()=>{
  const {bundle}=await refresh();
  const {ranking_view_count:count,last_ranking:saved}=await chrome.storage.local.get(["ranking_view_count","last_ranking"]);
  if(Number.isInteger(count)&&count>=1&&count<=RankingBatch.maxVacancies) $("viewCount").value=String(count);
  const chosen=bundle?.resumes?.find(r=>r.id===$("resume").value);
  // Restore an existing calculation for the same CV version without a network request.
  if(saved&&chosen&&saved.resume_id===chosen.id&&saved.resume_hash===chosen.content_hash&&saved.generated_at&&(saved.selection_source||"all")===$("source").value&&(!query.has("goal")||(saved.goal||"")===query.get("goal").trim())) {
    const filter=$("companyFilter").value,rows=rankedRows(saved).filter(row=>!filter||CompanyFilters.key(row.company)===filter);
    result={...saved,all:rows,top:rows.slice(0,10),company_filter:filter};$("model").value=saved.model;$("goal").value=saved.goal||"";
    if(saved.input_count>0) $("limit").value=String(Math.min(RankingBatch.maxVacancies,saved.requested_count||saved.input_count));
    show(result);await refresh();
    status(`Сохранённый расчёт от ${new Date(saved.generated_at).toLocaleString("ru-RU")}. Резюме: ${saved.resume_title}.${saved.partial?` Частичный результат: обработано ${saved.processed_count} из ${saved.requested_count}.`:''} Можно изменить число показанных вакансий без OpenAI. Для учёта новых вакансий или правок выполните новый расчёт.`);
  }
})().catch(e=>status(e.message));

$("companyFilter").addEventListener('change',async()=>{
 try{clear();await chrome.storage.local.set({ranking_company:$("companyFilter").value});const {bundle,vacancies}=await refresh(),{last_ranking:saved}=await chrome.storage.local.get('last_ranking'),chosen=bundle?.resumes.find(r=>r.id===$("resume").value);
  if(!saved||!chosen||saved.resume_id!==chosen.id||saved.resume_hash!==chosen.content_hash||saved.model!==$("model").value||(saved.goal||'')!==$("goal").value.trim()||(saved.selection_source||'all')!==$("source").value)return;
  const current=new Map(vacancies.map(v=>[v.id,v])),rows=rankedRows(saved).filter(r=>{const job=current.get(r.id);return job&&r.collected_at&&r.collected_at===job.collected_at;});
  if(rows.length){result={...saved,all:rows,top:rows.slice(0,10),company_filter:$("companyFilter").value};show(result);status(`Показано из сохранённого рейтинга: ${rows.length} из ${vacancies.length}. Запросов к OpenAI: 0. Кнопка расчёта добавит недостающие сравнения; готовые будут взяты из кэша.`);}
 }catch(e){status(e.message);}
});
