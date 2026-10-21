import test from 'node:test';import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';import vm from 'node:vm';import fs from 'node:fs';
globalThis.crypto??=webcrypto;import './resume-core.js';import './resume-import-core.js';
test('Google link is canonical, source-specific and cannot target arbitrary hosts',()=>{
 const d=ResumeImports.googleDoc('https://docs.google.com/document/d/1234567890_ABC/edit?usp=sharing');
 assert.equal(d.id,'gdoc_1234567890_ABC');assert.ok(d.export_url.endsWith('/export?format=txt'));
 for(const u of ['http://docs.google.com/document/d/1234567890/edit','https://docs.google.com.evil.test/document/d/1234567890/edit','https://docs.google.com/spreadsheets/d/1234567890/edit']) assert.throws(()=>ResumeImports.googleDoc(u));
});
test('document preview confirmation produces normalized content version without fabricating HH experience',async()=>{
 const file={id:'file_'+'a'.repeat(64),source_type:'file',file_hash:'a'.repeat(64),title:'CV'};
 const s=await ResumeImports.documentSnapshot(file,'PyTorch ML experience '.repeat(20)+' test@example.com +7 (999) 123-45-67','CV');
 assert.equal(s.quality,'full');assert.equal(s.sections[0].key,'document');assert.ok(!s.sections[0].text.includes('example.com'));assert.ok(!s.sections[0].text.includes('999'));
 assert.equal(s.content_hash,await ResumeSync.contentHash(s));assert.ok(s.reviewed_at);
 const b=ResumeImports.selectPrimary({primary_id:'old',resumes:[{id:'old',quality:'full'},s]},s.id);
 assert.equal(b.resumes[0].role,'secondary');assert.equal(b.primary_id,s.id);
 assert.throws(()=>ResumeImports.selectPrimary(b,'unknown'));
});
test('Google export rejects a login HTML page and failed fetch instead of saving it as a resume',async()=>{
 for(const fetch of [async()=>({ok:true,headers:{get:()=> 'text/html'},text:async()=>'<html>Sign in</html>'}),async()=>{throw new Error('Network denied');}]) {
  const result=await vm.runInNewContext(fs.readFileSync(new URL('docs-content.js',import.meta.url),'utf8'),{ResumeImports,ResumeSync,fetch,location:new URL('https://docs.google.com/document/d/1234567890/edit'),document:{title:'CV - Google Docs'},Date,AbortSignal});
  assert.ok(result.error);assert.equal(result.candidate,undefined);
 }
});

test('Google public export uses anonymous retry after credentialed CORS failure',async()=>{
 const calls=[];
 const result=await vm.runInNewContext(fs.readFileSync(new URL('docs-content.js',import.meta.url),'utf8'),{ResumeImports,ResumeSync,fetch:async(url,options)=>{calls.push(options.credentials);if(options.credentials==='include')throw new Error('CORS');return {ok:true,headers:{get:()=> 'text/plain'},text:async()=> 'PyTorch Transformer '.repeat(20)};},location:new URL('https://docs.google.com/document/d/1234567890/edit'),document:{title:'CV - Google Docs'},Date,AbortSignal});
 assert.deepEqual(calls,['include','omit']);assert.equal(result.candidate.title,'CV');assert.ok(result.candidate.text.length>100);
});
