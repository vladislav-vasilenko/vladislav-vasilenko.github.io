import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const sources=[['https://career.avito.com/vacancies/?direction=data-science','https://career.avito.com/vacancies/data-science/19450/','avito_19450'],['https://ozon.tech/vacancies/','https://ozon.tech/vacancies/12345/','ozon_12345'],['https://yandex.ru/jobs/vacancies?professions=ml-developer','https://yandex.ru/jobs/vacancies/ml-engineer-20372','yandex_20372'],['https://rabota.sber.ru/search/','https://rabota.sber.ru/search/ml-engineer-12345','sber_12345'],['https://www.tbank.ru/career/vacancies/it/','https://www.tbank.ru/career/it/vacancy/moscow/ml-engineer/0d772642-b21e-4529-a234-5e93b00210be/','tbank_0d772642-b21e-4529-a234-5e93b00210be']];
function worker([start,detail,id],{review=false,blocked=false,stop=false,closed=false,skipClosed=true,filters=[],filterError=null,previous=null,force=false,emptyQueries=[]}={}){
 let url=start,finish;const done=new Promise(r=>finish=r),handlers=[],storage={},urls=[];
 if(previous)storage.vacancies=[previous];
 if(closed)storage.vacancies=[{id,link:detail,title:'ML Research',description:'Saved full text',description_quality:'full',archived:true,collected_at:'2020-01-01T00:00:00Z'}];
 const row={id,link:detail,title:'ML Research',description:'PyTorch research '.repeat(30),collected_at:new Date().toISOString()};
 const chrome={runtime:{id:'fixture',onMessage:{addListener:f=>handlers.push(f)},getURL:p=>p},tabs:{get:async()=>({id:1,url})},storage:{local:{get:async keys=>Object.fromEntries((Array.isArray(keys)?keys:[keys]).map(k=>[k,storage[k]])),set:async value=>{Object.assign(storage,structuredClone(value));if(value.board_crawl_status?.state!=='running'&&value.board_crawl_status)finish();}}},scripting:{executeScript:async({files})=>{
  if(files?.includes('board-filter-content.js'))return [{result:filterError?{ok:false,error:filterError}:{ok:true,checked:filters,url}}];
  if(!files)return [];
  if(blocked)return [{result:{blocked:true,warning:'Источник ограничил доступ'}}];
  if(emptyQueries.includes(new URL(url).searchParams.get('search')))return [{result:{page_kind:'listing',empty:true,vacancies:[]}}];
  if(new URL(url).pathname===new URL(start).pathname)return [{result:{page_kind:'listing',vacancies:[{...row,description_quality:'snippet'},{...row,id:'hh_1',link:'https://hh.ru/vacancy/1'}]}}];
  if(stop)queueMicrotask(()=>handlers.forEach(f=>f({type:'stop_board_crawl',tabId:1},{id:'fixture'},()=>{})));
  return [{result:{page_kind:'detail',vacancies:[{...row,description_quality:review?'needs_review':'full'}]}}];
 }}};
 const context=vm.createContext({chrome,URL,Date,Map,Set,setTimeout,clearTimeout,LocalResumeService:{request:async()=>({tbank_filters:filters})},activeJobs:new Set(),navigate:async(id,next)=>{url=next;urls.push(next);}});
 for(const file of ['core.js','hh-crawl-core.js','board-core.js','board-adapters.js','board-crawl.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),context);
 return {context,storage,urls,done,send:()=>new Promise(r=>handlers.forEach(f=>f({type:'crawl_board',tabId:1,options:{skip_closed:skipClosed,force_details:force}},{id:'fixture'},r)))};
}
test('all five adapters collect same-origin full descriptions, persist partial coverage and return to the source',async()=>{
 for(const source of sources){const w=worker(source);assert.equal((await w.send()).ok,true);await w.done;assert.equal(w.storage.board_crawl_status.loaded,1);assert.equal(w.storage.board_crawl_status.planned,1);assert.equal(w.storage.board_crawl_status.state,'partial');assert.equal(w.storage.vacancies.find(r=>r.id===source[2]).description_quality,'full');assert.ok(!w.urls.some(url=>url.startsWith('https://hh.ru')));assert.equal(w.urls.at(-1),source[0]);}
});
test('unknown layout is retained for manual review and cannot silently enter the full-description ranking',async()=>{
 const w=worker(sources[4],{review:true});await w.send();await w.done;assert.equal(w.storage.board_crawl_status.loaded,0);assert.equal(w.storage.board_crawl_status.review,1);assert.equal(w.storage.vacancies[0].description_quality,'needs_review');
});
test('access challenge stops traversal without erasing saved records or opening further pages',async()=>{
 const w=worker(sources[3],{blocked:true});await w.send();await w.done;assert.equal(w.storage.board_crawl_status.state,'failed');assert.equal(w.urls.length,0);assert.equal(w.storage.vacancies,undefined);
});
test('stop preserves a completed description and ends further navigation',async()=>{
 const w=worker(sources[0],{stop:true});await w.send();await w.done;assert.equal(w.storage.board_crawl_status.state,'stopped');assert.equal(w.storage.board_crawl_status.loaded,1);assert.equal(w.urls.length,1);
});

test('corporate collectors skip known closed details, preserve history and allow explicit recheck',async()=>{
 const w=worker(sources[0],{closed:true});await w.send();await w.done;assert.ok(!w.urls.includes(sources[0][1]));assert.equal(w.storage.board_crawl_status.skipped_closed,1);assert.equal(w.storage.board_crawl_status.loaded,0);assert.equal(w.storage.board_crawl_status.reused,0);assert.equal(w.storage.vacancies[0].description,'Saved full text');
 const forced=worker(sources[0],{closed:true,skipClosed:false});await forced.send();await forced.done;assert.ok(forced.urls.includes(sources[0][1]));assert.equal(forced.storage.board_crawl_status.skipped_closed,0);
});

test('T-Bank no-www listing follows canonical www details without dropping the queue',async()=>{
 const source=[...sources[4]];source[0]='https://tbank.ru/career/vacancies/all/moscow/';const w=worker(source);await w.send();await w.done;assert.equal(w.storage.board_crawl_status.loaded,1);assert.ok(w.urls.includes(source[1]));
});

test('manual T-Bank collection reads saved IT + ML profile before reading vacancy cards',async()=>{
 const source=[...sources[4]];source[0]='https://www.tbank.ru/career/vacancies/all/moscow/';
 const w=worker(source,{filters:['IT-разработка','Машинное обучение']});await w.send();await w.done;
 assert.equal(w.storage.board_crawl_status.loaded,1);assert.deepEqual(w.storage.board_crawl_status.filters,['IT-разработка','Машинное обучение']);
 assert.equal(new URL(w.storage.board_crawl_status.start_url).searchParams.get('direction'),'it-razrabotka');assert.equal(new URL(w.storage.board_crawl_status.start_url).searchParams.get('profession'),'ml');
});
test('ML filter refusal stops collection before saving unrelated IT jobs',async()=>{
 const source=[...sources[4]];source[0]='https://www.tbank.ru/career/vacancies/all/moscow/';
 const w=worker(source,{filters:['IT-разработка','Машинное обучение'],filterError:'Фильтр не найден: Машинное обучение'});await w.send();await w.done;
 assert.equal(w.storage.board_crawl_status.state,'failed');assert.match(w.storage.board_crawl_status.error,/Машинное обучение/);assert.equal(w.storage.vacancies,undefined);
});


test('company boards reuse valid full descriptions for 24 hours; force bypasses this cache',async()=>{
 for(const source of sources){
  const previous={id:source[2],link:source[1],title:'ML Research',description:'Saved full text',description_quality:'full',collected_at:new Date(Date.now()-2*3600000).toISOString()};
  const cached=worker(source,{previous});await cached.send();await cached.done;assert.equal(cached.storage.board_crawl_status.reused,1);assert.ok(!cached.urls.includes(source[1]));
  const forced=worker(source,{previous,force:true});await forced.send();await forced.done;assert.ok(forced.urls.includes(source[1]));
 }
});

test('Ozon performs separate native keyword searches, accepts explicit empty results and deduplicates full reads',async()=>{
 const w=worker(sources[1],{emptyQueries:['PyTorch']});const start=sources[1][0];
 const result=await w.context.runBoardCrawl(1,start,w.context.JobBoardAdapters.resolve(start),{pages:1,details:10,search_terms:['ML','PyTorch','Diffusion'],listing_budget:3},{stop:false});
 assert.equal(result.loaded,1);assert.equal(result.failed,0);assert.equal(result.queries_done,3);assert.equal(result.discovered,1);
 const searches=w.urls.filter(u=>new URL(u).searchParams.has('search'));assert.deepEqual(searches.map(u=>new URL(u).searchParams.get('search')).slice(0,3),['ML','PyTorch','Diffusion']);assert.equal(w.urls.filter(u=>u===sources[1][1]).length,1);
});
test('Ozon keyword expansion respects total listing budget',async()=>{
 const w=worker(sources[1]),start=sources[1][0];const result=await w.context.runBoardCrawl(1,start,w.context.JobBoardAdapters.resolve(start),{pages:1,details:10,search_terms:['ML','PyTorch','Diffusion'],listing_budget:2},{stop:false});assert.equal(result.queries_done,2);assert.equal(result.pages,2);
});


test('service board crawl persists rows through SQLite callback without local writes',async()=>{
 const w=worker(sources[0]);const rows=[];w.context.chrome.storage.local.set=async()=>{throw Error('Quota');};
 const result=await w.context.runBoardCrawl(1,sources[0][0],w.context.JobBoardAdapters.resolve(sources[0][0]),{pages:1,details:2,skip_closed:true},{stop:false,loadVacancies:async()=>rows,saveVacancies:async batch=>{rows.push(...batch);}});
 assert.equal(result.loaded,1);assert.ok(rows.some(r=>r.description_quality==='full'));
});
