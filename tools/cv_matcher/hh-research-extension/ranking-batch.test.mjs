import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const scope=vm.createContext({});
vm.runInContext(fs.readFileSync(new URL('ranking-batch.js',import.meta.url),'utf8'),scope);
const batch=scope.RankingBatch;
function request(count){return {resume_id:'selected',model:'text-embedding-3-small',goal:'Research',allow_api:false,bundle:{resumes:[{id:'selected',content_hash:'cv-hash'}]},vacancies:Array.from({length:count},(_,i)=>({id:'hh_'+i}))};}
function reply(packet){const all=packet.vacancies.map(v=>({...v,score:Number(v.id.slice(3))/2000}));return {resume_id:packet.resume_id,resume_hash:'cv-hash',model:packet.model,goal:packet.goal,all,input_count:all.length,ranked_count:all.length,cache_reused:all.length,api_requests:0,usage_tokens:0,cached:true,generated_at:'2026-10-19T12:00:00Z'};}
test('718 selected jobs become four bounded requests and one globally sorted result',async()=>{
 const calls=[],progress=[],packet=request(718);
 const result=await batch.run(packet,async p=>{calls.push(p);return reply(p);},p=>progress.push(p));
 assert.deepEqual(calls.map(c=>c.vacancies.length),[200,200,200,118]);
 assert.equal(result.ranked_count,718);assert.equal(result.all[0].id,'hh_717');assert.equal(result.top.length,10);
 assert.equal(result.requested_count,718);assert.equal(result.processed_count,718);assert.equal(result.partial,false);
 assert.ok(calls.every(c=>c.allow_api===false&&c.bundle.resumes.length===1&&c.bundle===packet.bundle));
 assert.deepEqual(progress.map(p=>p.processed),[0,200,400,600]);assert.equal(result.api_requests,0);
});
test('2000 is a calculation limit rather than a silent 200 job selection',async()=>{
 let calls=0;const result=await batch.run(request(2000),async p=>{calls++;return {...reply(p),cached:false,cache_reused:0,api_requests:2,usage_tokens:50};});
 assert.equal(calls,10);assert.equal(result.all.length,2000);assert.equal(result.api_requests,20);assert.equal(result.usage_tokens,500);assert.equal(result.cached,false);
});
test('interrupted second batch preserves the first batch and never automatically retries',async()=>{
 let calls=0;
 await assert.rejects(batch.run(request(718),async p=>{if(++calls===2)throw Error('Offline');return reply(p);}),error=>{
  assert.equal(error.partial_ranking.processed_count,200);assert.equal(error.partial_ranking.requested_count,718);
  assert.equal(error.partial_ranking.all.length,200);assert.equal(error.partial_ranking.partial,true);return true;
 });assert.equal(calls,2);
});
test('a changed CV version cannot be merged into the selected calculation',async()=>{
 let calls=0;await assert.rejects(batch.run(request(201),async p=>({...reply(p),resume_hash:++calls===1?'cv-hash':'changed'})),error=>{assert.equal(error.partial_ranking.ranked_count,200);return /Контекст/.test(error.message);});
});
test('out of range selections are rejected before any request',async()=>{
 for(const count of [0,2001])await assert.rejects(batch.run(request(count),()=>{throw Error('must not call');}),/2000/);
});
