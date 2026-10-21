import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
async function setup(url='https://hh.ru/search/vacancy?text=ML'){
 class Element{constructor(){this.hidden=false;this.disabled=false;this.value='';this.attributes={};this.classList={toggle:()=>{}};}setAttribute(k,v){this.attributes[k]=v;}removeAttribute(k){delete this.attributes[k];}}
 const html=fs.readFileSync(new URL('popup.html',import.meta.url),'utf8'),ids=[...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]);assert.equal(new Set(ids).size,ids.length);
 const elements=Object.fromEntries(ids.map(id=>[id,new Element()])),buttons=Array.from({length:5},(_,i)=>Object.assign(new Element(),{dataset:{step:String(i+1)}})),storage={},messages=[];
 const chrome={runtime:{id:'fixture',sendMessage:async m=>{messages.push(m);return {ok:true};}},tabs:{query:async()=>[{url}]},storage:{local:{get:async()=>storage,set:async v=>Object.assign(storage,v)}}};
 const context=vm.createContext({URL,JobBoards:null,chrome,document:{getElementById:id=>elements[id],querySelectorAll:()=>buttons}});
 for(const name of ['board-core.js','board-adapters.js','pipeline.js'])vm.runInContext(fs.readFileSync(new URL(name,import.meta.url),'utf8'),context);
 await new Promise(r=>setImmediate(r));return {elements,buttons,context,storage,messages};
}
test('pipeline shows one stage, resumes collection on an HH listing, and does not imply automatic completion',async()=>{
 const {elements:e,buttons,context,storage}=await setup();assert.equal(e.stage3.hidden,false);assert.equal([1,2,3,4,5].filter(n=>!e['stage'+n].hidden).length,1);assert.equal(e.pipelineNext.disabled,true);
 context.SearchPipeline.update({selectedCV:{title:'Research CV'},full:20});assert.equal(e.pipelineNext.disabled,false);buttons[3].onclick();assert.equal(e.stage4.hidden,false);assert.equal(storage.pipeline_stage,4);assert.equal(e.stage3.hidden,true);
 e.pipelineBack.onclick();assert.equal(e.stage3.hidden,false);
});
test('switching corporate sources separates HH filters and preserves selected resume/goal',async()=>{
 const {elements:e}=await setup('https://yandex.ru/jobs/vacancies?professions=ml-developer');assert.equal(e.pipelineSource.value,'yandex');assert.equal(e.hhCollectPanel.hidden,true);assert.equal(e.boardCollectPanel.hidden,false);
 e.resume.value='cv-id';e.searchGoal.value='Diffusion research';e.pipelineSource.value='tbank';e.pipelineSource.onchange();assert.match(e.boardUrl.value,/tbank.ru/);assert.equal(e.resume.value,'cv-id');assert.equal(e.searchGoal.value,'Diffusion research');
 e.pipelineSource.value='hh';e.pipelineSource.onchange();assert.equal(e.hhSearchPanel.hidden,false);assert.equal(e.boardSearchPanel.hidden,true);
});
test('opening detailed analysis carries the selected CV and current goal',async()=>{
 const {elements:e,messages}=await setup();e.resume.value='chosen-cv';e.searchGoal.value='  DiT  ';await e.openAnalysis.onclick();assert.deepEqual(JSON.parse(JSON.stringify(messages[0])),{type:'archive_open',resume_id:'chosen-cv',goal:'DiT'});
});
