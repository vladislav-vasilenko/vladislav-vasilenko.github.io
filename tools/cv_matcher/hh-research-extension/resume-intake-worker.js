/* Import an accessible HH CV, including a friend's public link, without catalog lookup. */
async function importLinkedResume(command){
 if(/^gdoc_[A-Za-z0-9_-]{10,200}$/.test(command.payload.resume_id))return importLinkedGoogleResume(command);
 const id=command.payload.resume_id;if(!/^[a-f0-9]{38}$/.test(id))throw Error('Нужна прямая ссылка на HH-резюме.');
 if(!await chrome.permissions.contains({origins:['https://hh.ru/*']}))throw Error('Разрешите чтение HH в параметрах расширения и повторите импорт.');
 const url='https://hh.ru/resume/'+id,tab=await chrome.tabs.create({url:'about:blank',active:false});activeJobs.add(tab.id);
 try{
  await navigate(tab.id,url);
  const policy=await loadPolicy();
  // Explicit URL authorizes reading this CV, without replacing the selected primary CV.
  const entry={id,url,source_type:'hh',role:id===policy.primary_id?'primary':'secondary'};
  const scoped={...policy,resumes:[...policy.resumes.filter(r=>r.id!==id),entry]};
  const saved=await capture(tab.id,scoped,id),resume=saved.bundle.resumes.find(r=>r.id===id);
  if(!resume||resume.quality!=='full')throw Error('HH не открыл полный текст резюме. Проверьте доступ по ссылке.');
  const result=await LocalResumeService.request('/archive/sync',{client_id:'linked-resume-import',records:[await ArchiveSyncCore.record('resume',id,resume)]});
  if(result.rejected?.length)throw Error('Прочитанное резюме не сохранено в веб-сервисе.');
  return {state:'complete',resume_id:id,note:'Резюме сохранено. Основное резюме не изменено.',api_requests:0};
 }finally{activeJobs.delete(tab.id);try{if(!(await chrome.tabs.get(tab.id)).active)await chrome.tabs.remove(tab.id);}catch{}}
}
async function importLinkedGoogleResume(command){
 const id=command.payload.resume_id;
 if(!/^gdoc_[A-Za-z0-9_-]{10,200}$/.test(id))throw Error('Нужен идентификатор Google Docs.');
 if(!await chrome.permissions.contains({origins:['https://docs.google.com/*']}))throw Error('Разрешите Google Docs: откройте документ в Chrome и нажмите расширение → «Прочитать Google Docs». Затем повторите чтение на сайте.');
 const url='https://docs.google.com/document/d/'+id.slice(5)+'/edit',tab=await chrome.tabs.create({url:'about:blank',active:false});activeJobs.add(tab.id);
 try{
  await navigate(tab.id,url);
  const actual=ResumeImports.googleDoc((await chrome.tabs.get(tab.id)).url);if(actual.id!==id)throw Error('Google открыл другой документ. Проверьте доступ и аккаунт.');
  const result=(await chrome.scripting.executeScript({target:{tabId:tab.id},files:['resume-core.js','resume-import-core.js','docs-content.js']}))[0]?.result;
  if(!result?.candidate||result.candidate.id!==id)throw Error(result?.error||'Google Docs не передал полный текст. Можно скачать TXT/DOCX и загрузить файлом.');
  return {state:'complete',candidate:result.candidate,note:'Документ прочитан. Проверьте текст на сайте перед сохранением.',api_requests:0};
 }finally{activeJobs.delete(tab.id);try{if(!(await chrome.tabs.get(tab.id)).active)await chrome.tabs.remove(tab.id);}catch{}}
}
let resumeIntakeBusy=false;
async function resumeIntakePulse(){
 if(resumeIntakeBusy||activeJobs.size)return;resumeIntakeBusy=true;activeJobs.add('resume-import');let command,worker,finished=false;
 try{
  const local=await chrome.storage.local.get(null);
  for(const [key,receipt] of Object.entries(local))if(key.startsWith('resume_import_receipt_')){await workflowCall({op:'result',...receipt});await chrome.storage.local.remove(key);}
  worker=local.resume_import_worker_id||crypto.randomUUID();if(!local.resume_import_worker_id)await chrome.storage.local.set({resume_import_worker_id:worker});
  command=(await workflowCall({op:'next',worker_id:worker,kinds:['resume_import'],resume_import_version:2})).command;if(!command)return;
  const result=await importLinkedResume(command);finished=true;await receipt(result);
 }catch(error){if(command&&!finished)try{await receipt({state:'needs_input',note:error.message,api_requests:0});}catch{}}
 finally{activeJobs.delete('resume-import');resumeIntakeBusy=false;}
 async function receipt(result){const key='resume_import_receipt_'+command.id,value={command_id:command.id,worker_id:worker,result};await chrome.storage.local.set({[key]:value});await workflowCall({op:'result',...value});await chrome.storage.local.remove(key);}
}
if(chrome.alarms?.create){
 (async()=>{if(!chrome.alarms.get||!await chrome.alarms.get('resume-intake'))await chrome.alarms.create('resume-intake',{periodInMinutes:1});})().catch(()=>{});
 chrome.alarms.onAlarm.addListener(a=>{if(a.name==='resume-intake')resumeIntakePulse();});
 resumeIntakePulse();
}
