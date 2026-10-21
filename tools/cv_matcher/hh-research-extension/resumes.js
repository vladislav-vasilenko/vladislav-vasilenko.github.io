"use strict";
const $=id=>document.getElementById(id);
const status=text=>$("status").textContent=text;
let candidate=null, queue=[];
async function refresh() {
  const {resume_bundle:b,resume_catalog:c}=await chrome.storage.local.get(["resume_bundle","resume_catalog"]);
  const rows=b?.resumes||[];
  $("counts").textContent=`HH в каталоге: ${c?.resumes?.length||0}. Полных резюме: ${rows.filter(r=>r.quality==="full").length} из ${rows.length}.`;
  $("resumes").replaceChildren(...rows.map(r=>{
    const li=document.createElement("li"), label=document.createElement("span"), choose=document.createElement("button");
    label.textContent=`${r.id===b.primary_id?"Основное · ":""}${r.title} (${r.source_type||"hh"}; ${r.quality}; ${new Date(r.checked_at).toLocaleString("ru-RU")}) `;
    choose.textContent="Сделать основным";choose.disabled=r.quality!=="full"||r.id===b.primary_id;
    choose.onclick=async()=>{try {const {resume_bundle}=await chrome.storage.local.get("resume_bundle");await chrome.storage.local.set({resume_bundle:ResumeImports.selectPrimary(resume_bundle,r.id)});status("Основное резюме изменено.");} catch(e){status(e.message);}};
    const view=document.createElement("button");view.textContent="Посмотреть текст";view.className="secondary";
    view.onclick=()=>{candidate={...r,text:r.sections?.map(s=>`${s.heading}\n${s.text}`).join("\n\n")||""};showPreview();};
    li.append(label,choose,view);return li;
  }));
  $("export").disabled=!rows.some(r=>r.id===b?.primary_id&&r.quality==="full");
}
function showPreview() {
  $("preview").hidden=!candidate;
  if(!candidate) return;
  $("title").value=candidate.title||"";$("text").value=candidate.text||"";
  $("warnings").textContent=(candidate.warnings||[]).join("\n")||"Сравните текст с оригиналом перед сохранением.";
  $("save").disabled=(candidate.source_type||"hh")==="hh";
  if(candidate.source_type==="hh") $("warnings").textContent="Снимок HH доступен для просмотра. Обновите его из каталога расширением.";
}
async function nextCandidate() {
  candidate=null;showPreview();
  while(queue.length) {
    const file=queue.shift();
    try {
      if(!file.size||file.size>12*1024*1024) throw new Error("Пустой файл или больше 12 МБ.");
      const bytes=new Uint8Array(await file.arrayBuffer());
      if(/\.(txt|md)$/i.test(file.name)) {
        const utf16=bytes[0]===255&&bytes[1]===254?"utf-16le":bytes[0]===254&&bytes[1]===255?"utf-16be":"utf-8";
        const text=new TextDecoder(utf16,{fatal:true}).decode(bytes);
        if(text.includes("\0")) throw new Error("Файл содержит бинарные данные.");
        const digest=[...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))].map(b=>b.toString(16).padStart(2,"0")).join("");
        candidate={id:"file_"+digest,file_hash:digest,source_type:"file",title:file.name.replace(/\.[^.]+$/,""),filename:file.name,text:ResumeImports.redactContacts(text),extraction_method:"browser_text",quality:"needs_review"};
      } else {
        const {resume_import_token:token}=await chrome.storage.session.get("resume_import_token");
        if(!token) throw new Error("Сначала подключите локальный конвертер кнопкой ниже.");
        let binary="";for(let i=0;i<bytes.length;i+=32768) binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
        const response=await fetch("http://127.0.0.1:8788/extract",{method:"POST",headers:{"Content-Type":"application/json","X-Resume-Import-Token":token},body:JSON.stringify({filename:file.name,content_base64:btoa(binary)}),signal:AbortSignal.timeout(45000)});
        const data=await response.json();if(!response.ok) throw new Error(data.detail||"Ошибка конвертера.");candidate=data;
      }
      status(`Прочитан ${file.name}. В очереди: ${queue.length}. Проверьте текст.`);showPreview();return;
    } catch(e) {status(`${file.name}: ${e.message}`);}
  }
}
$("files").onchange=async()=>{if(candidate&&candidate.quality==="needs_review") {status("Сначала сохраните или пропустите текущий текст.");return;}queue.push(...$("files").files);$("files").value="";await nextCandidate();};
$("connect").onclick=async()=>{
  try {
    await LocalResumeService.connect($("token").value);$("token").value="";status("Локальный сервис подключён на время сеанса Chrome. Можно выбрать файлы или открыть ранжирование.");
  } catch(e){status(e.message);}
};
$("openGoogle").onclick=async()=>{try{const source=ResumeImports.googleDoc($("googleUrl").value);await chrome.tabs.create({url:source.url});}catch(e){status(e.message);}};
$("save").onclick=async()=>{
  try {
    const snapshot=await ResumeImports.documentSnapshot(candidate,$("text").value,$("title").value);
    // Do not store a redundant copy of the raw import or claim a document is an HH experience section.
    delete snapshot.text;delete snapshot.export_url;
    const {resume_bundle:b={resumes:[]}}=await chrome.storage.local.get("resume_bundle");
    let updated={...b,schema_version:2,resumes:[...(b.resumes||[]).filter(r=>r.id!==snapshot.id),snapshot]};
    if(!updated.primary_id) updated.primary_id=snapshot.id;
    updated.resumes=updated.resumes.map(r=>({...r,role:r.id===updated.primary_id?"primary":"secondary"}));
    await chrome.storage.local.set({resume_bundle:updated});await chrome.storage.local.remove("resume_import_candidate");
    status("Проверенное резюме сохранено.");await nextCandidate();
  } catch(e){status(e.message);}
};
$("skip").onclick=async()=>{await chrome.storage.local.remove("resume_import_candidate");await nextCandidate();};
$("export").onclick=async()=>{
  const {resume_bundle}=await chrome.storage.local.get("resume_bundle");
  const url=URL.createObjectURL(new Blob([JSON.stringify({...resume_bundle,exported_at:new Date().toISOString()},null,2)],{type:"application/json"}));
  const a=document.createElement("a");a.href=url;a.download="resumes.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
};
async function pending() {
  const {resume_import_candidate:c}=await chrome.storage.local.get("resume_import_candidate");
  if(c){candidate=c;showPreview();}
}
chrome.storage.onChanged.addListener((changes,area)=>{if(area!=="local")return;if(changes.resume_bundle||changes.resume_catalog)refresh();if(changes.resume_import_candidate?.newValue)pending();});
refresh().catch(e=>status(e.message));pending().catch(e=>status(e.message));
