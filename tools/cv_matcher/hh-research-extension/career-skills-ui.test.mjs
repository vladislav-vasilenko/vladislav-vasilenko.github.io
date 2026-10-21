import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.value='';this.isConnected=true;this.style={};this.textContent='';}
 append(...children){this.children.push(...children);for(const c of children)if(c&&typeof c==='object')c.parentElement=this;if(this.tagName==='select'&&!this.value)this.value=children[0]?.value||'';}
 replaceChildren(...children){this.children=children;}
 setAttribute(k,v){this.attributes[k]=v;}
 remove(){} scrollIntoView(){}
}
function env(){
 const elements=new Map(),head=new Element('head'),errors=[],snapshot={resume:{id:'fixture_cv',title:'CV',goal:'Research',model:'small'},rows:[],taxonomy:[{id:'other',label:'Other'}],skills:{learning_evidence:[],github_links:[]},methodology:[],as_of:new Date().toISOString()};
 const document={head,createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),getElementById:id=>{if(!elements.has(id)){const e=new Element('div');e.value='small';elements.set(id,e);}return elements.get(id);}};
 const context=vm.createContext({document,console,URL,location:{href:"http://127.0.0.1:8788/?view=analytics"},URLSearchParams,setTimeout,clearTimeout,localStorage:{getItem:()=>null,setItem(){}},summaryData:{goal:'Research'},api:async path=>path.startsWith('entities')?{items:[{id:'fixture_cv',title:'CV'}]}:snapshot,showDiagnostic:(e,op)=>errors.push({message:e.message,op}),CareerCharts:{categoryColors:['#333'],filters:r=>r,opportunityMap:()=>({points:[],total:0,missing:0}),stageLabels:{}}});
 return {context,elements,head,errors};
}
test('analytics still renders when new skills asset is missing; failure has a retry',async()=>{
 const e=env();e.head.append=(script)=>{queueMicrotask(()=>script.onerror());};
 vm.runInContext(fs.readFileSync(new URL('../archive-web/career-analytics.js',import.meta.url),'utf8'),e.context);
 await vm.runInContext('CareerAnalytics.enter("fixture_cv")',e.context);await new Promise(setImmediate);
 assert.equal(e.errors.length,1);assert.equal(e.errors[0].op,'Загрузка модуля навыков');assert.doesNotMatch(e.errors[0].message,/is not defined/);
 const labels=[];function walk(n){if(n.textContent)labels.push(n.textContent);for(const c of n.children||[])walk(c);}walk(e.elements.get('analytics'));
 assert.ok(labels.includes('Career Opportunity Map'));assert.ok(labels.includes('Повторить загрузку навыков'));
});
test('skills panel mount uses authenticated common API and waits for explicit plan click',async()=>{
 const e=env(),calls=[];e.context.api=async(_path,p)=>{calls.push(p.op);return {tracks:[{id:'generative',label:'Generative'}],skills:[],actions:{}};};
 vm.runInContext(fs.readFileSync(new URL('../archive-web/career-skills.js',import.meta.url),'utf8'),e.context);e.context.fixtureRoot=new Element('div');
 await vm.runInContext('CareerSkills.mount(fixtureRoot)',e.context);vm.runInContext('CareerSkills.update({resume_id:"fixture"})',e.context);
 assert.deepEqual(calls,['skills_catalog']);
});
