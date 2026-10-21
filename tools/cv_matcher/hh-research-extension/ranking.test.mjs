import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element {
 constructor(){this.children=[];this.value='';this.disabled=false;this.listeners={};}
 replaceChildren(...children){this.children=children;this.value=children[0]?.value||'';}
 append(...children){this.children.push(...children);}
 addEventListener(name,fn){this.listeners[name]=fn;}
 setAttribute(name,value){this[name]=value;}
 get options(){return this.children;}
}
function page({requested='b',missing=false,previous=null,displayCount=10,source='all',goal=null,vacancies=null}={}) {
 const elements=Object.fromEntries(['resume','source','companyFilter','model','goal','limit','status','results','export','rank','rankOffline','count','connect','token','viewCount','showAll','resultsSummary'].map(k=>[k,new Element()]));elements.model.value='text-embedding-3-small';elements.viewCount.value='10';
 const resumes=[{id:'a',title:'Main ML CV',quality:'full',source_type:'hh',content_hash:'a-hash'},{id:'b',title:'Selected iOS CV',quality:missing?'unavailable':'full',source_type:'file',content_hash:'b-hash'}];
 const storage={resume_bundle:{primary_id:'a',resumes},vacancies:vacancies||[{id:'hh_1',description_quality:'full'}]};storage.last_ranking=previous;storage.ranking_view_count=displayCount;const requests=[];
 const urls=[];const chrome={runtime:{getURL:p=>'chrome-extension://fake/'+p},tabs:{create:async({url})=>urls.push(url)},storage:{local:{get:async()=>storage,set:async obj=>Object.assign(storage,obj)},onChanged:{addListener:()=>{}}}};
 const context=vm.createContext({chrome,URL,URLSearchParams,Blob,Date,fetch:async()=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(new URL("company-groups.json",import.meta.url),"utf8"))}),setTimeout,clearTimeout,location:{href:'chrome-extension://fake/ranking.html?resume='+requested+'&source='+source+(goal===null?'':'&goal='+encodeURIComponent(goal))},document:{getElementById:id=>elements[id],createElement:()=>new Element()},LocalResumeService:{request:async(path,body)=>{requests.push(body);return rankedFixture(body.resume_id,body.bundle.resumes[0].title,body.bundle.resumes[0].content_hash);}}});
 vm.runInContext(fs.readFileSync(new URL('cover-letter-ui.js',import.meta.url),'utf8'),context);
 vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),context);
 vm.runInContext(fs.readFileSync(new URL('company-core.js',import.meta.url),'utf8'),context);
 vm.runInContext(fs.readFileSync(new URL('ranking-batch.js',import.meta.url),'utf8'),context);
 vm.runInContext(fs.readFileSync(new URL('ranking.js',import.meta.url),'utf8'),context);
 return {elements,storage,requests,urls,settle:()=>new Promise(resolve=>setImmediate(resolve))};
}
test('ranking page submits only explicitly selected CV, even when bundle primary differs',async()=>{
 const p=page();await p.settle();assert.equal(p.elements.resume.value,'b');
 await p.elements.rank.onclick();assert.equal(p.requests.length,1);assert.equal(p.requests[0].resume_id,'b');
 assert.equal(p.requests[0].bundle.resumes.length,1);assert.equal(p.requests[0].bundle.resumes[0].id,'b');
 assert.ok(p.elements.status.textContent.includes('Selected iOS CV'));
 p.elements.resume.value='a';await p.elements.resume.listeners.change();await p.settle();await p.elements.rank.onclick();assert.equal(p.requests[1].resume_id,'a');
});
test('unavailable requested CV does not silently fall back to first available resume',async()=>{
 const p=page({missing:true});await p.settle();assert.equal(p.elements.resume.value,'');assert.equal(p.elements.rank.disabled,true);assert.equal(p.requests.length,0);
});

