import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element{constructor(tag){this.tag=tag;this.dataset={};this.children=[];this.style={};this.value='';this.disabled=false;this.hidden=false;this.attributes={};this.listeners={};}addEventListener(type,fn){(this.listeners[type]||=[]).push(fn);}append(...rows){for(const row of rows){if(row.parent)row.parent.children=row.parent.children.filter(n=>n!==row);row.parent=this;}this.children.push(...rows);if(this.tag==='select'&&!this.value)this.value=rows[0]?.value||'';}replaceChildren(...rows){this.children=rows;}setAttribute(k,v){this.attributes[k]=v;}attachShadow(){return this.shadow=new Element('shadow');}remove(){this.removed=true;}}
function setup(){const body=new Element('body'),ctx=vm.createContext({URL,Date,document:{body,createElement:t=>new Element(t),addEventListener(){},removeEventListener(){}},innerWidth:1280,innerHeight:720,navigator:{clipboard:{writeText:async()=>{}}}});for(const file of ['hh-badges-core.js','chatgpt-export.js','hh-inline-ui.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),ctx);const find=(node,tag,text)=>{if(node.tag===tag&&(!text||node.textContent===text))return node;for(const child of node.children||[]){const result=find(child,tag,text);if(result)return result;}};return {ctx,body,find};}
const context={id:'hh_1',title:'ML role',resume_title:'Selected CV',question:'Какие модели вы обучали?'};
const report={cached:true,recommendation_reason:'Уточните опыт.',metrics:{overall:{percent:55},dimensions:[]},requirements:[],rubric:'Покрытие подтверждениями.'};
test('inline cached analysis opens without generation and missing requirements are complete disclosure text',async()=>{
 const {ctx,body,find}=setup(),calls=[],panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:report};},onResult(){}});await panel.open('analysis',context);const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.equal(calls.length,1);assert.equal(calls[0].action,'analysis_read');assert.equal(find(drawer,'button','Разбор сохранён').disabled,true);
 const target=new Element('div'),skill='Very long requirement '.repeat(30);ctx.HHInline.card(target,{data:{cv_ready:true,resume_title:'CV'},item:{full:true,title:'ML role',coverage:55,missing_skills:[skill],missing_count:1},title:'ML role',onAction(){}});assert.ok(find(target,'details'));assert.equal(find(target,'li').textContent,skill);assert.equal(find(target,'button','Соответствие').disabled,false);
});
test('cover and answer settings never generate until explicit button, pass selected vacancy and allow editing',async()=>{
 const {ctx,body,find}=setup(),calls=[],panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:{text:'Draft',answer:'Confirmed answer',cached:false,review_note:'Review'}};},onResult(){}});await panel.open('cover',context);let drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.equal(calls.length,1);assert.equal(calls[0].action,'cover_read');find(drawer,'input').value='50';find(drawer,'textarea').value='Моя мотивация';await find(drawer,'button','Составить письмо · Luna').onclick();assert.equal(calls[1].sentence_count,50);assert.equal(calls[1].comments,'Моя мотивация');assert.equal(calls[1].vacancy_id,'hh_1');assert.ok(find(drawer,'button','Скопировать'));
 await panel.open('answer',context);drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.equal(calls.length,2);find(drawer,'select').value='terra';find(drawer,'textarea').value='Edited question';await find(drawer,'button','Предложить ответ').onclick();assert.equal(calls[2].question,'Edited question');assert.equal(calls[2].model,'terra');assert.equal(calls[2].action,'answer');
});
test('missing full description disables paid actions and closing a panel discards delayed output',async()=>{
 const {ctx,body,find}=setup(),target=new Element('div');ctx.HHInline.card(target,{data:{cv_ready:true,resume_title:'CV'},item:{title:'ML role',full:false},title:'ML role',onAction(){}});assert.equal(find(target,'button','Соответствие').disabled,true);
 let resolve;const panel=ctx.HHInline.create({send:()=>new Promise(r=>resolve=r),onResult(){}}),opening=panel.open('analysis',context),drawer=body.children[0].shadow.children.find(n=>n.tag==='section');find(drawer,'button','Закрыть').onclick();resolve({result:report});await opening;assert.equal(drawer.hidden,true);assert.equal(find(drawer,'button','Разбор сохранён'),undefined);
});

