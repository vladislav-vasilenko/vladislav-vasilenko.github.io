import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import './catalog-core.js';
const primary='a'.repeat(38), secondary='b'.repeat(38), other='c'.repeat(38);
const policy={primary_id:primary,resumes:[{id:primary,role:'primary',url:`https://hh.ru/resume/${primary}`},{id:secondary,role:'secondary',url:`https://hh.ru/resume/${secondary}`}]};
const entries=[{url:`https://hh.ru/resume/${secondary}`,title:'LLM Engineer'},{url:`https://hh.ru/resume/${primary}?hhtmFrom=profile`,title:'Research Engineer'},{url:`https://hh.ru/resume/${other}`,title:'iOS Engineer'}];
test('catalog deduplicates resume URLs and preserves configured primary independently of order',()=>{
  const rows=ResumeCatalog.cleanCatalog([...entries,{...entries[1],title:'Research Engineer'}, {url:`https://example.com/resume/${primary}`,title:'External'},{...entries[0],title:'Редактировать'}],policy);
  assert.equal(rows.length,3); assert.equal(rows.find(r=>r.id===primary).role,'primary');
  assert.equal(rows.find(r=>r.id===other).enabled,true);
  assert.deepEqual(ResumeCatalog.syncPlan(rows,policy,true).map(r=>r.id),[primary,secondary,other]);
  assert.deepEqual(ResumeCatalog.syncPlan(rows,policy).map(r=>r.id),[primary,secondary,other]);
});
test('missing primary remains missing while other resumes can load',()=>{
  const rows=ResumeCatalog.cleanCatalog(entries.filter(r=>!r.url.includes(primary)),policy);
  assert.equal(rows.length,2);assert.ok(rows.every(r=>r.role==='secondary'));
  assert.equal(policy.primary_id,primary);
});
test('current HH catalog uses query resume IDs beside title buttons; draft editing links are excluded',()=>{
  assert.equal(ResumeCatalog.resumeLink(`https://hh.ru/search/vacancy?resume=${primary}&from=resumelist`).id,primary);
  assert.equal(ResumeCatalog.cardTitle('Постоянная работа, подработка Senior iOS Engineer Уровень дохода не указан · Гибрид'),'Senior iOS Engineer');
  assert.equal(ResumeCatalog.cardTitle('Постоянная работа Senior LLM / GenAI Engineer Многие не видят ваше резюме'),'Senior LLM / GenAI Engineer');
  assert.equal(ResumeCatalog.resumeLink(`https://hh.ru/profile/resume?resume=${primary}`),null);
  assert.equal(ResumeCatalog.resumeLink(`https://hh.ru/resume/edit/${primary}/visibility`),null);
});
test('DOM collector reads current Cyrillic button title without copying private profile or experience text',()=>{
  const button={innerText:'Постоянная работа Research Engineer / ML Engineer – Generative Models, PyTorch Уровень дохода не указан',getClientRects:()=>[{}]};
  const anchor={href:`https://hh.ru/search/vacancy?resume=${primary}&from=resumelist`,innerText:'1377 вакансий',getClientRects:()=>[{}],closest:()=>null};
  const card={innerText:'private contact and entire profile must not be read',parentElement:null,querySelectorAll:s=>s.startsWith('a[')?[anchor]:[button]};
  anchor.parentElement=card;
  const result=vm.runInNewContext(fs.readFileSync(new URL('catalog-content.js',import.meta.url),'utf8'),{document:{querySelectorAll:()=>[anchor]},location:new URL('https://hh.ru/applicant/profile/me'),URL,Date,Set,ResumeCatalog,getComputedStyle:()=>({display:'block',visibility:'visible'})});
  assert.equal(result.entries.length,1);assert.equal(result.entries[0].id,primary);
  assert.equal(result.entries[0].title,'Research Engineer / ML Engineer – Generative Models, PyTorch');
  assert.ok(!JSON.stringify(result).includes('private'));
});

