import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class E{constructor(tag=''){this.tag=tag;this.children=[];this.value='';this.checked=false;}append(...x){this.children.push(...x);}prepend(...x){this.children.unshift(...x);}replaceChildren(...x){this.children=x;}insertBefore(node,ref){this.children.splice(this.children.indexOf(ref),0,node);}setAttribute(){}}
function page(result,backfill={run:null,counts:{},sources:[],issues:[]}){let snapshot=backfill;const ticks=[];const root=new E(),cv={value:'selected-cv'},actions=[],calls=[];const c=vm.createContext({tab:'vacancy',selection:null,setInterval:fn=>ticks.push(fn),make:(tag,cls,text)=>Object.assign(new E(tag),{textContent:text}),$:id=>id==='analysisCV'?cv:root,document:{createTextNode:t=>t},api:async(path,data)=>{calls.push(data);if(data.op.startsWith('collection_backfill'))return snapshot;return ['collection_status','resume_import_status'].includes(data.op)?result:{vacancy_id:'yandex_11031',resume_id:'b'.repeat(38),command_id:'cmd'};},notice:t=>actions.push(['notice',t]),reload:async()=>actions.push(['reload']),setTab:t=>actions.push(['tab',t]),openDetail:async(k,id)=>actions.push(['open',id]),Flow:{create:async j=>actions.push(['letter',j.id])},Journey:{connect:async()=>actions.push(['setup'])}});vm.runInContext(fs.readFileSync(new URL('../intake.js',import.meta.url),'utf8'),c);const all=node=>[node,...(node.children||[]).flatMap(all)];const find=label=>all(root).find(n=>n.textContent===label);return {root,find,actions,calls,ticks,all:()=>all(root),setBackfill:v=>snapshot=v,settle:async()=>{await new Promise(resolve=>setImmediate(resolve));}};}
test('single URL capture surfaces permission refusal and releases the button without requesting any generation',async()=>{
 const p=page({state:'needs_input',result:{note:'Разрешите yandex.ru в настройках расширения.'}}),b=p.find('Загрузить полное описание');await b.onclick();assert.equal(b.disabled,false);assert.equal(p.calls.length,3);assert.match(p.actions.at(-1)[1],/Разрешите yandex/);await p.find('Настроить чтение сайтов в расширении').onclick();assert.equal(p.actions.at(-1)[0],'setup');
});
test('pasted or captured job enters the cover editor for selected CV without ranking or API generation',async()=>{
 for(const button of ['Сохранить текст и подготовить письмо','Загрузить полное описание']){const p=page({state:'complete',result:{},vacancy_id:'yandex_11031'});await p.find(button).onclick();assert.deepEqual(p.actions.at(-1),['letter','yandex_11031']);assert.ok(p.calls.every(r=>['collection_backfill','vacancy_import','collect_one','collection_status'].includes(r.op)));}
});
test('resume link import opens the saved CV explicitly without generating a letter or selecting it as primary',async()=>{
 const id='b'.repeat(38),p=page({state:'complete',result:{note:'Резюме сохранено'},resume_id:id});
 await p.find('Добавить через Chrome').onclick();assert.deepEqual(p.calls.map(c=>c.op),['collection_backfill','resume_import','resume_import_status']);
 await p.find('Открыть сохранённое резюме').onclick();assert.deepEqual(p.actions.at(-1),['open',id]);assert.ok(p.actions.every(a=>a[0]!=='letter'));
});

const running={run:{id:'durable-run',state:'running'},total:10,counts:{complete:3,reading:1,pending:5,needs_input:1},sources:[],issues:[]};
test('backfill restores a durable run and updates visible progress even with details collapsed',async()=>{
 const p=page({},running);await p.settle();
 const box=p.all().find(n=>n.tag==='details'&&n.open),meter=p.all().find(n=>n.tag==='progress');
 assert.ok(box);assert.equal(meter.value,40);assert.ok(p.find('Дозагрузка выполняется · 4 из 10 · 40%'));
 box.open=false;p.setBackfill({...running,counts:{complete:5,reading:1,pending:3,needs_input:1}});
 await p.ticks[0]();await p.settle();assert.equal(meter.value,60);assert.ok(p.find('Дозагрузка выполняется · 6 из 10 · 60%'));
 assert.ok(p.all().find(n=>n.textContent?.includes('не как загруженные описания')));
 assert.ok(p.calls.every(c=>c.op==='collection_backfill'));
});
test('starting backfill immediately reveals progress; terminal outcome is visible and no restart occurs',async()=>{
 const p=page({});await p.settle();p.setBackfill(running);
 await p.find('Дозагрузить полные описания').onclick();assert.ok(p.find('Дозагрузка выполняется · 4 из 10 · 40%'));
 p.setBackfill({...running,run:{id:'durable-run',state:'needs_input'},counts:{complete:9,needs_input:1}});
 await p.ticks[0]();await p.settle();assert.ok(p.find('Дозагрузка: нужна проверка · 10 из 10 · 100%'));
 const count=p.calls.filter(c=>c.op==='collection_backfill_start').length;await p.ticks[0]();await p.settle();assert.equal(p.calls.filter(c=>c.op==='collection_backfill_start').length,count);
});
