import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const fixtures=[
 ['avito','https://career.avito.com/vacancies/','https://career.avito.com/vacancies/data-science/19450/','avito_19450'],
 ['ozon','https://ozon.tech/vacancies/','https://ozon.tech/vacancies/12345/','ozon_12345'],
 ['ozon','https://career.ozon.ru/vacancy/?query=ML','https://career.ozon.ru/fintech/vacancy?id=137587804','ozon_137587804'],
 ['yandex','https://yandex.ru/jobs/professions/ml-developer','https://yandex.ru/jobs/vacancies/ml-engineer-20372','yandex_20372'],
 ['tbank','https://www.tbank.ru/career/vacancies/all/moscow/','https://www.tbank.ru/career/it/vacancy/moscow/ml-engineer/0d772642-b21e-4529-a234-5e93b00210be/','tbank_0d772642-b21e-4529-a234-5e93b00210be']
];
function worker(url){let page=url;const listeners=[],session={},calls=[],scripts=[],state={resume_bundle:{resumes:[{id:'cv',quality:'full',title:'Research CV',content_hash:'v1',sections:[{text:'PRIVATE RESUME'}]}]},cover_model:'terra'};let syncs=0;
 const chrome={runtime:{id:'test',onMessage:{addListener:f=>listeners.push(f)}},tabs:{get:async id=>({id,url:page}),onUpdated:{addListener(){}}},scripting:{executeScript:async params=>{scripts.push(params);return [{result:{vacancies:params.files?.includes('board-content.js')?[{id:'current',title:'Current page',description_quality:'snippet'}]:[]}}];}},storage:{session:{get:async()=>session,set:async value=>Object.assign(session,value)},local:{get:async()=>state,set:async value=>Object.assign(state,value)}}};
 const ctx=vm.createContext({URL,Date,setTimeout,chrome,archiveRunning:false,archiveSync:async()=>{syncs++;return {ok:true};},ResearchSearch:{mergeVacancies:(a,b)=>[...a,...b]},ArchiveSyncCore:{record:async(kind,id,data)=>({kind,id,data}),batches:rows=>rows.length?[rows]:[]},LocalResumeService:{request:async(path,data)=>{if(path==='/archive/sync'){syncs++;return {rejected:[]};}calls.push({path,data});return {items:[],cv_ready:true};}}});
 for(const file of ['board-core.js','board-adapters.js','board-widget-core.js','hh-badges-background.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),ctx);
 return {ctx,calls,scripts,state,get syncs(){return syncs;},set url(u){page=u;},send:(message,content=false)=>new Promise(resolve=>listeners[0](message,{id:'test',...(content?{tab:{id:1,url:page}}:{})},resolve))};
}
test('all employer boards activate with explicit CV, sync locally and reuse the inline transport',async()=>{
 for(const [provider,url,detail,id] of fixtures){const w=worker(url);assert.equal((await w.send({type:'hh_badges_activate',tabId:1,resume_id:'cv',goal:'DiT'})).ok,true,provider);assert.equal(w.syncs,1);assert.ok(w.scripts.some(s=>s.files.includes('board-widget-core.js')));
  const metadata=await w.send({type:'hh_badges_read',ids:[id]},true);assert.equal(metadata.ok,true);assert.equal(metadata.cover_model,'terra');assert.equal(w.calls[0].data.provider,provider);assert.equal(w.calls[0].data.resume_hash,'v1');assert.ok(!w.scripts.some(s=>s.files.includes('hh-sync-content.js')));assert.ok(!JSON.stringify(w.calls).includes('PRIVATE RESUME'));
  for(const action of ['analysis_read','analysis_export','cover_read','cover_export'])assert.equal((await w.send({type:'hh_inline',vacancy_id:id,action},true)).ok,true);
  assert.equal((await w.send({type:'hh_inline',vacancy_id:'hh_1',action:'analysis'},true)).ok,false);
  w.url=detail;assert.equal((await w.send({type:'hh_inline',vacancy_id:id,action:'analysis_read'},true)).ok,true);
  assert.equal((await w.send({type:'hh_inline',vacancy_id:provider+'_99999',action:'cover'},true)).ok,false);
  w.url='https://evil.example/jobs';assert.equal((await w.send({type:'hh_badges_read',ids:[id]},true)).ok,false);
 }
});
test('widget adapters are path and host scoped; Ozon layouts stay distinct',()=>{
 const w=worker(fixtures[0][1]),b=w.ctx.BoardWidgets;
 for(const url of ['https://www.tbank.ru/invest/','https://yandex.ru/mail','https://ozon.tech/blog/','https://career.avito.com.evil.test/vacancies/','http://career.avito.com/vacancies/'])assert.equal(b.provider(url),null);
 assert.notEqual(w.ctx.JobBoardAdapters.resolve(fixtures[1][1]).board_id,w.ctx.JobBoardAdapters.resolve(fixtures[2][1]).board_id);
 assert.equal(b.valid('avito_19450','ozon'),false);assert.equal(b.valid('tbank_bad-id','tbank'),false);
});
