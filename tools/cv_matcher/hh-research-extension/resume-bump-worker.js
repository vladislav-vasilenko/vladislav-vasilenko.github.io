/* Runs in the existing HH queue; owns a disposable tab and a persisted receipt. */
async function bumpBounded(promise,label,ms=15000){
 let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Chrome не завершил '+label+' вовремя. Проверьте результат на HH; автоматического повторного клика не будет.')),ms);})]);}finally{clearTimeout(timer);}
}
async function wfBumpResume(command,worker){
 const rid=command.payload.resume_id;if(!/^[a-f0-9]{38}$/.test(rid))throw Error('Нужно выбранное HH-резюме.');
 if(!await bumpBounded(chrome.permissions.contains({origins:['https://hh.ru/*']}),'проверку разрешения HH'))throw Error('Разрешите доступ расширения к HH.');
 const tab=await bumpBounded(chrome.tabs.create({url:'about:blank',active:false}),'открытие вкладки');activeJobs.add(tab.id);
 async function inject(action='inspect',extra={}){
  await chrome.scripting.executeScript({target:{tabId:tab.id},func:value=>{globalThis.__hhResumeBumpAction=value;},args:[{action,resume_id:rid,...extra}]});
  const value=await wfScript(tab.id,['resume-bump-core.js','resume-bump-content.js']);if(!value?.state)throw Error('Карточка резюме HH не прочитана.');return value;
 }
 const read=(action,extra)=>bumpBounded(inject(action,extra),'чтение или клик карточки');
 try{
  await navigate(tab.id,'https://hh.ru/applicant/profile/me');const before=await read();
  if(before.state!=='available')return {state:before.state==='cooldown'?'complete':'needs_input',outcome:before.state,resume_id:rid,note:before.note||(before.state==='cooldown'?'HH пока не разрешает бесплатное поднятие. Проверим доступность позже.':'Резюме скрыто или не опубликовано. Видимость не изменялась.')};
  const expires_at=Date.now()+15000;
  await bumpBounded(workflowCall({op:'resume_bump_claim',command_id:command.id,worker_id:worker}),'получение разрешения');
  await read('click',{fingerprint:before.fingerprint,command_id:command.id,expires_at});
  for(let n=0;n<10;n++){await new Promise(r=>setTimeout(r,500));const after=await read();if(after.state==='cooldown')return {state:'complete',outcome:'raised',resume_id:rid,source_url:after.source_url,evidence:after.evidence,note:'Бесплатное поднятие подтверждено изменением кнопки HH. Следующая попытка — не раньше чем через 4 часа.'};}
  return {state:'uncertain',outcome:'uncertain',resume_id:rid,note:'Клик выполнен, но подтверждение HH не получено. Повтор остановлен; проверьте резюме вручную.'};
 }finally{activeJobs.delete(tab.id);try{await bumpBounded((async()=>{if(!(await chrome.tabs.get(tab.id)).active)await chrome.tabs.remove(tab.id);})(),'закрытие временной вкладки',5000);}catch{}}
}