function worker({catalog=entries,failId='',tabUrl='https://hh.ru/applicant/profile/me',initial={}}={}) {
  let currentUrl=tabUrl;const handlers=[];
  const storage=structuredClone(initial),urls=[],listeners=new Set(),reads=[];
  const chrome={runtime:{id:'extension',getURL:p=>`chrome-extension://extension/${p}`,onMessage:{addListener:f=>{handlers.push(f);}}},
    tabs:{get:async()=>({url:currentUrl,status:"complete"}),onUpdated:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},
      update:async(id,{url})=>{currentUrl=url;urls.push(url); queueMicrotask(()=>[...listeners].forEach(f=>f(id,{status:'complete'})));}},
    storage:{local:{get:async key=>Object.fromEntries((Array.isArray(key)?key:[key]).map(k=>[k,storage[k]])),set:async obj=>Object.assign(storage,structuredClone(obj))}},
    scripting:{executeScript:async({files})=>{
      if(files.includes('catalog-content.js')) return [{result:{entries:catalog,checked_at:'2026-10-14T14:00:00Z'}}];
      const id=new URL(currentUrl).pathname.split('/').at(-1);reads.push(id);
      if(id===failId) throw new Error('Resume unavailable');
      return [{result:{resume:{id,title:'Research',quality:'full',captured_at:'2026-10-14T14:01:00Z',sections:[{key:'experience',heading:'Опыт',text:'PyTorch Transformer '.repeat(20)}]}}}];
    }}};
  const context=vm.createContext({chrome,URL,Date,Map,Set,TextEncoder,crypto:webcrypto,setTimeout,clearTimeout,queueMicrotask,
    fetch:async()=>({ok:true,json:async()=>policy})});
  context.importScripts=(...paths)=>paths.forEach(path=>vm.runInContext(fs.readFileSync(new URL(path,import.meta.url),'utf8'),context));
  vm.runInContext(fs.readFileSync(new URL('background.js',import.meta.url),'utf8'),context);
  return {storage,urls,reads,send:message=>new Promise(resolve=>handlers.forEach(handler=>handler({tabId:1,...message},{id:'extension'},resolve)))};
}
test('one action discovers catalog then reads primary, preserving origin and returning to catalog',async()=>{
  const w=worker(); const result=await w.send({type:'sync_catalog'});
  assert.equal(result.ok,true); assert.equal(result.catalog_count,3); assert.deepEqual(w.reads,[primary,secondary,other]);
  assert.equal(w.urls[0],'https://hh.ru/applicant/profile/me'); assert.equal(w.urls.at(-1),w.urls[0]);
  assert.equal(w.storage.resume_bundle.resumes[0].id,primary);
  assert.equal(w.storage.resume_bundle.catalog_source,'https://hh.ru/applicant/profile/me');
  assert.ok(w.urls.every(u=>new URL(u).origin==='https://hh.ru'));
});
test('reserve failure does not replace primary or hide the failure',async()=>{
  const w=worker({failId:secondary}); const result=await w.send({type:'sync_catalog',includeSecondary:true});
  assert.equal(result.ok,true); assert.equal(result.failures.length,1);
  assert.equal(w.storage.resume_bundle.primary_id,primary);assert.equal(w.storage.resume_bundle.resumes.length,2);
});
test('syncing own catalog retains a separately imported public resume',async()=>{
 const friend='d'.repeat(38),linked={id:friend,title:'Friend CV',quality:'full',source_type:'hh',import_origin:'direct_link'};
 const w=worker({initial:{resume_bundle:{primary_id:primary,resumes:[linked]}}});
 const result=await w.send({type:'sync_catalog'});assert.equal(result.ok,true);assert.ok(w.storage.resume_bundle.resumes.some(r=>r.id===friend&&r.import_origin==='direct_link'));
});
test('missing primary does not prevent loading all remaining resumes or silently promote one',async()=>{
  const previous={resumes:[{id:primary,content_hash:'old'}]};
  const w=worker({catalog:entries.filter(e=>!e.url.includes(primary)),initial:{resume_bundle:previous}});
  const result=await w.send({type:'sync_catalog',includeSecondary:true});
  assert.equal(result.ok,true);assert.deepEqual(w.reads,[secondary,other]);assert.equal(w.storage.resume_bundle.primary_id,primary);assert.ok(!w.storage.resume_bundle.resumes.some(r=>r.id===primary));
});
test('other origins cannot initiate privileged navigation under activeTab',async()=>{
  const w=worker({tabUrl:'https://career.huawei.ru/rri/'}); const result=await w.send({type:'sync_catalog'});
  assert.equal(result.ok,false);assert.deepEqual(w.urls,[]);
});

test('HH refresh preserves Google Docs primary and all imported file snapshots',async()=>{
  const google={id:'gdoc_1234567890123',source_type:'google_docs',source_url:'https://docs.google.com/document/d/1234567890123/edit',quality:'full',title:'Google CV'};
  const file={id:'file_'+'e'.repeat(64),source_type:'file',quality:'full',title:'File CV'};
  const w=worker({initial:{resume_bundle:{primary_id:google.id,resumes:[google,file]}}});
  const result=await w.send({type:'sync_catalog'});
  assert.equal(result.ok,true);assert.equal(w.storage.resume_bundle.primary_id,google.id);
  assert.equal(w.storage.resume_bundle.resumes.length,5);
  assert.equal(w.storage.resume_bundle.resumes.find(r=>r.id===google.id).role,'primary');
});
