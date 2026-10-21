import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import './hh-sync-core.js';import './hh-apply-core.js';
test('HH statuses distinguish unseen from viewed, never infer a rejection from arbitrary chat',()=>{
 assert.equal(HHSync.status('Отклик не просмотрен'),'submitted');assert.equal(HHSync.status('Просмотрен'),'viewed');assert.equal(HHSync.status('Приглашение'),'invited');assert.equal(HHSync.status('Ваc пригласили'),'invited');assert.equal(HHSync.status('Отказ'),'rejected');assert.equal(HHSync.status('Вакансия пропала из списка'),'unknown');
 assert.equal(HHSync.vacancy('https://evil.example/vacancy/123'),null);assert.equal(HHSync.thread('https://evil.example/chat/1'),null);
 assert.equal(HHSync.vacancy('https://hh.ru/vacancy/123'),'hh_123');assert.equal(HHSync.thread('https://chat.hh.ru/chat/23'),'thread:23');
});
function worker({rejectClaim=false,changed=false}={}){
 const cv='a'.repeat(38),fields=[{id:'f0',label:'Сопроводительное письмо',type:'textarea',purpose:'cover',required:false,value:'Точный текст.',options:[]}];
 const form={state:'form',selected_resume_id:cv,fields,fingerprint:'approved-frame',submit_label:'Отправить'};
 const intent={resume_id:cv,resume_hash:'cv-hash',form_fingerprint:form.fingerprint,submit_label:form.submit_label,answers:{f0:'Точный текст.'}};
 let filled=false,submitted=0,claims=0;
 const chrome={runtime:{id:'fixture',onMessage:{addListener(){}}},tabs:{get:async()=>({url:'https://hh.ru/vacancy/123'})},storage:{local:{get:async()=>({resume_bundle:{resumes:[{id:cv,content_hash:'cv-hash'}]}})}}};
 const ctx=vm.createContext({chrome,URL,Set,Map,Object,Error,setTimeout:fn=>{fn();},activeJobs:new Set(),LocalResumeService:{request:async(_path,data)=>{if(data.op==='claim'){claims++;if(rejectClaim)throw Error('Permission expired');return intent;}throw Error('Unexpected action');}}});
 vm.runInContext(fs.readFileSync(new URL('hh-apply-core.js',import.meta.url),'utf8'),ctx);vm.runInContext(fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8'),ctx);
 ctx.wfApply=async(_id,config)=>{
  if(config.action==='fill'){filled=true;return {state:'filled'};}
  if(config.action==='submit'){submitted++;return {state:'sent_unconfirmed'};}
  if(submitted)return {state:'submitted',source_url:'https://hh.ru/vacancy/123',evidence:'Вы откликнулись'};
  return {...form,fields:fields.map(f=>({...f,value:changed&&filled?'Незапрошенная правка':f.value}))};
 };
 return {run:()=>ctx.wfExecute(7,{id:'cmd',application:{context:{vacancy:{id:'hh_123'},resume_id:cv}}},'worker-1'),stats:()=>({submitted,claims})};
}
test('worker clicks exactly once only after a server claim and exact field verification',async()=>{
 const w=worker();const r=await w.run();assert.equal(r.state,'submitted');assert.deepEqual(w.stats(),{submitted:1,claims:1});
});
test('expired approval and changed answers stop before any submit click',async()=>{
 for(const options of [{rejectClaim:true},{changed:true}]){const w=worker(options);await assert.rejects(w.run());assert.equal(w.stats().submitted,0);}
});
test('approval verifier rejects added questions, changed resume or submit action',()=>{
 const f={id:'q',label:'Вопрос',type:'textarea',group:'q',required:true,value:'Ответ',options:[]},before={state:'form',fingerprint:'fp',selected_resume_id:'cv',fields:[f],submit_label:'Отправить'},intent={resume_id:'cv',form_fingerprint:'fp',submit_label:'Отправить',answers:{q:'Ответ'}};
 assert.doesNotThrow(()=>HHApply.verifyApproved(intent,before,before));for(const bad of [{...before,submit_label:'Продолжить'},{...before,selected_resume_id:'another'},{...before,fields:[f,{...f,id:'other'}]},{...before,fields:[{...f,value:'Другой ответ'}]}])assert.throws(()=>HHApply.verifyApproved(intent,before,bad));
});
test('visible invitation on HH detail is bound to this vacancy, including HH mixed-script label',()=>{
 const label={innerText:'Ваc пригласили',getBoundingClientRect:()=>({width:120,height:30})};
 const document={querySelector:s=>s.includes('vacancy-title')?{innerText:'Senior ML Engineer (Kandinsky)'}:null,querySelectorAll:s=>s.includes('vacancy-response')?[label]:[]};
 const ctx=vm.createContext({document,location:new URL('https://hh.ru/vacancy/138315487?hhtmFrom=chat'),URL,getComputedStyle:()=>({display:'block',visibility:'visible'})});
 vm.runInContext(fs.readFileSync(new URL('hh-sync-core.js',import.meta.url),'utf8'),ctx);
 const result=vm.runInContext(fs.readFileSync(new URL('hh-sync-content.js',import.meta.url),'utf8'),ctx);
 assert.equal(result.records.length,1);assert.equal(result.records[0].vacancy_id,'hh_138315487');assert.equal(result.records[0].status,'invited');assert.equal(result.source_url,'https://hh.ru/vacancy/138315487?hhtmFrom=chat');
});

test('missing Chrome script result yields actionable preparation error instead of null.state',async()=>{
 const ctx=vm.createContext({chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}},scripting:{executeScript:async()=>[{result:null}]}},LocalResumeService:{request(){}},Set,Map,URL,Error});vm.runInContext(fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8'),ctx);
 await assert.rejects(()=>ctx.wfApply(1,{action:'inspect'}),/Не удалось прочитать форму HH/);
});
test('already invited vacancy is observed before opening any response form and does not submit again',async()=>{
 let formReads=0,refreshes=0;const ctx=vm.createContext({chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}},tabs:{get:async()=>({url:'https://hh.ru/vacancy/123'})}},HHApply:{verifyURL:()=>true},LocalResumeService:{request(){}},Set,Map,URL,Error});vm.runInContext(fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8'),ctx);
 ctx.wfApply=async()=>{formReads++;throw Error('No form');};ctx.wfRefresh=async()=>refreshes++;ctx.wfCurrentSync=async()=>({observed_statuses:[{vacancy_id:'hh_123',status:'invited'}]});
 const result=await ctx.wfPrepare(1,{application:{context:{vacancy:{id:'hh_123'},resume_id:'cv'}}},'worker');assert.equal(result.state,'complete');assert.ok(result.note.includes('уже пригласили'));assert.equal(refreshes,1);assert.equal(formReads,1);
});

