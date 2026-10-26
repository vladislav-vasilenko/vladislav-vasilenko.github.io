import {initializePWA} from './features/pwa';
import './style.css';
import './printResume.css';
import {setLang,loadContent,type Lang} from './i18n';
import {loadHHSnapshot,applyHHSnapshot,localizeHHSnapshot,validateSnapshot,type HHSnapshot} from './features/hhExperience';
import {renderMinimal} from './features/minimalPortfolio';
import {presentationStyle} from './features/presentationStyle';
import {exportMarkdown} from './export';
import {portfolioLanguage} from './features/locale';
import {watchIntroPower} from './features/introPower';
import {renderPrintResume} from './features/printResume';
import {printResumeURL} from './features/resumeLinks';

const query=new URLSearchParams(location.search);
let language:Lang=portfolioLanguage(location.href,navigator.languages);
let focus=query.get('tech')||'all';
let style=presentationStyle(query.get('style'));
let snapshot:HHSnapshot|null=null;
try{snapshot=validateSnapshot(JSON.parse(document.getElementById('portfolio-snapshot')?.textContent||'null'));}catch{/* Fetch remains the fallback. */}
const detailed=query.get('layout')==='full';
const printView=query.get('print')==='true';
const resumeOnly=printView||query.get('resumeView')==='true';

function renderPage():void{
 setLang(language);document.documentElement.classList.add('minimal-mode');
 // Focus changes emphasis, never the source wording or work history.
 const pageSnapshot=localizeHHSnapshot(snapshot,language);
 const cv=applyHHSnapshot(loadContent(language,'vision'),pageSnapshot,language);
 const introName=document.querySelector<HTMLElement>('.latent-intro-name');
 if(introName)introName.textContent=language==='ru'?'Владислав Василенко':'Vladislav Vasilenko';
 const introLabel=document.querySelector<HTMLElement>('[data-intro-action]');
 if(introLabel)introLabel.textContent=language==='ru'?'Посмотреть резюме':'View resume';
 const introPrint=document.querySelector<HTMLAnchorElement>('[data-intro-print]');
 if(introPrint){
  introPrint.href=printResumeURL(location.href,language);
  introPrint.querySelector<HTMLElement>('[data-intro-print-label]')!.textContent=language==='ru'?'Резюме для печати':'Print-friendly resume';
 }
 const emailLabel=document.querySelector<HTMLElement>('[data-intro-email-label]');
 if(emailLabel)emailLabel.textContent=language==='ru'?'Почта':'Email';
 document.querySelector('.latent-intro-contacts')?.setAttribute('aria-label',language==='ru'?'Связаться с Владиславом':'Contact Vladislav');
 document.getElementById('latent-intro')?.setAttribute('aria-label',language==='ru'?'Анимационное вступление':'Animated introduction');
 const root=document.querySelector<HTMLDivElement>('#app')!;
 if(printView){
  document.documentElement.classList.add('print-resume-mode');
  root.innerHTML=renderPrintResume(cv,language,pageSnapshot);
  const printButton=root.querySelector<HTMLButtonElement>('[data-print-document]')!;
  const pdfButton=root.querySelector<HTMLButtonElement>('[data-download-resume]')!;
  const status=root.querySelector<HTMLElement>('[data-pdf-status]')!;
  const savePDF=async()=>{
   printButton.disabled=true;pdfButton.disabled=true;status.hidden=false;
   status.textContent=language==='ru'?'Подготавливаем PDF…':'Preparing PDF…';
   try{
    const {downloadResumePDF}=await import('./features/resumePdf');
    await downloadResumePDF(cv,language,pageSnapshot);
    status.textContent=language==='ru'?'PDF подготовлен. Если открыт предпросмотр, сохраните файл через «Поделиться».':'PDF prepared. If a preview opened, use Share to save the file.';
   }catch{
    status.textContent=language==='ru'?'PDF не удалось подготовить. Проверьте подключение и повторите; печатная версия остаётся доступна.':'Could not prepare the PDF. Check the connection and retry; the print document remains available.';
   }finally{printButton.disabled=false;pdfButton.disabled=false;}
  };
  pdfButton.onclick=()=>{void savePDF();};
  const standalone=matchMedia('(display-mode: standalone)').matches||!!(navigator as Navigator&{standalone?:boolean}).standalone;
  if(standalone){printButton.textContent=language==='ru'?'Сохранить PDF':'Save PDF';pdfButton.hidden=true;printButton.onclick=()=>{void savePDF();};}
  else printButton.onclick=()=>window.print();
  return;
 }
 root.innerHTML=renderMinimal(cv,language,pageSnapshot,focus,style,detailed);
 root.querySelectorAll<HTMLButtonElement>('button[data-presentation]').forEach(button=>button.onclick=()=>{
  style=presentationStyle(button.dataset.presentation||null);const url=new URL(location.href);
  if(style==='minimal')url.searchParams.delete('style');else url.searchParams.set('style',style);
  window.history.replaceState(null,'',url);
  const change=()=>{renderPage();root.querySelector<HTMLElement>('.presentation-picker>summary')?.focus();};
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){change();return;}
  if(document.startViewTransition)document.startViewTransition(change);
  else{change();root.animate([{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'translateY(0)'}],{duration:420,easing:'ease-out'});}
 });
 const selector=root.querySelector<HTMLSelectElement>('.minimal-focus')!;
 selector.onchange=()=>{focus=selector.value;const url=new URL(location.href);if(focus==='all')url.searchParams.delete('tech');else url.searchParams.set('tech',focus);window.history.replaceState(null,'',url);renderPage();};
 root.querySelector<HTMLButtonElement>('[data-export="print"]')?.addEventListener('click',()=>location.assign(printResumeURL(location.href,language)));
 root.querySelector<HTMLButtonElement>('[data-export="markdown"]')?.addEventListener('click',()=>exportMarkdown(cv));
 initializePWA();
}
renderPage();
// The intro is static HTML (no layout shift); its three.js bundle loads lazily so the CV paints first.
const intro=document.getElementById('latent-intro');
if(intro){
 if(detailed||resumeOnly||matchMedia('(prefers-reduced-motion: reduce)').matches)intro.remove();
 else {
  let controller:ReturnType<typeof import('./latentIntro.jsx')['mountLatentIntro']>|null=null;
  const disable=()=>{
   if(!intro.isConnected)return;
   const readingOffset=Math.max(0,-document.getElementById('app')!.getBoundingClientRect().top);
   controller?.destroy();intro.remove();
   if(readingOffset>0||window.scrollY>0)window.scrollTo({top:readingOffset,behavior:'instant'});
  };
  const power=watchIntroPower(navigator,matchMedia('(prefers-reduced-motion: reduce)'),disable);
  const scene=power.ready.then(async()=>{
   if(!intro.isConnected)return null;
   const m=await import('./latentIntro.jsx');
   if(!intro.isConnected)return null;
   controller=m.mountLatentIntro(intro);return controller;
  }).catch(()=>{disable();return null;});
  const play=intro.querySelector<HTMLButtonElement>('[data-intro-play]');
  if(play)play.onclick=()=>{void scene.then(controller=>controller?.play());};
 }
}
void loadHHSnapshot().then(value=>{if(value){snapshot=value;renderPage();}});
