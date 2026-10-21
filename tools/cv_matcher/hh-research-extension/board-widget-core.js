/* Shared, bounded discovery for employer widgets. Uses rendered links, never forms. */
(function(root){
 const providers=new Set(['yandex','avito','ozon','tbank','sber']);
 function provider(url){
  try{const u=new URL(url),a=JobBoardAdapters.resolve(u.href);if(!providers.has(a?.id))return null;
   return a.pages.test(u.pathname)?a.id:null;
  }catch{return null;}
 }
 function valid(id,source){return typeof id==='string'&&id.startsWith(source+'_')&&/^(?:(?:yandex|avito|sber)_\d{1,20}|ozon_(?:\d{1,20}|[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12})|tbank_[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12})$/i.test(id);}
 function cards(doc,url,visible=()=>true){
  const source=provider(url),adapter=JobBoardAdapters.resolve(url),rows=new Map();if(!source)return rows;
  const own=JobBoards.identity(url),clean=t=>String(t||'').replace(/\s+/g,' ').trim();
  if(own&&valid(own.id,source)){
   const title=doc.querySelector('h1'),fallback=source==='tbank'?clean(doc.title).match(/^Вакансия\s+(.+?)\s*\|\s*Т[‑-]Банк/i)?.[1]:'',heading=doc.querySelector('h2');
   if(title&&visible(title)&&clean(title.innerText))rows.set(own.id,{host:title.parentElement,title:clean(title.innerText)});
   else if(fallback&&heading&&visible(heading))rows.set(own.id,{host:heading,title:fallback,placement:'after'});return rows;
  }
  const identity=a=>{try{const u=new URL(a.href,url);return provider(u.href)===source?JobBoards.identity(u.href):null;}catch{return null;}};
  for(const a of doc.querySelectorAll('a[href]')){
   if(!visible(a)||a.closest('nav,footer,form,[data-cv-matcher-badges]'))continue;
   const job=identity(a),heading=JobBoardAdapters.titleNode(a,adapter),initialTitle=clean((heading||a).innerText);
   if(!job||!valid(job.id,source)||!initialTitle||rows.has(job.id))continue;
   // Find the largest small container belonging to exactly this job. Never the list.
   let host=a;const preferred=adapter.card?a.closest(adapter.card):null;
   for(let n=a.parentElement,depth=0;n&&depth<8;n=n.parentElement,depth++){
    if(/^(BODY|MAIN|NAV|HEADER|FOOTER|FORM|UL|OL)$/.test(n.tagName))break;
    const links=[...n.querySelectorAll('a[href]')];if(links.length>40)break;
    const ids=new Set(links.map(identity).filter(j=>j&&valid(j.id,source)).map(j=>j.id));
    if(ids.size!==1||!ids.has(job.id))break;host=n;
   }
   // A full-card link remains navigable; append the widget as its sibling.
   if(preferred){const ids=new Set([...preferred.querySelectorAll('a[href]')].map(identity).filter(j=>j&&valid(j.id,source)).map(j=>j.id));if(preferred===a)ids.add(job.id);if(ids.size===1&&ids.has(job.id))host=preferred;}
   const title=clean((heading||host.querySelector('h1,h2,h3,h4,[class*="vacancyTitle"]')||a).innerText);
   const placement=host.tagName==='A'?'after':'inside';rows.set(job.id,{host,title,placement});if(rows.size>=100)break;
  }
  return rows;
 }
 root.BoardWidgets={provider,valid,cards};
})(globalThis);
