import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=file=>fs.readFileSync(new URL(file,import.meta.url),'utf8');
async function screen({reply,protocol='chrome-extension:'}={}){
 const elements={};for(const [,id] of source('hh-cleanup.html').matchAll(/id="([^"]+)"/g))elements[id]={disabled:false,checked:false,hidden:false,textContent:'',replaceChildren(){},querySelectorAll:()=>[]};
 let calls=0;const c=vm.createContext({location:{protocol},chrome:{runtime:{sendMessage:async()=>{calls++;return reply;}},storage:{onChanged:{addListener(){}}}},document:{getElementById:id=>elements[id],createElement:()=>({append(){},addEventListener(){}})},setTimeout,clearTimeout,setInterval(){},Date,Error,Promise});
 vm.runInContext(source('hh-cleanup.js'),c);await new Promise(r=>setImmediate(r));return {elements,calls,c};
}
test('missing cleanup handler gives actionable reload guidance instead of a generic no-response message',async()=>{
 const f=await screen();assert.match(f.elements.status.textContent,/chrome:\/\/extensions/);assert.match(f.elements.status.textContent,/Перезагрузить/);assert.match(f.elements.status.textContent,/проверьте результат/);assert.ok(!f.elements.status.textContent.includes('Удаление не запускалось'));
});
test('opening cleanup as a file explains the correct extension entry point',async()=>{
 const f=await screen({protocol:'file:'});assert.match(f.elements.status.textContent,/Отклик/);assert.equal(f.calls,0);
});
test('cleanup initial UI has no deletion action available and hides irrelevant controls',async()=>{
 const f=await screen({reply:{ok:true,busy:false}});assert.equal(f.elements.execute.disabled,true);assert.equal(f.elements.stop.hidden,true);assert.equal(f.elements.open.hidden,true);
});
async function pipeline(url){
 const elements={},buttons=Array.from({length:5},(_,i)=>({dataset:{step:String(i+1)},classList:{toggle(){}},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];}}));
 for(const [,id] of source('popup.html').matchAll(/id="([^"]+)"/g))elements[id]={textContent:'',value:'',hidden:false};
 const c=vm.createContext({chrome:{runtime:{id:'fixture'},storage:{local:{get:async()=>({pipeline_stage:3}),set:async()=>{}}},tabs:{query:async()=>[{url}]}},document:{getElementById:id=>elements[id],querySelectorAll:()=>buttons},JobBoardAdapters:{registry:[],resolve:()=>null},URL,Number,Math});vm.runInContext(source('pipeline.js'),c);await new Promise(r=>setImmediate(r));return {elements,buttons};
}
test('negotiations, chats and application forms open the response stage; vacancy search opens collection',async()=>{
 for(const url of ['https://hh.ru/applicant/negotiations','https://hh.ru/applicant/vacancy_response?vacancyId=123','https://hh.ru/chat/123']){const f=await pipeline(url);assert.equal(f.elements.stage5.hidden,false);assert.equal(f.elements.stage3.hidden,true);}
 const search=await pipeline('https://hh.ru/search/vacancy?text=ML');assert.equal(search.elements.stage3.hidden,false);
});
