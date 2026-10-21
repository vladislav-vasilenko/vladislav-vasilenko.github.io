import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const sources=['board-core.js','board-adapters.js','board-widget-core.js','career-form-core.js','career-form-content.js'].map(f=>fs.readFileSync(new URL(f,import.meta.url),'utf8'));
async function extract(url,forms=1,{body='',frames=0}={}){
 const field=(type,label)=>({tagName:type==='textarea'?'TEXTAREA':'INPUT',type,name:label,labels:[{innerText:label}],required:true,value:type==='password'?'SECRET':'',checked:false,disabled:false,getBoundingClientRect:()=>({width:200,height:40}),getAttribute:()=>null,get files(){throw Error('File access forbidden');}});
 const nodes=[field('textarea','О себе'),field('email','Email'),field('password','Пароль'),field('hidden','token'),field('file','Резюме')];
 const root={getBoundingClientRect:()=>({width:300,height:300}),contains:()=>false,querySelector:()=>nodes[0],querySelectorAll:()=>nodes};
 const document={body:{innerText:body},querySelectorAll:selector=>selector==='form,[role="dialog"]'?Array.from({length:forms},()=>({...root})):selector==='iframe'?Array.from({length:frames},()=>({...root})):[]};
 const ctx=vm.createContext({document,location:new URL(url),URL,getComputedStyle:()=>({display:'block',visibility:'visible'})});let value;for(const s of sources)value=vm.runInContext(s,ctx);return value;
}
test('read-only questionnaires on all five boards omit secrets and file contents',async()=>{
 for(const [provider,url] of [['yandex','https://yandex.ru/jobs/vacancies/ml-11031'],['sber','https://rabota.sber.ru/search/ml-123456'],['avito','https://career.avito.com/vacancies/data-science/19450/'],['ozon','https://ozon.tech/vacancies/12345/'],['tbank','https://www.tbank.ru/career/it/vacancy/moscow/ml/0d772642-b21e-4529-a234-5e93b00210be/']]){
  const result=await extract(url);assert.equal(result.provider,provider);assert.equal(result.execution_supported,false);assert.equal(result.fields.length,3);assert.equal(result.fields[2].type,'file');assert.equal(result.fields[2].value,'');assert.ok(!result.fingerprint.includes('SECRET'));
 }
});
test('ambiguous forms, listings and unrelated sites cannot create a bound questionnaire',async()=>{
 for(const [url,count] of [['https://career.avito.com/vacancies/data-science/19450/',2],['https://career.avito.com/vacancies/',1],['https://evil.example/vacancies/123',1]])assert.equal((await extract(url,count)).state,'read_error');
});

test('missing native form explains login, iframe limitations and retryable mounting separately',async()=>{
 const url='https://yandex.ru/jobs/vacancies/ml-11031';
 const login=await extract(url,0,{body:'Войти и откликнуться'});assert.equal(login.code,'login_required');assert.equal(login.retryable,false);
 const frame=await extract(url,0,{frames:1});assert.equal(frame.code,'embedded_form');assert.match(frame.error,/iframe/);assert.equal(frame.retryable,false);
 const pending=await extract(url,0);assert.equal(pending.code,'form_not_open');assert.equal(pending.retryable,true);
});
