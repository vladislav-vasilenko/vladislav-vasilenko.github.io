import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=file=>fs.readFileSync(new URL(file,import.meta.url),'utf8');
const core={URL};vm.runInNewContext(source('resume-bump-core.js'),core);const B=core.HHResumeBump,rid='a'.repeat(38);
test('bump recognizes exact own-profile URL and free label; paid and publish controls never qualify',()=>{
 assert.ok(B.page('https://hh.ru/applicant/profile/me'));for(const u of ['https://evil.test/applicant/profile/me','https://hh.ru/resume/'+rid,'https://hh.ru/applicant/profile/me?x=1'])assert.equal(B.page(u),false);
 assert.ok(B.freeLabel('Поднять в поиске'));for(const text of ['Автоподнятие','Сделать видимым','Купить поднятие','Поднять за 100 ₽'])assert.equal(B.freeLabel(text),false);
 assert.equal(B.id('/resume/'+rid),rid);assert.equal(B.id('/search/vacancy?resume='+rid+'&from=resumelist'),rid);assert.equal(B.id('https://evil.test/resume/'+rid),null);
});
test('hidden/unpublished/ambiguous cards cannot be bumped even when a free-looking control exists',()=>{
 const row={ids:[rid],buttons:[{enabled:true,paid:false}]};assert.equal(B.state(row),'available');assert.equal(B.state({...row,buttons:[{enabled:false}]}),'cooldown');
 for(const patch of [{hidden:true},{unpublished:true}])assert.equal(B.state({...row,...patch}),'not_visible');
 for(const patch of [{ids:[rid,'b'.repeat(38)]},{buttons:[{enabled:true,paid:true}]},{buttons:[{enabled:true},{enabled:true}]}, {buttons:[]}])assert.equal(B.state({...row,...patch}),'needs_input');
});
function worker({initial='available',after='cooldown',deny=false}={}){
 const events=[],jobs=new Set();let action;
 const ctx=vm.createContext({Date,Promise,Error,Set,activeJobs:jobs,setTimeout:(fn,ms)=>{if(ms<1000)queueMicrotask(fn);return 1;},clearTimeout(){},chrome:{permissions:{contains:async()=>true},tabs:{create:async()=>({id:7}),get:async()=>({active:false}),remove:async()=>events.push('closed')},scripting:{executeScript:async input=>{action=input.args[0];}}},navigate:async(_id,url)=>events.push(url),workflowCall:async data=>{events.push(data.op);if(deny)throw Error('revoked');},wfScript:async()=>{events.push(action.action);return {state:action.action==='click'?'clicked':events.includes('click')?after:initial,resume_id:rid,fingerprint:'bound-card',source_url:'https://hh.ru/applicant/profile/me',evidence:'HH shows cooldown'};}});
 vm.runInContext(source('resume-bump-worker.js'),ctx);return {events,jobs,run:()=>ctx.wfBumpResume({id:'command',payload:{resume_id:rid}},'bump-worker')};
}
test('worker claims once before a single free click and verifies the selected card, without API or form submission',async()=>{
 const f=worker(),result=await f.run();assert.equal(result.outcome,'raised');assert.equal(f.events.filter(e=>e==='click').length,1);assert.ok(f.events.indexOf('resume_bump_claim')<f.events.indexOf('click'));assert.ok(f.events.includes('closed'));assert.equal(f.jobs.size,0);
});
test('cooldown/hidden cards and revoked owner policy never receive a click',async()=>{
 for(const initial of ['cooldown','not_visible','needs_input']){const f=worker({initial}),r=await f.run();assert.equal(r.outcome,initial);assert.ok(!f.events.includes('resume_bump_claim'));assert.ok(!f.events.includes('click'));}
 const f=worker({deny:true});await assert.rejects(f.run(),/revoked/);assert.ok(!f.events.includes('click'));assert.ok(f.events.includes('closed'));
});
test('unconfirmed HH result stops after one click; verification never retries it',async()=>{
 const f=worker({after:'available'}),result=await f.run();assert.equal(result.state,'uncertain');assert.equal(f.events.filter(e=>e==='click').length,1);
});
function content({hidden=false,paid=false,queryLink=false}={}){
 let clicks=0;
 class Node{
  constructor(tag,text='',attrs={},children=[]){this.tagName=tag;this.text=text;this.attrs=attrs;this.children=children;this.disabled=false;for(const n of children)n.parentElement=this;}
  get innerText(){return [this.text,...this.children.map(n=>n.innerText)].join(' ');}
  get href(){return new URL(this.attrs.href||'#','https://hh.ru').href;}
  getAttribute(key){return this.attrs[key]??null;}
  getBoundingClientRect(){return {width:100,height:20};}
  querySelectorAll(selector){const all=this.children.flatMap(n=>[n,...n.querySelectorAll('*')]);return all.filter(n=>selector==='*'||selector==='a[href]'&&n.tagName==='A'&&n.attrs.href||selector==='button,a,[role="button"],[role="link"]'&&(n.tagName==='A'||n.tagName==='BUTTON'||n.attrs.role==='button'||n.attrs.role==='link'));}
  click(){clicks++;this.disabled=true;}
 }
 const own=new Node(paid?'A':'BUTTON','Поднять в поиске',paid?{href:'/applicant/services'}:{}),foreign=new Node('BUTTON','Поднять в поиске');
 const card=new Node('ARTICLE',hidden?'Сделать видимым':'',{},[new Node('H3','',{},[new Node(queryLink?'BUTTON':'A','Research CV',queryLink?{}:{href:'/resume/'+rid})]),...(queryLink?[new Node('A','1324 вакансии',{href:'/search/vacancy?resume='+rid+'&from=resumelist'})]:[]),own]);
 const body=new Node('BODY','',{},[card,new Node('ARTICLE','',{},[new Node('A','Other CV',{href:'/resume/'+'b'.repeat(38)}),foreign])]);
 const document={body,querySelector:()=>null,querySelectorAll:s=>s==='a[href]'?body.querySelectorAll(s):[]};
 const ctx=vm.createContext({document,location:{href:'https://hh.ru/applicant/profile/me'},getComputedStyle:()=>({visibility:'visible',display:'block'}),Date,JSON,URL,Set,Error});vm.runInContext(source('resume-bump-core.js'),ctx);
 return {own,foreign,read(action){ctx.__hhResumeBumpAction={resume_id:rid,action:'inspect',...action};return vm.runInContext(source('resume-bump-content.js'),ctx);},clicks:()=>clicks};
}
test('content binds the exact resume card, clicks once, and reads its disabled control as confirmation',()=>{
 const f=content(),before=f.read();assert.equal(before.state,'available');f.read({action:'click',fingerprint:before.fingerprint,command_id:'one',expires_at:Date.now()+10000});assert.equal(f.clicks(),1);assert.equal(f.foreign.disabled,false);assert.equal(f.read().state,'cooldown');
 f.own.disabled=false;assert.throws(()=>f.read({action:'click',fingerprint:before.fingerprint,command_id:'one',expires_at:Date.now()+10000}),/Повторный клик/);assert.equal(f.clicks(),1);
});
test('content never publishes hidden resumes, opens services, or clicks stale/expired cards',()=>{
 for(const f of [content({hidden:true}),content({paid:true})]){const before=f.read();assert.notEqual(before.state,'available');assert.throws(()=>f.read({action:'click',fingerprint:before.fingerprint,command_id:'one',expires_at:Date.now()+10000}));assert.equal(f.clicks(),0);}
 const f=content(),before=f.read();for(const extra of [{fingerprint:'changed',expires_at:Date.now()+10000},{fingerprint:before.fingerprint,expires_at:Date.now()-1}])assert.throws(()=>f.read({action:'click',command_id:'one',...extra}));assert.equal(f.clicks(),0);
});
test('current HH title-button cards bind through adjacent recommendation links',()=>{
 const f=content({queryLink:true}),before=f.read();assert.equal(before.state,'available');f.read({action:'click',fingerprint:before.fingerprint,command_id:'current',expires_at:Date.now()+10000});assert.equal(f.clicks(),1);assert.equal(f.foreign.disabled,false);
});
test('a stalled Chrome script has a bounded failure and is not retried by the timeout helper',async()=>{
 let calls=0;const ctx=vm.createContext({Promise,Error,setTimeout,clearTimeout});vm.runInContext(source('resume-bump-worker.js'),ctx);const stalled=new Promise(()=>{calls++;});await assert.rejects(ctx.bumpBounded(stalled,'чтение карточки',5),/автоматического повторного клика/);assert.equal(calls,1);
});
