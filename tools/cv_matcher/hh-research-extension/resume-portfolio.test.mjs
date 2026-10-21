import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class E{constructor(tag,text=''){this.tag=tag;this.textContent=text;this.children=[];this.value='';this.checked=false;}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}setAttribute(){}}
const all=n=>[n,...n.children.filter(n=>n&&typeof n==='object').flatMap(all)];
function page(){const calls=[],copied=[],host=new E('main'),chosen=[{id:'one',version:1},{id:'two',version:2}],context={key:'immutable-context',track:{label:'Generative',revision:1},employment_record:'',snapshots:[],passages:{}};
 const c=vm.createContext({document:{createTextNode:v=>v},make:(t,cls,text)=>new E(t,text),date:String,navigator:{clipboard:{writeText:async v=>copied.push(v)}},api:async(path,data)=>{calls.push({path,...data});if(path==='agent')return {tracks:[{id:'generative',label:'Generative',revision:1}]};if(path.startsWith('entity/'))return {id:path.includes('one')?'one':'two',version_id:path.includes('one')?1:2,payload:{title:'CV'}};if(data.op==='prepare_portfolio')return {context,characters:1000,estimated_input_tokens:[200,500],analysis:null};if(data.op==='prompt')return {prompt:'Full detailed prompt with immutable sources'};if(data.op==='generate')throw Error('Fixture ends before paid execution');throw Error('Unexpected operation');}});
 vm.runInContext(fs.readFileSync(new URL('../archive-web/resume-portfolio.js',import.meta.url),'utf8'),c);const find=label=>all(host).find(n=>n.textContent===label);
 return {host,calls,copied,find,all:()=>all(host),mount:()=>vm.runInContext('ResumePortfolio',c).mount(host,chosen)};
}
test('multi-resume review has explicit API and offline routes; copying never generates',async()=>{
 const p=page();await p.mount();assert.equal(p.calls.filter(c=>c.path==='resume-review').length,0);
 await p.find('Скопировать подробный промпт · без API').onclick();assert.equal(p.copied.length,1);assert.deepEqual(p.calls.filter(c=>c.path==='resume-review').map(c=>c.op),['prepare_portfolio','prompt']);
 await p.find('Разобрать через Luna / Terra · API').onclick();assert.equal(p.calls.filter(c=>c.op==='generate').length,0);
 p.all().filter(n=>n.tag==='input'&&n.type==='checkbox').at(-1).checked=true;
 await p.find('Разобрать через Luna / Terra · API').onclick();assert.equal(p.calls.filter(c=>c.op==='generate').length,1);assert.equal(p.calls.at(-1).confirmed,true);
});
test('changed question invalidates consent and needs a new immutable context',async()=>{
 const p=page();await p.mount();await p.find('Подготовить источники и оценить объём').onclick();
 const paid=p.all().filter(n=>n.tag==='input'&&n.type==='checkbox').at(-1);paid.checked=true;
 const question=p.all().find(n=>n.placeholder?.startsWith('Например:'));question.value='What changed?';question.oninput();assert.equal(paid.checked,false);
 await p.find('Разобрать через Luna / Terra · API').onclick();assert.equal(p.calls.filter(c=>c.op==='generate').length,0);assert.equal(p.calls.filter(c=>c.op==='prepare_portfolio').length,2);
});
