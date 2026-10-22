import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import os from 'node:os';
import path from 'node:path';
import {buildPWA} from '../pwa-assets.mjs';
function worker(){
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'portfolio-pwa-'));
 const files={'index.html':'<script src="/assets/main-test.js"></script>','ru/index.html':'RU','hh-experience.json':'{}','profile.jpg':'photo','icon.svg':'svg','icon-192.png':'192','icon-512.png':'512','apple-touch-icon.png':'180','manifest.webmanifest':'{}','manifest-ru.webmanifest':'{}','assets/main-test.js':'script'};
 for(const [name,data] of Object.entries(files)){fs.mkdirSync(path.dirname(path.join(folder,name)),{recursive:true});fs.writeFileSync(path.join(folder,name),data);}
 buildPWA(folder,'https://example.org');const source=fs.readFileSync(path.join(folder,'sw.js'),'utf8');fs.rmSync(folder,{recursive:true,force:true});
 const listeners={},stored=new Map(),added=[];
 const cache={async addAll(list){added.push(...list);},async put(key,value){stored.set(key,value);}};
 let network=async()=>new Response('NETWORK'),activated=0;
 const context=vm.createContext({URL,Response,self:{location:{origin:'https://example.org'},addEventListener:(name,fn)=>listeners[name]=fn,clients:{claim:async()=>{}},skipWaiting:()=>activated++},caches:{open:async()=>cache,match:async key=>stored.get(key),keys:async()=>[],delete:async()=>true},fetch:request=>network(request)});vm.runInContext(source,context);
 return {listeners,stored,added,setNetwork:fn=>network=fn,activated:()=>activated,async fetch(url,method='GET',mode='navigate'){let response;const waiting=[];listeners.fetch({request:{url,method,mode},respondWith:p=>response=p,waitUntil:p=>waiting.push(p)});if(!response)return undefined;const result=await response;await Promise.all(waiting);return result;}};
}
test('PWA caches only explicit public resources and supports offline language navigation',async()=>{
 const w=worker();let installed;w.listeners.install({waitUntil:p=>installed=p});await installed;
 assert.ok(w.added.includes('/ru/'));assert.ok(w.added.includes('/hh-experience.json'));assert.ok(w.added.includes('/assets/main-test.js'));
 assert.equal(await w.fetch('http://127.0.0.1:8788/archive/resume'),undefined);
 assert.equal(await w.fetch('https://example.org/state.sqlite3'),undefined);
 assert.equal(await w.fetch('https://example.org/','POST'),undefined);
 assert.equal(await w.fetch('https://example.org/private.json','GET','cors'),undefined);
 assert.equal(await (await w.fetch('https://example.org/ru/?style=sber')).text(),'NETWORK');
 assert.ok(w.stored.has('/ru/'));
 w.setNetwork(async()=>{throw Error('offline');});
 assert.equal(await (await w.fetch('https://example.org/ru/?style=minimal')).text(),'NETWORK');
 assert.equal(w.activated(),0);w.listeners.message({data:{type:'ACTIVATE_PORTFOLIO_UPDATE'}});assert.equal(w.activated(),1);
});
test('both manifests identify the same installable app with independent language entry points',()=>{
 const root=new URL('../../public/',import.meta.url),en=JSON.parse(fs.readFileSync(new URL('manifest.webmanifest',root))),ru=JSON.parse(fs.readFileSync(new URL('manifest-ru.webmanifest',root)));
 assert.equal(en.id,ru.id);assert.equal(en.start_url,'/');assert.equal(ru.start_url,'/ru/');assert.equal(en.display,'standalone');
 for(const [file,size] of [['icon-192.png',192],['icon-512.png',512],['apple-touch-icon.png',180]]){const bytes=fs.readFileSync(new URL(file,root));assert.equal(bytes.toString('ascii',1,4),'PNG');assert.equal(bytes.readUInt32BE(16),size);assert.equal(bytes.readUInt32BE(20),size);}
});
