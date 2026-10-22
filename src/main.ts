import './style.css';
import {getLang,setLang,loadContent,type Lang} from './i18n';
import {loadHHSnapshot,applyHHSnapshot,type HHSnapshot} from './features/hhExperience';
import {renderMinimal} from './features/minimalPortfolio';
import {presentationStyle} from './features/presentationStyle';
import {exportMarkdown} from './export';

const query=new URLSearchParams(location.search);
let language:Lang=query.get('lang')==='ru'?'ru':query.get('lang')==='en'?'en':getLang();
let focus=query.get('tech')||'all';
let style=presentationStyle(query.get('style'));
let snapshot:HHSnapshot|null=null;
const detailed=query.get('layout')==='full';

function renderPage():void{
 setLang(language);document.documentElement.classList.add('minimal-mode');
 // Focus changes emphasis, never the source wording or work history.
 const cv=applyHHSnapshot(loadContent(language,'vision'),snapshot,language);
 const root=document.querySelector<HTMLDivElement>('#app')!;
 root.innerHTML=renderMinimal(cv,language,snapshot,focus,style,detailed);
 root.querySelectorAll<HTMLButtonElement>('.minimal-lang').forEach(button=>button.onclick=()=>{
  language=button.dataset.lang as Lang;const url=new URL(location.href);url.searchParams.set('lang',language);window.history.replaceState(null,'',url);renderPage();
 });
 root.querySelectorAll<HTMLButtonElement>('button[data-presentation]').forEach(button=>button.onclick=()=>{
  style=presentationStyle(button.dataset.presentation||null);const url=new URL(location.href);
  if(style==='minimal')url.searchParams.delete('style');else url.searchParams.set('style',style);
  window.history.replaceState(null,'',url);
  const change=()=>{renderPage();document.querySelector<HTMLDetailsElement>('.presentation-picker')?.setAttribute('open','');document.querySelector<HTMLButtonElement>('button[data-presentation="'+style+'"]')?.focus();};
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){change();return;}
  if(document.startViewTransition)document.startViewTransition(change);
  else{change();root.animate([{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'translateY(0)'}],{duration:420,easing:'ease-out'});}
 });
 const selector=root.querySelector<HTMLSelectElement>('.minimal-focus')!;
 selector.onchange=()=>{focus=selector.value;const url=new URL(location.href);if(focus==='all')url.searchParams.delete('tech');else url.searchParams.set('tech',focus);window.history.replaceState(null,'',url);renderPage();};
 root.querySelector<HTMLButtonElement>('[data-export="print"]')?.addEventListener('click',()=>window.print());
 root.querySelector<HTMLButtonElement>('[data-export="markdown"]')?.addEventListener('click',()=>exportMarkdown(cv));
}
renderPage();
void loadHHSnapshot().then(value=>{if(value){snapshot=value;renderPage();}});
