import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class E{
 constructor(tag,text){this.tag=tag;this.textContent=text;this.children=[];this.value='';}
 append(...nodes){this.children.push(...nodes);}
 prepend(...nodes){this.children.unshift(...nodes);}
 setAttribute(k,v){this[k]=v;}
 after(node){this.afterNode=node;}
 focus(){this.focused=true;}
 select(){this.selected=true;}
}
function page({clipboard=true,api}={}){
 const ids=Object.fromEntries(['rankingIntro','analysisCV','rankingGoal','filter','search','embeddingModel'].map(k=>[k,new E('input')]));
 Object.assign(ids.analysisCV,{value:'cv-selected'});ids.rankingGoal.value='Ranking goal';ids.filter.value='full';ids.embeddingModel.value='text-embedding-3-small';ids.search.value='PyTorch';
 const calls=[],copied=[],loads=[];
 const response=data=>({prompt:'PROMPT '+data.resume_id+' '+data.packet,packet:data.packet,packets:3,total:120,included:50,characters:75000,resume_title:'Selected CV',unknown_activity:4,fragments:8});
 const c=vm.createContext({tab:'vacancy',summaryData:{goal:'Research goal'},companyPicker:{value:['sber']},$:id=>ids[id],make:(tag,cls,text)=>new E(tag,text),notice(){},loadList:async()=>loads.push(ids.filter.value),navigator:{clipboard:{writeText:async text=>{if(!clipboard)throw Error('Clipboard unavailable');copied.push(text);}}},api:async(path,data)=>{calls.push({path,data});return api?api(data):response(data);}});
 vm.runInContext(fs.readFileSync(new URL('../archive-web/vacancy-selection.js',import.meta.url),'utf8'),c);
 const root=ids.rankingIntro.afterNode,all=node=>[node,...(node.children||[]).flatMap(all)],find=text=>all(root).find(n=>n.textContent===text),field=label=>find(label).children[0];
 return {c,ids,calls,copied,loads,root,find,field,response,copy:()=>find('Скопировать запрос на отбор вакансий · без API').onclick()};
}
test('copy selection uses selected CV and current filters without triggering ranking or generation',async()=>{
 const p=page();await p.copy();assert.equal(p.calls.length,1);assert.equal(p.calls[0].path,'workflow');const d=p.calls[0].data;
 assert.equal(d.op,'vacancy_selection_prompt');assert.equal(d.resume_id,'cv-selected');assert.equal(d.goal,'Research goal');assert.equal(d.q,'PyTorch');assert.equal(d.status,'full');assert.equal(d.ranked_only,false);assert.deepEqual(Array.from(d.companies),['sber']);assert.equal(d.limit,50);assert.equal(d.packet,1);assert.deepEqual(p.copied,['PROMPT cv-selected 1']);
});
test('next packet advances but changing CV or company filters restarts packet numbering',async()=>{
 const p=page();await p.copy();await p.find('Следующий пакет').onclick();assert.equal(p.calls.at(-1).data.packet,2);
 p.c.companyPicker.value=['yandex'];await p.find('Следующий пакет').onclick();assert.equal(p.calls.at(-1).data.packet,1);assert.deepEqual(Array.from(p.calls.at(-1).data.companies),['yandex']);
 p.ids.analysisCV.value='friend-cv';await p.copy();assert.equal(p.calls.at(-1).data.resume_id,'friend-cv');assert.equal(p.calls.at(-1).data.packet,1);
});
test('ranking view sends its goal and keeps ranking scope while allowing user preferences',async()=>{
 const p=page();p.c.tab='ranking';p.field('Что учитывать при отборе').value='Prioritize DiT';p.field('Карточек в пакете').value='100';p.field('Сколько рекомендаций запросить').value='20';await p.copy();
 const d=p.calls[0].data;assert.equal(d.ranked_only,true);assert.equal(d.goal,'Ranking goal');assert.equal(d.comments,'Prioritize DiT');assert.equal(d.limit,100);assert.equal(d.top,20);
});
test('missing clipboard permission reveals a selectable prompt for manual copy',async()=>{
 const p=page({clipboard:false});await p.copy();const text=p.find('Текст запроса · просмотр и ручное копирование');
 const area=p.root.children.find(n=>n.tag==='details'&&n.children.includes(text)).children.find(n=>n.tag==='textarea');
 assert.equal(area.value,'PROMPT cv-selected 1');assert.equal(area.selected,true);assert.equal(area.readOnly,true);assert.equal(p.find('Скопировать запрос на отбор вакансий · без API').disabled,false);
});
test('CV change while request is running prevents copying stale context',async()=>{
 let finish;const p=page({api:data=>new Promise(resolve=>{finish=()=>resolve(p.response(data));})}),pending=p.copy();
 p.ids.analysisCV.value='changed-cv';finish();await pending;assert.equal(p.copied.length,0);
 assert.equal(p.find('Скопировать запрос на отбор вакансий · без API').disabled,false);assert.ok(p.root.children.some(n=>String(n.textContent).includes('CV или фильтры изменились')));
});
test('short-card control changes only the quality filter and does not queue a paid operation',async()=>{
 const p=page();await p.find('Включить короткие карточки: статус «Все записи»').onclick();assert.deepEqual(p.loads,['']);assert.equal(p.calls.length,0);
});
test('all-vacancies checkbox requests entire archive and disables packet controls',async()=>{
 const p=page({api:data=>({...p.response(data),all_vacancies:true,packets:1,packet:1,included:1925,total:1925,large_prompt:true})});
 const checkbox=p.field('Все вакансии из архива · одним запросом');checkbox.checked=true;checkbox.onchange();
 assert.equal(p.field('Карточек в пакете').disabled,true);assert.equal(p.field('Номер пакета').disabled,true);
 p.c.tab='ranking';await p.copy();const data=p.calls[0].data;
 assert.equal(data.all_vacancies,true);assert.equal(data.ranked_only,false);assert.equal(data.companies,null);assert.equal(data.q,'');assert.equal(data.status,'');assert.equal(data.description_chars,600);
 assert.equal(p.find('Следующий пакет').hidden,true);assert.ok(p.root.children.some(n=>String(n.textContent).includes('весь архив')));
 checkbox.checked=false;checkbox.onchange();assert.equal(p.field('Номер пакета').disabled,false);assert.equal(p.field('Карточек в пакете').disabled,false);
});
