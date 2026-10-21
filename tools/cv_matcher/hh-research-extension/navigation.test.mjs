import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=file=>fs.readFileSync(new URL(file,import.meta.url),'utf8');
function fixture(target='https://hh.ru/search/vacancy?resume=cv&page=1',options={}){
 const timers=new Map(),listeners=new Set();let serial=0,tab={url:target,status:'loading'},read={url:target,ready:true,text:true},stopped=false,resolveUpdate;
 const chrome={tabs:{get:async()=>tab,onUpdated:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},update:()=>options.pendingUpdate?new Promise(r=>resolveUpdate=r):Promise.resolve({})},scripting:{executeScript:async()=>options.pendingRead?new Promise(()=>{}):[{result:read}]}};
 const c=vm.createContext({URL,Promise,chrome,setTimeout:(f,ms)=>{timers.set(++serial,{f,ms});return serial;},clearTimeout:id=>timers.delete(id)});
 for(const file of ['hh-crawl-core.js','board-core.js','board-adapters.js','browser-navigation.js'])vm.runInContext(source(file),c);
 let state='pending',error;const task=c.navigate(1,target,{shouldStop:()=>stopped,...options}).then(()=>state='complete',e=>{state='failed';error=e;});
 const flush=()=>new Promise(r=>setImmediate(r));
 return {c,task,timers,listeners,flush,get state(){return state;},get error(){return error;},set tab(v){tab=v;},set read(v){read=v;},stop(){stopped=true;},commit(){resolveUpdate?.({});},event(){for(const f of [...listeners])f(1,{status:'complete'});},async tick(ms=400){const entry=[...timers].find(([,v])=>v.ms===ms);assert.ok(entry,'scheduled timer '+ms);timers.delete(entry[0]);entry[1].f();await flush();}};
}
test('HH readable listing finishes while tab is still loading, without waiting for analytics',async()=>{
 const f=fixture();await f.task;assert.equal(f.state,'complete');assert.equal(f.timers.size,0);assert.equal(f.listeners.size,0);
});
test('HH readiness tolerates tracking but never another page, filter, CV, old or foreign document',async()=>{
 const url='https://hh.ru/search/vacancy?resume=cv&area=1&page=1',f=fixture(url,{pendingUpdate:true});
 for(const wrong of [url.replace('page=1','page=0'),url.replace('cv','other'),url.replace('area=1','area=2'),'https://evil.test/search/vacancy']){
  f.tab={url:wrong,status:'complete'};f.event();await f.flush();assert.equal(f.state,'pending');
 }
 f.tab={url,status:'loading',pendingUrl:url};f.commit();await f.flush();assert.equal(f.state,'pending');
 f.tab={url:url+'&search_session_id=changed',status:'loading'};f.read={url:url+'&hhtmFrom=search',ready:true,text:true};await f.tick();await f.task;assert.equal(f.state,'complete');
});
test('company DOM readiness verifies exact vacancy identity and readiness',async()=>{
 const url='https://www.tbank.ru/career/it/vacancy/moscow/ml/83aea7ca-a0ae-4414-8037-6cba82b2dc22/',f=fixture(url,{pendingUpdate:true});
 f.tab={url,status:'loading'};f.read={url:url.replace('83aea7ca','93aea7ca'),ready:true,text:true};f.commit();await f.flush();assert.equal(f.state,'pending');
 f.read={url,ready:false,text:true};await f.tick();assert.equal(f.state,'pending');
 f.read={url,ready:true,text:true};await f.tick();await f.task;assert.equal(f.state,'complete');
});
test('already complete expected URL needs no further complete event',async()=>{
 const f=fixture(undefined,{pendingUpdate:true});f.tab={url:'https://hh.ru/search/vacancy?resume=cv&page=1',status:'complete'};f.commit();await f.task;assert.equal(f.state,'complete');
});
test('readReady=false still requires complete committed expected URL',async()=>{
 const f=fixture(undefined,{readReady:false});await f.flush();assert.equal(f.state,'pending');f.tab={url:'https://hh.ru/search/vacancy?resume=cv&page=1',status:'complete'};f.event();await f.task;assert.equal(f.state,'complete');
});
test('stop interrupts a pending browser update or script and releases timers/listeners',async()=>{
 for(const options of [{pendingUpdate:true},{pendingRead:true}]){
  const f=fixture(undefined,options);await f.flush();f.stop();await f.tick();await f.task;assert.equal(f.state,'failed');assert.match(f.error.message,/остановлен/);assert.equal(f.listeners.size,0);assert.equal(f.timers.size,0);
 }
});
test('navigation timeout is bounded and releases resources',async()=>{
 const f=fixture(undefined,{pendingUpdate:true,timeoutMs:1234});await f.tick(1234);await f.task;assert.equal(f.state,'failed');assert.match(f.error.message,/не готова/);assert.equal(f.listeners.size,0);assert.equal(f.timers.size,0);
});
test('HH challenge redirect stops navigation; it is never a successful empty result',async()=>{
 const f=fixture(undefined,{pendingUpdate:true});f.tab={url:'https://hh.ru/account/login',status:'loading'};f.commit();await f.task;assert.equal(f.state,'failed');assert.match(f.error.message,/требует вход/);
});
test('DOM probe recognizes HH content even before readyState completes and rejects empty shells',async()=>{
 let probe;const f=fixture(undefined,{pendingUpdate:true});f.c.chrome.scripting.executeScript=async args=>{probe=args.func;return [{result:{ready:false}}];};f.commit();await f.flush();
 const evaluate=(path,selector,readyState='loading')=>vm.runInNewContext('('+probe.toString()+')()',{location:{href:'https://hh.ru'+path,hostname:'hh.ru',pathname:path},document:{readyState,body:{innerText:'Visible HH text'},querySelector:s=>s.includes(selector)?{}:null}});
 assert.equal(evaluate('/search/vacancy','vacancy-serp__vacancy-body').ready,true);
 assert.equal(evaluate('/vacancy/123','vacancy-description').ready,true);
 assert.equal(evaluate('/vacancy/123','vacancy-archive-message').ready,true);
 assert.equal(evaluate('/search/vacancy','nonexistent').ready,false);
 f.stop();await f.tick();await f.task;
});

