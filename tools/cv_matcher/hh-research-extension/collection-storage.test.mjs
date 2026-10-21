import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('collection-storage.js',import.meta.url),'utf8');
function fixture({quota=false,reject=false}={}){
 const local={vacancies:[{id:'hh_1',description:'old'}]},session={},calls=[];
 const area=data=>({get:async key=>key===null?data:{[key]:data[key]},set:async values=>Object.assign(data,values)});
 const storage={local:area(local),session:area(session)};
 if(quota)storage.local.set=async()=>{throw Error('QUOTA_BYTES');};
 const c=vm.createContext({Date,Map,Set,Promise,Error,setTimeout,clearTimeout,chrome:{storage},ResearchSearch:{mergeVacancies:(old,rows)=>[...new Map([...old,...rows].map(r=>[r.id,r])).values()]},ArchiveSyncCore:{record:async(kind,id,data)=>({kind,id,data})},LocalResumeService:{request:async(path,data)=>{calls.push({path,data});if(path==='/health')return {ok:true};return {accepted:reject?[]:data.records.map(r=>({id:r.id})),rejected:reject?[{id:'bad'}]:[]};}}});
 vm.runInContext(source,c);return {c,local,session,calls};
}
test('popup and scheduler use the same acknowledged SQLite stream even with full Chrome storage',async()=>{
 const f=fixture({quota:true}),sink=await f.c.createCollectionStorage({optional:true});
 await sink.saveVacancies([{id:'hh_2',description:'full'}]);await sink.saveScan({id:'scan-1',listing_complete:false});
 assert.equal((await sink.loadVacancies()).length,2);assert.equal(f.local.vacancies.length,1);
 assert.deepEqual(f.calls.map(c=>c.path),['/health','/archive/sync','/archive/sync']);
 await f.c.collectionStatusWrite('hh_crawl_status',{state:'complete',loaded:1});assert.equal(f.session.hh_crawl_status.loaded,1);
 assert.equal((await f.c.collectionStatusRead('hh_crawl_status')).state,'complete');
});
test('rejected archive records stop collection before advancing the in-memory snapshot',async()=>{
 const f=fixture({reject:true}),sink=await f.c.createCollectionStorage();
 await assert.rejects(sink.saveVacancies([{id:'hh_2'}]),/не подтвердил/);assert.equal((await sink.loadVacancies()).length,1);
});
test('an optional offline service preserves standalone capture; required service never silently accepts failed persistence',async()=>{
 const f=fixture();f.c.LocalResumeService.request=async()=>{throw Error('Offline');};
 assert.equal(await f.c.createCollectionStorage({optional:true}),null);
 const sink=await f.c.createCollectionStorage();await assert.rejects(sink.saveVacancies([{id:'hh_2'}]),/Offline/);
});
test('an unresolved DOM injection times out and releases its timer',async()=>{
 const f=fixture();let cleared=false;f.c.setTimeout=callback=>{queueMicrotask(callback);return 1;};f.c.clearTimeout=()=>{cleared=true;};
 await assert.rejects(f.c.collectionReadWithin(()=>new Promise(()=>{}),1000),/не ответила/);assert.equal(cleared,true);
});
