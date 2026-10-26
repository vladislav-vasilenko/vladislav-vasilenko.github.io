import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
export function buildPWA(dist,origin){
 const html=fs.readFileSync(path.join(dist,'index.html'),'utf8');
 const assets=[...new Set(html.match(/\/assets\/[\w.-]+\.(?:js|css)/g)||[])];
 const pdfAssets=fs.readdirSync(path.join(dist,'assets')).filter(name=>/^(?:resumePdf|pdfmake|vfs_fonts)-[\w.-]+\.js$/.test(name)).map(name=>'/assets/'+name);
 const resources=['/','/ru/','/hh-experience.json','/profile.jpg','/icon.svg','/icon-192.png','/icon-512.png','/apple-touch-icon.png','/manifest.webmanifest','/manifest-ru.webmanifest',...assets,...pdfAssets];
 const hash=createHash('sha256');for(const u of resources){hash.update(u);const file=path.join(dist,u==='/'?'index.html':u==='/ru/'?'ru/index.html':u);hash.update(fs.readFileSync(file));}const version=hash.digest('hex').slice(0,16);
 fs.writeFileSync(path.join(dist,'sw.js'),`'use strict';
const CACHE='portfolio-${version}';const PUBLIC=${JSON.stringify(resources)};
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(PUBLIC))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('portfolio-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('message',event=>{if(event.data?.type==='ACTIVATE_PORTFOLIO_UPDATE')self.skipWaiting();});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);if(request.method!=='GET'||url.origin!==self.location.origin)return;
 const navigation=request.mode==='navigate'&&(url.pathname==='/'||url.pathname==='/ru/'||url.pathname==='/ru/index.html');
 if(!navigation&&!PUBLIC.includes(url.pathname))return;
 const key=navigation?(url.pathname.startsWith('/ru')?'/ru/':'/'):url.pathname;
 if(navigation||url.pathname==='/hh-experience.json')event.respondWith(fetch(request).then(response=>{if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(key,copy)));}return response;}).catch(()=>caches.match(key).then(response=>response||Response.error())));
 else event.respondWith(caches.match(key).then(cached=>cached||fetch(request)));
});
`);
 console.log('PWA: versioned public cache '+version+'; '+resources.length+' allowlisted resources.');
}
