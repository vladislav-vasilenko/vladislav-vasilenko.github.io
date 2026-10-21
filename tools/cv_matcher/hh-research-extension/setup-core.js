/* Derive honest connection status from observed service, grant, tab and HH page state. */
(function(root){
 const readyService=data=>!!data.health?.ok&&data.health.service==='cv-matcher-local'&&data.health.workflow===true;
 function view(data){
  const service=readyService(data),old=!!data.health&&!service,worker=data.worker||{},permission=!!data.permission;
  let hh='disabled',hint='Разрешите доступ к hh.ru — расширение откроет служебную вкладку.';
  if(data.enabled){
   if(!permission){hh='permission_missing';hint='Доступ к hh.ru отозван. Разрешите его заново.';}
   else if(!worker.exists){hh='tab_missing';hint='Служебная вкладка закрыта. Нажмите «Восстановить вкладку HH».';}
   else if(worker.state==='login'){hh='login';hint='Откройте служебную вкладку и войдите в свой HH-аккаунт.';}
   else if(worker.state==='captcha'){hh='captcha';hint='В служебной вкладке HH требуется CAPTCHA. Пройдите её вручную.';}
   else if(worker.state==='authenticated'){hh='ready';hint='Вход в HH подтверждён. Служебная вкладка готова.';}
   else if(worker.state==='loading_stalled'){hh='loading_stalled';hint='HH долго загружается. Откройте служебную вкладку и проверьте страницу. Перед обновлением сохраните несохранённый текст анкеты.';}
   else if(worker.state==='loading'){hh='loading';hint='Служебная вкладка загружается…';}
   else{hh='unknown';hint='Вкладка открыта, но вход в HH ещё не подтверждён. Откройте её и проверьте.';}
  }
  const ready=service&&hh==='ready',step=!service?1:hh!=='ready'?2:3;
  return {service,old,hh,ready,step,headline:ready?'Всё подключено':step===1?'Подключите локальный сервис':hh==='login'?'Войдите в HH':hh==='captcha'?'HH ждёт проверки':data.enabled?'Проверьте вкладку HH':'Подключите HH',hint,enableLabel:!data.enabled?'Разрешить HH и подключить':!permission?'Вернуть доступ к HH':!worker.exists?'Восстановить вкладку HH':'Проверить подключение HH',enableDisabled:!service,openTab:!!worker.exists};
 }
 root.HHSetup={view,readyService};
})(globalThis);
