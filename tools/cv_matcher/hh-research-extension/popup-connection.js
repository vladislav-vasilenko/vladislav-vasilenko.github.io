/* Same capability/state model as setup; no repeated setup CTA once HH is ready. */
(()=>{
 const el=id=>document.getElementById(id),main=el('openHHSetup'),hint=el('hhConnectionState');let data=null,pending=false;
 const settings=()=>chrome.tabs.create({url:chrome.runtime.getURL('setup.html')});
 const request=type=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Не удалось проверить HH. Откройте настройки подключения.')),8000);chrome.runtime.sendMessage({type}).then(result=>{clearTimeout(timer);result?.ok?resolve(result):reject(Error(result?.error||'Перезагрузите расширение в chrome://extensions.'));},error=>{clearTimeout(timer);reject(error);});});
 async function refresh(){if(pending)return;pending=true;try{
   data=await request('connection_status');const state=HHSetup.view(data);main.disabled=false;
   hint.textContent=state.ready?'● HH подключён. Задачи сайта и Telegram выполняются в служебной вкладке.':state.service?state.hint:'Локальный сервис не подключён. Откройте настройки подключения.';
   main.textContent=state.ready?'Открыть мои отклики':!state.service?'Подключить локальный сервис':['login','captcha','unknown','loading','loading_stalled'].includes(state.hh)?'Открыть служебную вкладку HH':data.enabled&&data.permission?'Восстановить подключение HH':'Подключить HH';
  }catch(error){data=null;main.disabled=false;main.textContent='Проверить подключение HH';hint.textContent=error.message;}finally{pending=false;}}
 main.onclick=async()=>{if(!data)return settings();const state=HHSetup.view(data);main.disabled=true;try{
   if(state.ready){const link=await LocalResumeService.request('/archive/open',{}),url=new URL(link.url);url.searchParams.set('view','applications');await chrome.tabs.create({url:url.href});}
   else if(state.service&&data.worker?.exists)await request('managed_open');
   else if(state.service&&data.enabled&&data.permission){await request('managed_enable');await refresh();}
   else await settings();
  }catch(error){hint.textContent=error.message;}finally{main.disabled=false;}};
 el('connectionSettings').onclick=settings;
 chrome.storage.onChanged.addListener((changes,area)=>{if(['local','session'].includes(area)&&['hh_managed_enabled','hh_workflow_worker','hh_workflow_status','resume_import_token'].some(k=>k in changes))refresh();});
 refresh();setInterval(()=>{if(!document.hidden)refresh();},10000);
})();
