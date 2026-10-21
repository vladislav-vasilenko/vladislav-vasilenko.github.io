(function(root){
 const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
 function status(text){text=clean(text).toLowerCase();if(/отказ|не подош|не готов.*приглас/.test(text))return 'rejected';if(/пригла[сш]|собеседован/.test(text))return 'invited';if(/отозван|вы отозвали/.test(text))return 'withdrawn';if(/не просмотрен|доставлен|отклик отправлен|вы откликнулись|ожидает просмотра/.test(text))return 'submitted';if(/просмотрен/.test(text))return 'viewed';return 'unknown';}
 function cardStatus(labels){
  // Only standalone status badges, never the vacancy title, description or action buttons.
  const badge=/^(?:(?:отклик|резюме)\s+)?(?:не\s+просмотрен[оа]?|просмотрен[оа]?|доставлен[оа]?|ожидает просмотра|собеседование|приглашение(?: на (?:интервью|собеседование))?|приглаш[её]н[ыа]?|ва[сc] пригласили|вы откликнулись|отклик отправлен|отказ|вам отказали|получен отказ|не подошли|отозван[оа]?|вы отозвали отклик)[.!]?$/i;
  const found=[...new Set(labels.map(clean).filter(t=>badge.test(t)))],states=[...new Set(found.map(status))].filter(s=>s!=='unknown');
  return {status:states.length===1?states[0]:'unknown',text:found.join(' · ')};
 }
 function vacancy(url){try{const u=new URL(url);const id=u.pathname.match(/^\/vacancy\/(\d+)\/?$/)?.[1]||u.searchParams.get('vacancyId')||u.searchParams.get('vacancy_id');return u.origin==='https://hh.ru'&&/^\d+$/.test(id||'')?'hh_'+id:null;}catch{return null;}}
 function thread(url){try{const u=new URL(url);if(!['https://hh.ru','https://chat.hh.ru'].includes(u.origin))return null;for(const k of ['negotiationId','negotiation_id','chat_id','chatId','thread_id'])if(u.searchParams.get(k))return k+':'+u.searchParams.get(k);const id=u.pathname.match(/\/(?:chat|negotiations)\/(\d+)/)?.[1];return id?'thread:'+id:null;}catch{return null;}}
 function giga(url){try{let u=new URL(url);if(u.origin==='https://hh.ru'&&u.pathname==='/away'&&u.searchParams.getAll('to').length===1)u=new URL(u.searchParams.get('to'));if(u.protocol!=='https:'||!['t.me','telegram.me'].includes(u.host)||u.pathname.toLowerCase().replace(/\/$/,'')!=='/giga_recruiter_bot'||u.hash||[...u.searchParams].length!==1||!u.searchParams.has('start')||!/^[A-Za-z0-9_-]{1,64}$/.test(u.searchParams.get('start')))return null;return 'https://t.me/Giga_recruiter_bot?start='+u.searchParams.get('start');}catch{return null;}}
 root.HHSync={clean,status,cardStatus,vacancy,thread,giga};
})(globalThis);
