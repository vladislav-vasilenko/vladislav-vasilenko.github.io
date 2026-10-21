/* The token stays in the worker. Content scripts receive only display metadata. */
const hhBadgePage=url=>{try{const u=new URL(url);return u.origin==='https://hh.ru'&&(/^\/vacancy\/\d+\/?$/.test(u.pathname)||u.pathname==='/search/vacancy'||u.pathname==='/applicant/vacancy_response');}catch{return false;}};
const badgePage=url=>hhBadgePage(url)||!!BoardWidgets.provider(url);
const badgeFiles=()=>['board-core.js','board-adapters.js','board-widget-core.js','hh-badges-core.js','chatgpt-export.js','hh-form-assist.js','hh-inline-ui.js','hh-badges-content.js'];
async function captureWidgetPage(tab){
 const snapshot=(await chrome.scripting.executeScript({target:{tabId:tab.id},files:['board-core.js','board-adapters.js','board-content.js']}))?.[0]?.result;
 if(snapshot?.blocked)throw Error(snapshot.warning);
 if(snapshot?.vacancies?.length){const {vacancies=[]}=await chrome.storage.local.get('vacancies');await chrome.storage.local.set({vacancies:ResearchSearch.mergeVacancies(vacancies,snapshot.vacancies)});}
 if((await chrome.tabs.get(tab.id)).url!==tab.url)throw Error('Страница изменилась во время чтения. Повторите действие.');
 // A one-vacancy action must not depend on unrelated stale cache records.
 // Sync only what this page just yielded; never replay the whole archive here.
 const records=await Promise.all((snapshot?.vacancies||[]).map(v=>ArchiveSyncCore.record('vacancy',v.id,v)));
 for(const batch of ArchiveSyncCore.batches(records)){
  const synced=await LocalResumeService.request('/archive/sync',{client_id:'widget-current-page',records:batch});
  if(synced.rejected?.length)throw Error('Описание этой страницы не сохранено: '+(synced.rejected[0].error||'проверьте версию сервиса.'));
 }
 return snapshot?.warning||'';
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id||!['hh_badges_activate','hh_badges_read','hh_inline','board_widget_capture','career_form_capture','career_fill_approve','career_fill_status','capture_current_job'].includes(message.type))return;
 (async()=>{
  const activate=message.type==='hh_badges_activate';
  if(activate&&sender.tab)throw Error('Включите отметки из расширения.');
  const tab=activate?await chrome.tabs.get(message.tabId):sender.tab;
  if(!tab||!badgePage(tab.url))throw Error('Откройте вакансии HH, Яндекса, Sber, Avito, Ozon.Tech или T-Bank.');
  const key='hh_badge_context_'+tab.id;
  if(activate){
   if(typeof message.resume_id!=='string'||!message.resume_id||typeof message.goal!=='string'||message.goal.length>2000)throw Error('Выберите CV и цель поиска.');
   const {last_ranking}=await chrome.storage.local.get('last_ranking');
   await chrome.storage.session.set({[key]:{resume_id:message.resume_id,goal:message.goal,origin:new URL(tab.url).origin,model:last_ranking?.model||'text-embedding-3-small'}});
   await chrome.scripting.executeScript({target:{tabId:tab.id},files:badgeFiles(tab.url)});
   let note='';if(!hhBadgePage(tab.url))try{await captureWidgetPage(tab);await chrome.tabs.sendMessage?.(tab.id,{type:'cv_widget_refresh'});}catch(e){note=e.message;}
   return {ok:true,note};
  }
  const config=(await chrome.storage.session.get(key))[key];if(!config||(config.origin&&config.origin!==new URL(tab.url).origin))throw Error('Включите отметки из расширения заново.');
  if(message.type==='capture_current_job'){const id=JobBoards.identity(tab.url)?.id;if(id!==message.vacancy_id)throw Error('Откройте полную страницу этой вакансии.');return {ok:true,...await captureOne(tab.id,tab.url)};}
  if(message.type==='board_widget_capture'){if(hhBadgePage(tab.url))throw Error('Используйте сбор HH.');return {ok:true,note:await captureWidgetPage(tab)};}
  const provider=hhBadgePage(tab.url)?'hh':BoardWidgets.provider(tab.url);
  const valid=id=>provider==='hh'?/^hh_\d{1,20}$/.test(id||''):BoardWidgets.valid(id,provider);
  const {resume_bundle,cover_model='luna'}=await chrome.storage.local.get(['resume_bundle','cover_model']);
  const formCV=message.type==='hh_inline'&&String(message.action).startsWith('cover')&&message.form_resume_id;
  const cv=resume_bundle?.resumes?.find(r=>r.id===(formCV||config.resume_id)&&r.quality==='full');
  if(!cv)throw Error('Выбранное CV недоступно. Обновите его в расширении.');
  if(['career_fill_approve','career_fill_status','capture_current_job'].includes(message.type)){
   const {career_form_bindings={}}=await chrome.storage.session.get('career_form_bindings'),binding=career_form_bindings[message.app_id];
   if(provider==='hh'||!binding||binding.tab_id!==tab.id||binding.source_url!==tab.url||binding.resume_id!==cv.id||binding.resume_hash!==cv.content_hash)throw Error('Привязка анкеты изменилась. Прочитайте форму заново.');
   if(message.type==='career_fill_status')return {ok:true,transfer:await LocalResumeService.request('/archive/workflow',{op:'career_fill_status',app_id:message.app_id,command_id:message.command_id})};
   if(message.confirmed!==true)throw Error('Подтвердите перенос полей.');
   const result=await LocalResumeService.request('/archive/workflow',{op:'career_fill_approve',app_id:message.app_id,intent_hash:message.intent_hash,confirmed:true});
   await careerWorkflowPulse();return {ok:true,...result,transfer:await LocalResumeService.request('/archive/workflow',{op:'career_fill_status',app_id:message.app_id,command_id:result.command_id})};
  }
  if(message.type==='career_form_capture'){
   if(provider==='hh')throw Error('Для HH используйте подготовку формы отклика.');
   const captured=await careerCaptureForm(tab,{resume_id:cv.id,resume_hash:cv.content_hash,resume_url:cv.source_url,goal:config.goal,vacancy:{id:JobBoards.identity(tab.url)?.id}},{prepare:message.preview===true});
   const {result,snapshot}=captured;
   let intent=null,note='';if(message.preview===true)try{intent=await LocalResumeService.request('/archive/workflow',{op:'career_fill_intent',app_id:result.id});}catch(e){note=e.message;}
   return {ok:true,app_id:result.id,questions:snapshot.fields.length,...(message.preview===true?{intent,note}:{} )};
  }
  if(message.type==='hh_inline'){
   if(!valid(message.vacancy_id))throw Error('Не удалось определить вакансию для вопроса. Откройте её страницу.');
   const url=new URL(tab.url),own=url.pathname.match(/^\/vacancy\/(\d+)\/?$/)?.[1]||url.searchParams.get('vacancyId')||url.searchParams.get('vacancy_id');
   const ownJob=provider==='hh'?(own?'hh_'+own:null):JobBoards.identity(tab.url)?.id;
   if(ownJob&&message.vacancy_id!==ownJob)throw Error('Вопрос относится к другой вакансии.');
   const action=message.action;if(!['analysis_read','cover_read','analysis','cover','answer','analysis_export','analysis_import','cover_export','cover_save','answer_export'].includes(action))throw Error('Неизвестное действие.');
   if(['answer','answer_export'].includes(action)&&message.form_resume_id&&message.form_resume_id!==cv.id)throw Error('В форме HH выбрано другое резюме. Выберите то же CV в расширении и включите панель заново.');
   const result=await LocalResumeService.request('/archive/hh-inline',{resume_id:cv.id,resume_hash:cv.content_hash,vacancy_id:message.vacancy_id,goal:config.goal,action,...(action==='analysis_import'?{export_id:message.export_id,answer:message.answer}:{}),...(action==='cover_save'?{text:message.text,revision:message.revision,resume_hash_at_export:message.resume_hash_at_export,vacancy_hash_at_export:message.vacancy_hash_at_export}:{}),...(action==='cover'?{comments:message.comments,sentence_count:message.sentence_count,model:['luna','terra','sol'].includes(cover_model)?cover_model:'luna'}:{}),...(action==='answer'?{question:message.question,comments:message.comments,model:message.model}: {})},action==='cover'?400000:150000);
   const latest=await chrome.storage.local.get('resume_bundle');if(latest.resume_bundle?.resumes?.find(r=>r.id===cv.id)?.content_hash!==cv.content_hash)throw Error('CV изменилось во время генерации. Откройте панель заново.');
   return {ok:true,...result};
  }
  if(!Array.isArray(message.ids)||message.ids.length>100||message.ids.some(id=>!valid(id)))throw Error('Вакансии не относятся к этому источнику.');
  if(provider==='hh')try{const observed=(await chrome.scripting.executeScript({target:{tabId:tab.id},files:['hh-sync-core.js','hh-sync-content.js']}))?.[0]?.result;if(observed?.records?.length)await LocalResumeService.request('/archive/workflow',{op:'observe',snapshot:observed});}catch{}
  const data=await LocalResumeService.request('/archive/hh-badges',{...config,provider,resume_hash:cv.content_hash,ids:message.ids},20000);
  return {ok:true,...data,resume_title:cv.title,cover_model:['luna','terra','sol'].includes(cover_model)?cover_model:'luna',available_resumes:(resume_bundle?.resumes||[]).filter(r=>r.quality==='full').map(r=>({id:r.id,title:r.title}))};
 })().then(reply,e=>reply({ok:false,error:e.message}));return true;
});
// The activeTab grant survives navigation within the same origin. New tabs require activation.
chrome.tabs.onUpdated?.addListener((id,info,tab)=>{
 if(info.status!=='complete')return;
 (async()=>{const key='hh_badge_context_'+id,config=(await chrome.storage.session.get(key))[key];if(!config)return;if(!badgePage(tab?.url)||(config.origin&&config.origin!==new URL(tab.url).origin)){await chrome.storage.session.remove(key);return;}await chrome.scripting.executeScript({target:{tabId:id},files:badgeFiles(tab.url)});})().catch(()=>{});
});
