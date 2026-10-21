const byId = id => document.getElementById(id);
let reportText = '';
function paragraph(parent, text) { const p=document.createElement('p');p.textContent=text;parent.append(p); }
async function refreshDiagnostics() {
  byId('refresh').disabled=true;byId('copy').disabled=true;reportText='';byId('report').textContent='';
  byId('status').textContent='Проверяю…';byId('connections').replaceChildren();byId('adapters').replaceChildren();
  try {
    const result=await Promise.race([chrome.runtime.sendMessage({type:'diagnostics_snapshot'}),new Promise((_,reject)=>setTimeout(()=>reject(Error('Расширение не ответило за 8 секунд. Перезагрузите его в chrome://extensions.')),8000))]);
    if(!result?.ok)throw Error(result?.error||'Расширение не вернуло отчёт.');
    const r=result.report;
    paragraph(byId('connections'),r.service.reachable?'Локальный сервис отвечает · протокол '+r.service.protocol:'Локальный сервис недоступен или не подключён.');
    for(const [key,label] of [['hh','HH'],['collection','Сбор компаний'],['career','Анкеты компаний'],['giga','Giga / Telethon']])paragraph(byId('connections'),label+': '+(r.workers[key].connected?'связь подтверждена':'нет свежего подтверждения связи'));
    for(const adapter of r.adapters)paragraph(byId('adapters'),adapter.label+' — '+adapter.access.map(a=>a.host+': '+(a.granted?'чтение разрешено':'нужно разрешение')).join('; '));
    if(r.storage?.bytes!==null&&r.storage?.bytes!==undefined)paragraph(byId('connections'),'Кэш Chrome: '+(r.storage.bytes/1024/1024).toFixed(1)+' МБ'+(r.storage.limit_bytes?' из '+(r.storage.limit_bytes/1024/1024).toFixed(1)+' МБ':'')+(r.storage.near_limit?' — близко к лимиту. Сначала сохраните архив и резервную копию; не очищайте данные расширения вслепую.':''));
    reportText=JSON.stringify(r,null,2);byId('report').textContent=reportText;byId('copy').disabled=false;
    byId('status').textContent='Состояние обновлено. Если другие обработчики на связи, а «Анкеты компаний» нет — обновите расширение и проверьте журнал ошибок. Очередь не означает выполненное заполнение.';
  } catch(error) {byId('status').textContent=error.message;}
  finally {byId('refresh').disabled=false;}
}
byId('refresh').addEventListener('click',refreshDiagnostics);
byId('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(reportText);byId('status').textContent='Отчёт скопирован.';}catch{byId('status').textContent='Не удалось скопировать. Выделите технический отчёт вручную.';}});
refreshDiagnostics();
