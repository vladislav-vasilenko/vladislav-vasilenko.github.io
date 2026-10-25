import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import {buildPWA} from './pwa-assets.mjs';
import {marked} from 'marked';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
export const origin='https://vladislav-vasilenko.github.io';
function feature(name,href,cache=new Map()){
 if(cache.has(name))return cache.get(name);
 const exports={};cache.set(name,exports);
 const source=ts.transpileModule(fs.readFileSync(path.join(root,'src/features',name+'.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const context=vm.createContext({exports,URL,location:{href},require:p=>feature(p.replace('./',''),href,cache)});vm.runInContext(source,context);return exports;
}
function content(lang){
 const folder=path.join(root,'content',lang),cv=JSON.parse(fs.readFileSync(path.join(folder,'cv.json'),'utf8'));
 const read=(...names)=>{for(const n of names){const p=path.join(folder,n);if(fs.existsSync(p))return fs.readFileSync(p,'utf8');}return '';};
 cv.aboutMd=read('about-vision.md','about.md');cv.aboutHtml=marked.parse(cv.aboutMd);
 const stack=path.join(root,'content',fs.existsSync(path.join(root,'content/tech-stack-vision.json'))?'tech-stack-vision.json':'tech-stack.json');cv.techStack=JSON.parse(fs.readFileSync(stack,'utf8'));
 cv.experience=cv.experience.map(e=>{const descriptionMd=read('experience/'+e.id+'-vision.md','experience/'+e.id+'.md');return {...e,descriptionMd,descriptionHtml:marked.parse(descriptionMd)};});return cv;
}
export function staticHTML(template,lang,snapshot){
 const url=origin+(lang==='ru'?'/ru/':'/'),hh=feature('hhExperience',url),renderer=feature('minimalPortfolio',url);
 if(snapshot&&!hh.validateSnapshot(snapshot))throw Error('Public portfolio snapshot failed validation');
 const cv=hh.applyHHSnapshot(content(lang),snapshot,lang),escape=hh.escapeText;
 const plain=s=>s.replace(/<[^>]+>/g,' ').replace(/[\n\s]+/g,' ').trim();
 const description=plain(cv.aboutMd).slice(0,250).replace(/\s+\S*$/,'');
 const title=cv.name+' — '+plain(cv.title.split(/<br/i)[0]);
 const data={'@context':'https://schema.org','@type':'ProfilePage','@id':url+'#profile','url':url,'inLanguage':lang,
  'mainEntity':{'@type':'Person','@id':origin+'/#person','name':cv.name,'alternateName':lang==='ru'?'Vladislav Vasilenko':'Владислав Василенко','url':origin+'/',
   'image':origin+'/profile.jpg','jobTitle':plain(cv.title.split(/<br/i)[0]),'description':description,'sameAs':['https://github.com/vladislav-vasilenko']}};
 const json=JSON.stringify(data).replace(/</g,'\\u003c');
 const seo=`<link rel="manifest" href="/manifest${lang==='ru'?'-ru':''}.webmanifest"><link rel="icon" type="image/svg+xml" href="/icon.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#1d382d"><meta name="apple-mobile-web-app-title" content="Vasilenko"><meta name="description" content="${escape(description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="${url}"><link rel="alternate" hreflang="en" href="${origin}/"><link rel="alternate" hreflang="ru" href="${origin}/ru/"><link rel="alternate" hreflang="x-default" href="${origin}/"><meta property="og:type" content="profile"><meta property="og:url" content="${url}"><meta property="og:title" content="${escape(title)}"><meta property="og:description" content="${escape(description)}"><meta property="og:image" content="${origin}/profile.jpg"><meta property="og:locale" content="${lang==='ru'?'ru_RU':'en_US'}"><meta name="twitter:card" content="summary"><meta name="twitter:title" content="${escape(title)}"><meta name="twitter:description" content="${escape(description)}"><meta name="twitter:image" content="${origin}/profile.jpg"><script type="application/ld+json">${json}</script>`;
 if(!template.includes('<!--portfolio:seo-->')||!template.includes('<div id="app"></div>'))throw Error('Missing static portfolio template markers');
 return template.replace(/<html[^>]*>/,`<html lang="${lang}" class="minimal-mode">`).replace(/<title>.*?<\/title>/s,`<title>${escape(title)}</title>`).replace('<!--portfolio:seo-->',seo)
  .replace(/(class="latent-intro-name">)[^<]*/,(_,prefix)=>prefix+escape(cv.name))
  .replace(/(data-intro-play[^>]*><span>)[^<]*/,(_,prefix)=>prefix+(lang==='ru'?'Посмотреть резюме':'View resume'))
  .replace('<div id="app"></div>',`<div id="app">${renderer.renderMinimal(cv,lang,snapshot,'all','minimal')}</div>`)
  .replace('</body>',`<script type="application/json" id="portfolio-snapshot">${JSON.stringify(snapshot).replace(/</g,'\\u003c')}</script></body>`);
}
export function prerender(){
 const dist=path.join(root,'dist'),template=fs.readFileSync(path.join(dist,'index.html'),'utf8'),snapshot=JSON.parse(fs.readFileSync(path.join(root,'public/hh-experience.json'),'utf8'));
 fs.writeFileSync(path.join(dist,'index.html'),staticHTML(template,'en',snapshot));fs.mkdirSync(path.join(dist,'ru'),{recursive:true});fs.writeFileSync(path.join(dist,'ru/index.html'),staticHTML(template,'ru',snapshot));
 buildPWA(dist,origin);
 console.log('Prerendered EN and RU: semantic HTML, metadata, ProfilePage and Person.');
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))prerender();
