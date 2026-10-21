import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import {webcrypto,createHash} from 'node:crypto';
const id='a'.repeat(38),cv=(text='Old research',date='2026-10-14T10:00:00Z')=>({id,title:'Research CV',source_type:'hh',content_hash:text,quality:'full',checked_at:date,sections:[{key:'experience',heading:'Опыт',text}]}),job=(text='Complete job',date='2026-10-14T10:00:00Z')=>({id:'hh_1',title:'Research',company:'Sber',link:'https://hh.ru/vacancy/1',description:text,description_quality:'full',collected_at:date});
function core(){const c=vm.createContext({URL,Date,Map,Set,TextEncoder,Uint8Array,crypto:webcrypto});for(const f of ['core.js','archive-sync-core.js'])vm.runInContext(fs.readFileSync(new URL(f,import.meta.url),'utf8'),c);return c.ArchiveSyncCore;}
test('archive envelope has stable Unicode digests and sends only allowed fields',async()=>{
 const api=core(),r=await api.record('resume',id,{...cv('Опыт PyTorch 🧠'),OPENAI_API_KEY:'SECRET',sections:[...cv().sections,{key:'contacts',text:'PRIVATE'}]});
 assert.ok(!JSON.stringify(r).includes('SECRET'));assert.ok(!JSON.stringify(r).includes('PRIVATE'));
 const expected=JSON.stringify({checked_at:'2026-10-14T10:00:00Z',content_hash:'Опыт PyTorch 🧠',id,quality:'full',sections:[{heading:'Опыт',key:'experience',text:'Old research'}],source_type:'hh',title:'Research CV'});
 assert.equal(r.digest,createHash('sha256').update(expected).digest('hex'));
 assert.ok(api.batches(Array.from({length:205},()=>r)).every(b=>b.length<=100));
});
test('restore merges sources and never replaces a newer complete server document with an older browser copy',()=>{
 const api=core(),current={resume_bundle:{primary_id:id,resumes:[cv('Browser','2026-10-14T10:00:00Z')]},vacancies:[job('Old browser','2026-10-14T10:00:00Z')]};
 const backup={resume_bundle:{primary_id:'other',resumes:[cv('New archive','2026-10-14T12:00:00Z')]},vacancies:[job('New archive job','2026-10-14T12:00:00Z')]};
 const result=api.restore(current,backup);assert.equal(result.resume_bundle.primary_id,id);assert.equal(result.resume_bundle.resumes[0].sections[0].text,'New archive');assert.equal(result.vacancies[0].description,'New archive job');
});
function worker({enabled=false,fail=false,onBatch=null}={}){
 const storage={archive_enabled:enabled,resume_bundle:{primary_id:id,resumes:[cv()]},vacancies:[job()],ranking_goal:'DiT'},handlers=[],listeners=[],startup=[],alarms=[],requests=[],manifest={};let offline=fail;
 const area={get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,structuredClone(storage[k])])),set:async data=>{const changes={};for(const [k,value] of Object.entries(data)){changes[k]={oldValue:structuredClone(storage[k]),newValue:structuredClone(value)};storage[k]=structuredClone(value);}queueMicrotask(()=>listeners.forEach(f=>f(changes,'local')));}};
 const chrome={runtime:{id:'fixture',onMessage:{addListener:f=>handlers.push(f)},onStartup:{addListener:f=>startup.push(f)}},storage:{local:area,onChanged:{addListener:f=>listeners.push(f)}},alarms:{create:()=>{},onAlarm:{addListener:f=>alarms.push(f)}},tabs:{create:async()=>{}}};
 const ctx=vm.createContext({chrome,URL,Date,Map,Set,TextEncoder,Uint8Array,crypto:webcrypto,setTimeout,clearTimeout,AbortSignal});ctx.importScripts=(...files)=>files.forEach(file=>vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),ctx));ctx.importScripts('core.js','archive-sync.js');
 ctx.LocalResumeService={request:async(path,body)=>{requests.push({path,body:structuredClone(body)});if(offline)throw Error('Server offline');if(path==='/archive/manifest')return {records:{...manifest}};if(path==='/archive/sync'){if(onBatch)await onBatch(area);for(const r of body.records)manifest[r.kind+':'+r.id]=r.digest;return {accepted:body.records.map(({kind,id,digest})=>({kind,id,digest})),rejected:[]};}throw Error('Unexpected route');}};
 const flush=async()=>{for(let i=0;i<100;i++){await vm.runInContext('archiveQueue',ctx);await new Promise(r=>setImmediate(r));if(!vm.runInContext('archiveRunning',ctx))return;}throw Error('Archive did not settle');};
 const send=message=>new Promise(resolve=>handlers.forEach(h=>h({type:'archive_sync_now',...message},{id:'fixture'},resolve)));
 return {storage,requests,area,send,flush,startup,alarms,setOffline:v=>offline=v};
}
test('first sync archives all current records, unchanged repeat sends no data and never invokes model endpoints',async()=>{
 const w=worker();const first=await w.send({auto:true});assert.equal(first.ok,true);assert.equal(first.sent,3);await w.flush();
 assert.equal(w.storage.archive_outbox.length,0);const before=w.requests.filter(r=>r.path==='/archive/sync').length;
 const second=await w.send({auto:true});assert.equal(second.sent,0);assert.equal(w.requests.filter(r=>r.path==='/archive/sync').length,before);assert.ok(w.requests.every(r=>r.path.startsWith('/archive/')));
});
test('offline edits and deletion retain version snapshots until a successful retry acknowledges them',async()=>{
 const w=worker({enabled:true});await w.send({auto:true});await w.flush();w.setOffline(true);
 await w.area.set({resume_bundle:{primary_id:id,resumes:[cv('Offline edit','2026-10-14T11:00:00Z')]}});await w.flush();
 assert.ok(w.storage.archive_outbox.some(r=>r.data.sections[0].text==='Offline edit'));
 await w.area.set({resume_bundle:{primary_id:id,resumes:[]}});await w.flush();assert.ok(w.storage.archive_outbox.length>=2);assert.equal(w.storage.archive_pending,true);
 w.setOffline(false);const result=await w.send({auto:true});await w.flush();assert.equal(result.ok,true);assert.equal(w.storage.archive_outbox.length,0);assert.equal(w.storage.archive_pending,false);
});
test('edits arriving while a batch is being saved remain queued for the next sync',async()=>{
 let changed=false;const w=worker({onBatch:async area=>{if(changed)return;changed=true;await area.set({resume_bundle:{primary_id:id,resumes:[cv('Concurrent update','2026-10-14T12:00:00Z')]}});}});
 await w.send({auto:true});await w.flush();assert.equal(w.storage.archive_pending,true);assert.ok(w.storage.archive_outbox.some(r=>r.data.sections[0].text==='Concurrent update'));
 await w.send({auto:true});await w.flush();assert.equal(w.storage.archive_outbox.length,0);
});
test('disabled background synchronization does not run on startup or ordinary browser changes',async()=>{
 const w=worker();for(const callback of w.startup)await callback();await w.area.set({ranking_goal:'New goal'});await w.flush();assert.equal(w.requests.length,0);
});

test('ranking sync preserves every offline run and strips credentials and unknown row fields',async()=>{
 const w=worker({enabled:true,fail:true});
 const rank=n=>({generated_at:`2026-10-14T1${n}:00:00Z`,resume_id:id,resume_hash:'CV',model:'text-embedding-3-small',goal:'DiT',all:[{id:'hh_1',score:0.7,cv_similarity:0.7,collected_at:'2026-10-14T10:00:00Z',secret:'PRIVATE'}],api_key:'SECRET'});
 await w.area.set({last_ranking:rank(0)});await w.flush();await w.area.set({last_ranking:rank(1)});await w.flush();
 const runs=w.storage.archive_outbox.filter(r=>r.kind==='ranking');assert.equal(runs.length,2);assert.ok(!JSON.stringify(runs).includes('PRIVATE'));assert.ok(!JSON.stringify(runs).includes('SECRET'));
 w.setOffline(false);await w.send({auto:true});await w.flush();assert.equal(w.storage.archive_outbox.length,0);assert.equal(w.requests.filter(r=>r.path==='/archive/sync').flatMap(r=>r.body.records).filter(r=>r.kind==='ranking').length,2);
});
