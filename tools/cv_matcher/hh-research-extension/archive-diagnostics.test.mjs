import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('../archive-web/archive.js',import.meta.url),'utf8');
function harness(response){
 class Node{constructor(tag){this.tag=tag;this.children=[];this.hidden=false;this.content='';}append(...nodes){this.children.push(...nodes);}setAttribute(){}set textContent(s){this.content=s;this.children=[];}get textContent(){return this.content+this.children.map(n=>n.textContent||'').join(' ');}querySelectorAll(){return this.children.filter(n=>n.className==='diagnostic');}remove(){}}
 const elements=new Map();const sandbox={Error,JSON,String,Date,AbortSignal,navigator:{clipboard:{writeText:async()=>{}}},fetch:async()=>response,$:id=>{if(!elements.has(id))elements.set(id,new Node('div'));return elements.get(id);},make:(tag,cls,text)=>{const n=new Node(tag);n.className=cls;if(text)n.textContent=text;return n;}};
 vm.runInNewContext(source.slice(source.indexOf('let lastDiagnostic;'),source.indexOf('function external('))+';globalThis.publicAPI={api,notice,showDiagnostic};',sandbox);return {sandbox,elements,...sandbox.publicAPI};
}
test('request failure keeps HTTP status and request ID even after a legacy notice handler; no body or query secrets',async()=>{
 const h=harness({status:422,ok:false,headers:{get:()=> 'diagnostic-123'},json:async()=>({detail:'Описание изменилось'})});let error;try{await h.api('analytics-batch?token=fixture-secret',{cv:'PRIVATE CV'});}catch(e){error=e;}
 assert.equal(error.status,422);assert.equal(error.endpoint,'/archive/analytics-batch');assert.equal(error.diagnosticId,'diagnostic-123');h.notice(error.message);
 const text=h.elements.get('notice').textContent;assert.ok(text.includes('Техническая диагностика'));assert.ok(text.includes('diagnostic-123'));assert.ok(!text.includes('fixture-secret'));assert.ok(!text.includes('PRIVATE CV'));assert.notEqual(h.elements.get('login')?.hidden,false);
});
test('non JSON and client errors retain diagnostics, credential details are redacted',async()=>{
 const h=harness({status:502,ok:false,headers:{get:()=> 'd-502'},json:async()=>{throw Error('bad JSON');}});await assert.rejects(h.api('analytics'),/не является JSON/);assert.ok(h.elements.get('notice').textContent.includes('502'));
 h.showDiagnostic(new Error('Failed at https://localhost/#connect=secret-code'),'Загрузка');assert.ok(!h.elements.get('notice').textContent.includes('secret-code'));
});
