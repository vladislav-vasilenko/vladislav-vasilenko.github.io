import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import {webcrypto} from 'node:crypto';
const core=fs.readFileSync(new URL('linkedin-core.js',import.meta.url),'utf8'),content=fs.readFileSync(new URL('linkedin-content.js',import.meta.url),'utf8');
const ctx=vm.createContext({URL,crypto:webcrypto,TextEncoder});vm.runInContext(core,ctx);
test('LinkedIn IDs are stable and URL origins cannot escape',()=>{
 assert.equal(ctx.LinkedInCore.url('https://linkedin.com/jobs/search/?currentJobId=123&trackingId=x','job'),'https://www.linkedin.com/jobs/view/123/');assert.equal(ctx.LinkedInCore.url('https://www.linkedin.com/in/tech/en/','profile'),'https://www.linkedin.com/in/tech/');
 for(const url of ['http://www.linkedin.com/in/a/','https://www.linkedin.com.evil.test/in/a/','https://u:p@www.linkedin.com/in/a/','https://www.linkedin.com/in/%2f/'])assert.throws(()=>ctx.LinkedInCore.url(url,'profile'));
});
function formContext({title='Edit intro',two=false,url='https://www.linkedin.com/in/owner/',headline='Original'}={}){
 const node=(tag,type,label,value)=>({tagName:tag,type,labels:[{innerText:label}],value,checked:false,disabled:false,readOnly:false,maxLength:220,getAttribute:()=>null,getClientRects:()=>[{}]});const nodes=[node('INPUT','text','Headline',headline),node('INPUT','password','Password','SECRET'),node('INPUT','file','File','PRIVATE'),node('INPUT','hidden','Session','TOKEN')];
 const dialog={querySelector:()=>({innerText:title}),querySelectorAll:()=>nodes,getClientRects:()=>[{}]};const document={querySelector:()=>null,querySelectorAll:s=>s==='[role="dialog"],dialog[open]'?(two?[dialog,dialog]:[dialog]):[]};
 const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,document,location:new URL(url),getComputedStyle:()=>({visibility:'visible'})});vm.runInContext(core,c);vm.runInContext(content,c);return c;
}
test('editor excludes secrets and refuses ambiguous and messaging forms',async()=>{
 const p={account:'https://www.linkedin.com/in/owner/'};const state=await formContext().LinkedInSession.handle('profile.form',p);assert.equal(state.fields.length,1);assert.equal(state.fields[0].label,'Headline');assert.ok(!JSON.stringify(state).includes('SECRET'));
 for(const options of [{two:true},{title:'New message'},{url:'https://www.linkedin.com/in/somebody/'}])await assert.rejects(()=>formContext(options).LinkedInSession.handle('profile.form',p));
});
test('changed form stops before input',async()=>{
 await assert.rejects(()=>formContext({headline:'Changed'}).LinkedInSession.handle('profile.fill',{account:'https://www.linkedin.com/in/owner/',snapshot:{form_fingerprint:'old'},values:{f0:'new'}}),/изменилась/);
});
test('worker keeps its identity and receipt outside quota-limited chrome.storage',async()=>{
 const memory=new Map(),calls=[],localWrites=[];let resolveClaim;const claimed=new Promise(r=>resolveClaim=r);
 const db={close(){},transaction(){const t={};t.objectStore=()=>({get(key){const r={};queueMicrotask(()=>{r.result=memory.get(key);r.onsuccess?.();t.oncomplete?.();});return r;},put(value,key){memory.set(key,value);const r={};queueMicrotask(()=>{r.onsuccess?.();t.oncomplete?.();});return r;},delete(key){memory.delete(key);const r={};queueMicrotask(()=>{r.onsuccess?.();t.oncomplete?.();});return r;}});return t;}};
 const indexedDB={open(){const r={result:db};queueMicrotask(()=>r.onsuccess?.());return r;}};
 const chrome={permissions:{contains:async()=>true},alarms:{get:async()=>({name:'linkedin-workspace'}),create(){},onAlarm:{addListener(){}}},runtime:{id:'fixture',getManifest:()=>({version:'0.12.0'}),onMessage:{addListener(){}}},storage:{local:{get:async()=>({linkedin_enabled:true}),set:async()=>{localWrites.push(1);throw Error('Resource::kQuotaBytes quota exceeded');}},session:{get:async()=>({}),set:async()=>{throw Error('Resource::kQuotaBytes quota exceeded');}}}};
 const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,chrome,indexedDB,console,queueMicrotask,setTimeout,clearTimeout,LocalResumeService:{request:async(path,data)=>{calls.push(data);resolveClaim();return {command:null};}}});vm.runInContext(fs.readFileSync(new URL('linkedin-worker.js',import.meta.url),'utf8'),c);await claimed;assert.equal(calls[0].op,'claim');assert.match(calls[0].worker_id,/^linkedin-/);assert.equal(localWrites.length,0);assert.equal(memory.get('worker_id'),calls[0].worker_id);
});

test('current profile headline is read from scoped intro without mistaking location or name for headline',()=>{
 const headline='GenAI Research Engineer | Generative Modeling • LLMs • Flow Matching | Product Leader';
 const intro=['Vladislav Vasilenko','He/Him','Verify in 2 minutes',headline,'London Area, United Kingdom','·','Contact info'].join('\n\n');
 assert.equal(ctx.LinkedInCore.introHeadline(intro,'Vladislav Vasilenko'),headline);
 assert.equal(ctx.LinkedInCore.introHeadline('Vladislav Vasilenko\nLondon Area, United Kingdom\nContact info','Vladislav Vasilenko'),'');
 assert.equal(ctx.LinkedInCore.introHeadline(headline+'\nOther Research Engineer','Vladislav Vasilenko'),'');
});
