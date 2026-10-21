/* Read only visible HH response statuses and messages; never clicks or sends. */
(()=>{
 const visible=e=>{if(!e)return false;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
 const source=location.href,u=new URL(source);if(!['https://hh.ru','https://chat.hh.ru'].includes(u.origin))return {blocked:true,warning:'Откройте HH.'};
 if(document.querySelector('input[name*="captcha"],form[action*="captcha"]')||/\/account\/login/.test(u.pathname))return {blocked:true,warning:'HH требует вход или CAPTCHA.'};
 const records=[],seen=new Set(),seenLinks=new Set(),thread_urls=[];
 // The full chat directory exposes conversation links outside negotiation cards.
 if(/^\/chat(?:\/|$)/.test(u.pathname))for(const a of document.querySelectorAll('a[href]'))if(visible(a)&&HHSync.thread(a.href)){const target=new URL(a.href);thread_urls.push(target.origin+target.pathname.replace(/\/$/,''));}
 const cards=document.querySelectorAll('[data-qa="negotiations-item"],[data-qa="negotiations-list-item"],[data-qa="negotiations-list-item-wrapper"],article');
 for(const card of cards){if(!visible(card))continue;const link=[...card.querySelectorAll('a[href]')].find(a=>HHSync.vacancy(a.href));const id=link&&HHSync.vacancy(link.href);if(!id||seenLinks.has(link))continue;
  const badges=[...card.querySelectorAll('[data-qa*="status"],[data-qa*="response-state"]')].filter(visible).map(el=>HHSync.clean(el.innerText));
  const leaves=[...card.querySelectorAll('span,div,p')].filter(el=>visible(el)&&(!el.closest('a,button,[role="button"]')||el.closest('a,button,[role="button"]')===card)&&!([...el.children].some(child=>HHSync.clean(child.innerText)))).map(el=>HHSync.clean(el.innerText)).filter(t=>t&&t.length<=160);
  const parsed=HHSync.cardStatus([...badges,...leaves]);
  const status_text=parsed.text||(badges.length?badges.join(' · '):leaves.slice(-12).join(' · ')).slice(0,1600);
  if(!/^negotiations-/.test(card.getAttribute('data-qa')||'')&&!card.getAttribute('data-negotiation-id')&&parsed.status==='unknown')continue;seen.add(id);seenLinks.add(link);
  const chat=[...card.querySelectorAll('a[href]')].find(a=>HHSync.thread(a.href));if(chat)thread_urls.push(chat.href);
  const negotiation=card.getAttribute('data-negotiation-id')||null;
  const resumeLink=[...card.querySelectorAll('a[href]')].map(a=>{try{return new URL(a.href).pathname.match(/^\/resume\/([a-f0-9]{38})\/?$/i)?.[1];}catch{return null;}}).find(Boolean);
  records.push({vacancy_id:id,resume_id:resumeLink||null,title:HHSync.clean(link.innerText),negotiation_id:negotiation,thread_id:chat?HHSync.thread(chat.href):negotiation?'negotiation_id:'+negotiation:null,status:parsed.status,status_text,source_url:chat?.href||source});
 }
 const detailId=/^\/vacancy\/\d+\/?$/.test(u.pathname)?HHSync.vacancy(source):null;
 if(detailId){const candidates=[...document.querySelectorAll('[data-qa*="vacancy-response"],[data-qa*="vacancy-negotiation"],p,span')].filter(visible).map(e=>HHSync.clean(e.innerText)).filter(t=>/^(ва[сc] пригласили|вы откликнулись|отклик отправлен|вам отказали|отклик просмотрен|отклик отозван)[.!]?$/i.test(t));const states=[...new Set(candidates.map(HHSync.status))].filter(s=>s!=='unknown');if(states.length===1&&!seen.has(detailId))records.push({vacancy_id:detailId,title:HHSync.clean(document.querySelector('[data-qa="vacancy-title"],h1')?.innerText),status:states[0],status_text:candidates[0],source_url:source});}
 const chatRoute=/^\/chat\/\d+\/?$/.test(u.pathname);
 const conversation=[...document.querySelectorAll('[data-qa="chat-messages"],[data-qa="chat-conversation"],[data-qa="chat-dialog"],[role="log"]')].find(visible)||(chatRoute?(document.querySelector('main')||document.body):null);
 if(conversation){
  let headerLinks=[...document.querySelectorAll('[data-qa="chat-header"] a[href],[data-qa="chat-vacancy"] a[href]')].filter(visible);
  if(!headerLinks.length&&chatRoute)headerLinks=[...document.querySelectorAll('a[href*="/vacancy/"]')].filter(a=>{
   if(!visible(a)||a.closest('aside,nav,[data-qa*="chat-list"]'))return false;
   for(let parent=a.parentElement,n=0;parent&&n<4;n++,parent=parent.parentElement){const t=HHSync.clean(parent.innerText);if(t.length>1000)break;if(/^Вакансия(?:\s|:)/i.test(t))return true;}return false;
  });
  const links=[...new Set(headerLinks.map(a=>HHSync.vacancy(a.href)).filter(Boolean))],vacancy_id=links.length===1?links[0]:null;
  const tid=conversation.getAttribute('data-chat-id')?'chat_id:'+conversation.getAttribute('data-chat-id'):HHSync.thread(source)||'unbound:'+u.origin+u.pathname+u.search+u.hash;
  const candidates=[...conversation.querySelectorAll('[data-message-id],[data-qa="chat-message"],[data-qa="message"],[class*="message-content"],[class*="messageContent"],[class*="message-text"],[class*="messageText"]')].filter(visible);
  // Conservative fallback for an HH layout without semantic message attributes.
  // Only a small bubble containing the visible invitation; never the whole chat/sidebar.
  for(const a of conversation.querySelectorAll('a[href]'))if(visible(a)&&HHSync.giga(a.href)&&!candidates.some(node=>node.contains(a))){
   let bubble=a;for(let parent=a.parentElement,n=0;parent&&parent!==conversation&&n<5;n++,parent=parent.parentElement){const t=parent.innerText?.trim()||'';if(t.length>20000)break;bubble=parent;if(t.length>150&&/интервью|ГигаРекрутер/i.test(t))break;}candidates.push(bubble);
  }
  const messages=[],unique=new Set();for(const node of candidates){
   if(candidates.some(other=>other!==node&&node.contains(other)))continue;
   const content=node.querySelector('[data-qa="message-text"],[data-qa="chat-message-text"]')||node,text=content.innerText?.trim();if(!text||text.length>20000)continue;
   const anchors=[...node.querySelectorAll('a[href]')];const links=anchors.map(a=>HHSync.giga(a.href)).filter(Boolean);
   const wrapped=anchors.map(a=>{try{const x=new URL(a.href);return x.origin===u.origin&&x.pathname==='/away'&&x.searchParams.get('chatId')===u.pathname.split('/').filter(Boolean).pop()?x.searchParams.get('messageId'):null;}catch{return null;}}).filter(Boolean);
   const id=node.getAttribute('data-message-id')||node.closest('[data-message-id]')?.getAttribute('data-message-id')||([...new Set(wrapped)].length===1?wrapped[0]:'');
   const direction=node.getAttribute('data-direction')||'unknown',at=node.querySelector('time[datetime]')?.getAttribute('datetime')||'',key=id+'|'+at+'|'+text;if(unique.has(key))continue;unique.add(key);
   messages.push({id,text,links,direction:['incoming','outgoing'].includes(direction)?direction:'unknown',at});if(messages.length>=500)break;
  }
  if(messages.length)records.push({vacancy_id,thread_id:tid,status:'unknown',source_url:source,messages});
 }

 const next=[...document.querySelectorAll('a[href*="page="]')].filter(visible).find(a=>{try{const n=new URL(a.href);return n.origin===u.origin&&n.pathname===u.pathname&&Number(n.searchParams.get('page'))===Number(u.searchParams.get('page')||0)+1;}catch{return false;}});
 return {source_url:source,observed_at:new Date().toISOString(),page_kind:conversation?'chat':u.pathname==='/chat'?'chat_directory':'negotiations',records,next_page:next?.href||null,thread_urls:[...new Set(thread_urls)],warning:!records.length&&!thread_urls.length?'Не распознаны карточки откликов или открытая переписка. Статусы не изменены.':records.some(r=>r.vacancy_id&&r.status==='unknown'&&!r.messages)?'Часть статусов HH не распознана. Сохранены исходные метки; неизвестный статус не считается отказом.':''};
})();
