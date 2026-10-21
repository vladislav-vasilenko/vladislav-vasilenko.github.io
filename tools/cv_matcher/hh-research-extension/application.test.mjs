import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element{
 constructor(){this.children=[];this.value='';this.listeners={};this.disabled=false;}
 append(...rows){this.children.push(...rows);}replaceChildren(...rows){this.children=rows;}
 addEventListener(name,fn){this.listeners[name]=fn;}
}
async function page({badHash=false,continuing=false,pending=false}={}){
 const html=fs.readFileSync(new URL('application.html',import.meta.url),'utf8'),elements={};
 for(const [,id] of html.matchAll(/id="([^"]+)"/g))elements[id]=new Element();elements.channel.value='hh';elements.qaModel.value='luna';
 const cv={id:'a'.repeat(38),content_hash:'hash-a',title:'Research CV',quality:'full',source_type:'hh'};
 const job={id:'hh_123',link:'https://hh.ru/vacancy/123',title:'Research Engineer',company:'Example',description_quality:'full'};
 const app={id:'app-1',status:'queued',context:{resume_id:cv.id,resume_hash:cv.content_hash,resume_title:cv.title,goal:'DiT',channel:'hh',vacancy:job}};
 const snapshot={state:'form',selected_resume_id:cv.id,submit_label:'Отправить',fingerprint:'original',fields:[{id:'f0',label:'Почему интересна вакансия?',type:'textarea',value:'Ответ',required:true,options:[]}]};
 const storage={resume_bundle:{primary_id:'other',resumes:[cv,{id:'other',quality:'full'}]},vacancies:[job],pending_hh_application:app,hh_application_form:{application_id:app.id,tab_id:7,snapshot}};
 if(pending)storage.hh_application_submission={application_id:app.id,state:'sending',fingerprint:'original'};
 const requests=[],actions=[];let config;
 const chrome={storage:{local:{get:async()=>storage,set:async data=>Object.assign(storage,data)}},tabs:{create:async()=>{}},scripting:{executeScript:async request=>{if(request.args){config=request.args[0];return [];}actions.push(config.action);return [{result:config.action==='inspect'?snapshot:{state:'sent_unconfirmed'}}];}}};
 const url='chrome-extension://fixture/application.html?resume='+cv.id+'&hash='+(badHash?'old-hash':cv.content_hash)+'&vacancy='+job.id+'&goal=DiT'+(continuing?'&continue='+app.id:'');
 const ctx=vm.createContext({chrome,URL,Map,Object,location:{href:url},document:{getElementById:id=>elements[id],createElement:()=>new Element()},LocalResumeService:{request:async(path,body)=>{requests.push({path,body});return path==='/archive/open'?{url:'http://127.0.0.1:8788/#connect=fixture'}:app;}}});
 vm.runInContext(fs.readFileSync(new URL('application.js',import.meta.url),'utf8'),ctx);await new Promise(resolve=>setImmediate(resolve));
 return {elements,requests,actions,storage,cv};
}
test('application creation carries only the ranked CV/version and goal; changed CV is rejected',async()=>{
 const p=await page();await p.elements.create.onclick();assert.equal(p.requests[0].path,'/applications');assert.equal(p.requests[0].body.bundle.resumes.length,1);assert.equal(p.requests[0].body.resume_id,p.cv.id);assert.equal(p.requests[0].body.goal,'DiT');assert.equal(p.actions.length,0);
 const edited=await page({badHash:true});assert.equal(edited.elements.create.disabled,true);assert.equal(edited.requests.length,0);
});
test('legacy application screen delegates approval to shared workspace and never clicks HH submit',async()=>{
 const dirty=await page({continuing:true});const input=dirty.elements.hhFields.children[0].children[0].children[0];input.value='Изменённый ответ';input.listeners.input();await dirty.elements.submitHH.onclick();assert.equal(dirty.actions.length,0);assert.equal(dirty.requests.at(-1).path,'/archive/open');
 const p=await page({continuing:true});await p.elements.submitHH.onclick();await p.elements.submitHH.onclick();assert.deepEqual(p.actions,[]);assert.equal(p.storage.hh_application_submission,undefined);
 const restored=await page({continuing:true,pending:true});await restored.elements.submitHH.onclick();assert.equal(restored.actions.length,0);
});
