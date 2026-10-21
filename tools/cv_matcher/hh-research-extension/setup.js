'use strict';
const $=id=>document.getElementById(id),status=message=>$('status').textContent=message;
let refreshing=false,acting=false,initialized=false,last=null,manualStep=null,lastStep=null;
function bounded(task,ms,label){return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(label)),ms);Promise.resolve(task).then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});}
async function message(type,options={}){
 if(!globalThis.chrome?.runtime?.id)throw Error('Откройте эту страницу через параметры установленного расширения Chrome. HTML-файл не подключён к расширению.');
 const timeout=type==='connection_status'?8000:20000;
 let result;try{result=await bounded(chrome.runtime.sendMessage({type,...options}),timeout,'Расширение не ответило за '+timeout/1000+' секунд. Перезагрузите ML Research Vacancy Search в chrome://extensions, затем обновите эту страницу.');}
 catch(error){if(/receiving end|message port|context invalidated|could not establish/i.test(error.message||''))throw Error('Фоновая часть расширения недоступна. Перезагрузите ML Research Vacancy Search в chrome://extensions, затем обновите эту страницу.');throw error;}
 if(!result)throw Error('Фоновая часть расширения не ответила. Перезагрузите ML Research Vacancy Search в chrome://extensions, затем обновите эту страницу.');
 if(!result.ok)throw Error(result.error||'Расширение не смогло выполнить действие.');return result;
}
function failed(error){
 last=null;$('progress').textContent='Нужна проверка';$('headline').textContent='Не удалось проверить подключение';$('nextStep').textContent=error.message;
 showStep(1);
 $('serviceBadge').textContent='Не проверено';$('serviceBadge').className='badge pending';$('serviceState').textContent='Связь не подтверждена. Это не означает, что локальная база недоступна.';$('serviceSetup').open=true;
 $('hhBadge').textContent='Не проверено';$('hhBadge').className='badge pending';$('hhState').textContent='Сначала восстановите связь с расширением.';$('readyBadge').textContent='Ожидает проверки';$('enable').disabled=true;$('workspace').disabled=true;$('openHH').hidden=true;$('disable').hidden=true;status(error.message);
}

