import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class E{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.value='';this.checked=false;this.style={};}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}after(n){this.sibling=n;}}
const all=n=>[n,...n.children.filter(c=>c&&typeof c==='object').flatMap(all)];
const status={enabled:false,phase:'off',model:'text-embedding-3-small',spent_usd:0,monthly_cap_usd:1,max_cap_usd:20,pending:0,older_unscored:1984,last_error:'',embeddings_spent_usd:.25,ceiling_usd:5,max_ceiling_usd:50,history:[{at:'2026-11-05',action:'auto_on',cap_usd:1}]};
function page(value=status){const calls=[],host=new E('section'),anchor=new E('div');
 const c=vm.createContext({document:{createTextNode:v=>v,getElementById:id=>id==='autoScoringPanel'?host.mounted&&host:anchor},make:(t,cls,text)=>new E(t,text),notice:()=>{},api:async(path,body)=>{calls.push(body);return {...value,enabled:body.op==='auto_configure'?body.enabled:value.enabled};}});
 vm.runInContext(fs.readFileSync(new URL('../auto-scoring.js',import.meta.url),'utf8')+';globalThis.UI=AutoScoringUI',c);
 return {calls,enter:()=>c.UI.enter(),nodes:()=>all(anchor.sibling),find:t=>all(anchor.sibling).find(n=>n.textContent===t)};}
test('opening the panel only reads status',async()=>{const p=page();await p.enter();assert.deepEqual(p.calls.map(c=>c.op),['auto_status']);assert.ok(p.nodes().some(n=>/старых без оценки: 1984/.test(n.textContent)));});
test('enabling sends the consent and cap; editing the cap clears consent',async()=>{const p=page();await p.enter();
 const consent=p.nodes().find(n=>n.type==='checkbox'),cap=p.nodes().find(n=>n.type==='number');consent.checked=true;cap.value='2';cap.oninput();assert.equal(consent.checked,false);
 consent.checked=true;await p.find('Включить автоматический расчёт').onclick();
 const sent=p.calls.at(-1);assert.equal(sent.op,'auto_configure');assert.equal(sent.confirmed,true);assert.equal(sent.monthly_cap_usd,2);assert.equal(sent.enabled,true);});
test('the shared ceiling sends consent, and the panel shows spending and the settings log',async()=>{const p=page();await p.enter();
 assert.ok(p.nodes().some(n=>/\$0\.2500 из \$5\.00/.test(n.textContent)));assert.ok(p.nodes().some(n=>/Автоматический расчёт включён · \$1\.00/.test(n.textContent)));
 const consent=p.nodes().find(n=>n.type==='checkbox');const ceiling=p.nodes().filter(n=>n.type==='number').at(-1);ceiling.value='8';ceiling.oninput();assert.equal(consent.checked,false);
 consent.checked=true;await p.find('Сохранить потолок').onclick();const sent=p.calls.at(-1);assert.equal(sent.op,'spend_ceiling');assert.equal(sent.ceiling_usd,8);assert.equal(sent.confirmed,true);});
