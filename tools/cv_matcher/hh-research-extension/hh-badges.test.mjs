import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=name=>fs.readFileSync(new URL(name,import.meta.url),'utf8');
test('HH badges display stored values and missing evidence, suppress scores for changed titles or CV',()=>{
 const ctx=vm.createContext({});vm.runInContext(source('hh-badges-core.js'),ctx);
 const item={saved:true,title:'ML Engineer',score:.604,coverage:55,missing_skills:['FSDP','Triton','CUDA','DiT'],missing_count:4};
 const labels=ctx.HHBadges.badges(item,{title:'ML Engineer'}).map(r=>r.text);assert.ok(labels.includes('Сохранено в БД'));assert.ok(labels.includes('Близость: 0.604'));assert.ok(labels.includes('Покрытие: 55%'));assert.ok(labels.includes('Не подтверждено: FSDP'));assert.ok(labels.includes('Ещё 1 без подтверждения'));
 for(const params of [{title:'Changed role'},{cv_ready:false}])assert.ok(ctx.HHBadges.badges(item,params).every(r=>!['score','coverage','missing'].includes(r.kind)));
 assert.equal(ctx.HHBadges.badges(null)[0].text,'Нет в локальной БД');
});
test('HH worker limits lookup to activated HH tabs, sends one selected CV hash and never returns credentials',async()=>{
 const listeners=[],session={},calls=[],injections=[],local={resume_bundle:{resumes:[{id:'selected',title:'Research CV',quality:'full',content_hash:'cv-hash',sections:[{text:'PRIVATE CV TEXT'}]}]}};
 const chrome={runtime:{id:'fixture',onMessage:{addListener:f=>listeners.push(f)}},tabs:{get:async id=>({id,url:id===1?'https://hh.ru/search/vacancy':'https://foreign.example/jobs'})},scripting:{executeScript:async data=>injections.push(data)},storage:{session:{get:async()=>session,set:async data=>Object.assign(session,data)},local:{get:async()=>local}}};
 const ctx=vm.createContext({URL,chrome,LocalResumeService:{request:async(path,data)=>{calls.push({path,data});return {items:[],cv_ready:true};}}});for(const file of ['board-core.js','board-adapters.js','board-widget-core.js','hh-badges-background.js'])vm.runInContext(source(file),ctx);
 const send=(message,sender={id:'fixture'})=>new Promise(resolve=>listeners[0](message,sender,resolve));
 assert.equal((await send({type:'hh_badges_activate',tabId:2,resume_id:'selected',goal:'DiT'})).ok,false);assert.equal(calls.length,0);
 assert.equal((await send({type:'hh_badges_activate',tabId:1,resume_id:'selected',goal:'DiT'})).ok,true);assert.equal(injections.length,1);
 const result=await send({type:'hh_badges_read',ids:['hh_1']},{id:'fixture',tab:{id:1,url:'https://hh.ru/search/vacancy'}});assert.equal(result.ok,true);assert.equal(calls[0].path,'/archive/hh-badges');assert.equal(calls[0].data.resume_hash,'cv-hash');assert.equal(calls[0].data.resume_id,'selected');assert.ok(!JSON.stringify(calls).includes('PRIVATE CV TEXT'));assert.ok(!JSON.stringify(result).includes('token'));
 assert.equal((await send({type:'hh_badges_read',ids:['hh_1']},{id:'fixture',tab:{id:3,url:'https://hh.ru/search/vacancy'}})).ok,false);assert.equal(calls.length,1);
 const sender={id:'fixture',tab:{id:1,url:'https://hh.ru/vacancy/1'}},question={type:'hh_inline',vacancy_id:'hh_1',action:'answer',question:'What models?',model:'terra'};
 assert.equal((await send({...question,form_resume_id:'other'},sender)).ok,false);assert.equal(calls.length,1);
 assert.equal((await send({...question,vacancy_id:'hh_2'},sender)).ok,false);assert.equal(calls.length,1);
 assert.equal((await send(question,sender)).ok,true);assert.equal(calls[1].path,'/archive/hh-inline');assert.equal(calls[1].data.resume_id,'selected');assert.equal(calls[1].data.resume_hash,'cv-hash');assert.equal(calls[1].data.question,'What models?');assert.equal(calls[1].data.model,'terra');assert.ok(!JSON.stringify(calls).includes('PRIVATE CV TEXT'));
});
