import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element{constructor(){this.children=[];this.value='';this.listeners={};}append(...e){this.children.push(...e);}replaceChildren(...e){this.children=e;}setAttribute(k,v){this[k]=v;}addEventListener(k,v){this.listeners[k]=v;}focus(){}select(){}}
function page({changed=false,mixed=false,hungStorage=false}={}){
 const current={resume_id:'b',resume_hash:'hash-b'},storage={resume_bundle:{primary_id:'a',resumes:[{id:'a',content_hash:'hash-a',quality:'full'},{id:'b',title:'Chosen CV',content_hash:changed?'changed':'hash-b',quality:'full',sections:[{key:'experience',text:'CHOSEN CV END'}]}]},vacancies:[{id:'hh_1',description_quality:'full',description:'Full JD'}]},requests=[],copied=[];
 const response={resume_id:'b',resume_hash:mixed?'another-CV':'hash-b',vacancy_id:'hh_1',text:'Здравствуйте! Факты из выбранного CV. Буду рад обсудить задачи команды.',word_count:12,cached:false,review_note:'Проверьте факты.',evidence:[{claim:'Факты из выбранного CV.',resume_quote:'Реальная цитата CV.',vacancy_quote:'Требования вакансии.'}]};
 const timers=[];
 const context=vm.createContext({setTimeout:fn=>{timers.push(fn);return fn;},clearTimeout:()=>{},chrome:{storage:{local:{get:async()=>hungStorage?new Promise(()=>{}):storage}}},document:{createElement:()=>new Element()},navigator:{clipboard:{writeText:async text=>copied.push(text)}},LocalResumeService:{request:async(path,body,timeout)=>{requests.push({path,body,timeout});return {...response,sentence_count:body.sentence_count,comments:body.comments};}}});
 vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),context);
 vm.runInContext(fs.readFileSync(new URL('cover-letter-ui.js',import.meta.url),'utf8'),context);
 const article=new Element(),row={id:'hh_1',title:'Research Engineer'};context.CoverLetters.attach(article,row,()=>current);
 return {article,current,requests,copied,storage,timers,response,rerender:()=>{const next=new Element();context.CoverLetters.attach(next,row,()=>current);return next;}};
}
test('letter is generated on demand using only ranking CV and one full JD, then copied separately',async()=>{
 const p=page();assert.equal(p.requests.length,0);const [settings,button,offline,prompt,notice,box]=p.article.children;await button.onclick();
 assert.equal(p.requests[0].path,'/cover-letter');assert.equal(p.requests[0].body.resume_id,'b');assert.equal(p.requests[0].body.bundle.resumes.length,1);assert.equal(p.requests[0].body.bundle.resumes[0].id,'b');assert.equal(p.requests[0].body.vacancy.id,'hh_1');
 assert.equal(box.hidden,false);assert.ok(notice.textContent.includes('слов'));assert.ok(box.children[0].value.startsWith('Здравствуйте!'));
 box.children[0].value='Мой отредактированный текст';await box.children[1].onclick();assert.deepEqual(p.copied,['Мой отредактированный текст']);assert.equal(p.requests.length,1);
 const rerender=p.rerender();assert.equal(rerender.children[5].hidden,false);assert.equal(p.requests.length,1);
});
test('changed CV is rejected before an API call',async()=>{
 const p=page({changed:true});await p.article.children[1].onclick();assert.equal(p.requests.length,0);assert.ok(p.article.children[4].textContent.includes('Версия резюме изменилась'));
});
test('a response for another CV is not displayed or made copyable',async()=>{
 const p=page({mixed:true});await p.article.children[1].onclick();assert.equal(p.article.children[5].hidden,true);assert.ok(p.article.children[4].textContent.includes('не соответствует'));assert.equal(p.copied.length,0);
});
test('unresponsive Chrome storage releases the button without sending an API request',async()=>{
 const p=page({hungStorage:true});const [settings,button,offline,prompt,notice,box]=p.article.children;
 const pending=button.onclick();assert.equal(button.disabled,true);p.timers[0]();await pending;
 assert.equal(button.disabled,false);assert.equal(p.requests.length,0);assert.equal(box.hidden,true);assert.ok(notice.textContent.includes('не ответило'));
});
test('comments and length create separate variants, keep manual edits, and never request on a settings change',async()=>{
 const p=page(),[settings,button,offline,prompt,notice,box]=p.article.children,comments=settings.children[1].children[0],length=settings.children[2].children[0];
 await button.onclick();assert.equal(p.requests[0].body.sentence_count,2);assert.equal(p.requests[0].body.comments,'');
 box.children[0].value='Сохранённая ручная правка';box.children[0].oninput();
 comments.value='  Подчеркни интерес к Flow Matching.  ';comments.oninput();length.value='3';length.onchange();
 assert.equal(box.hidden,true);assert.equal(p.requests.length,1);await button.onclick();
 assert.equal(p.requests[1].body.sentence_count,3);assert.equal(p.requests[1].body.comments,'Подчеркни интерес к Flow Matching.');
 const rerender=p.rerender();assert.equal(rerender.children[0].children[2].children[0].value,'3');assert.equal(rerender.children[5].hidden,false);
 length.value='2';length.onchange();comments.value='';comments.oninput();
 assert.equal(box.hidden,false);assert.equal(box.children[0].value,'Сохранённая ручная правка');assert.equal(p.requests.length,2);
});
test('fifty sentences reach the service without clamping, with time for generation and paragraph-preserving copy',async()=>{
 const p=page(),[settings,button,offline,prompt,notice,box]=p.article.children,length=settings.children[2].children[0];
 length.value='50';length.onchange();assert.equal(p.requests.length,0);
 p.response.text='Здравствуйте!\n\nПервый абзац с подтверждённым опытом.\n\nВторой абзац с мотивацией.\n\nБуду рад обсудить задачи команды.';
 await button.onclick();assert.equal(p.requests[0].body.sentence_count,50);assert.ok(p.requests[0].timeout>=375000);
 assert.equal(box.hidden,false);assert.ok(box.children[0].rows>=10);assert.equal(box.children[0].value,p.response.text);
 await box.children[1].onclick();assert.equal(p.copied[0],p.response.text);
 length.value='51';length.onchange();await button.onclick();assert.equal(p.requests.length,1);assert.ok(notice.textContent.includes('от 1 до 50'));
 length.value='2.5';await button.onclick();assert.equal(p.requests.length,1);
});

test('cover letter without API uses identical wishes and sentence limit and leaves a pasteable editor',async()=>{const p=page(),[settings,button,offline,prompt,notice,box]=p.article.children;settings.children[1].children[0].value='Подчеркни DiT';settings.children[2].children[0].value='12';await offline.onclick();assert.equal(p.requests.length,0);assert.equal(p.copied.length,1);for(const value of ['CHOSEN CV END','Full JD','Подчеркни DiT','12 предложений'])assert.ok(p.copied[0].includes(value));assert.equal(box.hidden,false);box.children[0].value='Мой ответ из ChatGPT';await box.children[1].onclick();assert.equal(p.copied[1],'Мой ответ из ChatGPT');assert.equal(p.requests.length,0);});
