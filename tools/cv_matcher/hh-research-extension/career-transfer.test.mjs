import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const scripts=['board-core.js','board-adapters.js','board-widget-core.js','career-form-core.js'].map(f=>fs.readFileSync(new URL(f,import.meta.url),'utf8'));
const urls=['https://yandex.ru/jobs/vacancies/ml-11031','https://rabota.sber.ru/search/ml-123456','https://career.avito.com/vacancies/data-science/19450/','https://ozon.tech/vacancies/12345/','https://www.tbank.ru/career/it/vacancy/moscow/ml/0d772642-b21e-4529-a234-5e93b00210be/'];
function page(url=urls[2]){
 const writes=[];let onchange=()=>{};
 class Input{get files(){throw Error('Must not read files');}get value(){return this.raw||'';}set value(v){this.raw=v;writes.push([this.name,v]);}dispatchEvent(e){onchange(this,e);}}
 class Textarea extends Input{get value(){return super.value;}set value(v){super.value=v;}}
 class Select extends Input{get value(){return super.value;}set value(v){super.value=v;}}
 const field=(Ctor,type,label)=>Object.assign(new Ctor(),{tagName:Ctor===Textarea?'TEXTAREA':Ctor===Select?'SELECT':'INPUT',type,name:label,labels:[{innerText:label}],checked:false,required:false,disabled:false,getBoundingClientRect:()=>({width:100,height:40}),getAttribute:()=>null});
 const nodes=[field(Textarea,'textarea','О себе'),field(Textarea,'textarea','Сопроводительное письмо'),field(Input,'email','E-mail'),field(Input,'checkbox','Кадровый резерв'),field(Input,'file','Резюме'),field(Input,'password','Password'),field(Input,'hidden','csrfToken'),field(Select,'select','Город')];nodes[7].options=[{value:'',textContent:'Выберите'},{value:'moscow',textContent:'Москва'}];
 const form={getBoundingClientRect:()=>({width:800,height:700}),contains:()=>false,querySelector:()=>nodes[0],querySelectorAll:()=>nodes};
 const document={body:{innerText:''},querySelectorAll:s=>s==='form,[role="dialog"]'?[form]:[]};
 const ctx=vm.createContext({document,URL,location:new URL(url),getComputedStyle:()=>({display:'block',visibility:'visible'}),HTMLInputElement:Input,HTMLTextAreaElement:Textarea,HTMLSelectElement:Select,Event:class{constructor(type,options){this.type=type;Object.assign(this,options);}}});
 for(const s of scripts)vm.runInContext(s,ctx);
 const inspect=()=>ctx.CareerForms.inspect(document,url).snapshot;
 const fill=answers=>{const before=inspect();return ctx.CareerForms.fill(document,url,{source_url:url,vacancy_id:before.vacancy_id,fingerprint:before.fingerprint,answers});};
 return {ctx,document,nodes,writes,inspect,fill,onchange:fn=>{onchange=fn;}};
}
test('all five providers transfer exact approved native values and never files/consents',()=>{
 for(const url of urls){const p=page(url);const result=p.fill({f0:'Исследовательский опыт.',f1:'Мотивация из CV.',f2:'candidate@example.test',f5:'moscow'});assert.equal(result.state,'fields_filled');assert.equal(result.values.f0,'Исследовательский опыт.');assert.equal(p.nodes[3].checked,false);assert.equal(p.nodes[4].value,'');assert.equal(p.writes.length,4);assert.equal(p.inspect().execution_supported,false);}
});
test('one unsupported field rejects entire operation before any input',()=>{
 for(const id of ['f3','f4','unknown']){const p=page();assert.throws(()=>p.fill({f0:'Good',[id]:'Bad'}));assert.equal(p.writes.length,0);}
});
test('changed origin, vacancy, fingerprint and hidden closed-state stop before transfer',()=>{
 const p=page(),s=p.inspect();
 for(const change of [{source_url:'https://evil.example'},{vacancy_id:'avito_123'},{fingerprint:'changed'}])assert.throws(()=>p.ctx.CareerForms.fill(p.document,urls[2],{source_url:urls[2],vacancy_id:s.vacancy_id,fingerprint:s.fingerprint,answers:{f0:'Good'},...change}));
 p.document.body.innerText='Вакансия закрыта';assert.throws(()=>p.fill({f0:'Good'}));assert.equal(p.writes.length,0);
});
test('dynamic question changes halt and unexpected field mutations cannot be successful',()=>{
 const p=page();p.onchange((n,e)=>{if(e.type==='input')p.nodes[1].labels=[{innerText:'Другой вопрос'}];});assert.throws(()=>p.fill({f0:'First',f1:'Second'}));assert.equal(p.nodes[1].value,'');
 const q=page();q.onchange((n,e)=>{if(e.type==='change')q.nodes[3].checked=true;});assert.throws(()=>q.fill({f0:'First'}));
});
test('company worker runs without an HH tab and journals a fill receipt, never a submit',async()=>{
 const calls=[],local={},binding={tab_id:7,source_url:urls[2],resume_id:'cv',resume_hash:'hash'},app={context:{channel:'career',resume_id:'cv',resume_hash:'hash',vacancy:{id:'avito_19450'}}};
 const command={id:'command',app_id:'app',application:app},snapshot={state:'questionnaire',source_url:urls[2],fingerprint:'fp'},intent={source_url:urls[2],form_fingerprint:'fp',answers:{f0:'Reviewed'}};
 const ctx=vm.createContext({URL,crypto:{randomUUID:()=> 'career-worker'},activeJobs:new Set(),chrome:{storage:{session:{get:async()=>({career_form_bindings:{app:binding},career_worker_id:'career-worker'}),set:async()=>{}},local:{get:async key=>key==='resume_bundle'?{resume_bundle:{resumes:[{id:'cv',content_hash:'hash'}]}}:local,set:async x=>Object.assign(local,x),remove:async k=>{delete local[k];}}},tabs:{get:async()=>({url:urls[2]})},scripting:{executeScript:async()=>{}}},workflowCall:async data=>{calls.push(data);return data.op==='next'?{command:data.kinds[0]==='career_open'?null:command}:data.op==='career_fill_claim'?intent:{ok:true};},wfScript:async()=>snapshot});
 vm.runInContext(fs.readFileSync(new URL('career-workflow.js',import.meta.url),'utf8'),ctx);
 // Exercise the worker with an independently tested field transfer implementation.
 ctx.careerInspect=async(id,config)=>config?{state:'fields_filled',source_url:urls[2],values:{f0:'Reviewed'}}:snapshot;
 await ctx.careerWorkflowPulse();assert.deepEqual(calls.map(c=>c.op),['next','next','career_fill_claim','career_fill_result']);assert.equal(calls[0].kinds[0],'career_open');assert.equal(calls[1].kinds[0],'career_fill');assert.equal(calls[3].result.state,'fields_filled');assert.deepEqual(Object.keys(local),[]);
});

