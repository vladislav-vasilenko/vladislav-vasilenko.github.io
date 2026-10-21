import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const url='https://career.avito.com/vacancies/data-science/19450/';
const job={id:'avito_19450',link:url,description:'Complete original job text.',description_quality:'full'};
const app={context:{channel:'career',resume_id:'cv',resume_hash:'cv-hash',vacancy:job}};
function env({busyTab=99,quota=false,readErrors=0,fatalRead=false,archived=false,syncRejected=false}={}){
 const calls=[],local={},session={},writes=[];let reads=0,opening={id:'open-command',app_id:'app',payload:{url},application:app};
 const ctx=vm.createContext({URL,Date,Error,crypto:{randomUUID:()=> 'career-worker'},setTimeout:fn=>fn(),activeJobs:new Set([busyTab]),
  JobBoards:{identity:u=>u===url?{id:job.id}:null},JobBoardAdapters:{sameSource:(a,b)=>new URL(a).origin===new URL(b).origin},
  ArchiveSyncCore:{record:async(kind,id,data)=>({kind,id,data})},
  chrome:{permissions:{contains:async()=>true},tabs:{query:async()=>[{id:7,url}],get:async()=>({id:7,url}),update:async()=>{}},scripting:{executeScript:async()=>[]},storage:{
   local:{get:async()=>({...local}),set:async x=>{if(quota)throw Error('Resource::kQuotaBytes quota exceeded');Object.assign(local,x);},remove:async k=>delete local[k]},
   session:{get:async()=>({...session}),set:async x=>Object.assign(session,x),remove:async k=>delete session[k]}
  }},
  LocalResumeService:{request:async(path,data)=>{writes.push({path,data});return {rejected:syncRejected?[{error:'bad record'}]:[]};}},
  workflowCall:async data=>{calls.push(data);if(data.op==='next'){const command=opening;opening=null;return {command};}if(data.op==='career_form_for_application')return {id:'app'};return {ok:true};},
  wfScript:async(_,files)=>{
   if(files.includes('board-content.js'))return {page_kind:'detail',vacancies:[{...job,archived}]};
   reads++;if(fatalRead)return {state:'read_error',error:'Войдите на сайте',code:'login_required',retryable:false};
   if(reads<=readErrors)return {state:'read_error',error:'Откройте форму',code:'form_not_open',retryable:true};
   return {state:'questionnaire',source_url:url,vacancy_id:job.id,fingerprint:'fp'};
  }
 });
 vm.runInContext(fs.readFileSync(new URL('career-workflow.js',import.meta.url),'utf8'),ctx);
 return {ctx,calls,session,local,writes,reads:()=>reads,command:()=>({id:'open-command',app_id:'app',payload:{url},application:app})};
}
test('company worker processes independent form tasks while HH owns another tab',async()=>{
 const e=env();await e.ctx.careerWorkflowPulse();
 assert.equal(e.calls[0].op,'next');assert.equal(e.calls[0].kinds[0],'career_open');
 const result=e.calls.find(c=>c.op==='result');assert.equal(result.result.state,'complete');
 assert.equal(e.session.career_form_bindings.app.tab_id,7);assert.equal(e.ctx.activeJobs.has(99),true);assert.equal(e.ctx.activeJobs.has(7),false);
 const saved=e.writes[0].data.records[0].data;assert.equal(saved.archived,false);assert.ok(Date.parse(saved.availability_checked_at));
 assert.deepEqual(Object.keys(e.local),[]); // Large job text does not enter optional browser cache.
 assert.equal(e.calls.some(c=>c.op==='career_fill_claim'),false);
});
test('transient form mounting retries read-only capture but login stops immediately',async()=>{
 const e=env({readErrors:2});await e.ctx.careerOpenForm(e.command());assert.equal(e.reads(),3);assert.equal(e.writes.length,1);
 const login=env({fatalRead:true});await assert.rejects(()=>login.ctx.careerOpenForm(login.command()),/Войдите/);assert.equal(login.reads(),1);assert.equal(login.writes.length,0);
});
test('busy original tab, archived description or rejected sync cannot bind a form',async()=>{
 for(const options of [{busyTab:7},{archived:true},{syncRejected:true}]){
  const e=env(options);await assert.rejects(()=>e.ctx.careerOpenForm(e.command()));assert.equal(e.session.career_form_bindings,undefined);
  assert.equal(e.calls.some(c=>c.op==='career_form_for_application'),false);
 }
});
test('a full optional Chrome cache does not lose an already executed transfer receipt',async()=>{
 const e=env({quota:true});await e.ctx.careerReceipt({id:'fill-command'},'worker',{state:'fields_filled'});
 assert.equal(e.calls.filter(c=>c.op==='career_fill_result').length,1);assert.deepEqual(Object.keys(e.session),[]);
});
test('failed receipt delivery remains journalled and is retried without filling again',async()=>{
 const e=env({quota:true});e.ctx.workflowCall=async()=>{throw Error('Offline');};
 await assert.rejects(()=>e.ctx.careerReceipt({id:'fill-command'},'worker',{state:'fields_filled'}),/Offline/);
 assert.equal(e.session['career_receipt_fill-command'].result.state,'fields_filled');
 const delivered=[];e.ctx.workflowCall=async data=>{delivered.push(data);return {command:null};};await e.ctx.careerWorkflowPulse();
 assert.equal(delivered[0].op,'career_fill_result');assert.equal(delivered.some(c=>c.op==='career_fill_claim'),false);assert.equal(e.session['career_receipt_fill-command'],undefined);
});
