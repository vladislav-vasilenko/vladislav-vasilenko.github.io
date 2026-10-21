/* Free bump of an already visible resume. Publishing and paid upsells are excluded. */
(function(root){
 const clean=value=>String(value||'').replace(/\s+/g,' ').trim();
 function page(url){try{const u=new URL(url);return u.origin==='https://hh.ru'&&u.pathname==='/applicant/profile/me'&&!u.search&&!u.hash;}catch{return false;}}
 function id(href){try{const u=new URL(href,'https://hh.ru');if(u.origin!=='https://hh.ru')return null;const value=u.pathname.match(/^\/resume\/([a-f0-9]{38})\/?$/i)?.[1]||(/^\/search\/vacancy\/?$/.test(u.pathname)?u.searchParams.get('resume'):'');return /^[a-f0-9]{38}$/i.test(value||'')?value.toLowerCase():null;}catch{return null;}}
 const freeLabel=value=>/^(?:Поднять в поиске|Поднять резюме в поиске)$/i.test(clean(value));
 function state(card){
  if(!card||card.ids.length!==1)return 'needs_input';
  if(card.hidden||card.unpublished)return 'not_visible';
  if(card.buttons.length===1&&!card.buttons[0].paid)return card.buttons[0].enabled?'available':'cooldown';
  if(!card.buttons.length&&card.cooldown)return 'cooldown';
  return 'needs_input';
 }
 root.HHResumeBump={page,id,freeLabel,state,clean};
})(globalThis);
