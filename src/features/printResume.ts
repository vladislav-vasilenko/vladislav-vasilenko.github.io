import {directionArrow} from './directionArrow';
import type {CVContent, Lang} from '../i18n';
import {escapeText as e, type HHSnapshot} from './hhExperience';
import {introURL} from './resumeLinks';

const titleText = (value: string) => value.split(/<br\s*\/?\s*>/i)[0].replace(/<[^>]+>/g,' ').trim();
function blocks(value: string): string {
 const text=value.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,'$1 ($2)').replace(/(\*\*|__)(.*?)\1/g,'$2');
 return text.split(/\n\s*\n/).filter(v=>v.trim()).map(paragraph=>'<p>'+e(paragraph.trim()).replace(/\n/g,'<br>')+'</p>').join('');
}
export function renderPrintResume(cv:CVContent, lang:Lang, snapshot:HHSnapshot|null):string {
 const ru=lang==='ru';
 const back=new URL(location.href);back.searchParams.delete('print');back.searchParams.set('resumeView','true');
 const english=new URL(location.href);english.pathname='/';english.searchParams.set('lang','en');
 const russian=new URL(location.href);russian.pathname='/ru/';russian.searchParams.delete('lang');
 const about=snapshot?.about?.translations?.[lang]||snapshot?.about?.text||cv.aboutMd;
 const source=snapshot?.source.url;
 const pending=!!snapshot&&snapshot.source.language!==lang;
 const aboutPending=!!snapshot?.about&&snapshot.about.language!==lang&&!snapshot.about.translations?.[lang];
 const contact=[cv.contact.location,cv.contact.relocation].filter(Boolean);
 return `<nav class="print-toolbar" aria-label="${ru?'Управление печатью':'Print controls'}"><a href="${e(back.href)}">${directionArrow('left')} ${ru?'К портфолио':'Portfolio'}</a><a href="${e(introURL(location.href,lang))}" aria-label="${ru?'Показать Intro-анимацию':'Show Intro animation'}">${directionArrow('up')} Intro</a><span><a href="${e(english.href)}" hreflang="en">EN</a> / <a href="${e(russian.href)}" hreflang="ru">RU</a></span><button type="button" data-print-document>${ru?'Печать':'Print'}</button><button type="button" data-download-resume>${ru?'Сохранить PDF':'Save PDF'}</button></nav>
 <p class="print-export-status" data-pdf-status role="status" hidden></p>
 <main class="print-resume">
 <header class="print-resume-header"><div><h1>${e(cv.name)}</h1><h2>${e(titleText(cv.title))}</h2>
 <p><a href="mailto:${e(cv.contact.email)}">${e(cv.contact.email)}</a></p>
 <p>${contact.map(e).join('<br>')}</p>
 <p class="print-social"><a href="https://github.com/vladislav-vasilenko">github.com/vladislav-vasilenko</a><br><a href="https://huggingface.co/VVladTech">huggingface.co/VVladTech</a><br><a href="https://linkedin.com/in/tech">linkedin.com/in/tech</a> · <a href="https://t.me/vsvladis">t.me/vsvladis</a></p></div><img src="/profile.jpg" width="150" height="190" alt="${e(cv.name)}"></header>
 ${source?'<p class="print-source">'+(ru?'Источник: ':'Source: ')+'<a href="'+e(source)+'">'+(ru?'основное HH-резюме':'primary HH resume')+'</a>'+(snapshot?.source.translated_from?' · '+(ru?'Перевод с ':'Translated from ')+snapshot.source.translated_from.toUpperCase():'')+'</p>':''}
 <section><h2>${ru?'Обо мне':'About'}</h2>${aboutPending?'<p class="print-source">'+(ru?'Ожидается перевод · оригинал: ':'Translation pending · original: ')+snapshot!.about!.language.toUpperCase()+'</p>':''}${blocks(about)}</section>
 <section><h2>${ru?'Опыт работы':'Work experience'}</h2>${pending?'<p class="print-source">'+(ru?'Показан исходный текст опыта · ':'Original experience text · ')+snapshot!.source.language.toUpperCase()+'</p>':''}
 ${cv.experience.map(job=>`<article class="print-experience-entry"><div class="print-period">${e(job.period)}${job.duration?'<span class="print-duration">'+e(job.duration)+'</span>':''}</div><div><h3>${e(job.company)}</h3><p class="print-position">${e(job.role)}</p>${job.location?'<p>'+e(job.location)+'</p>':''}${blocks(job.descriptionMd)}</div></article>`).join('')}</section>
 ${snapshot?.confirmed_skills.length?`<section><h2>${ru?'Подтверждённые навыки':'Skills with evidence'}</h2>${snapshot.confirmed_skills.map(skill=>'<p><strong>'+e(skill.label)+'</strong>'+skill.links.map(link=>' · <a href="'+e(link.url)+'">'+e(link.label||link.url)+'</a>').join('')+'</p>').join('')}</section>`:''}
 <section><h2>${ru?'Навыки и инструменты':'Skills and tools'}</h2>${cv.techStack.categories.map(category=>'<p><strong>'+e(category.label[lang])+'</strong> — '+category.items.map(item=>e(item.name)).join(', ')+'</p>').join('')}</section>
 <section><h2>${ru?'Образование и курсы':'Education and courses'}</h2>${cv.education.map(item=>'<article class="print-education-entry"><div class="print-period">'+e(item.year)+'</div><div><h3>'+e(item.institution)+'</h3><p>'+e(item.program)+'</p></div></article>').join('')}</section>
 ${cv.languages?.length?'<section><h2>'+(ru?'Языки':'Languages')+'</h2><p>'+cv.languages.map(e).join('<br>')+'</p></section>':''}
 </main>`;
}
