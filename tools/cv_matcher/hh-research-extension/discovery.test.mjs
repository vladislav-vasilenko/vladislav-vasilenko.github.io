import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const code=fs.readFileSync(new URL('discovery-worker.js',import.meta.url),'utf8');
const hh='https://hh.ru/vacancy/7',yandex='https://yandex.ru/jobs/vacancies/ml-12345';
function fixture({url=hh,permission=true,blocked=false,quality='full'}={}){
 const calls=[],local={vacancies:[]};let current=url;
 const id=url===hh?'hh_7':'yandex_12345',row={id,link:url,title:'Research ML',description:'PyTorch '.repeat(40),description_quality:quality,archived:false};
 const c=vm.createContext({URL,Set,Error,Promise,setTimeout:(fn,ms)=>ms>=10000?1:fn(),clearTimeout:()=>{},setInterval:()=>1,clearInterval:()=>{},workflowCall:async()=>({stop:false}),activeJobs:new Set(),JobBoards:{identity:u=>u===hh?{id:'hh_7'}:u===yandex?{id:'yandex_12345'}:null,canonicalRows:async r=>r},ResearchSearch:{mergeVacancies:(a,b)=>b},ArchiveSyncCore:{record:async(kind,id,data)=>({kind,id,data})},chrome:{tabs:{get:async()=>({url:current}),create:async()=>{calls.push('create-tab');return {id:2};},remove:async()=>calls.push('close-tab'),update:async()=>calls.push('show-tab')},permissions:{contains:async()=>permission},storage:{local:{get:async()=>local,set:async x=>Object.assign(local,x)}}},wfScript:async()=>blocked?{blocked:true,warning:'CAPTCHA'}:{vacancies:[row]},navigate:async(id,u)=>{current=u;calls.push('navigate:'+u);},LocalResumeService:{request:async(path,data)=>{calls.push('saved:'+path);return {accepted:data.records,rejected:[]};}},HHCrawl:{limits:o=>o},JobBoardAdapters:{resolve:()=>({id:'yandex'}),sameSource:(a,b)=>new URL(a).origin===new URL(b).origin},runHHCrawl:async()=>{local.vacancies=[row];calls.push('crawl');return {state:'complete',ids:[id]};},runBoardCrawl:async()=>{local.vacancies=[row];calls.push('crawl');return {state:'partial',ids:[id],note:'Loaded subset'};}});
 vm.runInContext(fs.readFileSync(new URL('collection-storage.js',import.meta.url),'utf8'),c);vm.runInContext(code,c);return {c,calls,local};
}
test('single capture commits a full description to SQLite without model calls',async()=>{
 const {c,calls}=fixture();const result=await c.captureOne(1,hh);assert.equal(result.state,'complete');assert.equal(result.ids[0],'hh_7');assert.ok(calls.includes('saved:/archive/sync'));
});
test('challenge or ambiguous content cannot become a full vacancy',async()=>{
 const blocked=fixture({blocked:true});await assert.rejects(()=>blocked.c.captureOne(1,hh),/CAPTCHA/);assert.equal(blocked.calls.length,0);
 const review=fixture({quality:'needs_review'});assert.equal((await review.c.captureOne(1,hh)).state,'needs_input');
});
test('company collection requires explicit host permission and never navigates on refusal',async()=>{
 const {c,calls}=fixture({url:yandex,permission:false});const r=await c.wfCollect(1,{kind:'collect',payload:{source_url:yandex}});assert.equal(r.state,'needs_input');assert.equal(calls.length,0);
});
test('scheduled source collection is bounded, preserves partial coverage and syncs before receipt',async()=>{
 const {c,calls}=fixture({url:yandex});const r=await c.wfCollect(1,{kind:'discover',payload:{source_url:yandex,options:{pages:2,details:20}}});assert.equal(r.coverage,'partial');assert.equal(r.ids[0],'yandex_12345');assert.equal(r.warnings.length,1);assert.ok(calls.indexOf('crawl')<calls.indexOf('saved:/archive/sync'));assert.equal(calls.at(-1),'close-tab');
});
test('arbitrary hosts, credentials and non-TLS capture URLs are rejected',()=>{
 const {c}=fixture();for(const u of ['http://127.0.0.1/x','https://evil.test/x','https://u:p@hh.ru/vacancy/1'])assert.throws(()=>c.collectionURL(u));
});