test('vacancy actions mount their panel in the same card and preserve it after metadata refresh',async()=>{
 const {ctx,body,find}=setup(),target=new Element('div'),calls=[];body.append(target);
 const panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:{text:'Saved CRM letter',source:'crm',revision:2,cached:true}};},onResult(){}});
 const options={data:{cv_ready:true,resume_title:'CV'},item:{title:'ML role',full:true},title:'ML role',onAction:kind=>panel.open(kind,{...context,anchor:target})};
 ctx.HHInline.card(target,options);await find(target,'button','Письмо').onclick();
 const drawer=target.children.find(n=>n.className==='drawer inline');assert.ok(drawer);assert.equal(drawer.hidden,false);assert.equal(drawer.parent,target);assert.equal(find(drawer,'textarea')!==undefined,true);assert.equal(calls[0].action,'cover_read');assert.equal(calls.length,1);
 ctx.HHInline.card(target,options);assert.equal(target.children.find(n=>n.className==='drawer inline'),drawer);assert.equal(drawer.hidden,false);assert.ok(find(drawer,'button','Скопировать'));
});

test('external analysis exports and imports through local actions only and renders next to the vacancy',async()=>{
 const {ctx,body,find}=setup(),calls=[],panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:r.action==='analysis_export'?{export_id:'test-export',prompt:'PROMPT WITH CV AND JD'}:{...report,requirements:[]}};},onResult(){}});
 await panel.open('analysis_external',context);const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.equal(calls.length,0);
 await find(drawer,'button','1. Скопировать промпт разбора').onclick();assert.equal(calls[0].action,'analysis_export');const answer=drawer.children.find(n=>n.tag==='textarea'&&!n.readOnly);answer.value='{"analysis": {}}';await find(drawer,'button','2. Проверить и показать разбор').onclick();assert.equal(calls[1].action,'analysis_import');assert.equal(calls[1].export_id,'test-export');assert.equal(calls.length,2);assert.ok(find(drawer,'h4','Рекомендация'));
});
test('external letter prepares an immediate cover task, saves manually and inserts only on explicit user action',async()=>{
 const {ctx,body,find}=setup(),calls=[],inserted=[],panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:r.action==='cover_export'?{context:{resume_id:'cv',resume_hash:'hash',resume_text:'Confirmed CV',resume_title:'Research CV',vacancy:{id:'hh_1',description:'Full vacancy'}},vacancy_hash:'jd-hash',saved:null}:{revision:1}};},onResult(){}});
 await panel.open('cover_external',{...context,form_resume_id:'cv-in-form',onInsert:t=>inserted.push(t)});const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.equal(calls.length,1);assert.equal(calls[0].action,'cover_export');assert.equal(calls[0].form_resume_id,'cv-in-form');
 await find(drawer,'button','1. Скопировать промпт письма').onclick();assert.equal(calls.length,1);const prompt=drawer.children.find(n=>n.tag==='textarea'&&n.readOnly);assert.ok(prompt.value.startsWith('Сгенерируй сопроводительное письмо'));
 const answer=drawer.children.find(n=>n.tag==='textarea'&&n.attributes['aria-label']==='Письмо из ChatGPT');answer.value='Моё письмо.';
 await find(drawer,'button','2. Сохранить письмо в CRM').onclick();assert.equal(calls[1].action,'cover_save');assert.equal(calls[1].revision,0);assert.equal(calls[1].resume_hash_at_export,'hash');assert.equal(inserted.length,0);
 find(drawer,'button','Вставить письмо в поле HH').onclick();assert.deepEqual(inserted,['Моё письмо.']);
});


test('extension controls stop composed card events and anchor defaults while preserving checkbox and text defaults',()=>{
 const {ctx}=setup(),root=new Element('shadow');ctx.HHInline.shield(root);
 for(const type of ['click','auxclick','pointerdown','mousedown','keydown']){let outerClicks=0,prevented=false,stopped=false;const event={composedPath:()=>[{tagName:'BUTTON'}],stopPropagation:()=>stopped=true,preventDefault:()=>prevented=true};root.listeners[type][0](event);if(!stopped)outerClicks++;assert.equal(outerClicks,0);assert.equal(prevented,['click','auxclick'].includes(type));}
 let prevented=false;root.listeners.click[0]({composedPath:()=>[{tagName:'INPUT'}],stopPropagation(){},preventDefault:()=>prevented=true});assert.equal(prevented,false);
});

