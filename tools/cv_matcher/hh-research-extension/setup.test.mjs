import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=name=>fs.readFileSync(new URL(name,import.meta.url),'utf8');
function ui({result,send,permission=true,noChrome=false}={}){
 const elements={};for(const [,id] of source('setup.html').matchAll(/id="([^"]+)"/g))elements[id]={textContent:'',value:'',disabled:false,hidden:false,checked:false,open:false,setAttribute(k,v){this[k]=v;}};elements.headline.textContent='Проверяю подключения…';elements.remember.checked=false;
 const calls=[],permissions=[],timers=[],localCalls=[];let next=result||{ok:true,health:{ok:true,service:'cv-matcher-local',version:9,workflow:true},enabled:false,permission:false,worker:{exists:false}};
 const chrome=noChrome?undefined:{runtime:{id:'fixture',getURL:p=>'chrome-extension://fixture/'+p,sendMessage:async data=>{calls.push(data.type);return send?send(data):next;}},permissions:{request:async data=>{permissions.push(data);return permission;}},tabs:{create:async()=>{}}};
 const context=vm.createContext({chrome,document:{getElementById:id=>elements[id],hidden:false},Promise,Error,setTimeout:(fn,ms)=>{const t={fn,ms};timers.push(t);return t;},clearTimeout:t=>t.cancelled=true,setInterval:()=>{},LocalResumeService:{connect:async(...a)=>localCalls.push(a),request:async()=>({url:'http://127.0.0.1:8788/'})}});
 for(const name of ['setup-core.js','setup.js'])vm.runInContext(source(name),context);
 return {elements,calls,permissions,timers,localCalls,context,setResult:data=>next=data,flush:async()=>{await new Promise(r=>setImmediate(r));}};
}
const healthy={ok:true,health:{ok:true,service:'cv-matcher-local',version:9,workflow:true},enabled:true,permission:true,worker:{exists:true,state:'authenticated'}};
test('setup never confuses enabled preference with a ready HH connection',()=>{
 const ctx=vm.createContext({});vm.runInContext(source('setup-core.js'),ctx);
 for(const [data,hh] of [[healthy,'ready'],[{...healthy,permission:false},'permission_missing'],[{...healthy,worker:{exists:false}},'tab_missing'],[{...healthy,worker:{exists:true,state:'login'}},'login'],[{...healthy,worker:{exists:true,state:'captcha'}},'captcha']]){const state=ctx.HHSetup.view(data);assert.equal(state.hh,hh);assert.equal(state.ready,hh==='ready');}
 assert.equal(ctx.HHSetup.view({...healthy,health:{...healthy.health,version:8}}).service,true);assert.equal(ctx.HHSetup.view({...healthy,health:{...healthy.health,workflow:false}}).service,false);
});
test('successful setup shows actionable ready status and permits opening the website',async()=>{
 const p=ui({result:healthy});await p.flush();assert.equal(p.elements.headline.textContent,'Всё подключено');assert.equal(p.elements.serviceBadge.textContent,'Подключён');assert.equal(p.elements.workspace.disabled,false);assert.equal(p.elements.openHH.hidden,false);assert.equal(p.permissions.length,0);
});
test('undefined background response replaces Checking with an explicit recovery message',async()=>{
 const p=ui({send:async()=>undefined});await p.flush();assert.equal(p.elements.headline.textContent,'Не удалось проверить подключение');assert.ok(p.elements.nextStep.textContent.includes('chrome://extensions'));assert.equal(p.elements.serviceBadge.textContent,'Не проверено');assert.equal(p.elements.enable.disabled,true);assert.equal(p.elements.refresh.disabled,false);
});
test('a stalled background response times out and a later manual refresh can recover',async()=>{
 let stalled=true;const p=ui({send:async()=>stalled?new Promise(()=>{}):healthy});await p.flush();const timer=p.timers.find(t=>t.ms===8000&&!t.cancelled);assert.ok(timer);timer.fn();await p.flush();assert.ok(!p.elements.headline.textContent.includes('Проверяю'));assert.equal(p.elements.refresh.disabled,false);
 stalled=false;await p.elements.refresh.onclick();assert.equal(p.elements.headline.textContent,'Всё подключено');
});
test('missing service disables HH permission requests and denied HH access never enables the worker',async()=>{
 const p=ui({result:{ok:true,health:null,error:'Сервис не запущен',enabled:false,permission:false},permission:false});await p.flush();assert.equal(p.elements.enable.disabled,true);assert.equal(p.elements.serviceSetup.open,true);
 p.setResult({...healthy,enabled:false});await p.elements.refresh.onclick();await p.elements.enable.onclick();assert.equal(p.permissions.length,1);assert.ok(!p.calls.includes('managed_enable'));assert.ok(p.elements.status.textContent.includes('не предоставлен'));
});
test('file preview fails clearly instead of checking forever; connection does not store a code without opt-in',async()=>{
 const file=ui({noChrome:true});await file.flush();assert.ok(file.elements.nextStep.textContent.includes('HTML-файл'));assert.equal(file.elements.enable.disabled,true);
 const p=ui();await p.flush();p.elements.code.value='a'.repeat(43);await p.elements.connect.onclick();assert.equal(p.localCalls[0][1].remember,false);assert.equal(p.elements.code.value,'');
});


test('setup shows only current step, advances with capabilities and lets user return to a completed step',async()=>{
 const p=ui({result:{ok:true,health:null,error:'Нет кода',enabled:false,permission:false}});await p.flush();assert.equal(p.elements.serviceStep.hidden,false);assert.equal(p.elements.hhStep.hidden,true);assert.equal(p.elements.continueStep.hidden,true);
 p.setResult({...healthy,health:{...healthy.health,version:8},enabled:false});await p.elements.refresh.onclick();assert.equal(p.elements.serviceStep.hidden,true);assert.equal(p.elements.hhStep.hidden,false);assert.equal(p.elements.continueStep.hidden,true);assert.equal(p.elements.enable.disabled,false);assert.ok(!p.elements.serviceState.textContent.includes('версия 9'));
 p.elements.step1.onclick();await p.elements.refresh.onclick();assert.equal(p.elements.serviceStep.hidden,false);assert.equal(p.elements.hhStep.hidden,true);
 p.setResult(healthy);await p.elements.refresh.onclick();assert.equal(p.elements.continueStep.hidden,false);assert.equal(p.elements.hhStep.hidden,true);assert.equal(p.elements.headline.textContent,'Всё подключено');
});


test('slow HH load has an actionable status; an old URL error cannot invalidate a live ready connection',async()=>{
 const p=ui({result:{...healthy,worker:{exists:true,state:'loading_stalled'}}});await p.flush();assert.equal(p.elements.hhBadge.textContent,'Загрузка задержалась');assert.equal(p.elements.openHH.hidden,false);assert.match(p.elements.hhState.textContent,/Откройте служебную вкладку/);
 p.setResult({...healthy,status:{state:'needs_input',note:"Failed to construct 'URL': Invalid URL"}});await p.elements.refresh.onclick();assert.equal(p.elements.headline.textContent,'Всё подключено');assert.ok(!p.elements.workerNote.textContent.includes('Invalid URL'));assert.match(p.elements.workerNote.textContent,/ошибка предыдущей задачи/);
});