test('receipt survives lost HTTP acknowledgement and is replayed without browser execution',async()=>{
 const stored={},writes=[];let calls=0;
 const ctx=vm.createContext({chrome:{runtime:{onMessage:{addListener(){}}},storage:{local:{get:async()=>({...stored}),set:async obj=>Object.assign(stored,obj),remove:async key=>delete stored[key]}}},Set,Map,URL,Error,LocalResumeService:{request:async(_path,data)=>{writes.push(data);if(++calls===1)throw Error('Lost HTTP acknowledgement');return {ok:true,replayed:true};}}});
 vm.runInContext(fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8'),ctx);
 await assert.rejects(()=>ctx.wfSaveReceipt({id:'receipt-command'},'original-worker',{state:'submitted',source_url:'https://hh.ru/vacancy/123',evidence:'Отклик отправлен'}));
 assert.ok(stored.hh_receipt_receipt_command===undefined);assert.ok(stored['hh_receipt_receipt-command']);
 await ctx.wfFlushReceipts();assert.equal(Object.keys(stored).length,0);assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);assert.equal(writes[1].worker_id,'original-worker');
});

test('HH response badge fallback recognizes text labels without reading vacancy descriptions as statuses',()=>{
 for(const [text,state] of [['Приглашение','invited'],['Резюме просмотрено','viewed'],['Отклик не просмотрен','submitted'],['Вам отказали','rejected'],['Отклик отозван','withdrawn']])assert.equal(HHSync.cardStatus([text]).status,state);
 assert.equal(HHSync.cardStatus(['Работа с приглашением пользователей в сервис','Отказаться','Вакансия в архиве']).status,'unknown');assert.equal(HHSync.cardStatus(['Приглашение','Отказ']).status,'unknown');
});