test('answer without API exports context once and copying prompt or pasted answer never invokes generation',async()=>{
 const {ctx,body,find}=setup(),calls=[];const panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:{context:{resume_id:'cv',resume_hash:'v1',resume_text:'CV END',goal:'DiT',vacancy:{id:'hh_1',description:'JD END'}},saved:null}};},onResult(){}});
 await panel.open('answer_external',context);const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.deepEqual(calls.map(r=>r.action),['answer_export']);
 await find(drawer,'button','1. Скопировать промпт ответа').onclick();const prompt=drawer.children.find(n=>n.tag==='textarea'&&n.readOnly);for(const value of ['CV END','JD END','DiT',context.question])assert.ok(prompt.value.includes(value));
 const answer=drawer.children.find(n=>n.tag==='textarea'&&!n.readOnly);answer.value='Готовый проверенный ответ.';await find(drawer,'button','2. Скопировать готовый ответ').onclick();assert.equal(calls.length,1);assert.ok(find(drawer,'button','Через API'));assert.ok(find(drawer,'button','Без API'));
});

test('API/offline switch keeps cover motivation and length and shows only two task actions',async()=>{
 const {ctx,body,find}=setup(),calls=[],panel=ctx.HHInline.create({send:async r=>{calls.push(r);return {result:r.action==='cover_export'?{context:{resume_text:'CV',vacancy:{description:'JD'}},saved:null}:null};},onResult(){}});
 const target=new Element('div');ctx.HHInline.card(target,{data:{cv_ready:true,resume_title:'CV'},item:{full:true,title:'ML role'},title:'ML role',onAction(){}});
 const actions=target.children.find(n=>n.className==='actions');assert.equal(actions.children.length,2);
 await panel.open('cover',context);let drawer=body.children[0].shadow.children.find(n=>n.tag==='section');find(drawer,'textarea').value='Моя мотивация';find(drawer,'input').value='12';await find(drawer,'button','Без API').onclick();
 drawer=body.children[0].shadow.children.find(n=>n.tag==='section');const comments=find(drawer,'label','Пожелания к письму').children[0];assert.equal(comments.value,'Моя мотивация');assert.equal(find(drawer,'input').value,'12');
 await find(drawer,'button','Через API').onclick();assert.equal(find(drawer,'textarea').value,'Моя мотивация');assert.equal(find(drawer,'input').value,'12');assert.ok(calls.every(c=>['cover_read','cover_export'].includes(c.action)));
});
test('company form preview displays exact profile values and cannot approve until owner checks consent',async()=>{
 const {ctx,body,find}=setup(),calls=[],panel=ctx.HHInline.create({send:async()=>{throw Error('No model calls');},form:async options=>{calls.push(options);return {app_id:'app',intent:{intent_hash:'exact',answers:{name:'Владислав'},form_snapshot:{fields:[{id:'name',label:'Имя'}]},manual_fields:['Резюме','Согласия'],limitations:['Отправка вручную']}};},onResult(){}});
 await panel.open('form',context);const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');assert.equal(calls.length,1);assert.equal(calls[0].action,'prepare');assert.equal(find(drawer,'pre').textContent,'Владислав');
 const run=find(drawer,'button','Заполнить поля');assert.equal(run.disabled,true);await run.onclick();assert.equal(calls.length,1);const check=find(drawer,'input');check.checked=true;check.onchange();assert.equal(run.disabled,false);await run.onclick();assert.equal(calls[1].action,'approve');assert.equal(calls[1].intent_hash,'exact');assert.equal(calls[1].confirmed,true);
});

test('form footer separates actions and shows verified success instead of a disabled fill label',async()=>{
 const {ctx,body,find}=setup(),calls=[];const packet={app_id:'app',intent:{intent_hash:'exact',answers:{name:'Test'},form_snapshot:{fields:[{id:'name',label:'Имя'}]},manual_fields:[],limitations:[]}};
 const panel=ctx.HHInline.create({send:async()=>{},form:async r=>{calls.push(r);return r.action==='prepare'?packet:{command_id:'cmd',transfer:{state:'complete',result_state:'fields_filled'}};},onResult(){}});await panel.open('form',context);
 const drawer=body.children[0].shadow.children.find(n=>n.tag==='section'),check=find(drawer,'input'),run=find(drawer,'button','Заполнить поля'),link=find(drawer,'a');assert.equal(link.className,'secondaryLink');assert.equal(run.parent.className,'formActions');assert.equal(link.parent,run.parent);assert.notEqual(check.parent,run.parent);
 check.checked=true;check.onchange();await run.onclick();assert.equal(run.textContent,'Поля заполнены ✓');assert.equal(find(drawer,'button','Обновить результат').hidden,true);assert.ok(drawer.children.find(n=>n.className==='formResult').textContent.includes('Отклик ещё не отправлен'));
});
test('pending form result can be read without granting another transfer; errors remain visible',async()=>{
 const {ctx,body,find}=setup(),calls=[];const panel=ctx.HHInline.create({send:async()=>{},form:async r=>{calls.push(r);if(r.action==='prepare')return {app_id:'app',intent:{intent_hash:'exact',answers:{name:'Test'},form_snapshot:{fields:[{id:'name',label:'Имя'}]},manual_fields:[],limitations:[]}};return r.action==='approve'?{command_id:'cmd',transfer:{state:'running'}}:{transfer:{state:'failed',note:'Форма изменилась.'}};},onResult(){}});await panel.open('form',context);
 const drawer=body.children[0].shadow.children.find(n=>n.tag==='section'),check=find(drawer,'input');check.checked=true;check.onchange();await find(drawer,'button','Заполнить поля').onclick();const refresh=find(drawer,'button','Обновить результат');assert.equal(refresh.hidden,false);await refresh.onclick();assert.deepEqual(calls.map(c=>c.action),['prepare','approve','status']);assert.equal(calls[2].command_id,'cmd');assert.equal(find(drawer,'button','Перенос остановлен').disabled,true);assert.ok(drawer.children.find(n=>n.className==='formResult').textContent.includes('Форма изменилась.'));
});

