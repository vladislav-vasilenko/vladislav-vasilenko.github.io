import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
function connection({enabled=false,permission=false,session={},tabs={}}={}){
 const local={hh_managed_enabled:enabled},created=[],listeners=[];
 const chrome={runtime:{id:'fixture',getURL:p=>'chrome-extension://fixture/'+p,onMessage:{addListener:f=>listeners.push(f)}},permissions:{contains:async({origins})=>origins[0]==='https://hh.ru/*'&&permission},scripting:{},storage:{local:{get:async()=>local,set:async d=>Object.assign(local,d)},session:{get:async()=>session,set:async d=>Object.assign(session,d),remove:async k=>delete session[k]}},tabs:{get:async id=>{if(!tabs[id])throw Error('Closed');return tabs[id];},create:async options=>{created.push(options);const id=created.length+10;tabs[id]={url:options.url};return {id};}}};
 const ctx=vm.createContext({chrome,URL,Date,setTimeout,clearTimeout,crypto:{randomUUID:()=> 'worker-generated'},LocalResumeService:{request:async()=>({ok:true})},hhWorkflowPulse(){}});vm.runInContext(fs.readFileSync(new URL('hh-connection.js',import.meta.url),'utf8'),ctx);
 return {resolve:()=>ctx.wfResolveWorker(),inspect:()=>ctx.inspectWorker(),ctx,chrome,created,session,local,tabs};
}
test('managed HH worker only creates a tab after both opt-in and granted site access',async()=>{
 let c=connection();assert.equal(await c.resolve(),null);assert.equal(c.created.length,0);
 c=connection({enabled:true});await assert.rejects(c.resolve(),/Доступ к HH отключён/);assert.equal(c.created.length,0);
 c=connection({enabled:true,permission:true});const first=await c.resolve(),second=await c.resolve();assert.equal(first.tab_id,second.tab_id);assert.equal(c.created.length,1);assert.equal(c.created[0].active,false);assert.equal(c.created[0].url,'https://hh.ru/applicant/negotiations');
 delete c.tabs[first.tab_id];const recreated=await c.resolve();assert.notEqual(first.tab_id,recreated.tab_id);assert.equal(first.id,recreated.id);
});
test('manual activeTab worker is retained without expanding HH permissions or creating tabs',async()=>{
 const session={hh_workflow_worker:{id:'manual',tab_id:5}},c=connection({session});assert.equal((await c.resolve()).id,'manual');assert.equal(c.created.length,0);
});

test('complete background worker boots and answers setup page messages without a missing-handler dead end',async()=>{
 const handlers=[],loaded=[],local={},session={};
 const chrome={runtime:{id:'fixture',getURL:p=>'chrome-extension://fixture/'+p,onMessage:{addListener:f=>handlers.push(f)},onStartup:{addListener(){}},onInstalled:{addListener(){}}},storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,local[k]])),set:async d=>Object.assign(local,d)},session:{get:async()=>session,set:async d=>Object.assign(session,d)},onChanged:{addListener(){}}},permissions:{contains:async()=>false},scripting:{getRegisteredContentScripts:async()=>[]},tabs:{onUpdated:{addListener(){},removeListener(){}},query:async()=>[]},alarms:{create(){},onAlarm:{addListener(){}}}};
 const ctx=vm.createContext({chrome,URL,Date,Set,Map,TextEncoder,Uint8Array,AbortSignal,setTimeout,clearTimeout,crypto:{randomUUID:()=> 'fixture-worker'}});ctx.importScripts=(...files)=>{for(const name of files){loaded.push(name);vm.runInContext(fs.readFileSync(new URL(name,import.meta.url),'utf8'),ctx,{filename:name});}};
 ctx.importScripts('background.js');assert.ok(loaded.includes('hh-connection.js'));
 const sender={id:'fixture',url:'chrome-extension://fixture/setup.html',tab:{id:42,url:'chrome-extension://fixture/setup.html'}};
 const result=await new Promise((resolve,reject)=>{let accepted=0;for(const handler of handlers)if(handler({type:'connection_status'},sender,resolve)===true)accepted++;if(!accepted)reject(Error('No setup listener'));});
 assert.equal(result.ok,true);assert.equal(result.enabled,false);assert.equal(result.worker.exists,false);assert.ok(result.error.includes('подключите локальный сервис'));
});


