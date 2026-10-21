'use strict';
const $=id=>document.getElementById(id),status=text=>$('status').textContent=text;
async function refresh(){const data=await ArchiveStorage.read(['archive_sync_status','archive_enabled','archive_outbox']);if(data.archive_enabled!==undefined)$('auto').checked=data.archive_enabled;const s=data.archive_sync_status;status(s?`${s.note||s.state}\n${s.completed_at?'Последняя синхронизация: '+new Date(s.completed_at).toLocaleString('ru-RU'):''}${s.sent!==undefined?'\nПодтверждено записей: '+s.sent:''}${data.archive_outbox?.length?'\nВ очереди версий: '+data.archive_outbox.length:''}${s.rejected?.length?'\n'+s.rejected.map(r=>r.id+': '+r.error).join('\n'):''}`:'Архив ещё не подключён. Выполните первую синхронизацию.');}
$('connect').onclick=async()=>{try{const health=await LocalResumeService.connect($('token').value);$('token').value='';if(!health.archive)throw new Error('Перезапустите локальный сервис: в нём ещё нет архива.');$('connection').open=false;status('Сервис подключён. Можно синхронизировать архив.');}catch(e){status(e.message);}};
async function run(type){const response=await chrome.runtime.sendMessage({type,auto:$('auto').checked});if(!response?.ok)throw new Error(response?.error||'Команда не выполнена.');return response;}
$('sync').onclick=async()=>{$('sync').disabled=true;try{status('Сохраняю текущий набор…');await run('archive_sync_now');await refresh();}catch(e){status(e.message);$('connection').open=true;}finally{$('sync').disabled=false;}};
$('open').onclick=()=>run('archive_open').catch(e=>{status(e.message);$('connection').open=true;});
$('restore').onclick=async()=>{try{const result=await run('archive_restore');status(`Восстановлено из архива: ${result.resumes} CV и ${result.vacancies} вакансий. Более свежие местные записи сохранены.`);}catch(e){status(e.message);}};
$('auto').onchange=()=>ArchiveStorage.write({archive_enabled:$('auto').checked}).catch(e=>status(e.message));
setInterval(()=>refresh().catch(e=>status(e.message)),3000);
chrome.storage.onChanged.addListener((changes,area)=>{if(area==='local'&&(changes.archive_sync_status||changes.archive_outbox))refresh();});refresh().catch(e=>status(e.message));
