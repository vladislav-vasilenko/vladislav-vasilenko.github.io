import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const url='https://tbank.ru/career/vacancies/all/moscow/';
function fixture({missing=false,refuse=false}={}){const clicks=[],nodes=['Аналитика и данные',...(missing?[]:['IT-разработка']),'Senior'].map((label,i)=>({type:'checkbox',checked:i===0,labels:[{innerText:label,click(){nodes[i].click();}}],closest:()=>null,getAttribute:()=>null,click(){clicks.push(label);if(!refuse)this.checked=!this.checked;}})),doc={querySelectorAll:s=>s==='button'?[]:nodes},c=vm.createContext({URL,Set,Promise,location:{href:url},JobBoards:{identity:()=>null}});vm.runInContext(fs.readFileSync(new URL('board-filter-core.js',import.meta.url),'utf8'),c);return {c,doc,nodes,clicks,run:(values=['IT-разработка'],where=url)=>c.BoardFilters.apply(doc,where,values,()=>true,async()=>{})};}
test('T-Bank IT profile is applied and confirmed; Analytics is excluded, seniority remains unrestricted',async()=>{const f=fixture(),r=await f.run();assert.equal(r.ok,true);assert.deepEqual(Array.from(r.checked),['IT-разработка']);assert.equal(f.nodes[0].checked,false);assert.equal(f.nodes[2].checked,false);assert.deepEqual(f.clicks,['Аналитика и данные','IT-разработка']);});
test('unknown or ambiguous filters stop before toggling fields; no guessed selection',async()=>{const f=fixture({missing:true});await assert.rejects(()=>f.run(),/не найден/);assert.equal(f.clicks.length,0);const a=fixture();a.nodes.push(a.nodes[1]);await assert.rejects(()=>a.run(),/однозначно/);assert.equal(a.clicks.length,0);});
test('site refusal, detail pages and foreign hosts cannot masquerade as a filtered collection',async()=>{await assert.rejects(()=>fixture({refuse:true}).run(),/не подтвердил/);for(const where of ['https://evil.test/career/vacancies/all/moscow/','http://tbank.ru/career/vacancies/all/moscow/','https://tbank.ru/career/it/vacancy/moscow/ml/1/'])await assert.rejects(()=>fixture().run(['IT-разработка'],where));});


test('IT plus ML selects both dimensions without Analytics or extra specialization',async()=>{
 const f=fixture();f.nodes.push({type:'checkbox',checked:false,labels:[{innerText:'Машинное обучение',click(){f.nodes[3].checked=!f.nodes[3].checked;}}],closest:()=>null,getAttribute:()=>null});
 const result=await f.run(['IT-разработка','Машинное обучение']);
 assert.deepEqual(Array.from(result.checked),['IT-разработка','Машинное обучение']);assert.equal(f.nodes[0].checked,false);assert.equal(f.nodes[2].checked,false);
});
test('a missing ML profession prevents collecting the broad IT listing as success',async()=>{
 const f=fixture();await assert.rejects(()=>f.run(['IT-разработка','Машинное обучение']),/Машинное обучение/);assert.deepEqual(f.clicks,[]);
});
