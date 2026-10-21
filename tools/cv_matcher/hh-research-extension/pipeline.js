(function(root){
 'use strict';
 const $=id=>document.getElementById(id);let stage=1,data={},manual=false;
 const names=['','Резюме','Поиск','Сбор','Оценка','Отклик'],next=['','К поиску →','К сбору →','К оценке →','К отклику →',''];
 function show(value,persist=true){
  stage=Math.max(1,Math.min(5,Number(value)||1));
  for(let i=1;i<=5;i++)$('stage'+i).hidden=i!==stage;
  document.querySelectorAll('[data-step]').forEach(b=>{if(Number(b.dataset.step)===stage)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
  $('pipelineBack').disabled=stage===1;$('pipelineNext').textContent=next[stage]||'Выберите вакансию в рейтинге';$('pipelineNext').hidden=stage===5;
  $('pipelineNext').disabled=(stage===1&&!data.selectedCV)||(stage===3&&!data.full);
  $('pipelineMain').scrollTop=0;if(persist&&root.chrome?.runtime?.id)chrome.storage.local.set({pipeline_stage:stage});
 }
 function source(value,persist=true){
  $('pipelineSource').value=value;const hh=value==='hh',adapter=JobBoardAdapters.registry.find(a=>a.id===value);
  $('hhSearchPanel').hidden=!hh;$('boardSearchPanel').hidden=hh;$('hhCollectPanel').hidden=!hh;$('boardCollectPanel').hidden=hh;
  if(adapter){$('boardUrl').value=JobBoardAdapters.home(value)||adapter.url;$('adapterHint').textContent='Адаптер '+adapter.label+' · список, полные описания и единый локальный архив.';}
  else if(!hh)$('adapterHint').textContent='Для неизвестного сайта доступны JobPosting и ручная настройка границ описания.';
  $('pipelineSourceStatus').textContent=hh?'Откройте выдачу HH и нажмите значок расширения в этой вкладке.':`Откройте ${adapter?.label||'сайт компании'} и нажмите значок расширения в этой вкладке. Сначала сохраняются ссылки, затем полные описания.`;
  if(persist&&root.chrome?.runtime?.id)chrome.storage.local.set({pipeline_source:value});
 }
 function update(value){data=value;$('pipelineCV').textContent=value.selectedCV?.title||'Выберите загруженное CV';$('pipelineCV').title=value.selectedCV?.title||'';$('pipelineBadge').textContent=`${value.full||0} полных вакансий`;
  const ready=[!!value.selectedCV,true,!!value.full,!!value.ranking,false];document.querySelectorAll('[data-step]').forEach(b=>b.classList.toggle('ready',ready[Number(b.dataset.step)-1]));
  if(!manual)show(stage,false);else $('pipelineNext').disabled=(stage===1&&!data.selectedCV)||(stage===3&&!data.full);
 }
 document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>{manual=true;show(b.dataset.step);});
 $('pipelineNext').onclick=()=>{manual=true;show(stage+1);};$('pipelineBack').onclick=()=>{manual=true;show(stage-1);};$('pipelineSource').onchange=()=>source($('pipelineSource').value);
 $('openApplicationRanking').onclick=()=>$('openRanking').click();
 $('openAnalysis').onclick=async()=>{try{const reply=await chrome.runtime.sendMessage({type:'archive_open',resume_id:$('resume').value,goal:$('searchGoal').value.trim()});if(!reply?.ok)throw Error(reply?.error||'Откройте «Архив» и подключите локальный сервис.');}catch(e){$('status').textContent=e.message;}};
 root.SearchPipeline={update,show,source};
 show(1,false);source('hh',false);
 if(root.chrome?.runtime?.id)(async()=>{
  const stored=await chrome.storage.local.get(['pipeline_stage','pipeline_source','resume_bundle']);const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  const adapter=JobBoardAdapters.resolve(tab?.url),hhPage=/^https:\/\/hh\.ru\/(?:search\/vacancy|vacancy\/\d+|applicant\/vacancy_response)/.test(tab?.url||'');const responsePage=/^https:\/\/(?:chat\.)?hh\.ru\/(?:applicant\/(?:negotiations|vacancy_response)|chat(?:\/|$))/.test(tab?.url||'');source(hhPage||responsePage?'hh':adapter?.id||stored.pipeline_source||'hh',false);
  if(!manual)show(responsePage?5:adapter||hhPage?3:stored.pipeline_stage|| (stored.resume_bundle?.resumes?.length?2:1),false);
 })().catch(e=>{$('status').textContent=e.message;});
})(globalThis);