test('phone formatting masks preserve the approved digits without weakening other values',()=>{
 const p=page();p.nodes[2].type='text';p.nodes[2].labels=[{innerText:'Номер телефона*'}];p.onchange((n,e)=>{if(n===p.nodes[2]&&e.type==='change')n.raw='+7 (999) 111-22-33';});const r=p.fill({f2:'+79991112233'});assert.equal(r.values.f2,'+7 (999) 111-22-33');
 const q=page();q.nodes[2].type='text';q.nodes[2].labels=[{innerText:'Номер телефона*'}];q.onchange((n,e)=>{if(n===q.nodes[2]&&e.type==='change')n.raw='+7 (999) 111-22-34';});assert.throws(()=>q.fill({f2:'+79991112233'}));
});

test('resume URL is recognized separately from profile contacts and transfers as an approved value',()=>{
 const p=page();p.nodes[2].type='text';p.nodes[2].labels=[{innerText:'Ссылка на резюме'}];const s=p.inspect();assert.equal(s.fields[2].purpose,'resume_url');assert.equal(p.fill({f2:'https://hh.ru/resume/selected'}).values.f2,'https://hh.ru/resume/selected');
});
test('Avito preparation reveals link mode without input, but preserves an attached file and skips other boards',async()=>{
 for(const attached of [false,true]){
  const p=page(),radio=(label,checked)=>({tagName:'INPUT',type:'radio',name:'resume_source',labels:[{innerText:label}],checked,value:'',required:false,disabled:false,getBoundingClientRect:()=>({width:50,height:30}),getAttribute:()=>null});
  const fileMode=radio('Файл',true),linkMode=radio('Ссылка',false),file=p.nodes[4];file.raw=attached?'C:\\fakepath\\my-cv.pdf':'';let clicks=0;
  p.nodes.push(fileMode,linkMode);const form=p.ctx.CareerForms.inspect(p.document,urls[2]).form;form.querySelectorAll=selector=>selector==='input[type="file"]'?[file]:p.nodes;
  linkMode.click=()=>{clicks++;fileMode.checked=false;linkMode.checked=true;p.nodes[2].type='url';p.nodes[2].labels=[{innerText:'Ссылка на резюме'}];};
  p.ctx.setTimeout=fn=>fn();const snapshot=await p.ctx.CareerForms.prepareResumeLink(p.document,urls[2]);assert.equal(clicks,attached?0:1);assert.equal(p.writes.length,0);assert.equal(snapshot.fields.some(f=>f.purpose==='resume_url'),!attached);assert.equal(p.nodes[3].checked,false);
 }
 const q=page(urls[0]);assert.equal((await q.ctx.CareerForms.prepareResumeLink(q.document,urls[0])).provider,'yandex');assert.equal(q.writes.length,0);
});

