import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element{constructor(tag){this.tag=tag;this.children=[];this.disabled=false;this.attributes={};}append(...rows){this.children.push(...rows);}replaceChildren(...rows){this.children=rows;}setAttribute(k,v){this.attributes[k]=v;}}
function ui(){const context=vm.createContext({Date,URLSearchParams,document:{createElement:tag=>new Element(tag),createTextNode:text=>text}});vm.runInContext(fs.readFileSync(new URL('../skill-analysis-ui.js',import.meta.url),'utf8'),context);return context.SkillAnalysis;}
const ctx={resume_id:'chosen-cv',vacancy_id:'hh_1',goal:'Generative research'},metric={percent:50,requirements:2,statuses:{confirmed:1,partial:0,studying:0,not_evidenced:1,explicit_gap:0}},report={recommendation:'clarify',recommendation_reason:'Уточните опыт.',metrics:{overall:metric,must:metric,dimensions:[]},requirements:[],questions:[],limitations:[],rubric:'Покрытие текста, не вероятность найма.',created_at:'2026-10-15T12:00:00Z',model:'gpt-6-luna',cached:true};
test('opening a vacancy only reads saved analysis; model generation requires its explicit button',async()=>{
 const calls=[],parent=new Element('div');ui().attach(parent,{context:ctx,isCurrent:()=>true,api:async(path,body)=>{calls.push({path,body});return body?report:{analysis:null};}});await new Promise(r=>setImmediate(r));
 assert.equal(calls.length,1);assert.equal(calls[0].body,undefined);assert.ok(calls[0].path.startsWith('skill-analysis?'));
 const button=parent.children[0].children[2];assert.equal(button.disabled,false);await button.onclick();assert.equal(calls.length,2);assert.equal(calls[1].path,'skill-analysis');assert.equal(calls[1].body.resume_id,'chosen-cv');assert.equal(button.textContent,'Разбор сохранён');
});
test('existing cached analysis is displayed without a paid request and the generate button stays disabled',async()=>{
 let calls=0;const parent=new Element('div');ui().attach(parent,{context:ctx,isCurrent:()=>true,api:async(path,body)=>{calls++;assert.equal(body,undefined);return {analysis:report};}});await new Promise(r=>setImmediate(r));assert.equal(calls,1);assert.equal(parent.children[0].children[2].disabled,true);assert.ok(parent.children[0].children[4].children.length>0);
});
test('a response arriving after the selected CV or vacancy changes is not shown in the new context',async()=>{
 let current=true,resolve;const parent=new Element('div');ui().attach(parent,{context:ctx,isCurrent:()=>current,api:()=>new Promise(r=>resolve=r)});current=false;resolve({analysis:report});await new Promise(r=>setImmediate(r));assert.equal(parent.children[0].children[4].children.length,0);
});