function rankedFixture(id='b',title='Selected iOS CV',hash='b-hash') {
 const all=Array.from({length:25},(_,i)=>({id:'hh_'+(i+1),title:'Rank '+(i+1),link:'https://hh.ru/vacancy/'+(i+1),company:'Employer',score:1-i/100,cv_similarity:1-i/100,goal_similarity:null,evidence:{resume:'CV evidence',vacancy:'JD evidence'}}));
 return {resume_id:id,resume_title:title,resume_hash:hash,generated_at:new Date().toISOString(),model:'text-embedding-3-small',goal:'Research Engineer',top:all.slice(0,10),all,input_count:25,ranked_count:25,api_requests:0,usage_tokens:0,score_warning:'Fixture'};
}
test('display count expands calculated results without any new API calls',async()=>{
 const p=page();await p.settle();await p.elements.rank.onclick();assert.equal(p.elements.results.children.length,10);assert.equal(p.requests.length,1);
 p.elements.viewCount.value='20';await p.elements.viewCount.listeners.input();assert.equal(p.elements.results.children.length,20);assert.equal(p.requests.length,1);
 await p.elements.showAll.onclick();assert.equal(p.elements.results.children.length,25);assert.equal(p.requests.length,1);assert.equal(p.storage.ranking_view_count,25);
 assert.ok(p.elements.resultsSummary.textContent.includes('25 из 25'));assert.equal(p.elements.showAll.disabled,true);
 p.elements.viewCount.value='-3';await p.elements.viewCount.listeners.input();assert.equal(p.elements.results.children.length,1);
});
test('reopening restores all saved ranks and the preferred display count without re-embedding',async()=>{
 const p=page({previous:rankedFixture(),displayCount:20});await p.settle();assert.equal(p.elements.results.children.length,20);assert.equal(p.requests.length,0);
 assert.equal(p.elements.goal.value,'Research Engineer');assert.ok(p.elements.status.textContent.includes('Сохранённый расчёт'));
});
test('saved ranking is not restored for a different CV or edited CV version',async()=>{
 for(const previous of [rankedFixture('a','Main ML CV','a-hash'),rankedFixture('b','Edited CV','old-hash')]) {
  const p=page({previous});await p.settle();assert.equal(p.elements.results.children.length,0);assert.equal(p.requests.length,0);
 }
});
test('recommended collection uses the same selected CV and explicit career goal without unrelated jobs',async()=>{
 const p=page({source:'hh_recommended',goal:'DiT / pre-training',previous:rankedFixture(),vacancies:[
 {id:'hh_1',description_quality:'full',recommended_for:['b']},{id:'hh_2',description_quality:'full',recommended_for:['a']},
 {id:'hh_3',description_quality:'full'},{id:'hh_4',description_quality:'snippet',recommended_for:['b']} ]});
 await p.settle();assert.equal(p.elements.results.children.length,0);assert.equal(p.elements.goal.value,'DiT / pre-training');
 await p.elements.rank.onclick();assert.equal(p.requests[0].resume_id,'b');assert.equal(p.requests[0].goal,'DiT / pre-training');
 assert.deepEqual(p.requests[0].vacancies.map(v=>v.id),['hh_1']);assert.equal(p.storage.last_ranking.selection_source,'hh_recommended');
});
test('an explicit new goal does not silently restore an old calculation',async()=>{
 const p=page({goal:'Flow matching',previous:rankedFixture()});await p.settle();assert.equal(p.elements.results.children.length,0);assert.equal(p.elements.goal.value,'Flow matching');
});
test('apply button carries the ranked resume version, vacancy and goal without submitting anything',async()=>{
 const p=page();await p.settle();await p.elements.rank.onclick();const article=p.elements.results.children[0];
 const button=article.children.find(e=>e.textContent==='Подготовить отклик');assert.ok(button);await button.onclick();
 const url=new URL(p.urls[0]);assert.equal(url.pathname,'/application.html');assert.equal(url.searchParams.get('resume'),'b');assert.equal(url.searchParams.get('hash'),'b-hash');assert.equal(url.searchParams.get('vacancy'),'hh_1');assert.equal(url.searchParams.get('goal'),'Research Engineer');
});
test('company filter groups Sber teams and sends only selected company vacancies with one CV',async()=>{
 const p=page({vacancies:[{id:'hh_1',company:'Сбер. IT',description_quality:'full'},{id:'hh_2',company:'Сбер. Data Science',description_quality:'full'},{id:'hh_3',company:'Ozon',description_quality:'full'}]});await p.settle();p.elements.companyFilter.value='sber';await p.elements.companyFilter.listeners.change();await p.elements.rank.onclick();
 assert.deepEqual(p.requests[0].vacancies.map(v=>v.id),['hh_1','hh_2']);assert.equal(p.requests[0].bundle.resumes.length,1);assert.equal(p.requests[0].company_filter,'sber');
});
test('a company with no vacancies disables calculation instead of silently falling back to all employers',async()=>{
 const p=page({vacancies:[{id:'hh_1',company:'Ozon',description_quality:'full'}]});await p.settle();p.elements.companyFilter.value='sber';await p.elements.companyFilter.listeners.change();assert.equal(p.elements.companyFilter.value,'sber');assert.equal(p.elements.rank.disabled,true);assert.equal(p.requests.length,0);
});
test('changing company displays unchanged cached rows without invoking the local rank endpoint',async()=>{
 const previous=rankedFixture(),date='2026-10-15T12:00:00Z';previous.all[0].company='Сбер. IT';previous.all[0].collected_at=date;
 const p=page({previous,vacancies:[{id:'hh_1',company:'Сбер. IT',collected_at:date,description_quality:'full'}]});await p.settle();p.elements.companyFilter.value='sber';await p.elements.companyFilter.listeners.change();assert.equal(p.requests.length,0);assert.equal(p.elements.results.children.length,1);assert.match(p.elements.status.textContent,/Запросов к OpenAI: 0/);
});

test('cache-only ranking explicitly forbids paid embedding calls in request',async()=>{const p=page();await p.settle();await p.elements.rankOffline.onclick();assert.equal(p.requests.length,1);assert.equal(p.requests[0].allow_api,false);assert.equal(p.requests[0].bundle.resumes.length,1);});

test('UI selects all 718 full jobs when the calculation maximum is 2000',async()=>{
 const p=page({vacancies:Array.from({length:718},(_,i)=>({id:'hh_'+i,description_quality:'full'}))});await p.settle();
 p.elements.limit.value='2000';await p.elements.limit.listeners.change();await p.settle();
 assert.match(p.elements.count.textContent,/718 самых свежих/);await p.elements.rankOffline.onclick();
 assert.deepEqual(p.requests.map(r=>r.vacancies.length),[200,200,200,118]);assert.ok(p.requests.every(r=>r.allow_api===false));
});
test('a saved large ranking restores its calculation maximum and displays beyond 200 without API',async()=>{
 const saved=rankedFixture(),base=saved.all[0];saved.all=Array.from({length:718},(_,i)=>({...base,id:'hh_'+i}));saved.input_count=saved.ranked_count=saved.requested_count=718;
 const p=page({previous:saved,displayCount:500});await p.settle();assert.equal(p.elements.limit.value,'718');assert.equal(p.elements.results.children.length,500);
 await p.elements.showAll.onclick();assert.equal(p.elements.results.children.length,718);assert.equal(p.requests.length,0);
});