test('company URL queue runs independently of a managed HH tab',async()=>{
 const {c,local}=fixture({url:yandex});const calls=[];let issued=false;
 c.crypto={randomUUID:()=> 'collect-worker'};c.chrome.storage.local.remove=async k=>delete local[k];c.wfResolveWorker=async()=>{throw Error('HH must not be required for company capture');};
 c.workflowCall=async p=>{calls.push(p);if(p.op==='next'){if(issued)return {command:null};issued=true;return {command:{id:'cmd',kind:'collect',payload:{source_url:yandex}}};}return {ok:true};};
 await c.collectionPulse();assert.deepEqual(Array.from(calls[0].kinds),['discover','collect']);assert.equal(calls.at(-1).result.state,'complete');assert.equal(local.collection_receipt_cmd,undefined);
});
test('lost acknowledgment replays only a durable capture receipt',async()=>{
 const {c,calls,local}=fixture({url:yandex});let issued=false,fail=true,receipts=0;
 c.crypto={randomUUID:()=> 'collect-worker'};c.chrome.storage.local.remove=async k=>delete local[k];
 c.workflowCall=async p=>{if(p.op==='task_progress')return {ok:true};if(p.op==='task_control_status')return {stop:false};if(p.op==='next'){if(issued)return {command:null};issued=true;return {command:{id:'cmd',kind:'collect',payload:{source_url:yandex}}};}receipts++;if(fail){fail=false;throw Error('Ack lost');}return {ok:true};};
 await c.collectionPulse();assert.ok(local.collection_receipt_cmd);await c.collectionPulse();assert.equal(local.collection_receipt_cmd,undefined);assert.equal(receipts,2);assert.equal(calls.filter(x=>x==='create-tab').length,1);
});

test('single company URL reuses a loaded exact vacancy without navigation or a new tab',async()=>{
 const {c,calls}=fixture({url:yandex});c.chrome.tabs.query=async()=>[{id:9,status:'complete',url:yandex}];
 const r=await c.wfCollect(undefined,{kind:'collect',payload:{source_url:yandex}});assert.equal(r.state,'complete');assert.ok(!calls.includes('create-tab'));assert.ok(!calls.some(s=>s.startsWith('navigate:')));assert.ok(calls.includes('saved:/archive/sync'));
});

test('a slow or challenged company page stays open for the owner and does not masquerade as collected',async()=>{
 const {c,calls}=fixture({url:yandex});c.navigate=async()=>{throw Error('Страница не загрузилась за 60 секунд.');};
 const r=await c.wfCollect(undefined,{kind:'collect',payload:{source_url:yandex}});assert.equal(r.state,'needs_input');assert.match(r.note,/оставлена открытой/);assert.ok(!calls.includes('close-tab'));assert.ok(!calls.includes('saved:/archive/sync'));
});

test('a backend pause before collection prevents navigation and scraping',async()=>{
 const {c,calls}=fixture({url:yandex});c.workflowCall=async()=>({stop:true,action:'pause'});
 const result=await c.wfCollect(undefined,{id:'paused',worker_id:'fixture-worker',kind:'discover',payload:{source_url:yandex,options:{pages:2,details:20}}});
 assert.equal(result.state,'complete');assert.equal(result.ids.length,0);assert.equal(calls.length,0);
});
test('running crawl polls controls, stops cooperatively and saves partial reads before its receipt',async()=>{
 const {c,calls,local}=fixture({url:yandex});let poll,cleared=false,checks=0;
 c.setInterval=fn=>{poll=fn;return 9;};c.clearInterval=id=>{assert.equal(id,9);cleared=true;};
 c.workflowCall=async()=>({stop:++checks>1,action:checks>1?'cancel':''});
 c.runBoardCrawl=async(tab,url,adapter,limits,run)=>{assert.equal(run.stop,false);await poll();assert.equal(run.stop,true);local.vacancies=[{id:'yandex_12345',link:yandex,title:'ML'}];return {state:'stopped',ids:['yandex_12345']};};
 const result=await c.wfCollect(undefined,{id:'running',worker_id:'fixture-worker',kind:'discover',payload:{source_url:yandex,options:{pages:2,details:20}}});
 assert.equal(result.coverage,'stopped');assert.ok(calls.includes('saved:/archive/sync'));assert.equal(cleared,true);
});

