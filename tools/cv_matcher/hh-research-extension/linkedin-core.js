/* Shared, deterministic URL and snapshot rules; no platform APIs or credentials. */
(function(root){
 'use strict';
 function url(value,kind='any'){
  const u=new URL(value);if(u.protocol!=='https:'||!['linkedin.com','www.linkedin.com'].includes(u.host)||u.username||u.password||/%|\.\.|[\\\x00-\x20]/.test(u.pathname))throw Error('Нужна безопасная ссылка LinkedIn.');
  let path=u.pathname;
  if(kind==='profile'){const m=path.match(/^\/in\/([\w-]{1,150})(?:\/(?:en|ru))?\/?$/);if(!m)throw Error('Нужен профиль /in/….');path='/in/'+m[1]+'/';}
  if(kind==='job'){const m=path.match(/^\/jobs\/view\/(?:[^/]+-)?(\d{1,25})\/?$/),id=m?.[1]||u.searchParams.get('currentJobId');if(!/^\d{1,25}$/.test(id||'')||!path.startsWith('/jobs/'))throw Error('Нужна конкретная вакансия.');path='/jobs/view/'+id+'/';}
  if(kind==='thread'&&!/^\/messaging\/thread\/[\w-]{1,200}\/?$/.test(path))throw Error('Нужна ссылка диалога.');
  if(!/^\/(in|jobs|messaging|mynetwork)(\/|$)/.test(path))throw Error('Эта страница не поддерживается.');
  return 'https://www.linkedin.com'+path;
 }
 const stable=x=>Array.isArray(x)?x.map(stable):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,stable(x[k])])):x;
 async function hash(x){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(stable(x))));return [...new Uint8Array(b)].map(v=>v.toString(16).padStart(2,'0')).join('');}
 const names={connect:/^(connect|установить контакт|пригласить)(?:\s|$)/i,accept:/^(accept|принять)(?:\s|$)/i,ignore:/^(ignore|отклонить|игнорировать)(?:\s|$)/i,withdraw:/^(withdraw|отозвать)(?:\s|$)/i,remove:/^(remove connection|удалить контакт)(?:\s|$)/i};
 function introHeadline(text,name){const lines=[...new Set(text.split(/\n+/).map(s=>s.trim()).filter(Boolean))];const candidates=lines.filter(s=>s!==name&&s.length>=12&&s.length<=500&&!/^(verify|contact info|подтверд|контакт|add |добавить)|university|университет/i.test(s)&&/engineer|research|scientist|developer|architect|designer|manager|founder|product lead|разработчик|исследовател|инженер|руководител/i.test(s));return candidates.length===1?candidates[0]:'';}
 root.LinkedInCore={url,hash,names,stable,introHeadline};
})(globalThis);
