import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

const primary='a'.repeat(38),friend='b'.repeat(38);
function worker({redirect=false,rejected=false,permission=true}={}){
 const original={id:primary,title:'My CV',quality:'full'},local={resume_bundle:{primary_id:primary,primary_selection:'user',resumes:[original]}},requests=[],tabs=new Map(),closed=[];
 const chrome={runtime:{id:'test',onMessage:{addListener(){}}},permissions:{contains:async()=>permission},tabs:{create:async props=>{tabs.set(19,{...props,id:19});return tabs.get(19);},get:async id=>tabs.get(id),remove:async id=>{closed.push(id);tabs.delete(id);}},
  storage:{local:{get:async keys=>keys===null?{...local}:Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,local[k]])),set:async value=>Object.assign(local,value),remove:async key=>delete local[key]}},
  scripting:{executeScript:async()=>[{result:{resume:{id:redirect?primary:friend,title:'Friend research CV',quality:'full',captured_at:new Date().toISOString(),sections:[{key:'experience',heading:'Опыт',text:'Research with PyTorch. '.repeat(20)}]}}}]}};
 const c=vm.createContext({chrome,URL,TextEncoder,crypto:webcrypto,Set,Map,Date,Error,setTimeout:fn=>fn(),activeJobs:new Set(),ArchiveSyncCore:{record:async(kind,id,data)=>({kind,id,data})},LocalResumeService:{request:async(path,data)=>{requests.push({path,data});return {rejected:rejected?[{}]:[]};}}});
 for(const file of ['resume-core.js','resume-import-core.js','resume-worker.js','resume-intake-worker.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),c);
 c.navigate=async(id,url)=>{tabs.get(id).url=url;};c.loadPolicy=async()=>({primary_id:primary,resumes:[{id:primary,url:'https://hh.ru/resume/'+primary,role:'primary'}]});
 return {c,local,requests,tabs,closed,run:()=>c.importLinkedResume({payload:{resume_id:friend}})};
}
test('public friend CV can be imported without own catalog membership and without replacing primary',async()=>{
 const w=worker(),result=await w.run();assert.equal(result.state,'complete');assert.equal(result.api_requests,0);assert.equal(w.local.resume_bundle.primary_id,primary);assert.equal(w.local.resume_bundle.primary_selection,'user');
 assert.equal(w.local.resume_bundle.resumes.length,2);assert.equal(w.local.resume_bundle.resumes.find(r=>r.id===friend).role,'secondary');assert.equal(w.requests.length,1);assert.equal(w.requests[0].path,'/archive/sync');assert.equal(w.requests[0].data.records[0].id,friend);assert.deepEqual(w.closed,[19]);
});
test('redirect to another CV is rejected before changing local snapshots or SQLite',async()=>{
 const w=worker({redirect:true});await assert.rejects(w.run,/другое резюме/);assert.equal(w.local.resume_bundle.resumes.length,1);assert.equal(w.requests.length,0);assert.deepEqual(w.closed,[19]);
});
test('missing HH permission or rejected archive write cannot report a successful import',async()=>{
 const missing=worker({permission:false});await assert.rejects(missing.run,/Разрешите чтение HH/);assert.equal(missing.tabs.size,0);
 const rejected=worker({rejected:true});await assert.rejects(rejected.run,/не сохранено/);assert.deepEqual(rejected.closed,[19]);
});
test('lost import receipt replays acknowledgement without reading the resume again',async()=>{
 const w=worker();let reads=0,writes=0;w.local.resume_import_worker_id='reader-stable';
 w.c.importLinkedResume=async()=>{reads++;return {state:'complete',resume_id:friend};};
 w.c.workflowCall=async data=>{if(data.op==='next')return {command:reads?null:{id:'import-command',payload:{resume_id:friend}}};if(data.op==='result'){writes++;if(writes===1)throw Error('Lost HTTP acknowledgement');return {ok:true};}throw Error('Unexpected call');};
 await w.c.resumeIntakePulse();assert.ok(w.local['resume_import_receipt_import-command']);await w.c.resumeIntakePulse();assert.equal(reads,1);assert.equal(writes,2);assert.equal(w.local['resume_import_receipt_import-command'],undefined);
});
test('Google Docs queue returns a review candidate without saving or replacing the primary CV',async()=>{
 const w=worker(),id='gdoc_abcdefghijk',url='https://docs.google.com/document/d/abcdefghijk/edit';w.c.chrome.scripting.executeScript=async()=>[{result:{candidate:{id,source_url:url,title:'Google CV',text:'Professional experience. '.repeat(12)}}}];
 const result=await w.c.importLinkedResume({payload:{resume_id:id}});assert.equal(result.state,'complete');assert.equal(result.candidate.id,id);assert.equal(w.requests.length,0);assert.equal(w.local.resume_bundle.resumes.length,1);assert.equal(w.local.resume_bundle.primary_id,primary);assert.deepEqual(w.closed,[19]);
 const missing=worker({permission:false});await assert.rejects(missing.c.importLinkedResume({payload:{resume_id:id}}),/Разрешите Google Docs/);assert.equal(missing.tabs.size,0);
});