test('a full page can request capture before a first letter without a prior archive entry',async()=>{
 const {ctx,find}=setup(),target=new Element('div');let requested='';ctx.HHInline.card(target,{data:{cv_ready:true,resume_title:'CV'},item:null,title:'New employer job',canCapture:true,onAction:kind=>requested=kind});
 const letter=find(target,'button','Письмо');assert.equal(letter.disabled,false);await letter.onclick();assert.equal(requested,'cover');
});
test('revoked queued transfer reports cancellation rather than waiting forever',async()=>{
 const {ctx,body,find}=setup();const panel=ctx.HHInline.create({send:async()=>{},form:async r=>r.action==='prepare'?{app_id:'a',intent:{intent_hash:'h',answers:{n:'Name'},form_snapshot:{fields:[{id:'n',label:'Имя'}]},manual_fields:[],limitations:[]}}:{command_id:'cmd',transfer:{state:'cancelled'}},onResult(){}});await panel.open('form',context);
 const drawer=body.children[0].shadow.children.find(n=>n.tag==='section'),check=find(drawer,'input');check.checked=true;check.onchange();await find(drawer,'button','Заполнить поля').onclick();assert.ok(find(drawer,'button','Перенос остановлен'));assert.equal(find(drawer,'button','Обновить результат').hidden,true);
});

test('API and offline reviews use the same five labelled status colors and distinct CV/job quotes',async()=>{
 const rows=['confirmed','partial','studying','not_evidenced','explicit_gap'].map(status=>({status,requirement:status,explanation:'Связь с опытом',job_quote:'Точная цитата вакансии',resume_quotes:['Фрагмент CV'],action:'Уточнить факты'}));
 for(const offline of [false,true]){
  const {ctx,body,find}=setup(),panel=ctx.HHInline.create({send:async request=>({result:request.action==='analysis_export'?{export_id:'x',prompt:'prompt'}:{...report,requirements:rows}}),onResult(){}});
  await panel.open(offline?'analysis_external':'analysis',context);const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');
  if(offline){await find(drawer,'button','1. Скопировать промпт разбора').onclick();drawer.children.find(n=>n.tag==='textarea'&&!n.readOnly).value='{}';await find(drawer,'button','2. Проверить и показать разбор').onclick();}
  const all=[];function visit(n){if(n.className?.startsWith('requirement status-'))all.push(n);for(const child of n.children||[])visit(child);}visit(drawer);
  assert.deepEqual(all.map(n=>n.className),rows.map(r=>'requirement status-'+r.status));assert.ok(find(all[0],'span','✓ Подтверждено'));assert.ok(find(all[3],'span','Нет подтверждения в CV'));assert.ok(find(all[0],'span','Вакансия'));assert.ok(find(all[0],'span','Фрагмент CV'));
 }
});

test('an old extension context gives a concrete refresh instruction instead of a raw Chrome exception',async()=>{
 const {ctx,body}=setup(),panel=ctx.HHInline.create({send:async()=>{throw Error('Extension context invalidated.');},onResult(){}});
 await panel.open('analysis',context);const drawer=body.children[0].shadow.children.find(n=>n.tag==='section');
 const status=drawer.children.find(n=>n.attributes?.role==='status');assert.match(status.textContent,/Обновите страницу работодателя/);assert.match(status.textContent,/сохраните/);assert.ok(!status.textContent.includes('Extension context invalidated'));
});
