import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = name => fs.readFileSync(new URL('../archive-web/'+name+'.js', import.meta.url), 'utf8');
const core = vm.createContext({}); vm.runInContext(source('workflow-core'), core);
const {WorkflowCore} = core;
const application = (channel='career', state='draft', draft='', form=null, status='queued') => ({id:'app',status,context:{channel,vacancy:{link:'https://career.avito.com/vacancies/data-science/19450/'},resume_title:'Selected CV'},workflow:{state,draft,form,revision:2},commands:[],form_answers:{values:{f0:'Saved answer'},revisions:{f0:3},from_profile:{},from_resume:{}},draft_versions:[],discussion:[]});
const ready={can_prepare:true,activity_fresh:true,browser:{connected:true}};

test('next action follows channel and durable state, including company letter -> form', () => {
 for (const [channel,state,draft,form,status,expected] of [
  ['career','draft','',null,'queued','fit'],
  ['career','draft','Letter',null,'queued','form'],
  ['career','needs_input','Letter',{fields:[]},'queued','review'],
  ['career','fill_approved','Letter',{fields:[]},'queued','form'],
  ['career','filling','Letter',{fields:[]},'queued','form'],
  ['career','fields_filled','Letter',null,'queued','manual'],
  ['career','uncertain','Letter',{fields:[]},'queued','manual'],
  ['career','submitted','Letter',null,'submitted','manual'],
  ['hh','uncertain','Letter',{fields:[]},'queued','recovery'],
  ['hh','submitted','Letter',null,'submitted','messages'],
  ['telegram','draft','Letter',null,'queued','telegram']
 ]) assert.equal(WorkflowCore.nextStep(application(channel,state,draft,form,status),ready).target,expected);
 assert.equal(WorkflowCore.nextStep(application('career','needs_input','Letter',{fields:[]}),{...ready,activity_fresh:false}).target,'sources');
 assert.equal(WorkflowCore.nextStep(application('career','draft','Letter'),{...ready,can_prepare:false}).target,'sources');
 // A recently approved operation must not be presented as an idle freshness check.
 assert.equal(WorkflowCore.nextStep(application('career','filling','Letter',{}),{...ready,activity_fresh:false}).target,'form');
});

test('company connectivity never falls back to HH connectivity; damaged receipts remain readable',()=>{
 assert.equal(WorkflowCore.careerConnection(undefined).state,'offline');
 assert.equal(WorkflowCore.careerConnection({connected:true}).state,'ready');
 for(const result of ['broken','null','[]',undefined])assert.deepEqual({...WorkflowCore.commandResult({result})},{});
 assert.equal(WorkflowCore.commandResult({result:'{"note":"Open the questionnaire"}'}).note,'Open the questionnaire');
});

class Element {
 constructor(tag,text=''){this.tagName=tag;this.textContent=text;this.children=[];this.attributes={};this.dataset={};this.value='';this.style={};}
 append(...nodes){this.children.push(...nodes);for(const n of nodes)if(n&&typeof n==='object')n.parentElement=this;}
 replaceChildren(...nodes){this.children=[];this.append(...nodes);}
 setAttribute(k,v){this.attributes[k]=v;}
 focus(){} select(){}
}
const all = node => [node,...(node.children||[]).filter(n=>typeof n==='object').flatMap(all)];
function ui(module='workflow-career') {
 const calls=[],opens=[],messages=[],reveals=[];let current=true,handler=async()=>({});
 const context=vm.createContext({WorkflowCore,document:{createTextNode:t=>t},make:(t,cls,text)=>new Element(t,text),notice:t=>messages.push(t),date:t=>String(t),external:(url,label)=>new Element('a',label),navigator:{clipboard:{writeText:async()=>{}}},Journey:{connect:async()=>{}},ChatGPTExport:{coverTask:()=>{},buildApplicationPackage:()=> 'offline'},crypto:{randomUUID:()=> 'request'}});
 vm.runInContext(source(module),context);
 const app=application('career','needs_input','Letter',{adapter_version:'career-fields-v2',fingerprint:'fp',fields:[{id:'f0',label:'Your project',type:'textarea',purpose:'question'},{id:'f1',label:'Resume file',type:'file',manual_only:true}]});
 const p=new Element('main');
 const options={a:app,w:app.workflow,c:app.context,p,id:app.id,locked:false,lt:{value:'Letter'},ct:{value:''},model:{value:'luna'},isCurrent:()=>current,call:async(op,data)=>{calls.push({op,...data});return handler(op,data);},open:async id=>opens.push(id),reveal:(_,key)=>reveals.push(key),button:(label,fn)=>Object.assign(new Element('button',label),{onclick:fn}),section:title=>{const s=new Element('section');s.append(new Element('h3',title));return s;},copyOffline:async()=>{},labels:{queued:'Queued'},readiness:ready,letterPreferences:new Map(),hhKnown:null,sent:false,text:(label,value)=>{const l=new Element('label',label),i=new Element('textarea');i.value=value||'';l.append(i);return [l,i];}};
 const find=label=>all(p).find(n=>n.textContent===label);
 const renderer=vm.runInContext(module==='workflow-career'?'WorkflowCareer':'WorkflowLetter',context);
 const render=()=>renderer.render(options);
 return {calls,opens,messages,reveals,options,find,render,p,all:()=>all(p),setHandler:fn=>handler=fn,setCurrent:value=>current=value};
}