test('HH connection probes an authenticated DOM even while analytics keep the tab loading',async()=>{
 const c=connection({session:{hh_workflow_worker:{id:'w',tab_id:5,managed:true}},tabs:{5:{id:5,url:'https://hh.ru/applicant/negotiations',status:'loading'}}});
 c.chrome.scripting.executeScript=async()=>[{result:{state:'authenticated',url:'https://hh.ru/applicant/negotiations'}}];
 const observed=await c.inspect();assert.equal(observed.exists,true);assert.equal(observed.state,'authenticated');
});
test('HH loading never masks a visible login or CAPTCHA and never trusts a foreign probe',async()=>{
 for(const state of ['login','captcha']){
  const c=connection({session:{hh_workflow_worker:{id:'w',tab_id:5}},tabs:{5:{id:5,url:'https://hh.ru/account/login',status:'loading'}}});c.chrome.scripting.executeScript=async()=>[{result:{state,url:'https://hh.ru/account/login'}}];assert.equal((await c.inspect()).state,state);
 }
 const c=connection({session:{hh_workflow_worker:{id:'w',tab_id:5}},tabs:{5:{id:5,url:'https://hh.ru/',status:'loading'}}});c.chrome.scripting.executeScript=async()=>[{result:{state:'authenticated',url:'https://evil.test/'}}];assert.notEqual((await c.inspect()).state,'authenticated');
});
test('pending HH tabs are reused without constructing URL(undefined) or opening duplicate workers',async()=>{
 const session={hh_workflow_worker:{id:'w',tab_id:5,managed:true}},c=connection({enabled:true,permission:true,session,tabs:{5:{id:5,pendingUrl:'https://hh.ru/applicant/negotiations',status:'loading'}}});
 assert.equal((await c.resolve()).tab_id,5);assert.equal(c.created.length,0);assert.equal((await c.inspect()).state,'loading');
 const empty=connection({enabled:true,permission:true});const workers=await Promise.all([empty.resolve(),empty.resolve(),empty.resolve()]);assert.equal(empty.created.length,1);assert.ok(workers.every(w=>w.tab_id===workers[0].tab_id));
});
test('an unresolved loading state becomes actionable after 30 seconds rather than staying loading forever',async()=>{
 const c=connection({session:{hh_workflow_worker:{id:'w',tab_id:5},hh_worker_loading_since:{tab_id:5,at:Date.now()-31000}},tabs:{5:{id:5,url:'https://hh.ru/',status:'loading'}}});
 c.chrome.scripting.executeScript=async()=>[{result:{state:'loading',url:'https://hh.ru/'}}];assert.equal((await c.inspect()).state,'loading_stalled');
 c.chrome.scripting.executeScript=async()=>[{result:{state:'authenticated',url:'https://hh.ru/applicant/negotiations'}}];assert.equal((await c.inspect()).state,'authenticated');assert.equal(c.session.hh_worker_loading_since,undefined);
});
test('HH worker waits for a committed document, accepts DOM-ready loading and rejects a different site clearly',async()=>{
 const c=connection();let reads=0;c.ctx.setTimeout=f=>{queueMicrotask(f);return 1;};c.chrome.tabs.get=async()=>++reads<3?{pendingUrl:'https://hh.ru/applicant/negotiations',status:'loading'}:{url:'https://hh.ru/applicant/negotiations',status:'loading'};
 assert.equal((await c.ctx.waitForHHWorker(5)).url,'https://hh.ru/applicant/negotiations');assert.equal(reads,3);
 c.chrome.tabs.get=async()=>({url:'https://example.com'});await assert.rejects(c.ctx.waitForHHWorker(5),/другой сайт/);
 c.chrome.tabs.get=async()=>({status:'loading'});await assert.rejects(c.ctx.waitForHHWorker(5),/ещё не получила адрес/);
});


test('worker does not accept the old HH document during a pending transition to another site',async()=>{
 const c=connection({session:{hh_workflow_worker:{id:'w',tab_id:5}},tabs:{5:{id:5,url:'https://hh.ru/applicant/negotiations',pendingUrl:'https://example.com',status:'loading'}}});
 assert.equal((await c.inspect()).exists,false);await assert.rejects(c.ctx.waitForHHWorker(5),/другой сайт/);
});
function pageProbe(kind){
 const node={innerText:kind==='denied'?'Доступ ограничен':'',getBoundingClientRect:()=>({width:100,height:30})};
 const document={readyState:'loading',querySelectorAll:s=>{
  if(s==='h1')return kind==='denied'?[node]:[];
  if(s.includes('captcha'))return kind==='captcha'?[node]:[];
  if(s.includes('password'))return kind==='login'?[node]:[];
  if(s.includes('applicant/resumes'))return kind==='profile'?[node]:[];
  if(s.includes('negotiations-item'))return kind==='negotiations'?[node]:[];
  return [];
 }};
 return vm.runInNewContext(fs.readFileSync(new URL('hh-connection-probe.js',import.meta.url),'utf8'),{document,location:new URL('https://hh.ru/applicant/negotiations'),getComputedStyle:()=>({display:'block',visibility:'visible'})});
}
test('actual connection probe recognizes usable HH content while readyState is loading, preserving access challenges',()=>{
 for(const kind of ['profile','negotiations'])assert.equal(pageProbe(kind).state,'authenticated');
 for(const [kind,state] of [['captcha','captcha'],['denied','captcha'],['login','login'],['empty','loading']])assert.equal(pageProbe(kind).state,state);
});

test('idle managed worker identity polls without opening negotiations or any tab',async()=>{
 const f=connection({enabled:true,permission:true});const first=await f.ctx.wfWorkerIdentity(),second=await f.ctx.wfWorkerIdentity();
 assert.equal(first.id,second.id);assert.equal(first.tab_id,undefined);assert.equal(f.created.length,0);
});
