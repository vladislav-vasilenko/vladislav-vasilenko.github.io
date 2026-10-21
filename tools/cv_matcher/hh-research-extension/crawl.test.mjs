import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import './hh-crawl-core.js';
const start='https://hh.ru/search/vacancy?text=PyTorch&page=0';
test('pagination only follows an observed next HH page with identical search filters',()=>{
 assert.equal(HHCrawl.nextURL(start,start.replace('page=0','page=1')),start.replace('page=0','page=1'));
 for(const u of ['https://evil.test/search/vacancy?page=1',start.replace('PyTorch','Java').replace('page=0','page=1'),start,start.replace('page=0','page=2')]) assert.equal(HHCrawl.nextURL(start,u),null);
 assert.deepEqual(HHCrawl.limits({pages:1000,details:1000}),{pages:20,details:200,skip_closed:true,force_details:false});
});
function worker({blocked=false,stop=false,fail=false,initial={},initialUrl=start,tracked=false,badNext=false,redirect=false,archivedIds=[],returnFail=false,hangDetail=false,hangRead=false}={}) {
 let current=initialUrl;const handlers=[],listeners=new Set(),urls=[],reads=[],storage=structuredClone(initial);
 let completed;const done=new Promise(resolve=>completed=resolve);
 const row=id=>({id:'hh_'+id,title:'Research '+id,link:'https://hh.ru/vacancy/'+id,description:'PyTorch '.repeat(30),description_quality:'snippet',collected_at:new Date().toISOString()});
 const chrome={runtime:{id:'extension',getURL:p=>p,onMessage:{addListener:f=>handlers.push(f)}},tabs:{get:async()=>({url:current,status:hangDetail&&current.includes("/vacancy/")?"loading":"complete"}),onUpdated:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},update:async(id,{url})=>{if(returnFail&&url.includes("/search/vacancy")&&reads.some(u=>/hh.ru\/vacancy\//.test(u)))throw Error("Return navigation failed");current=redirect&&url.includes("/search/vacancy")?url+"&search_session_id=redirect-session":url;urls.push(current);queueMicrotask(()=>[...listeners].forEach(f=>f(id,{status:'complete'})));}},storage:{local:{get:async k=>Object.fromEntries((Array.isArray(k)?k:[k]).map(key=>[key,storage[key]])),set:async obj=>{Object.assign(storage,structuredClone(obj));if(obj.hh_crawl_status?.state!=='running'&&obj.hh_crawl_status)completed();}}},scripting:{executeScript:async args=>{
  if(args.func)return [{result:{url:current,ready:false,text:true}}];
  if(hangRead&&current.includes("/vacancy/"))return new Promise(()=>{});
  reads.push(current);
  if(blocked)return [{result:{blocked:true,warning:'HH ограничил доступ'}}];
  const u=new URL(current);
  if(u.pathname==='/search/vacancy')return [{result:{page_kind:'listing',page_url:current,vacancies:[row(u.searchParams.get('page')==='1'?'2':'1')],next_page:u.searchParams.get('page')==='0'?initialUrl.replace('page=0','page=1')+(tracked?'&search_session_id=hh-session':'')+(badNext?'&area=2':''):null}}];
  if(fail&&u.pathname.endsWith('/1'))throw new Error('Page unavailable');
  if(stop)queueMicrotask(()=>handlers.forEach(h=>h({type:'stop_hh_crawl',tabId:1},{id:'extension'},()=>{})));
  const vid=u.pathname.split('/').at(-1),archived=archivedIds.includes(vid);
  return [{result:{page_kind:'detail',page_url:current,vacancies:[{...row(vid),source_page:current,archived,description_quality:archived?'missing':'full'}]}}];
 }}};
 const ctx=vm.createContext({chrome,URL,Date,Map,Set,TextEncoder,crypto:globalThis.crypto,setTimeout,clearTimeout,queueMicrotask,fetch:async()=>({ok:false})});ctx.importScripts=(...paths)=>paths.forEach(path=>vm.runInContext(fs.readFileSync(new URL(path,import.meta.url),'utf8'),ctx));
 vm.runInContext(fs.readFileSync(new URL('background.js',import.meta.url),'utf8'),ctx);
 return {context:ctx,storage,urls,reads,done,send:m=>new Promise(resolve=>handlers.forEach(h=>h({tabId:1,...m},{id:'extension'},resolve)))};
}
test('crawl follows pages, opens complete JDs, deduplicates and returns to the listing',async()=>{
 const w=worker();assert.equal((await w.send({type:'crawl_hh',options:{pages:3,details:10}})).ok,true);await w.done;
 assert.equal(w.storage.hh_crawl_status.state,'complete');assert.equal(w.storage.hh_crawl_status.pages,2);assert.equal(w.storage.hh_crawl_status.loaded,2);assert.equal(w.storage.hh_crawl_status.planned,2);
 assert.equal(w.storage.vacancies.length,2);assert.ok(w.storage.vacancies.every(r=>r.description_quality==='full'));
 assert.equal(w.urls.at(-1),start.replace('page=0','page=1'));
});
test('page limit yields a partial result with a continuation URL',async()=>{
 const w=worker();await w.send({type:'crawl_hh',options:{pages:1,details:10}});await w.done;
 assert.equal(w.storage.hh_crawl_status.state,'partial');assert.equal(w.storage.hh_crawl_status.pages,1);assert.equal(w.storage.hh_crawl_status.next_page,start.replace('page=0','page=1'));
});
test('challenge stops without opening subsequent pages or overwriting saved content',async()=>{
 const w=worker({blocked:true});await w.send({type:'crawl_hh'});await w.done;
 assert.equal(w.storage.hh_crawl_status.state,'failed');assert.equal(w.urls.length,0);assert.equal(w.storage.vacancies,undefined);
});
test('stopping preserves completed descriptions and ends further navigation',async()=>{
 const w=worker({stop:true});await w.send({type:'crawl_hh'});await w.done;
 assert.equal(w.storage.hh_crawl_status.state,'stopped');assert.equal(w.storage.hh_crawl_status.loaded,1);assert.equal(w.storage.vacancies.filter(r=>r.description_quality==='full').length,1);
});
test('a failed detail is reported and other vacancies still load',async()=>{
 const w=worker({fail:true});await w.send({type:'crawl_hh'});await w.done;
 assert.equal(w.storage.hh_crawl_status.failed,1);assert.equal(w.storage.hh_crawl_status.loaded,1);assert.equal(w.storage.hh_crawl_status.state,'partial');
});

test('repeat crawl finishes pending descriptions from earlier pages of the same search',async()=>{
 const old={id:'hh_9',title:'Earlier job',link:'https://hh.ru/vacancy/9',description_quality:'snippet',source_page:start,collected_at:new Date().toISOString()};
 const w=worker({initial:{vacancies:[old]},initialUrl:start.replace('page=0','page=1')});await w.send({type:'crawl_hh'});await w.done;
 assert.equal(w.storage.hh_crawl_status.loaded,2);assert.ok(w.reads.includes(old.link));assert.equal(w.storage.vacancies.find(v=>v.id==='hh_9').description_quality,'full');
});

test('HH session tracking is ignored, while substantive filters remain mandatory',()=>{
 const a='https://hh.ru/search/vacancy?text=Research&area=1&employer_id=2&employer_id=3&order_by=publication_time';
 const b='https://hh.ru/search/vacancy?order_by=publication_time&employer_id=3&area=1&text=Research&employer_id=2&page=1&search_session_id=example-session&hhtmFrom=vacancy_search_list';
 assert.equal(HHCrawl.nextURL(a,b),b);
 assert.equal(HHCrawl.samePage(a,a+'&search_session_id=new-session'),true);
 for(const bad of [b.replace('area=1','area=113'),b.replace('text=Research','text=Java'),b.replace('employer_id=2&',''),b+'&work_format=REMOTE',b+'&unknown_filter=true']) assert.equal(HHCrawl.nextURL(a,bad),null);
 assert.equal(HHCrawl.samePage(a,b),false);
});
test('live HH pager shape with added search_session_id reaches the next page and loads JDs',async()=>{
 const w=worker({tracked:true,redirect:true});await w.send({type:'crawl_hh',options:{pages:2,details:2}});await w.done;
 assert.equal(w.storage.hh_crawl_status.pages,2);assert.equal(w.storage.hh_crawl_status.loaded,2);assert.equal(w.storage.hh_crawl_status.state,'complete');
 assert.ok(w.urls.some(url=>url.includes('page=1&search_session_id=')));
});
test('a changed filter stops pagination but still reads safe descriptions from the first page',async()=>{
 const w=worker({badNext:true});await w.send({type:'crawl_hh'});await w.done;
 assert.equal(w.storage.hh_crawl_status.state,'partial');assert.equal(w.storage.hh_crawl_status.pages,1);assert.equal(w.storage.hh_crawl_status.loaded,1);
 assert.ok(w.storage.hh_crawl_status.pagination_warning.includes('area'));
 assert.ok(!w.urls.some(url=>url.includes('area=2')));
 assert.equal(w.storage.vacancies[0].description_quality,'full');
});
test('recommendation pagination protects resume identity but tolerates navigation tracking',()=>{
 const id='a'.repeat(38),base='https://hh.ru/search/vacancy?resume='+id+'&from=resumelist&hhtmFrom=profile';
 const next='https://hh.ru/search/vacancy?resume='+id+'&page=1&search_session_id=abc';
 assert.equal(HHCrawl.nextURL(base,next),next);
 assert.equal(HHCrawl.nextURL(base,next.replace(id,'b'.repeat(38))),null);
 assert.equal(HHCrawl.nextURL(base,'https://hh.ru/search/vacancy?page=1'),null);
});
test('recommended crawl loads full descriptions on each page and retains the CV link even for reused JDs',async()=>{
 const id='a'.repeat(38),initialUrl='https://hh.ru/search/vacancy?resume='+id+'&page=0';
 const previous={id:'hh_1',link:'https://hh.ru/vacancy/1',description:'Existing complete JD',description_quality:'full',collected_at:new Date().toISOString()};
 const w=worker({initialUrl,initial:{vacancies:[previous]}});
 assert.equal((await w.send({type:'crawl_hh',recommended_resume_id:id,options:{pages:2,details:2}})).ok,true);await w.done;
 assert.equal(w.storage.hh_crawl_status.pages,2);assert.equal(w.storage.hh_crawl_status.reused,1);assert.equal(w.storage.hh_crawl_status.loaded,1);
 assert.equal(w.storage.hh_crawl_status.recommended_resume_id,id);
 assert.ok(w.storage.vacancies.every(r=>r.description_quality==='full'&&r.recommended_for.includes(id)));
 assert.equal(w.storage.vacancies.find(r=>r.id==='hh_1').description,previous.description);
});
test('recommendation button refuses a page belonging to another CV before reading it',async()=>{
 const w=worker({initialUrl:'https://hh.ru/search/vacancy?resume='+'a'.repeat(38)});
 const result=await w.send({type:'crawl_hh',recommended_resume_id:'b'.repeat(38)});
 assert.equal(result.ok,false);assert.equal(w.reads.length,0);assert.equal(w.urls.length,0);
});

test('scan coverage excludes backlog IDs, is incomplete from a later start page, and never treats page limits as a baseline',async()=>{
 const previous={id:'hh_9',title:'Backlog',link:'https://hh.ru/vacancy/9',description_quality:'snippet',source_page:start,collected_at:new Date().toISOString()};
 const complete=worker({initial:{vacancies:[previous]}});await complete.send({type:'crawl_hh',options:{pages:3,details:10}});await complete.done;
 assert.equal(complete.storage.hh_scan_runs[0].listing_complete,true);assert.deepEqual(complete.storage.hh_scan_runs[0].ids,['hh_1','hh_2']);
 const late=worker({initialUrl:start.replace('page=0','page=1')});await late.send({type:'crawl_hh'});await late.done;assert.equal(late.storage.hh_scan_runs[0].listing_complete,false);
 const limited=worker();await limited.send({type:'crawl_hh',options:{pages:1,details:5}});await limited.done;assert.equal(limited.storage.hh_scan_runs[0].listing_complete,false);
});
test('a known full vacancy missing from a complete search is rechecked and an explicit archived result preserves its full description',async()=>{
 const previous={id:'hh_9',title:'Earlier complete vacancy',link:'https://hh.ru/vacancy/9',description:'Preserved complete description',description_quality:'full',search_page:start,source_page:'https://hh.ru/vacancy/9',collected_at:new Date(Date.now()-25*60*60*1000).toISOString()};
 const w=worker({initial:{vacancies:[previous]},archivedIds:['9']});await w.send({type:'crawl_hh',options:{pages:3,details:10}});await w.done;
 assert.ok(w.reads.includes(previous.link));assert.equal(w.storage.hh_crawl_status.archived,1);assert.equal(w.storage.hh_crawl_status.failed,0);
 const saved=w.storage.vacancies.find(v=>v.id==='hh_9');assert.equal(saved.archived,true);assert.equal(saved.description,previous.description);assert.equal(saved.description_quality,'full');assert.ok(!w.storage.hh_scan_runs[0].ids.includes('hh_9'));
});


test('confirmed closed jobs are skipped before opening descriptions and do not consume the detail limit',async()=>{
 const known={id:'hh_1',title:'Closed',link:'https://hh.ru/vacancy/1',description:'Old full JD',description_quality:'full',source_page:'https://hh.ru/vacancy/1',search_page:start,archived:true,collected_at:'2020-01-01T00:00:00Z'};
 const backlog={...known,id:'hh_9',link:'https://hh.ru/vacancy/9',source_page:start,description_quality:'snippet',collected_at:new Date().toISOString()};
 const w=worker({initial:{vacancies:[known,backlog]}});await w.send({type:'crawl_hh',options:{pages:3,details:1}});await w.done;
 assert.ok(!w.reads.includes(known.link));assert.ok(!w.reads.includes(backlog.link));assert.ok(w.reads.includes('https://hh.ru/vacancy/2'));
 assert.equal(w.storage.hh_crawl_status.skipped_closed,2);assert.equal(w.storage.hh_crawl_status.loaded,1);assert.equal(w.storage.hh_crawl_status.remaining_descriptions,0);assert.equal(w.storage.hh_crawl_status.reused,0);
 assert.equal(w.storage.vacancies.find(r=>r.id==='hh_1').description,known.description);assert.equal(w.storage.vacancies.find(r=>r.id==='hh_1').archived,true);
});
test('closed jobs absent from a complete search are not repeatedly checked; explicit override can verify reopening',async()=>{
 const known={id:'hh_9',title:'Closed',link:'https://hh.ru/vacancy/9',description:'Saved complete JD',description_quality:'full',source_page:'https://hh.ru/vacancy/9',search_page:start,archived:true,collected_at:new Date().toISOString()};
 const normal=worker({initial:{vacancies:[known]}});await normal.send({type:'crawl_hh'});await normal.done;assert.ok(!normal.reads.includes(known.link));assert.equal(normal.storage.hh_crawl_status.absent_to_check,0);
 const forced=worker({initial:{vacancies:[known]}});await forced.send({type:'crawl_hh',options:{skip_closed:false}});await forced.done;assert.ok(forced.reads.includes(known.link));assert.equal(forced.storage.vacancies.find(r=>r.id==='hh_9').archived,false);assert.equal(forced.storage.hh_crawl_status.skipped_closed,0);
 assert.equal(HHCrawl.isClosed({availability:'unknown'}),false);assert.equal(HHCrawl.isClosed({archived:false}),false);assert.equal(HHCrawl.isClosed({availability:'closed'}),true);
});


test('return navigation failure preserves successful collected results and coverage',async()=>{
 const w=worker({returnFail:true});await w.send({type:'crawl_hh'});await w.done;
 assert.equal(w.storage.hh_crawl_status.state,'complete');assert.equal(w.storage.hh_crawl_status.loaded,2);
 assert.match(w.storage.hh_crawl_status.return_warning,/Результаты сохранены/);assert.equal(w.storage.hh_scan_runs[0].state,'complete');
});
test('stop cancels a loading detail promptly without counting it as a failed vacancy',async()=>{
 const w=worker({hangDetail:true});await w.send({type:'crawl_hh',options:{pages:1,details:1}});
 for(let n=0;n<50&&!w.urls.some(u=>/hh.ru\/vacancy\//.test(u));n++)await new Promise(r=>setTimeout(r,5));
 assert.ok(w.urls.some(u=>/hh.ru\/vacancy\//.test(u)));
 const time=Date.now();await w.send({type:'stop_hh_crawl'});await w.done;
 assert.ok(Date.now()-time<1500);assert.equal(w.storage.hh_crawl_status.state,'stopped');assert.equal(w.storage.hh_crawl_status.failed,0);assert.ok(w.storage.vacancies.length);
});


test('stop also interrupts a content-script read that never returns',async()=>{
 const w=worker({hangRead:true});await w.send({type:'crawl_hh',options:{pages:1,details:1}});
 for(let n=0;n<50&&!w.urls.some(u=>/hh.ru\/vacancy\//.test(u));n++)await new Promise(r=>setTimeout(r,5));
 await new Promise(r=>setTimeout(r,5));const time=Date.now();await w.send({type:'stop_hh_crawl'});await w.done;
 assert.ok(Date.now()-time<1500);assert.equal(w.storage.hh_crawl_status.state,'stopped');assert.equal(w.storage.hh_crawl_status.failed,0);
});


test('24-hour full-text cache also applies to automatic discovery; force overrides it',async()=>{
 const full={id:'hh_1',title:'Research 1',link:'https://hh.ru/vacancy/1',description:'Full existing description',description_quality:'full',collected_at:new Date(Date.now()-2*60*60*1000).toISOString()};
 const cached=worker({initial:{vacancies:[full]}});await cached.send({type:'crawl_hh',options:{pages:1,details:5,refresh_active:true}});await cached.done;
 assert.ok(!cached.urls.includes(full.link));assert.equal(cached.storage.hh_crawl_status.reused,1);
 const forced=worker({initial:{vacancies:[full]}});await forced.send({type:'crawl_hh',options:{pages:1,details:5,force_details:true}});await forced.done;assert.ok(forced.urls.includes(full.link));
});
test('listing does not make yesterday’s full text fresh, and absent fresh jobs are not reopened',async()=>{
 const old={id:'hh_1',title:'Research 1',link:'https://hh.ru/vacancy/1',description:'Old full description',description_quality:'full',collected_at:new Date(Date.now()-25*60*60*1000).toISOString()};
 const stale=worker({initial:{vacancies:[old]}});await stale.send({type:'crawl_hh'});await stale.done;assert.ok(stale.urls.includes(old.link));
 const absent={...old,id:'hh_9',link:'https://hh.ru/vacancy/9',search_page:start,collected_at:new Date().toISOString()};
 const fresh=worker({initial:{vacancies:[absent]}});await fresh.send({type:'crawl_hh'});await fresh.done;assert.ok(!fresh.urls.includes(absent.link));assert.equal(fresh.storage.vacancies.find(r=>r.id==='hh_9').archived,undefined);
});

test('backlog full reads are returned for SQLite but never counted as current listing discoveries',async()=>{
 const old={id:'hh_9',title:'Earlier job',link:'https://hh.ru/vacancy/9',description_quality:'snippet',source_page:start,collected_at:new Date().toISOString()};
 const w=worker({initial:{vacancies:[old]}});const result=await w.context.runHHCrawl(1,start,{pages:2,details:10,skip_closed:true},{stop:false});
 assert.equal(result.discovered,2);assert.equal(result.loaded,3);assert.deepEqual([...result.ids].sort(),['hh_1','hh_2','hh_9']);assert.deepEqual([...result.listing_ids].sort(),['hh_1','hh_2']);assert.equal(result.attempted_ids.length,3);
});
test('continuation checkpoint excludes previous attempts including unreadable backlog IDs',async()=>{
 const old={id:'hh_9',title:'Earlier job',link:'https://hh.ru/vacancy/9',description_quality:'snippet',source_page:start,collected_at:new Date().toISOString()};
 const w=worker({initial:{vacancies:[old]}});const result=await w.context.runHHCrawl(1,start,{pages:2,details:10,skip_closed:true,attempted_ids:['hh_9']},{stop:false});
 assert.equal(result.loaded,2);assert.equal(result.continuation.remaining,0);assert.equal(w.reads.includes(old.link),false);
});


test('scheduled HH collection streams full descriptions without writing a full local cache',async()=>{
 const w=worker();const rows=[];w.context.chrome.storage.local.set=async()=>{throw Error('Quota');};
 const result=await w.context.runHHCrawl(1,start,{pages:1,details:2,skip_closed:true},{stop:false,loadVacancies:async()=>rows,saveVacancies:async batch=>{rows.push(...batch);}});
 assert.equal(result.loaded,1);assert.ok(rows.some(r=>r.description_quality==='full'));assert.equal(result.error,undefined);
});