test('HH negotiations status inside a clickable card is readable, duplicate vacancy cards are preserved',()=>{
 const visible=()=>({width:200,height:30});
 function card(id,label){const link={href:'https://hh.ru/vacancy/'+id,innerText:'Research Engineer'},c={getBoundingClientRect:visible,getAttribute:k=>k==='data-qa'?'negotiations-item':null};const leaf={innerText:label,children:[],getBoundingClientRect:visible,closest:()=>c};c.querySelectorAll=s=>s==='a[href]'?[link]:s==='span,div,p'?[leaf]:[];return c;}
 const first=card(1,'Собеседование'),second=card(1,'Не просмотрен');
 const document={querySelector:()=>null,querySelectorAll:s=>s.includes('negotiations-item')?[first,first,second]:[]};
 const ctx=vm.createContext({document,location:new URL('https://hh.ru/applicant/negotiations'),URL,getComputedStyle:()=>({display:'block',visibility:'visible'})});
 vm.runInContext(fs.readFileSync(new URL('hh-sync-core.js',import.meta.url),'utf8'),ctx);const r=vm.runInContext(fs.readFileSync(new URL('hh-sync-content.js',import.meta.url),'utf8'),ctx);
 assert.equal(r.records.length,2);assert.equal(r.records[0].status,'invited');assert.equal(r.records[0].status_text,'Собеседование');assert.equal(r.records[1].status,'submitted');assert.equal(r.warning,'');
});

