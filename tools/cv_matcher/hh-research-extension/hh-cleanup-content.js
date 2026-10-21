/* Native HH controls only. An action is injected by the extension worker. */
(()=>{
 const action=globalThis.__hhCleanupAction||{action:'scan'};delete globalThis.__hhCleanupAction;
 if(!HHCleanup.page(location.href))throw Error('Очистка доступна только в списке откликов HH.');
 const clean=HHSync.clean,visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
 if(document.querySelector('form[action*="captcha"],input[name*="captcha"]')||/доступ ограничен|подтвердите, что вы не робот/i.test(document.querySelector('h1')?.innerText||''))throw Error('HH требует вход или CAPTCHA. Очистка остановлена.');
 const dialogs=()=>{
  const all=[...document.querySelectorAll('[role="dialog"],[role="alertdialog"],dialog,[aria-modal="true"],[data-qa="magritte-modal"]')].filter(visible);
  // Magritte nests its content container inside the semantic alertdialog.
  return all.filter(node=>!all.some(parent=>parent!==node&&parent.contains(node)));
 };
 function cards(){
  const all=[...document.querySelectorAll('[data-qa="negotiations-item"],[data-qa="negotiations-list-item"],[data-qa="negotiations-list-item-wrapper"],article')].filter(visible);
  return all.filter(card=>!all.some(other=>other!==card&&card.contains(other)&&other.querySelector('a[href*="/vacancy/"]')));
 }
 const label=n=>clean(n.innerText||n.getAttribute('aria-label')||n.getAttribute('title'));
 const controls=card=>[...card.querySelectorAll('button,[role="button"],a')].filter(n=>visible(n)&&n!==card);
 function row(card){
  const links=[...card.querySelectorAll('a[href]')],job=links.find(a=>HHSync.vacancy(a.href));if(!job)return null;
  const badges=[...card.querySelectorAll('[data-qa*="status"],[data-qa*="response-state"]')].filter(visible).map(n=>clean(n.innerText));
  const leaves=[...card.querySelectorAll('span,div,p')].filter(n=>visible(n)&&(!n.closest('a,button,[role="button"]')||n.closest('a,button,[role="button"]')===card)&&![...n.children].some(c=>clean(c.innerText))).map(n=>clean(n.innerText));
  const parsed=HHSync.cardStatus([...badges,...leaves]);
  const value={vacancy_id:HHSync.vacancy(job.href),link:'https://hh.ru/vacancy/'+HHSync.vacancy(job.href).slice(3),title:clean(job.innerText),negotiation_id:card.getAttribute('data-negotiation-id')||'',resume_id:links.map(a=>{try{return new URL(a.href).pathname.match(/^\/resume\/([a-f\d]{38})\/?$/i)?.[1];}catch{return null;}}).find(Boolean)||'',status:parsed.status,status_text:parsed.text,card_text:clean(card.innerText).replace(/(?:Удалить(?: отклик)?|Перейти в чат|Смотреть статистику по вакансии|Усилить отклик)/g,'').replace(/\s+/g,' ').trim(),page_url:location.href};
  value.key=HHCleanup.key(value);return value;
 }
 const entries=cards().map(card=>({card,row:row(card)})).filter(e=>e.row),rows=entries.map(e=>e.row);
 if(action.action==='scan'){
  const next=[...document.querySelectorAll('a[href*="page="]')].filter(visible).map(a=>HHCleanup.next(location.href,a.href)).find(Boolean)||null;
  const unknown=rows.filter(r=>r.status==='unknown').length;
  const more_available=[...document.querySelectorAll('button,[role="button"]')].some(n=>visible(n)&&/^(?:Показать ещ[её]|Загрузить ещ[её]|Следующая(?: страница)?)$/i.test(label(n)));
  return {source_url:location.href,items:rows,unknown,next_page:next,more_available,empty:!!document.querySelector('[data-qa="negotiations-empty"],[data-qa="negotiations-list-empty"]')};
 }
 const approved=action.target;
 const find=()=>{const match=HHCleanup.target(rows,approved);return entries.find(e=>e.row===match).card;};
 const deletion=/^(?:Удалить|Удалить отклик)$/i;
 if(action.action==='remove'){
  if(dialogs().length)throw Error('На HH уже открыто диалоговое окно. Закройте его и обновите список.');
  const card=find(),buttons=controls(card).filter(n=>deletion.test(label(n)));
  if(buttons.length!==1)throw Error('Кнопка удаления этого отклика не распознана. Удаление остановлено.');
  // Re-read the exact card immediately before the single native click.
  HHCleanup.target([row(card)],approved);globalThis.__hhCleanupPending={key:approved.key,at:Date.now(),confirmed:false};buttons[0].click();return {state:'clicked'};
 }
 if(action.action==='confirm'){
  const pending=globalThis.__hhCleanupPending;
  if(!pending||pending.key!==approved.key||Date.now()-pending.at>15000)throw Error('Нет актуального начала удаления этого отклика. Закройте старый диалог и проверьте список заново.');
  if(pending.confirmed)return {state:'already_confirmed'};
  const open=dialogs();if(!open.length)return {state:'no_dialog'};
  const titles=open.length===1?[...open[0].querySelectorAll('h1,h2,h3,[data-qa="magritte-alert-title"],[data-qa="title"]')].filter(visible).map(n=>clean(n.innerText)):[];
  if(open.length!==1||!titles.some(t=>/^Удалить отклик[?]?$/i.test(t)))throw Error('Диалог HH не подтверждён как удаление отклика. Проверьте его вручную.');
  find();const buttons=controls(open[0]).filter(n=>/^(?:Удалить|Да,? удалить|Удалить отклик)$/i.test(label(n)));
  if(buttons.length!==1)throw Error('Подтверждение удаления не распознано.');pending.confirmed=true;buttons[0].click();return {state:'confirmed'};
 }
 if(action.action==='verify'){
  if(globalThis.__hhCleanupPending?.key!==approved.key)return {state:'uncertain'};
  if(dialogs().length)return {state:'pending'};
  if(rows.some(r=>r.key===approved.key))return {state:'pending'};
  if(rows.some(r=>r.vacancy_id===approved.vacancy_id&&(!approved.negotiation_id||r.negotiation_id===approved.negotiation_id)))return {state:'uncertain'};
  if(!rows.length&&!document.querySelector('[data-qa="negotiations-empty"],[data-qa="negotiations-list-empty"]'))return {state:'uncertain'};
  delete globalThis.__hhCleanupPending;
  return {state:'removed',evidence:'После единственного клика удаления карточка отсутствует в обновлённом списке HH.'};
 }
 throw Error('Неизвестное действие очистки.');
})();