test('form extraction errors preserve the actionable cause rather than a generic null snapshot',async()=>{
 const c=vm.createContext({chrome:{scripting:{executeScript:async()=>{}}},wfScript:async()=>({state:'read_error',error:'Откройте форму отклика и повторите чтение.'})});vm.runInContext(fs.readFileSync(new URL('career-workflow.js',import.meta.url),'utf8'),c);await assert.rejects(()=>c.careerInspect(1),/Откройте форму отклика/);
});

function cityPage({labels=['Россия, г Москва'],ignoreClick=false}={}){
 const p=page(urls[4]),input=p.nodes[7];input.tagName='INPUT';input.type='text';input.getAttribute=k=>k==='role'?'combobox':k==='aria-controls'?'cities':null;let opened=false,chosen=0;
 input.click=()=>{opened=true;};
 const list={querySelectorAll:()=>labels.map(label=>({innerText:label,getAttribute:()=>null,getBoundingClientRect:()=>({width:200,height:40}),click(){chosen++;if(!ignoreClick){input.raw=label;opened=false;}}}))};
 p.document.getElementById=id=>id==='cities'&&opened?list:null;
 const original=p.document.querySelectorAll;p.document.querySelectorAll=selector=>selector==='[role="listbox"]'?(opened?[list]:[]):original(selector);
 const apply=async()=>{const snapshot=p.inspect();return p.ctx.CareerForms.fillApproved(p.document,urls[4],{source_url:urls[4],vacancy_id:snapshot.vacancy_id,fingerprint:snapshot.fingerprint,answers:{f5:'Россия, г Москва',f2:'candidate@example.test'}},()=>true,async()=>{});};
 return {...p,apply,chosen:()=>chosen};
}
test('T-Bank city is selected as an exact actual option before native profile fields transfer',async()=>{
 const p=cityPage(),result=await p.apply();assert.equal(result.values.f5,'Россия, г Москва');assert.equal(p.chosen(),1);assert.equal(result.values.f2,'candidate@example.test');assert.equal(p.nodes[3].checked,false);assert.equal(p.nodes[4].value,'');
});
test('typing Moscow without a matching accepted city option never counts as a successful transfer',async()=>{
 for(const settings of [{labels:['Москва, США']},{labels:['Россия, г Москва','Россия, г Москва']},{ignoreClick:true}]){
  const p=cityPage(settings);await assert.rejects(()=>p.apply(),/город|Город|списков/);assert.equal(p.nodes[2].value,'');assert.equal(p.nodes[3].checked,false);
 }
});

test('T-Bank portfolio preparation reveals only the exact empty field without transferring values',async()=>{
 const p=page(urls[4]),form=p.ctx.CareerForms.inspect(p.document,urls[4]).form;let clicks=0;
 const button={innerText:'Добавить портфолио',getBoundingClientRect:()=>({width:120,height:40}),click(){clicks++;const node=Object.assign(Object.create(Object.getPrototypeOf(p.nodes[2])),p.nodes[2]);node.name='portfolio';node.labels=[{innerText:'Ссылка на портфолио'}];node.raw='';p.nodes.push(node);}};
 form.querySelectorAll=selector=>selector==='button,a,[role="button"]'?[button]:p.nodes;p.ctx.setTimeout=fn=>fn();
 const result=await p.ctx.CareerForms.prepareProfile(p.document,urls[4],{portfolio:true});assert.equal(clicks,1);assert.ok(result.fields.some(f=>f.label==='Ссылка на портфолио'&&f.purpose==='contact'));assert.equal(p.writes.length,0);assert.equal(p.nodes[3].checked,false);
 await p.ctx.CareerForms.prepareProfile(p.document,urls[4],{portfolio:true});assert.equal(clicks,1);
});
