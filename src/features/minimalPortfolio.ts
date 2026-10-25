import {directionArrow} from './directionArrow';
import {pwaPanel} from './pwaView';
import {renderPublicVisuals} from './publicVisuals';
import {stylePicker,presentationCopy,type PresentationStyle} from './presentationStyle';
import type {CVContent,Lang} from '../i18n';
import {escapeText,renderConfirmedSkills,type HHSnapshot} from './hhExperience';
import {experienceFocus} from './experienceFocus';
import {introURL,printResumeURL} from './resumeLinks';

const clean=(value:string)=>value.replace(/<[^>]*>/g,' ').replace(/!?\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/[*#_`]/g,'').replace(/\s+/g,' ').trim();
const brief=(value:string,limit:number)=>{const text=clean(value);return text.length<=limit?text:text.slice(0,limit).replace(/\s+\S*$/,'')+'…';};
const link=(url:string,label:string)=>`<a href="${escapeText(url)}" target="_blank" rel="noopener noreferrer">${escapeText(label)}</a>`;
export function renderMinimal(cv:CVContent,lang:Lang,snapshot:HHSnapshot|null,focus:string,style:PresentationStyle='minimal',detailed=false):string{
 const copy=presentationCopy(style,lang);
 const english=new URL(location.href);english.pathname='/';english.searchParams.set('lang','en');const russian=new URL(english);russian.pathname='/ru/';russian.searchParams.delete('lang');
 const full=new URL(location.href);if(detailed)full.searchParams.delete('layout');else full.searchParams.set('layout','full');full.searchParams.set('lang',lang);
 const printURL=printResumeURL(location.href,lang);
 const projectLinks=new Map<string,string>();
 for(const job of cv.experience)for(const match of job.descriptionMd.matchAll(/https:\/\/github\.com\/[\w.-]+\/[\w.-]+/g)){const url=match[0];projectLinks.set(url,url.split('/').pop()!);}
 const pending=!!snapshot&&snapshot.source.language!==lang;
 const sourceLabel=lang==='ru'?'основное HH-резюме':'primary HH resume';
 const sourceLink=snapshot?.source.url?`<a href="${escapeText(snapshot.source.url)}" target="_blank" rel="noopener noreferrer">${sourceLabel} ${directionArrow('external')}</a>`:sourceLabel;
 const about=snapshot?.about;
 const aboutText=about?.translations?.[lang]||about?.text||cv.aboutMd;
 const aboutPending=!!about&&about.language!==lang&&!about.translations?.[lang];
 const introText=detailed||aboutText.length<=1100?clean(aboutText):brief(aboutText,380);
 const intro=aboutPending?`<p class="minimal-intro minimal-source">${lang==='ru'?'Ожидается перевод введения на RU':'Introduction: EN translation pending'}</p><details class="minimal-about-original"${detailed?' open':''}><summary>${lang==='ru'?'Показать оригинал':'Read original'} · ${about!.language.toUpperCase()}</summary><p>${escapeText(aboutText).replace(/\n/g,'<br>')}</p></details>`:`<p class="minimal-intro">${copy.intro?escapeText(copy.intro)+' ':''}${escapeText(about&&(detailed||aboutText.length<=1100)?aboutText:introText).replace(/\n\n+/g,'<br><br>').replace(/\n/g,' ')}</p>${!detailed&&aboutText.length>1100?`<details class="minimal-about-original"><summary>${lang==='ru'?'Продолжить чтение':'Continue reading'}</summary><p>${escapeText(aboutText).replace(/\n/g,'<br>')}</p></details>`:''}`;

 const options=[['all',lang==='ru'?'Весь опыт':'All experience'],['vision','Vision & GenAI'],['audio','Audio / Speech'],['multimodal','Multimodal'],['multiagent','Multi-agent'],['llm','NLP / LLM'],['ios','iOS / Swift']];
 return `<main class="minimal-portfolio" data-presentation="${style}">
 <nav class="minimal-nav" aria-label="${lang==='ru'?'Язык и версия':'Language and view'}"><span><a class="minimal-lang" href="${escapeText(english.href)}" hreflang="en" aria-current="${lang==='en'?'page':'false'}">EN</a><span aria-hidden="true"> / </span><a class="minimal-lang" href="${escapeText(russian.href)}" hreflang="ru" aria-current="${lang==='ru'?'page':'false'}">RU</a></span><div class="minimal-nav-right"><a class="minimal-print-link" href="${escapeText(printURL)}"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 8V3h10v5M7 17H4V9h16v8h-3M7 14h10v7H7z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="17" cy="11" r="1" fill="currentColor"/></svg>${lang==='ru'?'Резюме для печати':'Print-friendly resume'}</a><a class="minimal-intro-return" href="${escapeText(introURL(location.href,lang))}" aria-label="${lang==='ru'?'Показать Intro-анимацию':'Show Intro animation'}" title="${lang==='ru'?'Показать Intro-анимацию':'Show Intro animation'}">${directionArrow('up')} Intro</a>${stylePicker(style,lang)}<a href="${escapeText(full.href)}">${detailed?(lang==='ru'?'Краткая версия':'Overview'):(lang==='ru'?'Полное резюме':'Full CV')} ${directionArrow()}</a></div></nav>
 ${style==='macintosh'?`<div class="mac-window-bar"><span aria-hidden="true">□</span><span>PERSONAL COMPUTER. PERSONAL ENGINEER.</span></div>`:''}
 ${detailed?`<div class="minimal-document-actions"><button type="button" data-export="print">${lang==='ru'?'Печать / PDF':'Print / PDF'}</button><button type="button" data-export="markdown">Markdown ↓</button></div>`:''}
 ${copy.kicker?`<p class="presentation-kicker">${copy.kicker}</p>`:''}${copy.hello?`<p class="presentation-hello">${copy.hello}</p>`:''}
 <header class="minimal-header"><img src="/profile.jpg" alt="${escapeText(cv.name)}" width="112" height="112"><div><h1>${escapeText(cv.name)}</h1><p class="minimal-role">${escapeText(clean(cv.title.split(/<br\s*\/?\s*>/i)[0]))}</p>${copy.contact?`<p class="presentation-interface">${copy.contact}</p>`:''}<p class="minimal-links">${link('https://github.com/vladislav-vasilenko','GitHub')} · ${link('https://huggingface.co/VVladTech','Hugging Face')} · ${link('https://linkedin.com/in/tech','LinkedIn')} · <a href="mailto:${escapeText(cv.contact.email)}">Email</a> · <a class="header-telegram" href="https://t.me/vsvladis" target="_blank" rel="noopener noreferrer" aria-label="${lang==='ru'?'Написать в Telegram (откроется в новой вкладке)':'Message on Telegram (opens in a new tab)'}"><svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor" aria-hidden="true"><path d="M21.6 3.3 18.3 20c-.2 1.2-.9 1.5-1.9.9l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1 9.3-8.4c.4-.4-.1-.6-.6-.3L5.6 13.4.7 11.9c-1.1-.3-1.1-1.1.2-1.6L20 2.9c.9-.3 1.8.2 1.6.4Z"/></svg><span>Telegram</span>${directionArrow('external')}</a></p></div></header>
 ${copy.headline?`<h2 class="presentation-headline">${copy.headline}</h2>`:''}${copy.manifest?`<p class="presentation-manifest-label">${copy.manifest}</p>`:''}${intro}${about?`<p class="minimal-about-source">${about.origin==='reviewed'?(lang==='ru'?'Редакция для портфолио · основа: ':'Edited for portfolio · based on: '):(lang==='ru'?'Источник введения: ':'Introduction source: ')}${sourceLink}</p>`:''}
 ${renderPublicVisuals(snapshot?.visuals,lang)}
 <section class="minimal-work"><div class="minimal-section-heading"><h2>${copy.experience}</h2><label>${lang==='ru'?'Фокус':'Focus'} <select class="minimal-focus" aria-label="${lang==='ru'?'Фокус опыта':'Experience focus'}">${options.map(([value,label])=>`<option value="${value}"${focus===value?' selected':''}>${label}</option>`).join('')}</select></label></div>
 ${snapshot?`<p class="minimal-source">${lang==='ru'?'Источник: ':'Source: '}${sourceLink}${snapshot.source.translated_from?' · '+(lang==='ru'?'Перевод с ':'Translated from ')+snapshot.source.translated_from.toUpperCase():''}${pending?' · '+(lang==='ru'?'Ожидается перевод на RU':'EN translation pending'):''}</p>`:''}
 <div class="minimal-timeline">${cv.experience.map(job=>{const relevant=experienceFocus(job,focus,lang);return `<article class="minimal-entry${relevant?' is-focused':''}"><p class="minimal-period">${escapeText(job.period)}</p><div><h3>${escapeText(job.role)}</h3><p class="minimal-company">${escapeText(job.company)}</p>${relevant?`<span class="minimal-focus-tag">${escapeText(relevant)}</span>`:''}
 ${pending?`<p class="minimal-source">${lang==='ru'?'Ожидается перевод':'Translation pending'}</p>`:detailed?'':`<p>${escapeText(brief(job.descriptionMd,300))}</p>`}
 ${detailed&&!pending?`<div class="minimal-description">${job.descriptionHtml}</div>`:`<details${detailed?' open':''}><summary>${pending?(lang==='ru'?'Показать оригинал':'Read original')+' · '+snapshot!.source.language.toUpperCase():(lang==='ru'?'Подробнее':'Read more')}</summary><div class="minimal-description">${job.descriptionHtml}</div></details>`}</div></article>`;}).join('')}</div></section>
 ${renderConfirmedSkills(snapshot,lang)}
 ${projectLinks.size&&!snapshot?.visuals?.trajectory?.labs.length?`<section class="minimal-projects"><h2>${copy.projects}</h2><ul>${[...projectLinks].slice(0,8).map(([url,name])=>`<li>${link(url,name)}</li>`).join('')}</ul></section>`:''}
 ${detailed?`<section class="minimal-projects"><details><summary>${lang==='ru'?'Архитектура компетенций · стек':'Skills & tools'}</summary>${cv.techStack.categories.map(c=>`<p><strong>${escapeText(c.label[lang])}</strong> — ${c.items.map(i=>escapeText(i.name)).join(', ')}</p>`).join('')}</details></section>`:''}
 <section class="minimal-education"><h2>${copy.education}</h2>${cv.education.map(e=>`<p><span>${escapeText(e.year)}</span> ${escapeText(e.institution)}<br><small>${escapeText(e.program)}</small></p>`).join('')}</section>
 ${copy.closing?`<p class="presentation-closing">${copy.closing}</p>`:''}<footer class="minimal-footer"><a href="${escapeText(full.href)}">${detailed?(lang==='ru'?'Вернуться к краткой версии':'Back to overview'):(lang==='ru'?'Полное резюме и экспорт':'Full CV & export')} ${directionArrow()}</a>${pwaPanel(lang)}</footer></main>`;
}