test('rendering a company case does not call API or transfer data; there is one form action',async()=>{
 const e=ui();e.render();assert.equal(e.calls.length,0);
 assert.equal(e.all().filter(n=>n.textContent==='Перечитать форму в Chrome').length,1);
 await e.find('Перечитать форму в Chrome').onclick();assert.equal(e.calls[0].op,'career_open');
 assert.equal(e.all().filter(n=>n.tagName==='textarea').length,1); // File remains manual.
 e.setHandler(async()=>({revisions:{f0:4}}));await e.find('Сохранить ответ').onclick();assert.equal(e.calls[1].op,'field_answer');assert.equal(e.calls[1].revision,3);
});
const intent={source_url:'https://career.avito.com/vacancies/data-science/19450/',revision:2,form_snapshot:{fields:[{id:'f0',label:'Your project'}]},answers:{f0:'Reviewed answer'},manual_fields:['Resume file'],limitations:[],intent_hash:'hash'};
test('transfer needs a fresh preview, explicit check and current readiness',async()=>{
 const e=ui();e.setHandler(async op=>op==='career_fill_intent'?intent:op==='application_readiness'?ready:{revisions:{f0:4}});e.render();
 await e.find('Проверить, что будет заполнено').onclick();
 const approve=e.find('Разрешить заполнение полей');await assert.rejects(()=>approve.onclick(),/Подтвердите/);
 assert.equal(e.calls.filter(c=>c.op==='career_fill_approve').length,0);
 e.all().find(n=>n.type==='checkbox').checked=true;await approve.onclick();
 assert.deepEqual(e.calls.map(c=>c.op),['career_fill_intent','application_readiness','career_fill_approve']);assert.equal(e.calls[2].intent_hash,'hash');assert.equal(e.calls[2].confirmed,true);
});
test('stale activity and a replaced card cannot approve or receive an old preview',async()=>{
 const e=ui();e.setHandler(async op=>op==='career_fill_intent'?intent:{...ready,activity_fresh:false});e.render();await e.find('Проверить, что будет заполнено').onclick();e.all().find(n=>n.type==='checkbox').checked=true;
 await assert.rejects(()=>e.find('Разрешить заполнение полей').onclick(),/обновите/);assert.deepEqual(e.reveals,['sources']);assert.equal(e.calls.some(c=>c.op==='career_fill_approve'),false);
 const stale=ui();stale.setHandler(async()=>{stale.setCurrent(false);return intent;});stale.render();await stale.find('Проверить, что будет заполнено').onclick();assert.equal(stale.find('Разрешить заполнение полей'),undefined);
});
test('letter editor preserves save -> chat revision order, and stale replies do not reopen a card',async()=>{
 const e=ui('workflow-letter');e.options.a.workflow.form=null;e.options.a.workflow.state='draft';e.options.w=e.options.a.workflow;
 const editor=e.render();assert.equal(e.calls.length,0);editor.lt.value='Edited letter';
 e.setHandler(async op=>op==='draft'?{workflow:{revision:3,draft:'Edited letter'}}:{draft_applied:true});
 await e.find('Сгенерировать другой вариант').onclick();assert.deepEqual(e.calls.map(c=>c.op),['draft','chat']);assert.equal(e.options.w.revision,3);assert.deepEqual(e.opens,['app']);
 const stale=ui('workflow-letter');stale.render();stale.setHandler(async()=>{stale.setCurrent(false);return {draft_applied:true};});await stale.find('Сгенерировать другой вариант').onclick();assert.deepEqual(stale.opens,[]);
});
test('all workflow dependencies are declared before the shell and included in asset routes',()=>{
 const html=fs.readFileSync(new URL('../archive-web/index.html',import.meta.url),'utf8'),routes=fs.readFileSync(new URL('../src/archive_routes.py',import.meta.url),'utf8');
 for(const name of ['workflow-core','workflow-letter','workflow-career']){assert.ok(html.indexOf('/assets/'+name+'.js')<html.indexOf('/assets/workflow.js'));assert.ok(routes.includes("'"+name+".js'"));new vm.Script(source(name));}
 new vm.Script(source('workflow'));
});
