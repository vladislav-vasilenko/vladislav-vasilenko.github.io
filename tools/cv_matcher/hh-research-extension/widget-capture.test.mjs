import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
test('single company widget sync ignores unrelated broken cache records and preserves targeted errors',async()=>{
 const good={id:'tbank_good',title:'Research',description_quality:'full'},bad={id:'old-broken',title:'Old'},calls=[],storage={vacancies:[bad]};let reject=false;
 const c=vm.createContext({URL,chrome:{runtime:{onMessage:{addListener(){}}},tabs:{get:async()=>({url:'https://tbank.ru/career/it/vacancy/moscow/ml/id/'})},scripting:{executeScript:async()=>[{result:{vacancies:[good]}}]},storage:{local:{get:async()=>storage,set:async x=>Object.assign(storage,x)}}},ResearchSearch:{mergeVacancies:(a,b)=>[...a,...b]},ArchiveSyncCore:{record:async(kind,id,data)=>({kind,id,data}),batches:r=>[r]},LocalResumeService:{request:async(path,data)=>{calls.push(data);return {rejected:reject?[{error:'Changed schema'}]:[]};}}});
 vm.runInContext(fs.readFileSync(new URL('hh-badges-background.js',import.meta.url),'utf8'),c);
 await c.captureWidgetPage({id:1,url:'https://tbank.ru/career/it/vacancy/moscow/ml/id/'});assert.equal(calls[0].records.length,1);assert.equal(calls[0].records[0].id,good.id);assert.equal(storage.vacancies[0].id,bad.id);
 reject=true;await assert.rejects(()=>c.captureWidgetPage({id:1,url:'https://tbank.ru/career/it/vacancy/moscow/ml/id/'}),/Changed schema/);
});
