/* Bounded active-session DOM adapters. Unknown/ambiguous forms stop for review. */
(function(root){
 'use strict';
 const C=root.LinkedInCore,all=(s,n=document)=>[...n.querySelectorAll(s)],visible=n=>!!n&&n.getClientRects().length>0&&getComputedStyle(n).visibility!=='hidden',txt=n=>(n?.innerText||n?.textContent||'').trim();
 const main=()=>all('main,[role="main"]').filter(visible).sort((a,b)=>txt(b).length-txt(a).length)[0]||document.querySelector('main,[role="main"]')||document.body;
 function profileLanguages(){const heading=all('h1,h2,h3,[role="heading"]').find(n=>visible(n)&&/^(?:profile language|язык профиля)$/i.test(txt(n)));if(!heading)return [];for(let scope=heading.parentElement;scope&&scope!==document.body;scope=scope.parentElement){if(txt(scope).length>1500)break;const controls=all('input[type="checkbox"],input[type="radio"],[role="checkbox"],[role="radio"]',scope).filter(n=>visible(n)||visible(n.closest('label')));if(controls.length)return controls.map(node=>({node,label:node.getAttribute('aria-label')||txt(node.labels?.[0])||txt(node.closest('label'))||txt(node.parentElement),checked:node.checked===true||node.getAttribute('aria-checked')==='true'}));}return [];}
 const profileLanguage=()=>{const checked=profileLanguages().filter(control=>control.checked);const label=checked.length===1?checked[0].label:'';return /English|Английск/i.test(label)?'en':/Русский|Russian/i.test(label)?'ru':'';};
 function gate(){C.url(location.href);const login=all('input[type="password"]').some(visible),challenge=all('iframe[src*="captcha"]').some(n=>visible(n)&&n.clientWidth>240&&n.clientHeight>120);if(/^\/(?:login|authwall|checkpoint|challenge)(?:\/|$)/.test(location.pathname)||login||challenge)throw Error('LinkedIn требует вход или ручную проверку.');}
 const link=(value,kind)=>{try{return C.url(new URL(value,location.href).href,kind);}catch{return null;}};
 const owned=p=>C.url(location.href).startsWith(p.account)&&(all('a[href*="/edit/"]',main()).some(a=>link(a.href)?.startsWith(p.account))||all('button,[role="button"]',main()).some(button=>visible(button)&&/^(?:edit intro|edit introduction|редактировать вводную информацию|редактировать профиль)$/i.test(button.getAttribute('aria-label')||txt(button))));
 function fieldNodes(dialog){return all('input,textarea,select,[contenteditable="true"]',dialog).filter(n=>visible(n)&&!n.disabled&&!n.readOnly&&!['hidden','password','file','submit','button','radio','search'].includes(n.type));}
 function field(n,i){const labelled=(n.getAttribute('aria-labelledby')||'').split(/\s+/).filter(Boolean).map(id=>txt(document.getElementById?.(id))).filter(Boolean).join(' ');const label=txt(n.labels?.[0])||n.getAttribute('aria-label')||labelled||txt(n.closest('label'))||n.name||n.getAttribute('placeholder')||n.id||'Поле '+(i+1);return {id:'f'+i,label:label.slice(0,300),type:n.tagName==='SELECT'?'select':n.type==='checkbox'?'checkbox':n.tagName==='TEXTAREA'||n.isContentEditable?'textarea':'text',value:n.type==='checkbox'?n.checked:n.isContentEditable?txt(n):n.value,max_length:n.maxLength>0?n.maxLength:20000,...(n.tagName==='SELECT'?{options:[...n.options].slice(0,300).map(o=>({value:o.value,label:txt(o)}))}:{})};}
 function dialog(){const list=all('[role="dialog"],dialog[open]').filter(visible);if(list.length!==1)throw Error('Откройте ровно одну форму редактирования LinkedIn.');return list[0];}
 async function form(p){gate();if(!C.url(location.href).startsWith(p.account))throw Error('Открыта форма другого профиля.');const d=dialog(),fields=fieldNodes(d).map(field);if(!fields.length||fields.length>80)throw Error('Поля формы не распознаны.');const title=txt(d.querySelector('h1,h2,h3,[role="heading"]'));if(/message|сообщени|invite|приглашени/i.test(title))throw Error('Это форма общения, а не редактирования профиля.');const state={url:C.url(location.href),title,fields,profile_language:profileLanguage()};return {...state,form_fingerprint:await C.hash(state)};}
 const sectionLabels={about:/^(about|о себе)$/i,experience:/^(experience|опыт работы|опыт)$/i,education:/^(education|образование)$/i,certifications:/^(licenses.*certifications|лицензии.*сертификаты)$/i,courses:/^(courses|курсы)(?:\s*\(\d+\))?$/i};
 const headingLabel=h=>[...new Set(txt(h).split(/\n+/).map(s=>s.trim()).filter(Boolean))].join(' ');
 const profileHeadings=()=>all('h1,h2,h3,[role="heading"]',main()).filter(visible);
 function profileAdvance(){
  gate();const page=document.scrollingElement;let scroller=page&&page.scrollHeight>page.clientHeight+25?page:null;
  // Profile navigation must follow the page, never the nested Activity carousel.
  if(!scroller)for(let node=main();node&&node!==document.body;node=node.parentElement){if(node.clientHeight>150&&node.scrollHeight>node.clientHeight+25){scroller=node;break;}}
  if(!scroller)return {at_end:true,scroll_top:0,height:0};const state={at_end:scroller.scrollTop+scroller.clientHeight>=scroller.scrollHeight-8,scroll_top:scroller.scrollTop,height:scroller.scrollHeight,viewport:scroller.clientHeight};scroller.scrollBy(0,Math.max(300,scroller.clientHeight*.8));return state;
 }
 function sectionScope(key,headings=profileHeadings()){
  const heading=headings.find(h=>sectionLabels[key]?.test(headingLabel(h)));
  if(!heading)return null;
  const level=h=>Number(h.getAttribute('aria-level')||h.tagName?.match(/^H([1-6])$/)?.[1]||2);
  const boundaries=headings.filter(h=>h!==heading&&(level(h)<=level(heading)||Object.values(sectionLabels).some(re=>re.test(headingLabel(h)))));
  let scoped=null;
  // A <section> may wrap the entire redesigned profile. Never trust its tag.
  for(let parent=heading.parentElement;parent&&parent!==main()&&parent!==document.body;parent=parent.parentElement){
   if(boundaries.some(h=>parent.contains(h)))break;
   if(txt(parent).length>txt(heading).length+10)scoped=parent;
  }
  return scoped;
 }
 function sliceSection(heading,stopPattern){
  if(!heading||!document.createRange)return null;
  const headings=profileHeadings(),next=headings.find(h=>h!==heading&&(heading.compareDocumentPosition(h)&4)&&stopPattern.test(headingLabel(h))),range=document.createRange();
  range.setStartBefore(heading);if(next)range.setEndBefore(next);else range.setEnd(main(),main().childNodes.length);
  const buttons=all('button,[role="button"]',main()).filter(n=>visible(n)&&range.intersectsNode(n)),clone=document.createElement('div');clone.append(range.cloneContents());
  for(const n of all('script,style,iframe,nav,aside,footer,[role="complementary"],[aria-hidden="true"],.visually-hidden,.sr-only,button',clone))n.remove();
  const blocks=new Set(['P','DIV','LI','H1','H2','H3','H4','BR']),serialize=n=>n.nodeType===3?n.textContent:[...(n.childNodes||[])].map(serialize).join('')+(blocks.has(n.tagName)?'\n':'');
  const text=serialize(clone).split('\n').map(s=>s.trim()).filter(Boolean).join('\n\n');
  return {text,clone,buttons};
 }
 const profileStops=/^(about|о себе|experience|опыт(?: работы)?|education|образование|licenses.*certifications|лицензии.*сертификаты|courses|курсы|profile language|who your viewers also viewed|people you may know|interests|languages|causes|analytics|activity|suggested for you|connected apps|skills(?: \(\d+\))?)$/i;
 function readSection(key,p,headings){
  const node=sectionScope(key,headings),sliced=!node?sliceSection((headings||profileHeadings()).find(h=>sectionLabels[key].test(headingLabel(h))),profileStops):null,sectionText=node?txt(node):sliced?.text||'';
  return {text:sectionText.slice(0,150000),coverage:sectionText?'bounded_section':'not_visible',links:all('a[href]',node||sliced?.clone||document.createElement('div')).map(a=>({label:txt(a),url:link(a.href)})).filter(a=>a.url?.startsWith(p.account))};
 }
 async function profile(p){
  gate();if(!owned(p))throw Error('Не удалось подтвердить режим редактирования собственного профиля. Проверьте ссылку и аккаунт.');
  const headings=profileHeadings(),sections={};
  for(const key of Object.keys(sectionLabels))sections[key]=readSection(key,p,headings);
  const introLink=all('a[href]',main()).find(a=>link(a.href)?.startsWith(p.account)&&/\/edit\/(?:intro|forms\/intro)(?:\/|$)/.test(link(a.href)));
  let intro=introLink?.parentElement,title='';
  for(let i=0;intro&&i<7;i++,intro=intro.parentElement){const names=headings.filter(h=>intro.contains(h)&&!Object.values(sectionLabels).some(re=>re.test(headingLabel(h))));if(names.length===1){title=headingLabel(names[0]);break;}}
  title=title||txt(main().querySelector('h1'))||'';
  let headline=txt(main().querySelector('.text-body-medium.break-words,[data-generated-suggestion-target="headline"]'));
  intro=headings.find(h=>headingLabel(h)===title);
  for(let i=0;!headline&&intro&&i<7;i++,intro=intro.parentElement){if(txt(intro).length>2200)break;headline=C.introHeadline(txt(intro),title);}
  const aboutEdit=all('a[href]',main()).map(a=>link(a.href)).find(u=>u?.startsWith(p.account)&&/\/edit\/(?:about\/|forms\/summary\/)/.test(u));
  const edit_controls={};for(const [key,pattern] of [['headline',/^(?:edit intro|edit introduction|редактировать вводную информацию|редактировать профиль)$/i],['about',/^(?:edit about|редактировать раздел.*о себе|редактировать.*о себе)$/i]])edit_controls[key]=all('button,[role="button"]',main()).filter(visible).map(button=>button.getAttribute('aria-label')||txt(button)).filter(label=>pattern.test(label));
  return {url:p.account,title,headline,sections,edit_controls,profile_language:profileLanguage(),language_controls:profileLanguages().map(({label,checked})=>({label,checked})),extractor_version:3,intro_edit_url:introLink?link(introLink.href):'',about_edit_url:aboutEdit||'',root_diagnostics:{roots:all('main,[role="main"]').map(n=>({visible:visible(n),length:txt(n).length,headings:all('h1,h2,h3,[role="heading"]',n).filter(visible).slice(0,15).map(headingLabel)})),document_headings:all('h1,h2,h3,[role="heading"]').filter(visible).slice(0,35).map(headingLabel)},observed_headings:headings.slice(0,40).map(headingLabel),observed_at:new Date().toISOString()};
 }

 const jobSectionLabels={preferences:/jobs based on your preferences|вакансии.*предпочтени/i,profile:/jobs that match your profile|вакансии.*соответств.*профил/i,more:/more jobs for you|другие вакансии для вас/i};
 function jobSection(a){let section=location.pathname==='/jobs/'?'search':'search';for(const h of profileHeadings()){if(!(h.compareDocumentPosition(a)&4))continue;for(const [key,re]of Object.entries(jobSectionLabels))if(re.test(txt(h)))section=key;}return section;}
 function jobLinks(n=main()){return all('a[href]',n).map(a=>({a,u:link(a.href,'job')})).filter(r=>r.u);}
 function jobCard(a,u){
  if(txt(a).includes('•')||txt(a).split(/\n+/).filter(Boolean).length>2)return a;
  let result=a;
  for(let n=a.parentElement;n&&n!==main()&&n!==document.body;n=n.parentElement){
   if(txt(n).length>6000||jobLinks(n).some(r=>r.u!==u))break;
   result=n;
  }
  return result;
 }
 function jobButtons(){
  const result=[],seen=new Set();
  for(const dismiss of all('button[aria-label]',main()).filter(n=>visible(n)&&/^Dismiss .+ job$/i.test(n.getAttribute('aria-label')||''))){
   let card=dismiss.parentElement,candidate=null;
   for(let n=card;n&&n!==main()&&n!==document.body;n=n.parentElement){
    if(txt(n).length>6000||all('button[aria-label]',n).filter(b=>/^Dismiss .+ job$/i.test(b.getAttribute('aria-label')||'')).length>1)break;
    candidate=n;if(n.getAttribute('role')==='button'){candidate=n;break;}
   }
   card=candidate;if(!card||seen.has(card))continue;seen.add(card);
   const body=txt(card),title=(dismiss.getAttribute('aria-label')||'').replace(/^Dismiss | job$/gi,''),lines=body.split(/\n+/).map(s=>s.trim()).filter(Boolean),at=lines.findIndex(s=>s.replace(/\s*\(Verified job\)/i,'').trim()===title),fields=C.cardFields(body,title);
   if(!fields.company&&at>=0){const after=lines.slice(at+1).filter(s=>s.replace(/\s*\(Verified job\)/i,'').trim()!==title);fields.company=(after[0]||'').slice(0,500);fields.location=(after[1]||'').slice(0,500);fields.locations=fields.location?[fields.location]:[];}
   result.push({card,body,fields,selected:card.getAttribute('aria-selected')==='true'||card.getAttribute('aria-current')==='true'||/^Selected[,\s]/i.test(card.getAttribute('aria-label')||'')||/^Selected[,\s]/i.test(body)});
  }
  return result;
 }
 async function jobsSelect(p){
  gate();const cards=jobButtons();if(location.pathname==='/jobs/'||!cards.length)return {clicked:false};
  const seen=new Set(p.seen_keys||[]);
  for(let index=0;index<cards.length;index++){
   const row=cards[index],key=await C.hash({index,...row.fields});if(seen.has(key))continue;
   const before=link(location.href,'job'),normalize=s=>s.replace(/\(Verified job\)/gi,'').replace(/\s+/g,' ').trim(),headerMatches=jobLinks().some(r=>r.u===before&&normalize(txt(r.a))===normalize(row.fields.title));row.card.click();let url;
   for(let wait=0;wait<20;wait++){await new Promise(r=>setTimeout(r,150));url=link(location.href,'job');if(url&&(url!==before||row.selected||headerMatches))break;}
   if(!url||url===before&&!row.selected&&!headerMatches)return {clicked:true,loading:true,key};
   const logo=row.card.querySelector('img[src]');return {clicked:true,key,item:{link:url,...row.fields,description:row.body.slice(0,4000),description_quality:'snippet',company_logo_url:logo?.currentSrc||logo?.src||'',linkedin_signals:C.jobSignals(row.body),recommendation_sections:[p.collection&&p.collection!=='all'?p.collection:C.recommendationSource(location.href)]}};
  }
  return {clicked:false};
 }
 function jobsListing(p){
  gate();const map=new Map();
  // Redesigned search results use clickable cards without job hrefs. Read each
  // actual card selection, rather than assigning the selected ID to its peers.
  const buttonMode=location.pathname!=='/jobs/'&&jobButtons().length>0;
  for(const {a,u}of (buttonMode?[]:jobLinks())){
   const card=jobCard(a,u),body=txt(card).slice(0,4000),dismiss=all('button,[role="button"]',card).map(n=>n.getAttribute('aria-label')||txt(n)).find(s=>/^Dismiss .+ job$/i.test(s));
   const hint=txt(card.querySelector('h1,h2,h3,strong'))||dismiss?.replace(/^Dismiss | job$/gi,'')||txt(a).split('\n')[0];
   const logo=card.querySelector('img[src]'),fields=C.cardFields(body,hint,txt(card.querySelector('.artdeco-entity-lockup__subtitle,.job-card-container__primary-description,a[href*="/company/"]')),txt(card.querySelector('.artdeco-entity-lockup__caption,.job-card-container__metadata-item')));
   const source=location.pathname==='/jobs/'?jobSection(a):p.collection&&p.collection!=='all'?p.collection:C.recommendationSource(location.href);
   if(!fields.title||p.collection&&p.collection!=='all'&&location.pathname==='/jobs/'&&source!==p.collection)continue;
   const previous=map.get(u);if(previous&&/^(hybrid|remote|on[ -]?site|full[ -]?time|part[ -]?time|verified job)$/i.test(fields.title))continue;map.set(u,{link:u,...fields,company_logo_url:logo?.currentSrc||logo?.src||'',linkedin_signals:C.jobSignals(body),description:body,description_quality:'snippet',recommendation_sections:[...new Set([...(previous?.recommendation_sections||[]),source])]});
   if(map.size>=p.limit)break;
  }
  const preferencesHeading=profileHeadings().find(h=>jobSectionLabels.preferences.test(txt(h))),preferencesRoot=preferencesHeading?.parentElement;
  const diagnostics=p.diagnostics?all('a[href]',main()).filter(a=>a.href.includes('/jobs/')).slice(0,35).map(a=>{const u=new URL(a.href);return {label:txt(a).slice(0,80),path:u.pathname,params:[...u.searchParams.keys()],jobIds:Object.fromEntries([...u.searchParams].filter(([k])=>/job.*id|landingJob/i.test(k)).map(([k,v])=>[k,v.slice(0,150)])),attributes:[a,a.parentElement,a.parentElement?.parentElement].filter(Boolean).map(n=>({tag:n.tagName,attributes:[...n.attributes].filter(a=>/job|entity|urn|component|test/i.test(a.name)).map(a=>[a.name,a.value.slice(0,100)])}))};}):undefined;
  return {items:[...map.values()],...(diagnostics?{diagnostics}:{}),preferences_unconfigured:!!preferencesRoot&&/no jobs yet|add job preferences|ещ[её] нет вакансий/i.test(txt(preferencesRoot))};
 }
 function visibleBadges(container){
  const nodes=all('[class*="badge"],[data-test*="badge"],[aria-label],time',container).filter(visible),labels=[];
  for(const n of nodes){const label=(n.getAttribute('aria-label')||txt(n)).trim();if(!label||label.length>200)continue;
   if(/badge/i.test(n.className||'')||/premium|verified|hiring|open.?to.?work|\b(?:1st|2nd|3rd)\b|mutual|common connections|unread|online|active (?:now|\d)|inmail|\bread\b|\bseen\b|delivered|edited|прочитано|доставлено|изменено|подтвержд|общих контакт|непрочитан|в сети|степен/i.test(label)){if(!labels.includes(label))labels.push(label);}
  }
  return labels.slice(0,30);
 }
 function observedAvatar(container){for(const image of all('img,image',container)){const sources=[image.currentSrc,image.src,typeof image.href==='string'?image.href:image.href?.baseVal,image.getAttribute('src'),image.getAttribute('href'),image.getAttribute('data-delayed-url')];for(const value of sources){try{const u=new URL(value);if(u.protocol==='https:'&&['media.licdn.com','static.licdn.com'].includes(u.hostname))return u.href;}catch{}}}return '';}
 function recordMetadata(container){
  const text=txt(container),badges=visibleBadges(container),unread=all('[aria-label]',container).filter(visible).map(n=>n.getAttribute('aria-label')).find(s=>!/mark as|пометить/i.test(s||'')&&/unread|непрочитан/i.test(s||'')),timeNode=container.querySelector('time'),avatar_url=observedAvatar(container);
  return {badges,...(unread?{unread_label:unread}:{}),...(timeNode?{time_label:txt(timeNode),time:timeNode.getAttribute('datetime')||''}:{}),...(avatar_url?{avatar_url}:{}),...(text.match(/(?:\d+\s+(?:mutual|shared|общих).*?(?:connections|контакт[а-я]*))/i)?{mutual_label:text.match(/(?:\d+\s+(?:mutual|shared|общих).*?(?:connections|контакт[а-я]*))/i)[0]}:{})};
 }
 function conversationCards(){
  const root=main(),list=root.querySelector?.('.msg-conversations-container__conversations-list'),seen=new Set();
  return all(list?'h3,h4,[role="heading"]':'h3.msg-conversation-listitem__participant-names',list||root).filter(visible).map(h=>{const card=h.closest('li,.msg-conversation-listitem')||h.closest('.msg-conversation-card__content--selectable')||h.parentElement;return {heading:h,card,name:txt(h)};}).filter(row=>{if(!row.name||seen.has(row.card))return false;seen.add(row.card);return true;});
 }
 function conversationPreview(row){const snippet=row.card.querySelector('.msg-conversation-card__message-snippet,.msg-conversation-listitem__message-snippet,.msg-conversation-card__message-snippet-body');if(snippet)return txt(snippet).slice(0,1000);return txt(row.card).split(/\n+/).map(s=>s.trim()).filter(s=>s&&s!==row.name&&!/^(?:Active conversation|Press return|Open the options|Select conversation|\.|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}$)/i.test(s)).join(' ').slice(0,1000);}
 function messagesListing(p){
  gate();const items=[];for(const row of conversationCards()){const a=all('a[href]',row.card).find(a=>link(a.href,'thread'));if(!a)continue;items.push({url:link(a.href,'thread'),name:row.name,text:conversationPreview(row),preview:conversationPreview(row),...recordMetadata(row.card)});if(items.length>=p.limit)break;}
  const diagnostics=p.diagnostics?{list_structure:(()=>{const list=main().querySelector?.('.msg-conversations-container__conversations-list');return list?{children:list.children.length,headings:all('h3,h4,[role="heading"]',list).slice(0,30).map(n=>({tag:n.tagName,cls:String(n.className).slice(0,160)})),rows:[...list.children].slice(-5).map(n=>({tag:n.tagName,cls:String(n.className).slice(0,160)}))}:null;})(),cards:conversationCards().slice(0,3).map(r=>({tag:r.card.tagName,attributes:[...r.card.attributes].filter(a=>/id|class|role|data-|aria-/.test(a.name)).map(a=>[a.name,a.value.slice(0,180)])})),count:conversationCards().length,controls:all('button',main()).filter(visible).map(button=>({label:txt(button).slice(0,70),pressed:button.getAttribute('aria-pressed')})).filter(button=>/jobs|unread|inmail|starred|focused|other|connections/i.test(button.label)),scroll_candidates:(()=>{const rows=[],first=conversationCards()[0];for(let n=first?.card.parentElement;n&&n!==document.body;n=n.parentElement)rows.push({tag:n.tagName,cls:String(n.className).slice(0,180),height:n.clientHeight,scroll_height:n.scrollHeight,scroll_top:n.scrollTop,overflow:getComputedStyle(n).overflowY});return rows;})()}:undefined;
  return {items,card_count:conversationCards().length,...(diagnostics?{diagnostics}:{})};
 }
 async function messagesSelect(p){
  gate();const seen=new Set(p.seen_keys||[]),cards=conversationCards();
  for(let index=0;index<cards.length;index++){
   const row=cards[index],thread=all('a[href]',row.card).map(a=>link(a.href,'thread')).find(Boolean),key=thread||await C.hash({name:row.name,preview:conversationPreview(row),time:txt(row.card.querySelector('time'))});if(seen.has(key))continue;
   const metadata=recordMetadata(row.card),preview=conversationPreview(row),before=link(location.href,'thread'),active=/Active conversation/i.test(txt(row.card))||/--active|is-active/.test(row.card.className||'');row.card.scrollIntoView({block:'nearest',inline:'nearest'});row.heading.click();let url;
   for(let retry=0;retry<20;retry++){await new Promise(r=>setTimeout(r,150));url=link(location.href,'thread');if(url&&(url!==before||active))break;}
   if(!url||url===before&&!active)return {clicked:true,loading:true,key};
   return {clicked:true,key,item:{url,name:row.name,text:preview,preview,...metadata}};
  }return {clicked:false};
 }
 function messageScroller(){const first=conversationCards()[0];if(!first)return null;const list=first.card.closest('.msg-conversations-container__conversations-list');if(list&&visible(list)&&list.clientHeight>120)return list;for(let node=first.card.parentElement;node&&node!==document.body;node=node.parentElement){if(node.clientHeight>120&&node.scrollHeight>node.clientHeight+25&&/auto|scroll/.test(getComputedStyle(node).overflowY))return node;}return null;}
 function messagesReset(){gate();const scroller=messageScroller();if(!scroller)return {reset:false};scroller.scrollTo(0,0);return {reset:true};}
 function messagesAdvance(){
  gate();const scroller=messageScroller();if(!scroller)throw Error('Прокручиваемый список диалогов не определён. Сохранённые карточки остаются в сервисе.');const atEnd=scroller.scrollTop+scroller.clientHeight>=scroller.scrollHeight-8;
  // LinkedIn can replace automatic loading with an explicit button at the list boundary.
  const more=atEnd?all('button',main()).filter(visible).filter(button=>/^(?:Load more conversations|Загрузить (?:больше|ещё|еще) (?:диалоги|диалогов|разговоров)|Показать (?:ещё|еще) (?:диалоги|диалогов))$/i.test(txt(button))):[];if(more.length>1)throw Error('Несколько кнопок дозагрузки диалогов. Проверьте список LinkedIn.');if(more.length){const waiting=more[0].disabled||more[0].getAttribute('aria-disabled')==='true';if(!waiting)more[0].click();return {at_end:false,load_more:!waiting,waiting:!!waiting,height:scroller.scrollHeight,scroll_top:scroller.scrollTop,viewport:scroller.clientHeight};}
  scroller.scrollBy(0,Math.max(220,scroller.clientHeight*.85));return {at_end:atEnd,height:scroller.scrollHeight,scroll_top:scroller.scrollTop,viewport:scroller.clientHeight};
 }
 function messagesNavigate(p){
  gate();if(!p.scope||p.scope==='all'){const active=all('button',main()).find(button=>visible(button)&&button.getAttribute('aria-pressed')==='true'&&/^(jobs|работа|вакансии|unread|непрочитанные|connections|контакты|inmail|starred|избранные)$/i.test(txt(button)));if(active){active.click();return {navigated:true};}return {navigated:false};}const labels={jobs:/^(jobs|работа|вакансии)$/i,unread:/^(unread|непрочитанные)$/i,inmail:/^inmail$/i},button=all('button',main()).find(b=>visible(b)&&labels[p.scope]?.test(txt(b)));
  if(button&&button.getAttribute('aria-pressed')!=='true'){button.click();return {navigated:true};}return {navigated:false};
 }
 function otherProfile(node,url){for(const a of all('a[href]',node)){const value=link(a.href,'profile');if(value&&value!==url)return true;}return false;}
 function listing(operation,p){
  if(operation==='jobs.list')return jobsListing(p);if(operation==='messages.list')return messagesListing(p);gate();if(p.url&&C.url(location.href)!==p.url)throw Error('Открыт другой список контактов. Проверьте страницу LinkedIn.');const root=main(),map=new Map(),kind=operation==='messages.list'?'thread':'profile',skip=new Set([...(p.skip_contacts||[]),...(p.only_new?p.known_contacts||[]:[])]);
  for(const a of all('a[href]',root)){
   const u=link(a.href,kind);if(!u||u===p.account||skip.has(u))continue;let card=a.closest('li,article,[role="listitem"],[data-entity-urn]');
   if(!card){card=a;for(let n=a.parentElement;n&&n!==root&&n!==document.body;n=n.parentElement){if(txt(n).length>6000||otherProfile(n,u))break;card=n;}}
   if(otherProfile(card,u))continue;
   const name=txt(a.querySelector('[aria-hidden="true"]'))||txt(a).split('\n')[0];if(!name||map.has(u))continue;
   const body=txt(card).slice(0,6000);const lines=body.split(/\n+/).map(s=>s.trim()).filter(Boolean),nameAt=lines.indexOf(name),headline=txt(card.querySelector('.mn-connection-card__occupation,.invitation-card__subtitle'))||(nameAt>=0?lines[nameAt+1]:'')||'',company=txt(card.querySelector('a[href*="/company/"]'));map.set(u,{url:u,name:name.slice(0,500),text:body,headline:headline.slice(0,1000),company:company.slice(0,500),company_source:company?'profile_link':'',degree:(body.match(/\b(?:1st|2nd|3rd)\b/)||[])[0]||'',relationship:p.scope||'connections',...recordMetadata(card)});if(map.size>=p.limit)break;
  }const total=String(root.textContent||'').slice(0,3000).match(/(?:^|\D)([\d][\d, \u00a0]*)\s+connections\b/i);const diagnostics=operation==='network.list'?{expected_total:total?Number(total[1].replace(/\D/g,'')):null}:p.diagnostics?{cards:all('h3',root).slice(0,5).map(h=>({ancestors:[h,h.parentElement,h.parentElement?.parentElement,h.parentElement?.parentElement?.parentElement].filter(Boolean).map(n=>({tag:n.tagName,attributes:[...n.attributes].filter(a=>/^(id|class|role|href|data-|aria-)/.test(a.name)).map(a=>[a.name,a.value.slice(0,180)])}))})),thread_links:all('a[href]',root).map(a=>link(a.href,'thread')).filter(Boolean).slice(0,10)}:undefined;return {items:[...map.values()],...(diagnostics?{diagnostics}:{})};
 }
 function job(p){
  gate();const u=C.url(location.href,'job');if(u!==p.url)throw Error('Открыта другая вакансия.');
  const root=main(),headings=profileHeadings(),about=headings.find(h=>/^(about the job|об этой вакансии|о вакансии)$/i.test(headingLabel(h)));
  let description=root.querySelector('.jobs-description__content,.jobs-box__html-content,[class*="job-details-about-the-job"]');
  if(!description&&about){for(let n=about.parentElement;n&&n!==root&&n!==document.body;n=n.parentElement){if(headings.some(h=>h!==about&&n.contains(h)))break;if(txt(n).length>txt(about).length+80)description=n;}}
  const jobStops=/^(requirements added by the job poster|about the company|unlock hiring insights.*|meet the hiring team|people you can reach out to|similar jobs|other jobs.*)$/i,sliced=!description&&about?sliceSection(about,jobStops):null;
  const descriptionText=description?txt(description):sliced?.text||'';
  if(descriptionText.length<150)throw Error('Полное описание ещё не видно. Раскройте описание и повторите.');
  const expand=(description?all('button,[role="button"]',description):sliced?.buttons||[]).find(n=>visible(n)&&/^(?:…|\.\.\.)?\s*(see more|show more|more|показать больше|развернуть|ещ[её])$/i.test(txt(n)||n.getAttribute('aria-label')||''));
  if(expand){expand.click();throw Error('Раскрываю полное описание.');}
  const card=jobsListing({...p,limit:300,collection:'all'}).items.find(j=>j.link===u),h=root.querySelector('h1,.job-details-jobs-unified-top-card__job-title');
  const headerText=(about?txt(root).split(txt(about))[0]:txt(root).slice(0,8000)),header=C.jobHeader(headerText);
  const title=txt(h)||header.title||p.job_title||card?.title||headings.find(h=>h!==about&&!/notifications|уведомлени|about|об этой/i.test(txt(h)))?.innerText;
  if(!title)throw Error('Название вакансии не распознано.');
  const buttons=all('a,button',root).filter(n=>visible(n)&&(!about||(n.compareDocumentPosition(about)&4))),apply=buttons.find(n=>/^(?:easy apply(?: to this job)?|прост(?:ая|ой) подача|упрощ[её]нный отклик)$/i.test(txt(n)||n.getAttribute('aria-label')||'')),external=buttons.find(n=>n.tagName==='A'&&/^(apply|откликнуться|подать заявку)/i.test(txt(n))&&C.applyTarget(n.href));
  const companyAnchor=all('a[href*="/company/"]',root).find(visible);
  const company=txt(root.querySelector('.job-details-jobs-unified-top-card__company-name,.jobs-unified-top-card__company-name'))||txt(companyAnchor).split('\n')[0]||companyAnchor?.getAttribute('aria-label')?.replace(/^Company,?\s*|\.$/g,'')||card?.company||'',locationText=txt(root.querySelector('.job-details-jobs-unified-top-card__tertiary-description-container'))||header.location||card?.location||'';
  return {items:[{link:u,title:title.trim(),company,location:locationText,locations:locationText?[locationText]:[],description:(descriptionText+(()=>{const requirements=headings.find(h=>/^requirements added by the job poster$/i.test(headingLabel(h)));return requirements?'\n\n'+(sliceSection(requirements,/^(about the company|unlock hiring insights.*|similar jobs|other jobs.*)$/i)?.text||''):'';})()).slice(0,200000),description_quality:'full',company_logo_url:companyAnchor?.querySelector('img')?.src||card?.company_logo_url||'',linkedin_signals:{...card?.linkedin_signals,...C.jobSignals(headerText),...Object.fromEntries(Object.entries(header).filter(([k])=>!['location','title'].includes(k)))},apply:{kind:apply?'easy_apply':external?'external':'unknown',url:external?C.applyTarget(external.href):u}}]};
 }
 function team(p){
  job(p); // Loads and bounds this exact job before reading its hiring block.
  const headings=profileHeadings(),heading=headings.find(h=>/^people you can reach out to|^meet the hiring team|^hiring team|^команда найма/i.test(headingLabel(h)));
  if(!heading)return {items:[],reason:'LinkedIn не показывает блок участников у этой вакансии.'};
  const section=sliceSection(heading,/^(about the job|about the company|unlock hiring insights.*|similar jobs)$/i),map=new Map();
  for(const a of all('a[href]',section?.clone||document.createElement('div'))){const url=link(a.href,'profile');if(!url||map.has(url))continue;const body=txt(a).slice(0,6000),lines=body.split(/\n+/).map(s=>s.trim()).filter(Boolean);if(!lines.length)continue;map.set(url,{url,name:lines[0].replace(/\s+Verified.*$/i,''),role:lines.slice(1).filter(s=>!/^verified|^[·•]|^job poster$|^\d(?:st|nd|rd)/i.test(s)).join(' · ').slice(0,1000),relationship:/job poster/i.test(body)?'job_poster':'listed_hiring_contact',evidence_url:p.url,evidence_quote:body,badges:[]});}
  return {items:[...map.values()],reason:'Только участники, явно показанные LinkedIn для этой вакансии; полнота команды неизвестна.'};
 }
 function jobsNavigate(p){
  gate();if(location.pathname!=='/jobs/'||p.listing_mode==='infinite'||!p.collection||p.collection==='all'&&!p.expand_more)return {navigated:false};
  const wanted=p.collection==='all'?'more':p.collection,candidates=all('a[href]',main()).filter(a=>visible(a)&&link(a.href)?.includes('/jobs/')&&/show all|все вакансии|показать все/i.test(txt(a)));
  const target=candidates.find(a=>jobSection(a)===wanted||(wanted==='profile'?/match your profile|соответств.*профил/i.test(txt(a)):wanted==='preferences'?/preferences|предпочтени/i.test(txt(a)):false))||jobLinks().find(({a})=>visible(a)&&jobSection(a)===wanted&&new URL(a.href).pathname.includes('/jobs/search-results/'))?.a;
  if(target){target.click();return {navigated:true,collection:wanted};}return {navigated:false};
 }
 function jobsAdvance(p={}){
  gate();let scroll=null;
  for(const a of [...jobLinks().map(r=>r.a),...jobButtons().map(r=>r.card)]){for(let n=a.parentElement;n&&n!==document.body;n=n.parentElement){if(n.clientHeight>=200&&n.clientWidth>=250&&n.scrollHeight>n.clientHeight+80&&/(auto|scroll)/.test(getComputedStyle(n).overflowY)&&(new Set(jobLinks(n).map(r=>r.u)).size>=2||all('button[aria-label]',n).filter(b=>/^Dismiss .+ job$/i.test(b.getAttribute('aria-label')||'')).length>=2)){scroll=n;break;}}if(scroll)break;}
  scroll=scroll||document.scrollingElement||document.documentElement;
  const atEnd=scroll.scrollTop+scroll.clientHeight>=scroll.scrollHeight-8;
  if(!atEnd){scroll.scrollBy(0,Math.max(400,scroll.clientHeight*.85));return {at_end:false,scroll_top:scroll.scrollTop,height:scroll.scrollHeight,viewport:scroll.clientHeight,tag:scroll.tagName};}
  // Reaching the lower boundary triggers the homepage's lazy pagination.
  scroll.scrollTo({top:scroll.scrollHeight,behavior:'instant'});
  if(location.pathname==='/jobs/'){const more=all('button,[role="button"]',main()).find(n=>visible(n)&&!n.disabled&&/^(?:load|show|see) more(?: jobs)?$|^показать ещ[её](?: вакансии)?$/i.test(txt(n)||n.getAttribute('aria-label')||'')&&jobSection(n)==='more');if(more){more.click();return {at_end:false,expanded:true};}}
  if(location.pathname!=='/jobs/'&&p.listing_mode!=='infinite'){
   const controls=all('button,a,[role="button"]',main()).filter(n=>visible(n)&&!n.disabled&&n.getAttribute('aria-disabled')!=='true');
   const next=controls.find(n=>/^(?:next(?: page)?|следующая(?: страница)?|далее)\s*[›»→❯]?$|^next page\b/i.test(n.getAttribute('aria-label')||txt(n))||n.getAttribute('rel')==='next');
   const numbers=controls.map(n=>({node:n,page:Number((n.getAttribute('aria-label')||txt(n)).match(/^(?:page|страница)?\s*(\d+)$/i)?.[1])})).filter(r=>r.page>0);
   const current=numbers.find(r=>r.node.getAttribute('aria-current')==='page'||r.node.getAttribute('aria-pressed')==='true'||r.node.getAttribute('aria-selected')==='true');
   const numbered=current?numbers.find(r=>r.page===current.page+1):null,target=next||numbered?.node;
   if(target){target.click();return {at_end:false,paginated:true,page:current?current.page+1:null};}
  }
  return {at_end:true,height:scroll.scrollHeight,scroll_top:scroll.scrollTop,viewport:scroll.clientHeight,tag:scroll.tagName};
 }
 function networkAdvance(){
  gate();const anchors=all('a[href]',main()).filter(a=>link(a.href,'profile'));let scroller=null;
  for(const a of anchors){for(let n=a.parentElement;n&&n!==document.body;n=n.parentElement){if(n.clientHeight>150&&n.clientWidth>250&&n.scrollHeight>n.clientHeight+50&&/(auto|scroll)/.test(getComputedStyle(n).overflowY)){scroller=n;break;}}if(scroller)break;}
  scroller=scroller||document.scrollingElement||document.documentElement;const atEnd=scroller.scrollTop+scroller.clientHeight>=scroller.scrollHeight-8;scroller.scrollBy(0,Math.max(400,scroller.clientHeight*.85));return {at_end:atEnd,height:scroller.scrollHeight,scroll_top:scroller.scrollTop};
 }
 function messageContainer(){return main().querySelector('.msg-s-message-list-content,[role="log"],.msg-s-message-list');}
 async function thread(p){
  gate();if(C.url(location.href,'thread')!==p.url)throw Error('Открыт другой диалог.');const container=messageContainer();if(!container)throw Error('Сообщения выбранного диалога ещё не загружены.');
  let nodes=all('li.msg-s-message-list__event',container);if(!nodes.length)nodes=all('.msg-s-event-listitem',container);
  const messages=[],occurrences=new Map();let currentDate='';
  for(const n of nodes){const dateHeading=n.querySelector('.msg-s-message-list__time-heading');if(dateHeading)currentDate=txt(dateHeading).slice(0,200);const body=n.querySelector('.msg-s-event-listitem__body,.msg-s-event-listitem__message-bubble'),text=txt(body);if(!text)continue;const sender=txt(n.querySelector('.msg-s-message-group__name,.msg-s-message-group__profile-link'))||txt(n.closest('.msg-s-message-group')?.querySelector('.msg-s-message-group__name')),timeNode=n.querySelector('.msg-s-message-group__timestamp')||n.querySelector('time[datetime]')||n.querySelector('time'),sent_label=txt(timeNode)||txt(n.querySelector('.msg-s-message-group__timestamp')),sent_at=timeNode?.getAttribute('datetime')||'',urn=n.getAttribute('data-event-urn')||n.querySelector('[data-event-urn]')?.getAttribute('data-event-urn')||'';
   const fingerprint=await C.hash({sender,text,sent_label,sent_at}),occurrence=occurrences.get(fingerprint)||0;occurrences.set(fingerprint,occurrence+1);
   const attachments=all('a[href]',body||n).map(a=>{try{const u=new URL(a.href);if(u.protocol!=='https:'||u.username||u.password)return null;return {label:txt(a).slice(0,200),url:u.href.slice(0,2500)};}catch{return null;}}).filter(Boolean).slice(0,10);
   messages.push({id:urn||fingerprint+':'+occurrence,id_kind:urn?'source':'content',sender:sender.slice(0,500),text:text.slice(0,20000),sent_label:sent_label.slice(0,200),sent_at:sent_at.slice(0,100),date_label:currentDate,avatar_url:(n.querySelector('img.msg-s-message-group__avatar,img[class*="avatar"]')||n.closest('.msg-s-message-group')?.querySelector('img[class*="avatar"]'))?.src||'',badges:visibleBadges(n),attachments});
  }
  const name=txt(main().querySelector('.msg-thread__link-to-profile,.msg-thread__topcard .msg-entity-lockup__entity-title,.msg-thread__topcard h2'));
  return {items:[{url:p.url,name,text:txt(container).slice(-180000),messages,read_quality:'loaded',...recordMetadata(container),avatar_url:main().querySelector('.msg-thread__topcard img,.msg-thread__link-to-profile img')?.src||'',headline:txt(main().querySelector('.msg-thread__topcard .msg-entity-lockup__entity-headline')),badges:visibleBadges(main().querySelector('.msg-thread')||container),vacancy_links:all('a[href]',container).map(a=>link(a.href,'job')).filter(Boolean)}],reason:'Видимая загруженная часть диалога'};
 }
 function threadAdvance(){
  gate();const container=messageContainer();if(!container)return {at_start:true};let scroller=null;for(let n=container;n&&n!==document.body;n=n.parentElement){if(n.clientHeight>100&&n.scrollHeight>n.clientHeight+20&&/(auto|scroll)/.test(getComputedStyle(n).overflowY)){scroller=n;break;}}
  if(!scroller)return {at_start:true};const atStart=scroller.scrollTop<=8;scroller.scrollBy(0,-Math.max(300,scroller.clientHeight*.8));return {at_start:atStart,scroll_top:scroller.scrollTop,height:scroller.scrollHeight};
 }
 function target(p){
  let container,button;
  const ds=all('[role="dialog"],dialog[open]').filter(visible);
  if(ds.length){if(ds.length!==1||!p.snapshot?.confirmation)throw Error('Закройте постороннее окно или подготовьте подтверждение заново.');container=ds[0];if(all('textarea,input:not([type="hidden"])',container).some(visible))throw Error('В диалоге есть дополнительные поля. Завершите действие вручную.');button=all('button',container).filter(visible).find(b=>txt(b)===p.snapshot.button_label);}
  else {const candidates=all('a[href]',main()).filter(a=>link(a.href,'profile')===p.url);container=candidates.map(a=>a.closest('li,article')).find(n=>n&&all('button',n).some(b=>C.names[p.network_action].test(txt(b)||b.getAttribute('aria-label')||'')));if(!container&&C.url(location.href).startsWith(p.url))container=main();if(container){const matches=all('button',container).filter(b=>visible(b)&&C.names[p.network_action].test(txt(b)||b.getAttribute('aria-label')||''));if(matches.length===1)button=matches[0];if(!button&&C.url(location.href).startsWith(p.url)){const menu=all('[role="menu"]').filter(visible),items=menu.flatMap(m=>all('button,[role="menuitem"]',m)).filter(b=>visible(b)&&C.names[p.network_action].test(txt(b)));if(items.length===1){button=items[0];container=menu[0];}}}}
  if(!container||!button)throw Error('Нужная кнопка контакта не найдена однозначно. Откройте контакт или нужный список приглашений.');return {container,button};
 }
 async function prepare(p){gate();const {container,button}=target(p),state={url:p.url,page_url:C.url(location.href),action:p.network_action,name:txt(container.querySelector('h1,h2,h3,a[href*="/in/"]')),button_label:txt(button)||button.getAttribute('aria-label'),context:txt(container).slice(0,6000),confirmation:!!p.snapshot?.confirmation};return {...state,target_fingerprint:await C.hash(state)};}
 async function execute(p){const fresh=await prepare(p);if(fresh.target_fingerprint!==p.snapshot.target_fingerprint)throw Error('Контакт или кнопка изменились. Подготовьте действие заново.');const {button}=target(p);button.click();return {clicked:true};}
 async function handle(operation,p){
  if(operation==='profile.language'){gate();if(!owned(p))throw Error('Собственный профиль не подтверждён.');if(profileLanguage()===p.profile_language)return {changed:false};const candidates=profileLanguages().filter(item=>(p.profile_language==='en'?/English|Английск/i:/Русский|Russian/i).test(item.label));if(candidates.length!==1)throw Error('Переключатель языка профиля не распознан. Выберите язык непосредственно в LinkedIn.');candidates[0].node.click();return {changed:true};}
  if(operation==='profile.read')return profile(p);
  if(operation==='profile.advance')return profileAdvance();
  if(operation==='profile.detail'){gate();if(!C.url(location.href).startsWith(p.account+'details/')||!sectionLabels[p.section])throw Error('Неизвестная секция профиля.');const section=readSection(p.section,p);if(!section.text)throw Error('Границы раскрытой секции не распознаны; сохранена доступная часть исходного блока.');return {url:C.url(location.href),section:p.section,...section};}
  if(operation==='profile.form')return form(p);
  if(operation==='profile.editor.open'){gate();if(!owned(p))throw Error('Собственный профиль не подтверждён.');const buttons=all('button,[role="button"]',main()).filter(button=>visible(button)&&(button.getAttribute('aria-label')||txt(button))===p.edit_label);if(buttons.length!==1)throw Error('Редактор выбранного блока не определён однозначно.');buttons[0].click();return {opened:true};}
  if(operation==='owner'){gate();return {verified:owned(p)};}
  if(operation==='profile.fill'){
   const fresh=await form(p);if(fresh.form_fingerprint!==p.snapshot.form_fingerprint)throw Error('Форма изменилась. Прочитайте её снова.');const nodes=fieldNodes(dialog());for(const [key,value] of Object.entries(p.values)){const n=nodes[Number(key.slice(1))];if(!n)throw Error('Поле исчезло.');if(n.type==='checkbox'){if(n.checked!==value)n.click();}else if(n.isContentEditable){n.textContent=value;n.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));}else{const proto=n.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:n.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(n,value);n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}));}}return form(p);
  }
  if(operation==='profile.save'){const fresh=await form(p);if(fresh.form_fingerprint!==p.snapshot.form_fingerprint)throw Error('Поля изменились после переноса. Прочитайте форму снова.');const buttons=all('button',dialog()).filter(b=>visible(b)&&/^(save|сохранить)$/i.test(txt(b)));if(buttons.length!==1)throw Error('Кнопка сохранения не распознана.');buttons[0].click();return {clicked:true};}
  if(['jobs.list','messages.list','network.list'].includes(operation))return listing(operation,p);
  if(operation==='jobs.diagnostics')return {navigation_controls:all('button,a,[role="button"]',main()).filter(visible).map(n=>n.getAttribute('aria-label')||txt(n)).filter(s=>s&&s.length<120&&/next|page|more|ещ[её]|далее/i.test(s)).slice(0,40),headings:all('h1,h2,h3,[role="heading"]').filter(visible).slice(0,50).map(headingLabel),buttons:all('button,[role="button"]',main()).filter(n=>/Dismiss .+ job/i.test(txt(n)||n.getAttribute('aria-label')||'')).slice(0,3).map(n=>({tag:n.tagName,attributes:[...n.attributes].filter(a=>/job|entity|urn|component|test|aria|role/i.test(a.name)).map(a=>[a.name,a.value.slice(0,150)]),ancestors:[n.parentElement,n.parentElement?.parentElement].filter(Boolean).map(n=>({tag:n.tagName,attributes:[...n.attributes].filter(a=>/job|entity|urn|component|test|aria|role/i.test(a.name)).map(a=>[a.name,a.value.slice(0,150)])}))})),root:{tag:main().tagName,length:txt(main()).length,headings:profileHeadings().map(headingLabel)},roots:all('main,[role="main"]').map(n=>({tag:n.tagName,length:txt(n).length,visible:visible(n)}))};
  if(operation==='team.read')return team(p);
  if(operation==='jobs.detail')return job(p);
  if(operation==='jobs.select')return jobsSelect(p);
  if(operation==='jobs.navigate')return jobsNavigate(p);
  if(operation==='jobs.advance')return jobsAdvance(p);
  if(operation==='network.advance')return networkAdvance();
  if(operation==='messages.navigate')return messagesNavigate(p);
  if(operation==='messages.advance')return messagesAdvance();
  if(operation==='messages.reset')return messagesReset();
  if(operation==='messages.select')return messagesSelect(p);
  if(operation==='messages.history.advance')return threadAdvance();
  if(operation==='messages.thread')return thread(p);
  if(operation==='network.prepare'){try{return await prepare(p);}catch(error){if(C.url(location.href).startsWith(p.url)&&p.network_action==='remove'){const more=all('button',main()).filter(b=>visible(b)&&/^(more|ещ[её]|дополнительно)$/i.test(txt(b)||b.getAttribute('aria-label')||''));if(more.length===1){more[0].click();throw Error('Меню контакта раскрыто. Нажмите «Подготовить действие» повторно.');}}throw error;}}
  if(operation==='network.execute')return execute(p);
  if(operation==='scroll'){const nodes=all('main,[role="main"],main *,[role="main"] *').filter(n=>visible(n)&&n.clientHeight>=200&&n.clientWidth>=250&&n.scrollHeight>n.clientHeight+80&&/(auto|scroll)/.test(getComputedStyle(n).overflowY));const n=nodes.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0];if(n)n.scrollBy(0,Math.max(500,n.clientHeight*.8));else window.scrollBy(0,innerHeight*.8);return {};}
  if(operation==='mutation.status'){const d=all('[role="dialog"],dialog[open]').filter(visible);return {dialog_open:!!d.length,alerts:all('[role="alert"]').filter(visible).map(txt).slice(0,5),url:C.url(location.href)};}
  throw Error('Неизвестная операция адаптера LinkedIn.');
 }
 root.LinkedInSession={handle};
})(globalThis);