test('Yandex legacy single ML profession redirects to verified canonical listing without loosening filters',async()=>{
 const old='https://yandex.ru/jobs/vacancies?professions=ml-developer',correct='https://yandex.ru/jobs/professions/ml-developer';
 const f=fixture(old,{pendingUpdate:true});f.tab={url:correct,status:'complete'};f.commit();await f.task;assert.equal(f.state,'complete');
 for(const wrong of ['https://yandex.ru/jobs/professions/backend-developer','https://yandex.ru/jobs/vacancies','https://yandex.com/jobs/professions/ml-developer',correct+'?city=other']){
  const f=fixture(old,{pendingUpdate:true});f.tab={url:wrong,status:'complete'};f.commit();await f.flush();assert.equal(f.state,'pending');f.stop();await f.tick();await f.task;
 }
});

test('Ozon query plans are a union of separate searches and preserve employer filters',()=>{
 const f=fixture();const urls=f.c.JobBoardAdapters.searchURLs('https://ozon.tech/vacancies/?levels=Senior',['ML','PyTorch','ML']);assert.equal(urls.length,2);assert.equal(new URL(urls[0]).searchParams.get('search'),'ML');assert.equal(new URL(urls[1]).searchParams.get('search'),'PyTorch');assert.ok(urls.every(u=>new URL(u).searchParams.get('levels')==='Senior'));
 assert.equal(f.c.JobBoardAdapters.searchURLs('https://ozon.tech/vacancies/?search=LLM',['ML']).length,1);assert.equal(f.c.JobBoardAdapters.searchURLs('https://career.avito.com/vacancies/',['ML']).length,1);
});
