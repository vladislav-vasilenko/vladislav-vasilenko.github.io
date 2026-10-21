import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import './hh-apply-core.js';
test('HH applications never navigate arbitrary hosts or change the target vacancy',()=>{
 assert.equal(HHApply.verifyURL('https://hh.ru/vacancy/123?hhtmFrom=search','hh_123'),true);
 assert.equal(HHApply.verifyURL('https://hh.ru/applicant/vacancy_response?vacancyId=123','hh_123'),true);
 for(const u of ['https://evil.test/vacancy/123','https://hh.ru/vacancy/124','https://hh.ru/resume/123','https://hh.ru/applicant/vacancy_response?vacancyId=124'])assert.equal(HHApply.verifyURL(u,'hh_123'),false);
});
test('submission requires the exact resume, complete required fields and one recognized action',()=>{
 const s={state:'form',selected_resume_id:'a',fields:[{id:'f0',type:'text',required:true,value:'Ответ'}],submit_label:'Отправить'};
 assert.doesNotThrow(()=>HHApply.canSubmit(s,'a'));
 for(const bad of [{...s,selected_resume_id:'b'},{...s,submit_label:''},{...s,state:'submitted'},{...s,fields:[{type:'checkbox',required:true,value:false}]}])assert.throws(()=>HHApply.canSubmit(bad,'a'));
 assert.notEqual(HHApply.signature(s.fields,'a'),HHApply.signature([{...s.fields[0],value:'Другая правка'}],'a'));
});
class Field {
 constructor(value,type='textarea'){this._value=value;this.type=type;this.tagName=type==='textarea'?'TEXTAREA':'INPUT';this.checked=false;this.required=type==='textarea';this.name='answer';this.labels=[{innerText:'Почему интересна вакансия?'}];this.events=[];}
 get value(){return this._value;}set value(v){this._value=v;}
 getAttribute(){return null;}getBoundingClientRect(){return {width:100,height:20};}
 dispatchEvent(event){this.events.push(event.type);}click(){this.checked=true;}
}
function formPage(){
 const cv='a'.repeat(38),radio=new Field(cv,'radio'),answer=new Field(''),submitted=[];
 radio.checked=true;radio.name='resume';
 const button={innerText:'Отправить',getBoundingClientRect:()=>({width:100,height:20}),click:()=>submitted.push(true)};
 const form={tagName:'FORM',getAttribute:()=>null,getBoundingClientRect:()=>({width:100,height:20}),querySelector:()=>radio,
 querySelectorAll:s=>s==='input[type="radio"]'?[radio]:s==='input, textarea, select'?[radio,answer]:[button],checkValidity:()=>!!answer.value};
 const document={querySelector:()=>null,querySelectorAll:s=>s.includes(', form')?[form]:[]};
 const ctx=vm.createContext({document,location:new URL('https://hh.ru/vacancy/123'),URL,HTMLInputElement:Field,HTMLTextAreaElement:Field,HTMLSelectElement:Field,Event:class{constructor(type){this.type=type;}}});
 vm.runInContext(fs.readFileSync(new URL('hh-apply-core.js',import.meta.url),'utf8'),ctx);
 const run=(action,extra={})=>{ctx.__hhApplyAction={action,resume_id:cv,vacancy_id:'hh_123',...extra};return vm.runInContext(fs.readFileSync(new URL('hh-apply-content.js',import.meta.url),'utf8'),ctx);};
 return {run,cv,answer,radio,submitted};
}
test('form adapter fills an explicit answer, rejects concurrent edits, and never submits during inspect/fill',()=>{
 const p=formPage(),initial=p.run('inspect');assert.equal(initial.fields.length,1);
 assert.throws(()=>p.run('submit',{fingerprint:initial.fingerprint}));assert.equal(p.submitted.length,0);
 p.run('fill',{fingerprint:initial.fingerprint,answers:{f0:'Мой проверенный ответ.'}});assert.equal(p.answer.value,'Мой проверенный ответ.');assert.equal(p.submitted.length,0);
 const filled=p.run('inspect');p.answer.value='Правка в HH';assert.throws(()=>p.run('submit',{fingerprint:filled.fingerprint}));
 const latest=p.run('inspect');p.run('submit',{fingerprint:latest.fingerprint});assert.equal(p.submitted.length,1);
});
