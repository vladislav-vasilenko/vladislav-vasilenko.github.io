async function collectionReadWithin(operation,milliseconds=12000){
 let timer;try{return await Promise.race([Promise.resolve().then(operation),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Страница не ответила на чтение DOM за '+milliseconds/1000+' секунд.')),milliseconds);})]);}finally{clearTimeout(timer);}
}
function collectionErrorReason(error){
 const text=String(error?.message||error).toLowerCase();
 if(/captcha|капч|ограничил|разрешите|требует вход|авторизац/.test(text))return 'access_required';
 if(/не распознана|не распознано/.test(text))return 'unsupported_layout';
 if(/error page|net::|не загрузилась|не готова|секунд|timeout/.test(text))return 'navigation_timeout';
 return 'transport_failed';
}
/* One persistence contract for popup crawls and service-queued crawls. */
async function collectionStatusWrite(key,value){
 const data={[key]:{...value,updated_at:new Date().toISOString()}};
 try{await chrome.storage.local.set(data);}catch(error){if(!chrome.storage.session)throw error;await chrome.storage.session.set(data);}
}
async function collectionStatusRead(key){
 const local=(await chrome.storage.local.get(key))[key];
 const session=chrome.storage.session?(await chrome.storage.session.get(key))[key]:null;
 return Date.parse(session?.updated_at||0)>Date.parse(local?.updated_at||0)?session:local||session;
}
async function createCollectionStorage({optional=false}={}){
 if(optional){try{const health=await LocalResumeService.request('/health',null,1800);if(!health.ok)return null;}catch{return null;}}
 let rows;
 const loadVacancies=async()=>rows||(rows=(await chrome.storage.local.get('vacancies')).vacancies||[]);
 const sync=async(kind,values)=>{
  for(let n=0;n<values.length;n+=30){
   const records=await Promise.all(values.slice(n,n+30).map(v=>ArchiveSyncCore.record(kind,v.id,v)));
   const reply=await LocalResumeService.request('/archive/sync',{client_id:'collection-stream',records});
   const accepted=new Set((reply.accepted||[]).map(r=>r.id));
   if(reply.rejected?.length||records.some(r=>!accepted.has(r.id)))throw Error('Архив не подтвердил сохранение всех записей. Сбор остановлен; прочитанное ранее сохранено.');
  }
 };
 return {loadVacancies,saveVacancies:async batch=>{await sync('vacancy',batch);rows=ResearchSearch.mergeVacancies(await loadVacancies(),batch);},saveScan:async scan=>sync('scan',[scan])};
}
