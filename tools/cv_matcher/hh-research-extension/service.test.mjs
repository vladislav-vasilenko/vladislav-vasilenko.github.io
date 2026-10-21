import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
function bridge(ok=true){const stored={},calls=[];const ctx=vm.createContext({AbortSignal,chrome:{permissions:{request:async()=>true},storage:{session:{get:async()=>stored,set:async obj=>Object.assign(stored,obj)}}},fetch:async(url,options)=>{calls.push({url,options});return {ok,json:async()=>ok?{ok:true,service:'cv-matcher-local',openai_configured:false}:{detail:'Неверный код'}};}});vm.runInContext(fs.readFileSync(new URL('local-service.js',import.meta.url),'utf8'),ctx);return {api:ctx.LocalResumeService,stored,calls};}
test('local pairing stores only a verified session code and targets fixed loopback endpoint',async()=>{const b=bridge();await b.api.connect('a'.repeat(43));await b.api.request('/rank',{resume_id:'selected'});assert.equal(b.stored.resume_import_token,'a'.repeat(43));assert.ok(b.calls.every(c=>c.url.startsWith('http://127.0.0.1:8788/')));await assert.rejects(b.api.request('/unknown'));});
test('incorrect code and API-key-shaped input are not stored in the extension',async()=>{const b=bridge(false);await assert.rejects(b.api.connect('a'.repeat(43)));assert.equal(b.stored.resume_import_token,undefined);await assert.rejects(b.api.connect('sk-proj-'+'a'.repeat(100)));assert.equal(b.calls.length,1);});

test('pairing persistence requires an explicit remember option and can be disabled again',async()=>{
 const local={},session={},chrome={permissions:{request:async()=>true},storage:{local:{get:async()=>local,set:async d=>Object.assign(local,d),remove:async k=>delete local[k]},session:{get:async()=>session,set:async d=>Object.assign(session,d)}}};
 const ctx=vm.createContext({chrome,AbortSignal,fetch:async()=>({ok:true,json:async()=>({ok:true,service:'cv-matcher-local'})})});vm.runInContext(fs.readFileSync(new URL('local-service.js',import.meta.url),'utf8'),ctx);
 await ctx.LocalResumeService.connect('a'.repeat(43));assert.equal(local.remembered_resume_import_token,undefined);
 await ctx.LocalResumeService.connect('a'.repeat(43),{remember:true});assert.equal(local.remembered_resume_import_token,'a'.repeat(43));delete session.resume_import_token;await ctx.LocalResumeService.request('/health');
 await ctx.LocalResumeService.connect('a'.repeat(43));assert.equal(local.remembered_resume_import_token,undefined);
});
