(()=>{
 const config=globalThis.__hhResumeBumpAction;delete globalThis.__hhResumeBumpAction;
 if(!config||!HHResumeBump.page(location.href)||!HHResumeBump.id('https://hh.ru/resume/'+config.resume_id))throw Error('Откройте свой профиль HH для поднятия выбранного резюме.');
 const visible=node=>{const r=node.getBoundingClientRect(),s=getComputedStyle(node);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none';};
 if(document.querySelector('form[action*="captcha"],input[name*="captcha"]')||[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].some(visible))throw Error('HH показывает CAPTCHA или диалог. Проверьте страницу вручную.');
 const clean=HHResumeBump.clean,label=n=>clean(n.innerText||n.getAttribute('aria-label'));
 const links=[...document.querySelectorAll('a[href]')].filter(a=>visible(a)&&HHResumeBump.id(a.href)===config.resume_id);let card;
 for(const link of links){for(let node=link.parentElement,depth=0;node&&node!==document.body&&depth<9;node=node.parentElement,depth++){
  const ids=[...new Set([...node.querySelectorAll('a[href]')].map(a=>HHResumeBump.id(a.href)).filter(Boolean))];if(ids.length>1)break;
  const text=clean(node.innerText);if(ids.length===1&&/Поднять|Сделать видимым|Не опубликовано/i.test(text)){card=node;break;}
 }if(card)break;}
 if(!card)return {state:'needs_input',resume_id:config.resume_id,note:'В личном профиле не найдена однозначная карточка выбранного резюме. Чужие и неопубликованные резюме не изменяются.'};
 const text=clean(card.innerText),buttons=[...card.querySelectorAll('button,a,[role="button"],[role="link"]')].filter(n=>visible(n)&&HHResumeBump.freeLabel(label(n)));
 const controls=buttons.map(n=>({paid:/оплат|купить|подписк|автоподнят|hh\s*pro/i.test(label(n))||n.tagName==='A'&&n.getAttribute('href')&&!['#',''].includes(n.getAttribute('href'))&&/services|payment|premium/i.test(n.href),enabled:!n.disabled&&n.getAttribute('aria-disabled')!=='true'}));
 const value={ids:[...new Set([...card.querySelectorAll('a[href]')].map(a=>HHResumeBump.id(a.href)).filter(Boolean))],hidden:/Сделать видимым/i.test(text),unpublished:/Не опубликовано/i.test(text),buttons:controls,cooldown:/поднять.{0,35}(?:через|можно будет|будет доступно)|следующее поднятие|резюме (?:успешно )?поднято/i.test(text)};
 const state=HHResumeBump.state(value),fingerprint=JSON.stringify([config.resume_id,state,controls]),result={state,resume_id:config.resume_id,fingerprint,source_url:location.href,evidence:state==='cooldown'?'Кнопка бесплатного поднятия выбранного резюме недоступна или HH показывает период ожидания.':''};
 if(config.action==='inspect')return result;
 if(config.action!=='click'||state!=='available'||fingerprint!==config.fingerprint||config.expires_at<Date.now())throw Error('Карточка или разрешение на поднятие изменились. Клик остановлен.');
 if(globalThis.__hhResumeBumpClicked===config.command_id)throw Error('Повторный клик поднятия запрещён.');
 globalThis.__hhResumeBumpClicked=config.command_id;buttons[0].click();return {...result,state:'clicked'};
})();
