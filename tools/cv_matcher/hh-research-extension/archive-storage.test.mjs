import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const c=vm.createContext({});vm.runInContext(fs.readFileSync(new URL('archive-storage.js',import.meta.url),'utf8'),c);
test('quota overflow is durable across storage instances and superseded after local recovery',async()=>{
 const localValues={archive_outbox:[{id:'old'}]},diskValues={};let quota=true;
 const local={get:async keys=>Object.fromEntries(keys.map(k=>[k,localValues[k]])),set:async values=>{if(quota)throw Error('Resource::kQuotaBytes quota exceeded');Object.assign(localValues,values);}};
 const disk={read:async keys=>Object.fromEntries(keys.filter(k=>k in diskValues).map(k=>[k,diskValues[k]])),write:async values=>Object.assign(diskValues,structuredClone(values)),remove:async keys=>keys.forEach(k=>delete diskValues[k])};
 const first=c.createArchiveStorage(local,disk);await first.write({archive_outbox:[{id:'old'},{id:'new'}],archive_pending:true});
 const restored=c.createArchiveStorage(local,disk);assert.equal((await restored.read('archive_outbox')).archive_outbox.length,2);assert.equal(localValues.archive_outbox.length,1);
 quota=false;await restored.write({archive_outbox:[],archive_pending:false});assert.equal((await first.read('archive_outbox')).archive_outbox.length,0);assert.equal(Object.keys(diskValues).length,0);
});
test('double storage failure is explicit and preserves unacknowledged records',async()=>{
 const rows=[{id:'unsent'}],local={get:async()=>({archive_outbox:rows}),set:async()=>{throw Error('quota');}},disk={read:async()=>({}),write:async()=>{throw Error('disk full');}};
 await assert.rejects(c.createArchiveStorage(local,disk).write({archive_outbox:[]}),/Данные не очищались/);assert.equal(rows.length,1);
});