test('scheduled progress reports real crawl counters without DOM text and includes the final snapshot in receipt',async()=>{
 const {c}=fixture({url:yandex});const reports=[];
 c.workflowCall=async p=>{if(p.op==='task_progress')reports.push(p);return {stop:false,ok:true};};
 c.runBoardCrawl=async(tab,url,adapter,limits,run)=>{
  await run.onProgress({phase:'listing',discovered:12,pages:1});
  await run.onProgress({phase:'descriptions',discovered:12,planned:8,loaded:3,failed:2,reused:4,current_title:'Do not send arbitrary document content'});
  return {state:'partial',discovered:12,planned:8,loaded:3,failed:2,reused:4,ids:['yandex_12345']};
 };
 const result=await c.wfCollect(undefined,{id:'progress-command',worker_id:'progress-reader',kind:'discover',payload:{source_url:yandex,options:{pages:2,details:20}}});
 assert.ok(reports.length>=2);const first=reports[0],last=reports.at(-1);assert.equal(first.progress.planned,null);assert.equal(last.progress.planned,8);assert.equal(last.progress.loaded,3);assert.equal(last.progress.failed,2);assert.equal(last.progress.reused,4);assert.equal(last.progress.current_title,undefined);assert.ok(last.sequence>first.sequence);assert.equal(result.progress.loaded,3);
});


test('single capture bypasses a full local cache and still commits to SQLite',async()=>{
 const {c,calls}=fixture({url:yandex});c.chrome.storage.local.set=async()=>{throw Error('QUOTA_BYTES');};
 assert.equal((await c.captureOne(1,yandex)).state,'complete');assert.ok(calls.includes('saved:/archive/sync'));
});
test('scheduled reads stream to SQLite and receipt uses session when local quota is exhausted',async()=>{
 const {c,local,calls}=fixture({url:yandex});let issued=false,saved=0;const session={};
 c.crypto={randomUUID:()=> 'quota-worker'};
 c.chrome.storage.local.set=async()=>{throw Error('QUOTA_BYTES');};c.chrome.storage.local.remove=async k=>delete local[k];
 c.chrome.storage.session={get:async()=>session,set:async p=>Object.assign(session,p),remove:async k=>delete session[k]};
 c.runBoardCrawl=async(tab,url,adapter,limits,job)=>{assert.equal(typeof job.saveVacancies,'function');await job.saveVacancies([{id:'yandex_12345',link:yandex,title:'Research',description_quality:'full'}]);saved++;return {state:'complete',ids:['yandex_12345']};};
 c.workflowCall=async p=>{if(p.op==='next'){if(issued)return {command:null};issued=true;return {command:{id:'quota',kind:'discover',payload:{source_url:yandex,options:{}}}};}if(p.op==='result'){assert.ok(session.collection_receipt_quota);assert.equal(p.result.state,'complete');}return {ok:true,stop:false};};
 await c.collectionPulse();assert.equal(saved,1);assert.ok(calls.includes('saved:/archive/sync'));assert.equal(session.collection_receipt_quota,undefined);
});

test('HH service collection uses its own read tab and does not wait for unrelated busy tabs',async()=>{
 const {c,calls,local}=fixture();c.activeJobs.add(44);let issued=false;
 c.crypto={randomUUID:()=> 'reader'};c.chrome.storage.local.remove=async key=>delete local[key];c.wfResolveWorker=async()=>{throw Error('Must not touch a prepared HH form');};
 c.workflowCall=async p=>{if(p.op==='next'){if(issued)return {command:null};issued=true;return {command:{id:'isolated-hh',kind:'collect',payload:{source_url:hh}}};}return {ok:true,stop:false};};
 await c.collectionPulse();assert.ok(calls.includes('create-tab'));assert.ok(calls.includes('close-tab'));assert.equal(c.activeJobs.has(44),true);assert.ok(calls.includes('saved:/archive/sync'));
});
