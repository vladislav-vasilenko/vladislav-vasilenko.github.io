import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8');
function fixture({permission=true,managed=true}={}){
 const local={},tabs=new Map([[7,{id:7,url:'https://hh.ru/applicant/vacancy_response?vacancyId=123',active:false}]]),navigations=[],closed=[],observations=[];
 const chrome={runtime:{id:'test',onMessage:{addListener(){}}},permissions:{contains:async()=>permission},
  tabs:{create:async props=>{const tab={...props,id:99};tabs.set(99,tab);return tab;},get:async id=>tabs.get(id),remove:async id=>{closed.push(id);tabs.delete(id);},query:async()=>{throw Error('Auto-sync must not inspect user tabs');}},
  storage:{local:{get:async key=>key===null?{...local}:{[key]:local[key]},set:async values=>Object.assign(local,values),remove:async key=>delete local[key]},session:{get:async()=>({hh_workflow_worker:{id:'managed-worker',tab_id:7,managed}})}}};
 const activeJobs=new Set(),ctx=vm.createContext({chrome,activeJobs,URL,Set,Map,Error,Date,setTimeout,clearTimeout,LocalResumeService:{request:async(_path,data)=>{if(data.op==='hh_sync_targets')return {urls:[]};assert.equal(data.op,'observe');observations.push(data.snapshot);return {observations_added:1,messages_added:0};}}});
 vm.runInContext(source,ctx);
 ctx.navigate=async(id,url)=>{assert.notEqual(id,7,'never navigate the prepared form');tabs.set(id,{...tabs.get(id),url});navigations.push(url);};
 return {ctx,local,tabs,navigations,closed,observations,activeJobs};
}
test('background HH read uses a disposable tab and cleans up without touching the prepared form',async()=>{
 const f=fixture();f.ctx.wfCurrentSync=async(id,walk,options)=>{assert.equal(id,99);assert.equal(walk,true);assert.equal(options.automatic,true);return {messages_added:2};};
 const result=await f.ctx.wfAutomaticSync();assert.equal(result.state,'complete');assert.equal(result.messages_added,2);
 assert.deepEqual(f.closed,[99]);assert.deepEqual([...f.activeJobs],[]);assert.equal(f.tabs.get(7).url,'https://hh.ru/applicant/vacancy_response?vacancyId=123');
});
test('lost HH permission stops before any tab is opened',async()=>{
 const f=fixture({permission:false});await assert.rejects(()=>f.ctx.wfAutomaticSync(),/Разрешите доступ/);assert.equal(f.tabs.size,1);assert.deepEqual(f.navigations,[]);
});
test('CAPTCHA failure closes only the temporary tab and releases worker lock',async()=>{
 const f=fixture();f.ctx.wfCurrentSync=async()=>{throw Error('CAPTCHA');};await assert.rejects(()=>f.ctx.wfAutomaticSync(),/CAPTCHA/);assert.deepEqual(f.closed,[99]);assert.equal(f.activeJobs.size,0);assert.ok(f.tabs.has(7));
});
test('user-focused temporary tab stays open for inspection',async()=>{
 const f=fixture();f.ctx.wfCurrentSync=async()=>{f.tabs.get(99).active=true;return {};};await f.ctx.wfAutomaticSync();assert.deepEqual(f.closed,[]);assert.ok(f.tabs.has(99));
});
test('chat rotation eventually reads beyond the first six chats without querying user tabs',async()=>{
 const f=fixture(),threads=Array.from({length:8},(_,i)=>'https://hh.ru/chat/'+(100+i)),read=[];
 f.ctx.wfScript=async(id,files)=>{assert.deepEqual(Array.from(files),['hh-sync-core.js','hh-sync-content.js']);const url=f.tabs.get(id).url;read.push(url);return {source_url:url,records:[{vacancy_id:'hh_1',status:'unknown'}],thread_urls:url.includes('negotiations')?threads:[]};};
 await f.ctx.wfAutomaticSync();assert.deepEqual(read.slice(2),threads.slice(0,6));assert.equal(f.local.hh_auto_sync_cursor,6);read.length=0;
 await f.ctx.wfAutomaticSync();assert.deepEqual(read.slice(2),[...threads.slice(6),...threads.slice(0,4)]);assert.equal(f.local.hh_auto_sync_cursor,4);
});
test('unrecognized empty page is an actionable failure, never a successful empty sync',async()=>{
 const f=fixture();f.ctx.wfScript=async()=>({records:[],warning:'Не распознаны карточки'});await assert.rejects(()=>f.ctx.wfAutomaticSync(),/Не распознаны отклики HH/);assert.deepEqual(f.closed,[99]);
});
test('bounded sync persists progress and stops before the queue lease expires',async()=>{
 const f=fixture();let clock=0;f.ctx.Date={now:()=>clock};const navigate=f.ctx.navigate;
 f.ctx.navigate=async(...args)=>{clock+=25000;return navigate(...args);};
 f.ctx.wfScript=async id=>({source_url:f.tabs.get(id).url,records:[{vacancy_id:'hh_1',status:'unknown'}],thread_urls:Array.from({length:20},(_,i)=>'https://hh.ru/chat/'+i)});
 const result=await f.ctx.wfAutomaticSync();assert.equal(result.partial,true);assert.ok(result.threads_read<6);assert.ok(clock<180000);assert.ok(f.local.hh_auto_sync_cursor>0);assert.ok(result.warnings.some(w=>w.includes('лимит времени')));
});
test('managed worker advertises isolated-sync capability and records result once without executing a response',async()=>{
 const f=fixture();let next=0,receipts=0,reads=0;
 f.ctx.LocalResumeService.request=async(_path,data)=>{if(data.op==='next'){next++;assert.equal(data.auto_sync,true);return {command:{id:'auto-job',kind:'sync',payload:{automatic:true}}};}if(data.op==='result'){receipts++;assert.equal(data.result.state,'complete');return {ok:true};}throw Error('Unexpected operation');};
 f.ctx.wfAutomaticSync=async()=>{reads++;return {state:'complete'};};f.ctx.wfExecute=async()=>{throw Error('Background sync must never send');};
 await f.ctx.hhWorkflowPulse();assert.equal(next,1);assert.equal(reads,1);assert.equal(receipts,1);assert.equal(f.activeJobs.size,0);
});
test('previously connected manual HH tab also permits isolated sync when persistent HH access exists',async()=>{
 const f=fixture({managed:false});let advertised;
 f.ctx.LocalResumeService.request=async(_path,data)=>{assert.equal(data.op,'next');advertised=data.auto_sync;return {command:null};};
 await f.ctx.hhWorkflowPulse();assert.equal(advertised,true);assert.deepEqual(f.navigations,[]);
});


