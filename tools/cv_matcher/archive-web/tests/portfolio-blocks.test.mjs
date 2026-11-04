import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class E{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.value='';this.checked=false;this.style={};}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}}
const all=n=>[n,...n.children.filter(c=>c&&typeof c==='object').flatMap(all)];
const row={company:'Lab',role:'Engineer',period:'Март 2025 — сейчас',duration:'1 год',description:'Новый текст'};
const data=()=>({basis:'b1',captured_at:'2026-11-05',source_url:'',block_review:true,auto_publish:true,translation_language:null,counts:{pending:1,acknowledged:0,same:1},blocks:[
 {key:'title',kind:'title',label:'Заголовок резюме',status:'same',acknowledged:false,fields_changed:[],diff:{text:[]},site:{text:'T'},hh:{text:'T'}},
 {key:'experience:lab|2025-03',kind:'experience',label:'Lab · Март 2025',status:'changed',acknowledged:false,fields_changed:['description'],diff:{company:[],role:[],period:[],duration:[],description:[{op:'del',text:'<b>Старый</b>'},{op:'add',text:'Новый'}]},site:{...row,description:'Старый'},hh:row,site_translation:null}]});
function page(value){const calls=[],notices=[],root=new E('div');
 const c=vm.createContext({document:{createTextNode:v=>v},make:(t,cls,text)=>{const n=new E(t,text);n.className=cls;return n;},date:String,external:(u,l)=>new E('a',l),notice:m=>notices.push(m),api:async(path,body)=>{calls.push(body);if(body.op==='block_compare')return value;return {phase:'published',comparison:{...value,blocks:[value.blocks[0]],counts:{pending:0,acknowledged:0,same:1}}};}});
 vm.runInContext(fs.readFileSync(new URL('../portfolio-blocks.js',import.meta.url),'utf8')+';globalThis.PB=PortfolioBlocks',c);
 return {root,calls,notices,mount:()=>c.PB.mount(root),nodes:()=>all(root),find:t=>all(root).find(n=>n.textContent===t)};}
test('differences render as text nodes, and comparing sends no apply request',async()=>{
 const p=page(data());await p.mount();
 const removed=p.nodes().find(n=>n.tag==='del');assert.equal(removed.textContent,'<b>Старый</b>');assert.equal(p.nodes().find(n=>n.tag==='ins').textContent,'Новый');
 assert.deepEqual(p.calls.map(c=>c.op),['block_compare']);assert.ok(!p.nodes().some(n=>n.textContent==='Заголовок резюме'));
});
test('rewrite opens editable fields and editing clears the review confirmation',async()=>{
 const p=page(data());await p.mount();
 const radio=p.nodes().find(n=>n.value==='rewrite');radio.onchange();
 const area=p.nodes().find(n=>n.tag==='textarea');assert.equal(area.value,'Новый текст');
 const review=p.nodes().filter(n=>n.type==='checkbox').at(-1);review.checked=true;area.value='Своя редакция';area.oninput();assert.equal(review.checked,false);
 review.checked=true;await p.find('Применить решения и опубликовать').onclick();
 const sent=p.calls.at(-1);assert.equal(sent.op,'block_apply');assert.equal(sent.basis,'b1');assert.equal(sent.reviewed,true);
 const decision=sent.decisions['experience:lab|2025-03'];assert.equal(decision.action,'rewrite');assert.equal(decision.value.description,'Своя редакция');
});
test('a changed block asks for its translation when the site has one',async()=>{
 const p=page({...data(),translation_language:'en'});await p.mount();
 assert.equal(p.nodes().filter(n=>n.tag==='textarea').length,0);
 p.nodes().find(n=>n.value==='hh').onchange();assert.ok(p.nodes().some(n=>n.textContent==='EN · Описание'));
});
test('warns while automatic publication would overwrite the site without review',async()=>{
 const p=page({...data(),block_review:false});await p.mount();
 assert.ok(p.nodes().some(n=>/без проверки/.test(n.textContent)));
});
