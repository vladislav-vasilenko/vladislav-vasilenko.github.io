import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import './diagnostics-core.js';
test('diagnostics projects counters and known states without leaking raw storage, content or errors',()=>{
 const secret='PRIVATE_SENTINEL';
 const report=ExtensionDiagnostics.snapshot({version:'0.11.3',adapters:[{id:'tbank',label:'T-Bank',hosts:['tbank.ru']}],permissions:{'tbank.ru':true},
 saved:{remembered_resume_import_token:secret,resume_bundle:{resumes:[{text:secret}]},vacancies:[{description:secret,link:secret,description_quality:'full'}],hh_workflow_status:{state:secret,note:secret},board_crawl_status:{state:'partial',pages:2,errors:-1}},
 worker:{exists:true,state:'captcha',tab_id:42,url:secret},health:{service:'cv-matcher-local',version:10,api_key:secret,connections:{workers:{giga:{connected:true,error:secret},hh:{connected:false}}}}});
 assert.ok(!JSON.stringify(report).includes(secret));assert.ok(!JSON.stringify(report).includes('tab_id'));
 assert.equal(report.cache.full,1);assert.equal(report.cache.resumes,1);assert.equal(report.hh.page_state,'captcha');assert.equal(report.tasks.hh_workflow_status.state,'unknown');assert.equal(report.tasks.board_crawl_status.errors,0);assert.equal(report.workers.giga.connected,true);assert.equal(report.adapters[0].access[0].granted,true);
});
test('diagnostics is read-only and only callable from its own extension page',async()=>{
 let handler,reads=0,probes=0,health=0;
 const c=vm.createContext({ExtensionDiagnostics,JobBoardAdapters:{registry:[]},hhWorkflowBusy:false,careerWorkflowBusy:false,collectionBusy:false,
 inspectWorker:async()=>{probes++;return {exists:false};},LocalResumeService:{request:async(path,body)=>{health++;assert.equal(path,'/health');assert.equal(body,null);return null;}},
 chrome:{runtime:{id:'fixture',getURL:p=>'chrome-extension://fixture/'+p,getManifest:()=>({version:'0.11.3'}),onMessage:{addListener:f=>handler=f}},storage:{local:{get:async keys=>{reads++;assert.ok(!keys.includes('remembered_resume_import_token'));return {};}}},permissions:{contains:async()=>false}}});
 vm.runInContext(fs.readFileSync(new URL('diagnostics-worker.js',import.meta.url),'utf8'),c);
 for(const sender of [{id:'foreign',url:'chrome-extension://fixture/diagnostics.html'},{id:'fixture',url:'http://127.0.0.1:8788/'}])assert.equal(handler({type:'diagnostics_snapshot'},sender,()=>assert.fail('unexpected response')),undefined);
 assert.equal(reads,0);
 const reply=await new Promise(resolve=>assert.equal(handler({type:'diagnostics_snapshot'},{id:'fixture',url:'chrome-extension://fixture/diagnostics.html'},resolve),true));
 assert.equal(reply.ok,true);assert.equal(reply.report.service.reachable,false);assert.equal(reads,1);assert.equal(probes,1);assert.equal(health,1);
});

test('storage diagnostics distinguish an unknown capacity from a full browser cache',()=>{
 const unknown=ExtensionDiagnostics.snapshot({version:'test'});assert.equal(unknown.storage.bytes,null);assert.equal(unknown.storage.near_limit,false);
 const full=ExtensionDiagnostics.snapshot({version:'test',storage:{bytes:9_000_000,limit_bytes:10_000_000,raw:'SECRET'}});assert.equal(full.storage.near_limit,true);assert.equal(full.storage.bytes,9_000_000);assert.ok(!JSON.stringify(full).includes('SECRET'));
});