test('manual reading does not reload the current tab when traversal never left its document',async()=>{
 const f=fixture();f.ctx.chrome.tabs.query=async()=>[];
 f.ctx.wfScript=async()=>({records:[{vacancy_id:'hh_123',status:'viewed'}],thread_urls:[]});
 const result=await f.ctx.wfCurrentSync(7,true);assert.equal(result.observations_added,1);assert.equal(f.navigations.length,0);assert.equal(f.tabs.get(7).url,'https://hh.ru/applicant/vacancy_response?vacancyId=123');
});

test('an empty HH queue on startup never resolves or opens the permanent negotiations tab',async()=>{
 const f=fixture();let polls=0;
 f.ctx.wfWorkerIdentity=async()=>({id:'managed-worker',managed:true});
 f.ctx.wfResolveWorker=async()=>{throw Error('Idle worker must not open a tab');};
 f.ctx.LocalResumeService.request=async(path,p)=>{assert.equal(p.op,'next');polls++;return {command:null};};
 await f.ctx.hhWorkflowPulse();await f.ctx.hhWorkflowPulse();assert.equal(polls,2);assert.equal(f.tabs.size,1);assert.equal(f.navigations.length,0);
});
test('automatic sync claims one real task and uses only its disposable tab',async()=>{
 const f=fixture();let finished;
 f.ctx.wfWorkerIdentity=async()=>({id:'managed-worker',managed:true});f.ctx.wfResolveWorker=async()=>{throw Error('No permanent tab needed');};
 f.ctx.wfCurrentSync=async()=>({messages_added:0});f.ctx.LocalResumeService.request=async(path,p)=>{if(p.op==='next')return {command:{id:'auto-1',kind:'sync',payload:{automatic:true}}};if(p.op==='result')finished=p.result;return {ok:true};};
 await f.ctx.hhWorkflowPulse();assert.equal(finished.state,'complete');assert.deepEqual(f.closed,[99]);assert.equal(f.activeJobs.size,0);
});
test('a stalled background read releases the disposable tab after the deadline',async()=>{
 const f=fixture();f.ctx.wfCurrentSync=()=>new Promise(()=>{});f.ctx.setTimeout=callback=>{queueMicrotask(callback);return 1;};f.ctx.clearTimeout=()=>{};
 await assert.rejects(f.ctx.wfAutomaticSync(),/Истекло время/);assert.deepEqual(f.closed,[99]);assert.equal(f.activeJobs.size,0);
});

test('HH inbox polling never releases a tab lock held by a different reader',async()=>{
 const f=fixture();f.activeJobs.add(7);f.ctx.wfWorkerIdentity=async()=>({id:'managed-worker',managed:true,tab_id:7});
 await f.ctx.hhWorkflowPulse();assert.equal(f.activeJobs.has(7),true);
});
