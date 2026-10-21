/* Search filters only. Never touches applications, contact forms or consent. */
(function(root){
 const clean=s=>String(s||'').normalize('NFKC').replace(/[‑–—]/g,'-').replace(/\s+/g,' ').trim();
 async function apply(doc,url,values,visible=n=>!!n.getClientRects().length,pause=ms=>new Promise(r=>setTimeout(r,ms))){
  const u=new URL(url);
  if(!['tbank.ru','www.tbank.ru'].includes(u.hostname)||u.protocol!=='https:'||!/^\/career\/vacancies\//.test(u.pathname)||JobBoards.identity(url))throw Error('Фильтры доступны только в выдаче T-Bank.');
  if(!Array.isArray(values)||!values.length||values.length>20||values.some(v=>typeof v!=='string'||!v.trim()||v.length>100))throw Error('Проверьте названия фильтров.');
  const wanted=new Set(values.map(clean));
  function fields(){return [...doc.querySelectorAll('input[type="checkbox"],[role="checkbox"]')].filter(n=>!n.disabled&&!n.closest('form,nav,footer,[data-cv-matcher-badges]')).map(n=>{const label=[...(n.labels||[])].map(l=>l.innerText).join(' ')||n.getAttribute('aria-label')||n.closest('label')?.innerText||n.parentElement?.innerText;return {node:n,label:clean(label),checked:n.type==='checkbox'?!!n.checked:n.getAttribute('aria-checked')==='true'};}).filter(f=>f.label&&f.label.length<=100&&(visible(f.node)||[...(f.node.labels||[])].some(visible)));}
  let available=fields(),missing=[...wanted].filter(v=>!available.some(f=>f.label===v));
  if(missing.length){for(const b of [...doc.querySelectorAll('button')].filter(n=>visible(n)&&!n.closest('form')&&/^показать ещ[её]$/i.test(clean(n.innerText))).slice(0,10))b.click();await pause(500);available=fields();}
  for(const label of wanted)if(available.filter(f=>f.label===label).length!==1)throw Error('Фильтр не найден однозначно: '+label+'. Сбор остановлен; проверьте профиль фильтров.');
  // Validate every requested filter before changing any checkbox. Re-find nodes
  // after each click because the site can rebuild its filter controls.
  const plan=available.filter(f=>f.checked!==wanted.has(f.label)).map(f=>({label:f.label,value:wanted.has(f.label)}));
  for(const p of plan){const matches=fields().filter(f=>f.label===p.label);if(matches.length!==1)throw Error('Разметка фильтров изменилась. Повторите сбор.');if(matches[0].checked!==p.value)(matches[0].node.labels?.[0]||matches[0].node).click();await pause(200);}
  let previous='';
  for(let n=0;n<12;n++){await pause(500);const current=fields(),checked=current.filter(f=>f.checked).map(f=>f.label).sort();const signature=JSON.stringify(checked),ok=checked.length===wanted.size&&checked.every(v=>wanted.has(v));if(ok&&signature===previous)return {ok:true,checked,url:root.location?.href||url};previous=signature;}
  throw Error('T-Bank не подтвердил выбранные фильтры. Выбраны: '+(fields().filter(f=>f.checked).map(f=>f.label).join(', ')||'ни одного')+'. Сбор не начат.');
 }
 root.BoardFilters={apply};
})(globalThis);
