/* Shared, deterministic URL and snapshot rules; no platform APIs or credentials. */
(function(root){
 'use strict';
 function url(value,kind='any'){
  const u=new URL(value);if(u.protocol!=='https:'||!['linkedin.com','www.linkedin.com'].includes(u.host)||u.username||u.password)throw Error('Нужна безопасная ссылка LinkedIn.');
  let path=u.pathname,slug='';if(path.startsWith('/in/')){const match=path.match(/^\/in\/([^/]+)(.*)$/);if(!match)throw Error('Нужен профиль /in/….');try{slug=decodeURIComponent(match[1]).normalize('NFC');}catch{throw Error('Некорректный адрес профиля.');}if(!/^[\p{L}\p{N}_-]{1,150}$/u.test(slug))throw Error('Некорректный адрес профиля.');path='/in/'+encodeURIComponent(slug)+match[2];}
  if(path.startsWith('/messaging/thread/'))path=path.replace(/%3d/gi,'=');const checked=path.startsWith('/in/')?path.replace(/^\/in\/[^/]+/,'/in/profile'):path;if(/%|\.\.|[\\\x00-\x20]/.test(checked))throw Error('Нужна безопасная ссылка LinkedIn.');
  if(kind==='profile'){if(!/^\/in\/[^/]+(?:\/(?:en|ru))?\/?$/.test(path))throw Error('Нужен профиль /in/….');path='/in/'+encodeURIComponent(slug)+'/';}
  if(kind==='job'){const m=path.match(/^\/jobs\/view\/(?:[^/]+-)?(\d{1,25})\/?$/),id=m?.[1]||u.searchParams.get('currentJobId');if(!/^\d{1,25}$/.test(id||'')||!path.startsWith('/jobs/'))throw Error('Нужна конкретная вакансия.');path='/jobs/view/'+id+'/';}
  if(kind==='thread'&&!/^\/messaging\/thread\/[\w-]{1,200}={0,2}\/?$/.test(path))throw Error('Нужна ссылка диалога.');
  if(!/^\/(in|jobs|messaging|mynetwork)(\/|$)/.test(path))throw Error('Эта страница не поддерживается.');
  const query=new URL('https://www.linkedin.com').searchParams;if(kind==='any'&&path.startsWith('/jobs/'))for(const key of ['keywords','geoId','location','origin','originToLandingJobPostings','start','currentJobId','f_TPR','f_WT','f_E','f_C'])if(u.searchParams.has(key))query.set(key,u.searchParams.get(key));
  if(kind==='any'&&path.startsWith('/in/')&&/^(en_US|ru_RU)$/.test(u.searchParams.get('locale')||''))query.set('locale',u.searchParams.get('locale'));
  return 'https://www.linkedin.com'+path+(query.size?'?'+query.toString():'');
 }
 const stable=x=>Array.isArray(x)?x.map(stable):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,stable(x[k])])):x;
 async function hash(x){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(stable(x))));return [...new Uint8Array(b)].map(v=>v.toString(16).padStart(2,'0')).join('');}
 const names={connect:/^(connect|установить контакт|пригласить)(?:\s|$)/i,accept:/^(accept|принять)(?:\s|$)/i,ignore:/^(ignore|отклонить|игнорировать)(?:\s|$)/i,withdraw:/^(withdraw|отозвать)(?:\s|$)/i,remove:/^(remove connection|удалить контакт)(?:\s|$)/i};
 function introHeadline(text,name){const lines=[...new Set(text.split(/\n+/).map(s=>s.trim()).filter(Boolean))];const candidates=lines.filter(s=>s!==name&&s.length>=12&&s.length<=500&&!/^(verify|contact info|подтверд|контакт|add |добавить)|university|университет/i.test(s)&&/engineer|research|scientist|developer|architect|designer|manager|founder|product lead|разработчик|исследовател|инженер|руководител/i.test(s));return candidates.length===1?candidates[0]:'';}
 function recommendationSource(value){const u=new URL(value),origin=u.searchParams.get('origin')||'';if(/QUALIFICATION_LANDING/i.test(origin))return 'profile';if(/INFINITE_JOBS_LANDING/i.test(origin))return 'more';return 'search';}
 function cardFields(body,titleHint='',companyHint='',locationHint=''){
  const lines=body.split(/\n+/).map(s=>s.trim()).filter(Boolean);
  const title=(titleHint||lines[0]||'').replace(/\s*\(Verified job\)\s*/gi,'').split(' • ')[0].trim();
  const bullet=lines.indexOf('•');
  if(bullet>0){companyHint=companyHint||lines[bullet-1];locationHint=locationHint||lines[bullet+1]||'';}
  let metadata=lines.find(s=>s.includes('•')&&s!==title);
  if(metadata&&metadata.startsWith(title))metadata=metadata.slice(title.length).trim();
  const parts=(metadata||'').split(/\s*•\s*/);
  const company=(companyHint||parts[0]||'').replace(/^(?:company logo|логотип)\s*/i,'').trim();
  const location=(locationHint||parts[1]||'').replace(/\s+(More options|Dismiss|Actively reviewing|Promoted|Easy Apply).*$/i,'').trim();
  return {title:title.slice(0,500),company:company.slice(0,500),location:location.slice(0,500),locations:location?[location]:[]};
 }
 function jobSignals(text){
  const alumni=text.match(/(\d[\d, ]*)\s+school alumni work here/i);
  const values={viewed:/(?:^|[\n·])\s*Viewed(?:\s|[·\n]|$)/im.test(text),early_applicant:/be an early applicant/i.test(text),promoted:/\bpromoted\b/i.test(text),actively_reviewing:/actively reviewing applicants/i.test(text),...(alumni?{school_alumni_count:Number(alumni[1].replace(/[, ]/g,'')),school_alumni_label:alumni[0]}:{})};return Object.fromEntries(Object.entries(values).filter(([,value])=>value!==false));
 }
 function jobHeader(text){
  const lines=text.split(/\n+/).map(s=>s.trim()).filter(Boolean),flat=lines.join(' '),result={};
  const posted=text.match(/\b(?:reposted\s+)?(?:\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago|just now|today|yesterday)\b/i);
  if(posted){result.posted_label=posted[0].replace(/\s+/g,' ');const before=text.slice(0,posted.index).split(/\n+/).map(s=>s.replace(/[·•\s]+$/,'').trim()).filter(Boolean);const place=before.at(-1)||'';if(place&&place.length<300)result.location=place;const title=before.slice(0,-1).reverse().find(s=>s.length>=4&&s.length<=500&&!/^(verified job|more options|save|company[, .]|0 notifications)/i.test(s));if(title)result.title=title;}
  const applicants=flat.match(/\b(over\s+)?(\d[\d,]*)\s+applicants?\b/i);
  if(applicants){result.applicants_label=applicants[0];result.applicants_count=Number(applicants[2].replace(/,/g,''));result.applicants_lower_bound=!!applicants[1];}
  const salary=lines.find(s=>s.length<200&&/\b(?:GBP|USD|EUR|CNY)\s*\/(?:yr|year|hr|hour)\b/i.test(s));if(salary)result.salary_label=salary;
  const format=lines.find(s=>/^(hybrid|remote|on[ -]?site)$/i.test(s));if(format)result.work_format_label=format;
  const employment=lines.find(s=>/^(full[ -]?time|part[ -]?time|contract|temporary|internship)$/i.test(s));if(employment)result.employment_label=employment;
  return result;
 }
 function applyTarget(value){
  try{let u=new URL(value);if(u.protocol!=='https:'||u.username||u.password)return '';if(['linkedin.com','www.linkedin.com'].includes(u.hostname)){if(u.pathname!=='/safety/go/')return '';u=new URL(u.searchParams.get('url')||'');}if(u.protocol!=='https:'||u.username||u.password||/(^|\.)linkedin\.com$/.test(u.hostname))return '';return u.href;}catch{return '';}
 }
 function profileLinks(links,account){
  const map=new Map();for(const item of links||[]){let safe;try{safe=url(item.url);}catch{continue;}if(!safe.startsWith(account))continue;
   const label=String(item.label||'').trim(),old=map.get(safe);if(!old||label&&!old.label)map.set(safe,{url:safe,label});
  }
  const entries=[],sections=[];
  for(const item of map.values()){
   if(/\/skill-associations-details\//.test(item.url))continue;
   if(/\/edit\/forms\/(?:position|education|certification|course|\d+)\//.test(item.url)&&item.label){const lines=item.label.split(/\n+/).map(s=>s.trim()).filter(Boolean);entries.push({...item,label:lines[0],meta:lines.slice(1,4).join(' · ')});continue;}
   if(/\/details\/[^/]+\/$/.test(item.url)){sections.push({...item,label:'Открыть все записи этой секции в LinkedIn ↗'});}
  }
  return {entries,sections};
 }
 root.LinkedInCore={url,hash,names,stable,introHeadline,recommendationSource,cardFields,profileLinks,jobSignals,jobHeader,applyTarget};
})(globalThis);
