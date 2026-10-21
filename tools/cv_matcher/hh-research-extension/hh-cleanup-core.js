/* Rejection cleanup is independent of vacancy availability and CRM deletion. */
(function(root){
 const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
 function page(value){try{const u=new URL(value);return u.origin==='https://hh.ru'&&!u.username&&!u.password&&/^\/applicant\/negotiations\/?$/.test(u.pathname)?u:null;}catch{return null;}}
 function next(current,value){const a=page(current),b=page(value);if(!a||!b)return null;const filters=u=>JSON.stringify([...u.searchParams].filter(([k])=>!['page','from','hhtmFrom','search_session_id'].includes(k)).sort());return filters(a)===filters(b)&&/^\d+$/.test(b.searchParams.get('page')||'')&&Number(b.searchParams.get('page'))===Number(a.searchParams.get('page')||0)+1?b.href:null;}
 function rejected(row){return /^hh_\d+$/.test(row?.vacancy_id||'')&&HHSync.cardStatus([row.status_text]).status==='rejected'&&row.status==='rejected';}
 function key(row){return JSON.stringify([row.vacancy_id,row.negotiation_id||'',row.resume_id||'',clean(row.title),clean(row.status_text),clean(row.card_text)]);}
 function unique(rows){const counts=new Map();for(const row of rows)counts.set(row.key,(counts.get(row.key)||0)+1);return rows.filter(r=>rejected(r)&&r.key===key(r)&&counts.get(r.key)===1);}
 function target(rows,approved){if(!rejected(approved)||approved.key!==key(approved))throw Error('Не подтверждён явный отказ HH.');const matches=rows.filter(r=>r.key===approved.key);if(matches.length!==1||!rejected(matches[0]))throw Error('Отклик изменился, не найден или неоднозначен. Удаление пропущено.');return matches[0];}
 function selection(plan,keys,now=Date.now()){
  if(!plan||plan.state!=='preview'||!Number.isFinite(plan.expires_at)||now>=plan.expires_at)throw Error('Предпросмотр устарел. Найдите отказы заново.');
  if(!Array.isArray(keys)||!keys.length||new Set(keys).size!==keys.length)throw Error('Выберите отклики из списка.');
  const allowed=unique(plan.items);const selected=keys.map(key=>allowed.find(r=>r.key===key));if(selected.some(r=>!r))throw Error('Выбор не соответствует предпросмотру.');return selected;
 }
 root.HHCleanup={page,next,rejected,key,unique,target,selection};
})(globalThis);
