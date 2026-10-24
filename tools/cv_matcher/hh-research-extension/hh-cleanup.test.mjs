import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
import './hh-sync-core.js';import './hh-cleanup-core.js';
const row=(patch={})=>{const r={vacancy_id:'hh_123',title:'ML Research',status:'rejected',status_text:'Отказ',card_text:'ML Research Company 18 октября Отказ',page_url:'https://hh.ru/applicant/negotiations',...patch};r.key=HHCleanup.key(r);return r;};
test('cleanup accepts only exact standalone refusal badges; unknown/invited/missing/closed never qualify',()=>{
 assert.equal(HHCleanup.rejected(row()),true);
 for(const patch of [{status:'unknown'},{status:'invited',status_text:'Приглашение'},{status_text:'Есть отказоустойчивые системы'},{status_text:'Вакансия закрыта'},{status_text:'Карточка исчезла'},{status_text:'Отказ · Приглашение'}])assert.equal(HHCleanup.rejected(row(patch)),false);
});
test('cleanup binds exact unique cards and skips ambiguous or changed records',()=>{
 const r=row();assert.equal(HHCleanup.target([r],r),r);
 for(const rows of [[],[r,r],[row({status:'invited',status_text:'Приглашение'})],[row({card_text:'New response'})]])assert.throws(()=>HHCleanup.target(rows,r));
 assert.equal(HHCleanup.unique([r,r]).length,0);assert.throws(()=>HHCleanup.target([r],{...r,key:'forged'}));
});
test('cleanup approval expires, contains only preview IDs and is single-use',()=>{
 const r=row(),p={state:'preview',expires_at:100,items:[r]};assert.equal(HHCleanup.selection(p,[r.key],99).length,1);
 for(const [plan,keys,now] of [[p,[r.key],100],[{...p,state:'consumed'},[r.key],99],[p,['other'],99],[p,[r.key,r.key],99],[p,[],99]])assert.throws(()=>HHCleanup.selection(plan,keys,now));
});
test('cleanup follows only same-filter next negotiations page',()=>{
 const u='https://hh.ru/applicant/negotiations';assert.equal(HHCleanup.next(u,u+'?page=1'),u+'?page=1');
 for(const v of ['https://evil.test/applicant/negotiations?page=1','https://hh.ru/vacancy/1',u+'?page=2',u+'?page=1&resume=another'])assert.equal(HHCleanup.next(u,v),null);
});
function fixture({failArchive=false,changed=false,uncertain=false,lateDialog=false}={}){
 let confirmReads=0,verifyReads=0;const storage={},session={},handlers=[],clicks=[],observed=[],events=[],r=row(),plan={id:'plan',state:'preview',tab_id:7,expires_at:Date.now()+60000,items:[r]};session.hh_cleanup_plan=plan;
 const chrome={runtime:{id:'fixture',getURL:f=>'chrome-extension://fixture/'+f,onMessage:{addListener:f=>handlers.push(f)}},storage:{local:{get:async k=>Object.fromEntries((Array.isArray(k)?k:[k]).map(key=>[key,structuredClone(storage[key])])),set:async v=>{Object.assign(storage,structuredClone(v));events.push(['save',structuredClone(v)]);}},session:{get:async()=>structuredClone(session),set:async v=>Object.assign(session,structuredClone(v)),remove:async k=>delete session[k]}},permissions:{contains:async()=>true},tabs:{get:async()=>({url:r.page_url}),update:async()=>{}}};
 const c=vm.createContext({chrome,URL,Date,Promise,Set,Map,Object,Error,crypto:{randomUUID:()=> 'run'},setTimeout:f=>{queueMicrotask(f);return 1;},clearTimeout(){},activeJobs:new Set(),hhWorkflowBusy:false,collectionBusy:false,careerWorkflowBusy:false,navigate:async()=>{},wfReadWithin:operation=>Promise.resolve().then(operation),wfScript:async()=>({records:[r]}),LocalResumeService:{request:async(_url,body)=>{observed.push(body);events.push(['archive']);if(failArchive)throw Error('SQLite offline');return {};}}});
 for(const file of ['hh-sync-core.js','hh-cleanup-core.js','hh-cleanup-worker.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),c);
 c.cleanupScript=async(_id,action)=>{if(action.action==='scan')return {items:changed?[row({status:'invited',status_text:'Приглашение'})]:[r]};clicks.push(action.action);events.push([action.action]);if(action.action==='confirm')return {state:lateDialog&&++confirmReads<3?'no_dialog':'confirmed'};if(action.action==='verify')return {state:uncertain||lateDialog&&++verifyReads<5?'pending':'removed'};return {state:'clicked'};};
 return {c,r,plan,storage,session,clicks,observed,events,send:(m,sender={id:'fixture',url:'chrome-extension://fixture/hh-cleanup.html'})=>new Promise(resolve=>{let handled=false;for(const h of handlers)if(h(m,sender,resolve))handled=true;if(!handled)resolve(undefined);})};
}
test('cleanup archives refusals before any click and records the attempt before native removal',async()=>{
 const f=fixture();await f.c.cleanupExecute(f.plan,[f.r]);assert.equal(f.observed.length,1);assert.deepEqual(f.clicks,['remove','confirm','verify']);assert.equal(f.storage.hh_cleanup_run.removed,1);
 const click=f.events.findIndex(e=>e[0]==='remove');assert.ok(f.events.findIndex(e=>e[0]==='archive')<click);assert.ok(f.events.slice(0,click).some(e=>e[0]==='save'&&e[1].hh_cleanup_run?.items?.some(i=>i.state==='started')));
});
test('offline SQLite or a changed refusal prevent all native deletion clicks',async()=>{
 for(const options of [{failArchive:true},{changed:true}]){const f=fixture(options);await f.c.cleanupExecute(f.plan,[f.r]);assert.equal(f.clicks.length,0);assert.equal(f.storage.hh_cleanup_run.removed,0);}
});
test('uncertain deletion is recorded and never retried; the batch stops',async()=>{
 const f=fixture({uncertain:true});await f.c.cleanupExecute(f.plan,[f.r,row({vacancy_id:'hh_456'})]);assert.equal(f.clicks.filter(a=>a==='remove').length,1);assert.equal(f.storage.hh_cleanup_run.state,'needs_input');assert.equal(f.storage.hh_cleanup_run.items[0].state,'uncertain');
});
test('only the dedicated extension page can execute; explicit confirmation and preview ID required',async()=>{
 const f=fixture(),message={type:'hh_cleanup_execute',plan_id:'plan',keys:[f.r.key],confirm:true};
 for(const sender of [{id:'fixture',url:'https://hh.ru/applicant/negotiations'},{id:'foreign',url:'chrome-extension://fixture/hh-cleanup.html'},{id:'fixture',url:'chrome-extension://fixture/popup.html'}])assert.equal(await f.send(message,sender),undefined);
 for(const patch of [{confirm:false},{plan_id:'other'},{keys:['forged']}])assert.equal((await f.send({...message,...patch})).ok,false);
 assert.equal(f.clicks.length,0);
});
test('a worker restart marks started operations uncertain and never resumes deletion',async()=>{
 const f=fixture();f.storage.hh_cleanup_status={state:'running'};f.storage.hh_cleanup_run={state:'running',items:[{state:'started'}]};
 const value=await f.send({type:'hh_cleanup_status'});assert.equal(value.status.state,'needs_input');assert.equal(f.storage.hh_cleanup_run.items[0].state,'uncertain');assert.equal(f.clicks.length,0);
});

function contentFixture({status='Отказ',dialogText='',hiddenDelete=false,dialogRole='dialog',nested=false}={}){
 let deleted=0,confirmed=0,currentDialog=dialogText;
 const visibleNode=text=>({innerText:text,children:[],getBoundingClientRect:()=>({width:100,height:20}),getAttribute:()=>null,closest:()=>card,contains:()=>false});
 const link={...visibleNode('ML Research'),href:'https://hh.ru/vacancy/123'},badge=visibleNode(status),remove={...visibleNode('Удалить'),getBoundingClientRect:()=>({width:hiddenDelete?0:100,height:20}),click:()=>deleted++};
 const card={...visibleNode('ML Research Company 18 октября '+status),querySelector:()=>link,getAttribute:k=>k==='data-negotiation-id'?'12345':null,querySelectorAll:s=>s==='a[href]'?[link]:s.includes('response-state')?[badge]:s==='span,div,p'?[badge]:s==='button,[role="button"],a'?[remove,link]:[]};
 const confirm={...visibleNode('Удалить'),click:()=>confirmed++};
 const inner={...visibleNode(''),get innerText(){return currentDialog;},querySelectorAll:s=>s.includes('h1,h2')?[visibleNode(currentDialog)]:[confirm]};
 const dialog={...inner,contains:n=>n===inner};
 const document={querySelector:()=>null,querySelectorAll:s=>{
  if(s.includes('negotiations-item'))return [card];
  if(currentDialog&&(s.includes('[role="'+dialogRole+'"]')||s.includes('[aria-modal="true"]')))return nested?[dialog,inner]:[dialog];
  return [];
 }};
 const c=vm.createContext({document,location:new URL('https://hh.ru/applicant/negotiations'),URL,Date,Map,Set,Error,getComputedStyle:()=>({display:'block',visibility:'visible'})});for(const file of ['hh-sync-core.js','hh-cleanup-core.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),c);
 const read=action=>{c.__hhCleanupAction=action;return vm.runInContext(fs.readFileSync(new URL('hh-cleanup-content.js',import.meta.url),'utf8'),c);};
 return {read,showDialog:text=>{currentDialog=text;},stats:()=>({deleted,confirmed})};
}
test('native cleanup scan never clicks; remove is scoped to the approved refusal only',()=>{
 const f=contentFixture(),snap=f.read({action:'scan'});assert.equal(snap.items[0].status,'rejected');assert.deepEqual(f.stats(),{deleted:0,confirmed:0});
 assert.equal(f.read({action:'remove',target:snap.items[0]}).state,'clicked');assert.equal(f.stats().deleted,1);
 const changed=contentFixture({status:'Приглашение'});assert.throws(()=>changed.read({action:'remove',target:snap.items[0]}));assert.equal(changed.stats().deleted,0);
});
test('unknown buttons, hidden delete and unrelated dialogs stop without destructive clicks',()=>{
 const preview=contentFixture().read({action:'scan'}).items[0];
 const hidden=contentFixture({hiddenDelete:true});assert.throws(()=>hidden.read({action:'remove',target:preview}));assert.equal(hidden.stats().deleted,0);
 const dialog=contentFixture({dialogText:'Удалить аккаунт?'});assert.throws(()=>dialog.read({action:'confirm',target:preview}));assert.equal(dialog.stats().confirmed,0);
});
test('confirmation can only click the recognized native refusal-removal dialog',()=>{
 const f=contentFixture(),preview=f.read({action:'scan'}).items[0];
 f.read({action:'remove',target:preview});f.showDialog('Удалить отклик?');
 assert.equal(f.read({action:'confirm',target:preview}).state,'confirmed');assert.equal(f.stats().confirmed,1);
});
test('cleanup entry belongs to the response stage, never collection or global pipeline footer',()=>{
 const html=fs.readFileSync(new URL('popup.html',import.meta.url),'utf8'),start=html.indexOf('id="stage5"'),end=html.indexOf('</section>',start),button=html.indexOf('id="cleanupHH"');assert.ok(button>start&&button<end);
});


test('actual HH Magritte alertdialog with nested modal confirms exactly once',()=>{
 const f=contentFixture({dialogRole:'alertdialog',nested:true}),target=f.read({action:'scan'}).items[0];
 f.read({action:'remove',target});assert.equal(f.read({action:'confirm',target}).state,'no_dialog');
 f.showDialog('Удалить отклик?');assert.equal(f.read({action:'confirm',target}).state,'confirmed');assert.equal(f.read({action:'confirm',target}).state,'already_confirmed');assert.deepEqual(f.stats(),{deleted:1,confirmed:1});
});
test('an old or manually opened removal dialog never receives an unbound confirmation click',()=>{
 const f=contentFixture({dialogRole:'alertdialog',dialogText:'Удалить отклик?'}),target=f.read({action:'scan'}).items[0];assert.throws(()=>f.read({action:'confirm',target}),/начала удаления/);assert.equal(f.stats().confirmed,0);
});


test('worker waits for a delayed HH confirmation dialog and never repeats its confirmation',async()=>{
 const f=fixture({lateDialog:true});await f.c.cleanupExecute(f.plan,[f.r]);assert.equal(f.storage.hh_cleanup_run.state,'complete');assert.equal(f.clicks.filter(x=>x==='remove').length,1);assert.equal(f.clicks.filter(x=>x==='confirm').length,3);assert.equal(f.clicks.filter(x=>x==='verify').length,5);
});
test('even after an approved removal starts, an unrelated account dialog is never confirmed',()=>{
 const f=contentFixture({dialogRole:'alertdialog'}),target=f.read({action:'scan'}).items[0];f.read({action:'remove',target});f.showDialog('Удалить аккаунт?');assert.throws(()=>f.read({action:'confirm',target}),/не подтверждён/);assert.equal(f.stats().confirmed,0);
});
