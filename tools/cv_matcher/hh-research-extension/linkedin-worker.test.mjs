import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('linkedin-worker.js',import.meta.url),'utf8');
function fixture(){
 let version='0.13.2',injections=0,allow=true;const calls=[],windowChanges=[],doc=vm.createContext({});const chrome={runtime:{getManifest:()=>({version}),onMessage:{addListener(){}}},permissions:{contains:async()=>true},alarms:{get:async()=>({}),create:async()=>{},onAlarm:{addListener(){}}},tabs:{query:async()=>[{id:1}],get:async()=>({id:1,windowId:7}),update:async()=>{}},windows:{get:async()=>({state:'normal'}),update:async(id,data)=>windowChanges.push({id,...data})},scripting:{executeScript:async data=>{if(data.files){injections++;doc.LinkedInSession={handle:async op=>({operation:op})};return [];}doc.args=data.args||[];return [{result:await vm.runInContext('('+data.func.toString()+')(...args)',doc)}];}}};
 const context=vm.createContext({chrome,LocalResumeService:{request:async(path,data)=>{calls.push(data);return {continue:allow};}},setTimeout:fn=>{queueMicrotask(fn);return 1;},clearTimeout(){},console});const marker=' void tick();\n})();';assert.ok(source.includes(marker));vm.runInContext(source.replace(marker,' globalThis.workerTest={ensureAdapters,readProfile,collectListing,setDom:fn=>{dom=fn;}};\n})();'),context);
 return {api:context.workerTest,calls,windowChanges,get injections(){return injections;},set version(value){version=value;},navigate(){delete doc.LinkedInSession;delete doc.__linkedinAdapterVersion;},stop(){allow=false;},doc};
}
test('adapter caching injects once and invalidates on page navigation or extension version change',async()=>{
 const f=fixture();await f.api.ensureAdapters(1);await f.api.ensureAdapters(1);assert.equal(f.injections,1);f.navigate();await f.api.ensureAdapters(1);assert.equal(f.injections,2);f.version='0.13.3';await f.api.ensureAdapters(1);assert.equal(f.injections,3);await f.api.ensureAdapters(1);assert.equal(f.injections,3);
});
const profile=()=>({headline:'Research Engineer',sections:Object.fromEntries(['about','experience','education','certifications','courses'].map(key=>[key,{text:'',coverage:'not_visible',links:[]}]))});
test('profile traversal passes an unchanged Activity area and waits for the page boundary',async()=>{
 const f=fixture();let scrolls=0;f.api.setDom(async(id,op)=>{if(op==='profile.advance')return {at_end:++scrolls>=20};if(op==='profile.read'){const value=profile();if(scrolls>=12)value.sections.experience.text='LATE LOADED EXPERIENCE';return value;}throw Error('Unexpected '+op);});
 const result=await f.api.readProfile({cmd:{id:'read'},w:'worker',op:'profile.read',p:{}},1);assert.ok(scrolls>=20);assert.equal(result.data.sections.experience.text,'LATE LOADED EXPERIENCE');
});
test('cancelled profile reading does not open About or follow detail editors afterwards',async()=>{
 const f=fixture();f.stop();const operations=[];f.api.setDom(async(id,op)=>{operations.push(op);if(op==='profile.advance')return {at_end:false};if(op==='profile.read')return {...profile(),about_edit_url:'https://www.linkedin.com/in/owner/edit/forms/summary/new/'};throw Error('No editor may open after Stop');});const result=await f.api.readProfile({cmd:{id:'read'},w:'worker',op:'profile.read',p:{}},1);assert.equal(result.state,'cancelled');assert.deepEqual(operations,['profile.read','profile.advance','profile.read']);
});

test('chat collection scrolls a virtualized list past 70 rows, waits for a slow next batch and checkpoints each thread',async()=>{
 const f=fixture(),selected=new Set(),operations=[];let first=0,advances=0,waiting=0;
 f.api.setDom(async(id,op,p)=>{operations.push(op);if(op==='messages.navigate')return {navigated:false};if(op==='messages.reset'){first=0;return {reset:true};}if(op==='messages.list')return {items:[],card_count:10};if(op==='messages.select'){const index=Array.from({length:Math.min(10,85-first)},(_,i)=>first+i).find(i=>!p.seen_keys.includes('thread-'+i));if(index===undefined)return {clicked:false};selected.add(index);return {clicked:true,key:'thread-'+index,item:{url:'https://www.linkedin.com/messaging/thread/t'+index+'/',name:'Person '+index}};}if(op==='messages.advance'){advances++;const at_end=first>=70;if(first===70&&waiting++<7)return {at_end:true};if(first<80)first+=10;return {at_end};}throw Error('Unexpected '+op);});
 const result=await f.api.collectListing({cmd:{id:'all-chats'},w:'worker',op:'messages.list',p:{scope:'all',limit:10000,collect_all:true}},1);
 assert.deepEqual(f.windowChanges,[{id:7,focused:true}]);assert.equal(result.state,'completed');assert.equal(result.data.collected_threads.length,85);assert.equal(selected.size,85);assert.equal(result.data.listing_coverage,'available_boundary');assert.ok(advances>20);assert.ok(operations.indexOf('messages.reset')<operations.indexOf('messages.list'));assert.equal(f.calls.filter(c=>c.op==='checkpoint'&&c.outcome.data.items.length===1).length,85);
});

test('a selected chat limit is reported separately from reaching the available list boundary',async()=>{
 const f=fixture();f.api.setDom(async(id,op)=>{if(op==='messages.navigate')return {navigated:false};if(op==='messages.reset')return {reset:true};if(op==='messages.list')return {items:[{url:'https://www.linkedin.com/messaging/thread/one/'}],card_count:1};throw Error('No scrolling or opening after limit');});const result=await f.api.collectListing({cmd:{id:'limit'},w:'worker',op:'messages.list',p:{scope:'all',limit:1}},1);assert.equal(result.data.listing_coverage,'selected_limit');
});

test('a chat list that keeps offering more without loading data stops as incomplete',async()=>{
 const f=fixture();let clicks=0;f.api.setDom(async(id,op)=>{if(op==='messages.navigate')return {navigated:false};if(op==='messages.reset')return {reset:true};if(op==='messages.list')return {items:[{url:'https://www.linkedin.com/messaging/thread/one/'}],card_count:1};if(op==='messages.select')return {clicked:false};if(op==='messages.advance'){clicks++;return {load_more:true,at_end:false};}throw Error('Unexpected '+op);});const result=await f.api.collectListing({cmd:{id:'no-next-batch'},w:'worker',op:'messages.list',p:{scope:'all',limit:10000}},1);assert.equal(result.state,'needs_input');assert.equal(result.data.listing_coverage,'read_error');assert.ok(clicks<=30);assert.equal(result.data.collected_threads.length,1);
});