test('MV3 wake preserves an existing queue alarm instead of postponing it, and reads the queue',async()=>{
 let resets=0,reads=0;
 const ctx=vm.createContext({chrome:{runtime:{onMessage:{addListener(){}}},alarms:{get:async()=>({name:'hh-workflow'}),create:async()=>resets++,onAlarm:{addListener(){}}},tabs:{get:async()=>({url:'https://hh.ru/applicant/negotiations'})},storage:{local:{get:async()=>({}),set:async()=>{}},session:{get:async()=>({hh_workflow_worker:{id:'worker-persisted',tab_id:7}})}}},LocalResumeService:{request:async()=>{reads++;return {command:null};}},Set,Map,URL,Error,activeJobs:new Set()});
 vm.runInContext(fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8'),ctx);await new Promise(resolve=>setImmediate(resolve));assert.equal(resets,0);assert.equal(reads,1);
});

test('Giga links are restricted to the exact bot with one job start parameter',()=>{
 assert.equal(HHSync.giga('https://telegram.me/Giga_recruiter_bot?start=job_A-1'),'https://t.me/Giga_recruiter_bot?start=job_A-1');
 assert.equal(HHSync.giga('https://hh.ru/away?to='+encodeURIComponent('https://telegram.me/Giga_recruiter_bot?start=job_A-1')+'&chatId=123&messageId=456'),'https://t.me/Giga_recruiter_bot?start=job_A-1');
 for(const u of ['https://evil.example/Giga_recruiter_bot?start=a','https://t.me/another?start=a','https://t.me/Giga_recruiter_bot?start=a&start=b','https://t.me/Giga_recruiter_bot?start=a&x=1'])assert.equal(HHSync.giga(u),null);
});
test('full HH chat directory exposes canonical thread links when negotiations use embedded buttons',()=>{
 const anchor=href=>({href,getBoundingClientRect:()=>({width:100,height:25})});
 const links=[anchor('https://hh.ru/chat/123?hhtmFrom=app'),anchor('https://hh.ru/chat/123/'),anchor('https://hh.ru/chat/-1'),anchor('https://evil.example/chat/456')];
 const document={querySelector:()=>null,querySelectorAll:selector=>selector==='a[href]'?links:[]};
 const ctx=vm.createContext({document,location:new URL('https://hh.ru/chat'),URL,getComputedStyle:()=>({display:'block',visibility:'visible'})});
 vm.runInContext(fs.readFileSync(new URL('hh-sync-core.js',import.meta.url),'utf8'),ctx);
 const result=vm.runInContext(fs.readFileSync(new URL('hh-sync-content.js',import.meta.url),'utf8'),ctx);
 assert.equal(result.page_kind,'chat_directory');assert.deepEqual(Array.from(result.thread_urls),['https://hh.ru/chat/123']);assert.equal(result.warning,'');assert.equal(result.records.length,0);
});

test('chat invitation preserves visible bubble and explicit vacancy binding, ambiguous header stays unbound',()=>{
 const visible=()=>({width:200,height:40});
 const a={href:'https://telegram.me/Giga_recruiter_bot?start=job_fixture',getBoundingClientRect:visible};
 const bubble={innerText:'Здравствуйте! Пройдите интервью с ГигаРекрутером. '+a.href,getBoundingClientRect:visible,getAttribute:()=>null,closest:()=>null,contains:n=>n===a,querySelector:()=>null,querySelectorAll:s=>s==='a[href]'?[a]:[]};a.parentElement=bubble;
 const conversation={getBoundingClientRect:visible,getAttribute:()=>null,querySelectorAll:s=>s==='a[href]'?[a]:[bubble]};
 const header={href:'https://hh.ru/vacancy/123',getBoundingClientRect:visible};let ambiguous=false;
 const document={querySelector:()=>null,querySelectorAll:s=>s.includes('chat-messages')?[conversation]:s.includes('chat-header')?(ambiguous?[header,{...header,href:'https://hh.ru/vacancy/456'}]:[header]):[]};
 const ctx=vm.createContext({document,location:new URL('https://hh.ru/chat/12345'),URL,getComputedStyle:()=>({display:'block',visibility:'visible'})});vm.runInContext(fs.readFileSync(new URL('hh-sync-core.js',import.meta.url),'utf8'),ctx);
 const source=fs.readFileSync(new URL('hh-sync-content.js',import.meta.url),'utf8');let r=vm.runInContext(source,ctx);assert.equal(r.records[0].vacancy_id,'hh_123');assert.equal(r.records[0].thread_id,'thread:12345');assert.equal(r.records[0].status,'unknown');assert.equal(r.records[0].messages[0].links[0],HHSync.giga(a.href));
 ambiguous=true;r=vm.runInContext(source,ctx);assert.equal(r.records[0].vacancy_id,null);
});


test('HH queue is not claimed while the worker tab has no committed HH address',async()=>{
 const saved={},calls=[];
 const ctx=vm.createContext({URL,Date,Set,Map,Object,Error,Promise,setTimeout,clearTimeout,activeJobs:new Set(),chrome:{runtime:{onMessage:{addListener(){}}},storage:{local:{get:async()=>saved,set:async data=>Object.assign(saved,data)}}},wfResolveWorker:async()=>({id:'w',tab_id:7}),waitForHHWorker:async()=>{throw Error('Служебная вкладка HH ещё не получила адрес.');},LocalResumeService:{request:async(_url,data)=>{calls.push(data);return {command:null};}}});
 vm.runInContext(fs.readFileSync(new URL('hh-workflow.js',import.meta.url),'utf8'),ctx);await ctx.hhWorkflowPulse();
 assert.equal(calls.filter(c=>c.op==='next').length,0);assert.equal(saved.hh_workflow_status.state,'needs_input');assert.match(saved.hh_workflow_status.note,/ещё не получила адрес/);
 assert.throws(()=>ctx.wfHHAddress(undefined),/Не удалось определить адрес/);assert.equal(ctx.wfHHAddress('https://chat.hh.ru/chat/123',{chat:true}).origin,'https://chat.hh.ru');
});