function showStep(step){for(const [number,id] of [[1,'serviceStep'],[2,'hhStep'],[3,'continueStep']]){$(id).hidden=number!==step;$('step'+number).setAttribute('aria-current',number===step?'step':'false');}}
function paint(data){
 last=data;const state=HHSetup.view(data);if(lastStep!==state.step){manualStep=null;lastStep=state.step;}showStep(manualStep||state.step);
 $('step1State').textContent=state.service?'✓ Подключён':state.old?'Обновите сервис':'Нужен код';$('step2State').textContent=state.hh==='ready'?'✓ Готов':state.step===2?'Текущий шаг':'После сервиса';$('step3State').textContent=state.ready?'Можно начинать':'После HH';$('step2').disabled=!state.service;$('step3').disabled=!state.ready;$('progress').textContent='Шаг '+state.step+' из 3';$('headline').textContent=state.headline;$('nextStep').textContent=state.ready?'Выбирайте вакансию на сайте или в Telegram. Отправка — после вашего разрешения.':state.step===1?'Запустите сервис и подключитесь локальным кодом.':state.hint;
 $('serviceBadge').textContent=state.service?'Подключён':state.old?'Нужно обновить':'Нет связи';$('serviceBadge').className='badge '+(state.service?'ok':'pending');
 $('serviceState').textContent=state.service?'База и история доступны. '+(data.remembered?'Подключение сохранено на этом компьютере.':'Код действует в текущем сеансе Chrome.'):state.old?'Код принят, но в сервисе ещё нет функций работы с откликами. Перезапустите обновлённый resume_import_server.py.':data.error||'Нет ответа сервиса.';
 if(!initialized||!state.service)$('serviceSetup').open=!state.service;
 $('forget').hidden=!state.service&&!data.remembered;if(!initialized)$('remember').checked=!!data.remembered;
 $('enable').textContent=state.enableDisabled?'Сначала подключите сервис':state.enableLabel;$('enable').disabled=acting||state.enableDisabled;
 $('hhBadge').textContent=({ready:'Готов',login:'Нужен вход',captcha:'Нужна CAPTCHA',loading:'Загружается',loading_stalled:'Загрузка задержалась',permission_missing:'Нет доступа',tab_missing:'Вкладка закрыта',unknown:'Проверьте вход',disabled:'Не подключён'})[state.hh];$('hhBadge').className='badge '+(state.hh==='ready'?'ok':'pending');$('hhState').textContent=state.hint;
 $('enable').hidden=['ready','login','captcha','loading','loading_stalled','unknown'].includes(state.hh);$('openHH').hidden=!state.openTab;$('workspaceEarly').hidden=!state.service||state.ready;$('disable').hidden=!data.enabled;$('disable').disabled=acting||!!data.busy;$('workspace').disabled=acting||!state.service;
 $('readyBadge').textContent=state.ready?'Готово':'Можно подготовить письмо';$('readyBadge').className='badge '+(state.ready?'ok':'pending');
 $('workerNote').textContent=data.busy?'HH выполняет текущую задачу. Отключить автоматизацию можно после её завершения.':data.status?.state==='needs_input'?'Последняя задача: '+(/Failed to construct.*URL|Invalid URL/i.test(data.status.note||'')?'Не удалось определить адрес HH при открытии вкладки. Это ошибка предыдущей задачи; текущая связь проверяется отдельно.':data.status.note):'';
 initialized=true;
}
async function refresh(){if(refreshing||acting)return;refreshing=true;$('refresh').disabled=true;try{paint(await message('connection_status'));}catch(e){failed(e);}finally{refreshing=false;$('refresh').disabled=false;}}
async function action(fn){if(acting)return;acting=true;for(const id of ['connect','enable','disable','workspace','forget','refresh'])$(id).disabled=true;try{await fn();}catch(e){status(e.message);}finally{acting=false;$('connect').disabled=false;$('forget').disabled=false;$('refresh').disabled=false;if(last)paint(last);await refresh();}}
$('connect').onclick=()=>action(async()=>{await LocalResumeService.connect($('code').value,{remember:$('remember').checked});$('code').value='';await message('workspace_bridge_register');status('Код принят. Проверяю доступные функции сервиса…');});
$('enable').onclick=()=>action(async()=>{
 // Keep permissions.request as the first asynchronous call in the click gesture.
 const granted=await chrome.permissions.request({origins:['https://hh.ru/*']});if(!granted)throw Error('Доступ к HH не предоставлен. Подключение не включено; разрешение можно запросить снова.');
 await message('managed_enable');status('Служебная вкладка открыта. Если HH просит вход, войдите в аккаунт — статус обновится здесь.');
});
$('disable').onclick=()=>action(async()=>{await message('managed_disable');status('Автоматизация HH отключена. Открытая вкладка и все данные сохранены.');});
$('forget').onclick=()=>action(async()=>{await message('pairing_forget');status('Код удалён из расширения. Данные в локальной базе сохранены.');});
$('openHH').onclick=async()=>{try{await message('managed_open');}catch(e){status(e.message);await refresh();}};
$('workspace').onclick=()=>action(async()=>{const link=await LocalResumeService.request('/archive/open',{});await chrome.tabs.create({url:link.url});});
$('workspaceEarly').onclick=()=>$('workspace').onclick();
for(const number of [1,2,3])$('step'+number).onclick=()=>{manualStep=number;showStep(number);};
$('pipeline').onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL('popup.html')});$('refresh').onclick=refresh;
refresh();setInterval(()=>{if(!document.hidden)refresh();},5000);

$('companySettings').onclick=async()=>{try{await message('archive_open',{view:'settings'});}catch(e){status(e.message);}};

$('collectionPermissions').onclick=async()=>{try{const origins=['https://career.avito.com/*','https://ozon.tech/*','https://career.ozon.ru/*','https://yandex.ru/*','https://yandex.com/*','https://rabota.sber.ru/*','https://tbank.ru/*','https://www.tbank.ru/*'];const ok=await chrome.permissions.request({origins});$('collectionPermissionsState').textContent=ok?'Чтение разрешено. Настройте адреса выдачи на рабочем сайте.':'Чтение не разрешено. Доступна ручная вставка текста вакансии.';}catch(e){$('collectionPermissionsState').textContent=e.message;}};
