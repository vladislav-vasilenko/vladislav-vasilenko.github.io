import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const code=f=>fs.readFileSync(new URL(f,import.meta.url),'utf8'),uuid='97dc014e-7657-4140-989b-0d4011a8acc9',url='https://tbank.ru/career/it/vacancy/moscow/portfelnyj-risk-analitik/'+uuid+'/';
function extract({omit='',title='Вакансия Портфельный риск-аналитик | Т-Банк ex. Тинькофф'}={}){
 const names=['Описание','Обязанности','Требования','Мы предлагаем','Откликнуться на вакансию','Похожие вакансии'].filter(n=>n!==omit),headings=names.map((innerText,index)=>({innerText,index,getClientRects:()=>[{}]})),chunks=names.map(n=>n+': '+'Содержательная часть вакансии Python SQL модели и стратегии. '.repeat(4));let start,end;
 const document={title,body:{innerText:chunks.join(' ')},querySelectorAll:s=>s==='h2,h3'?headings:[],createRange:()=>({setStartAfter:n=>{start=n.index;},setEndBefore:n=>{end=n.index;},cloneContents:()=>({textContent:chunks.slice(start,end).join(' ')})}),createElement:()=>({textContent:'',append(fragment){this.textContent+=fragment.textContent;},querySelectorAll:()=>[]})};
 const c=vm.createContext({document,location:new URL(url),URL,Date,Set,Map,getComputedStyle:()=>({display:'block',visibility:'visible'})});for(const f of ['board-core.js','board-adapters.js'])vm.runInContext(code(f),c);const result=vm.runInContext(code('board-content.js'),c);return {c,result};
}
test('T-Bank hero without h1 uses its title and bounded visible job sections, excluding form and related jobs',()=>{
 const {result}=extract();assert.equal(result.vacancies[0].title,'Портфельный риск-аналитик');assert.equal(result.vacancies[0].description_quality,'full');assert.equal(result.vacancies[0].locations[0],'Москва');assert.ok(!/Откликнуться на вакансию|Похожие вакансии/.test(result.vacancies[0].description));assert.equal(extract({omit:'Мы предлагаем'}).result.vacancies[0].description_quality,'needs_review');
});
test('T-Bank alias is bounded to the two known TLS hosts and supports service job identities',()=>{
 const {c}=extract();assert.equal(c.JobBoardAdapters.sameSource(url,url.replace('tbank.ru','www.tbank.ru')),true);
 for(const other of ['https://evil.test/career/','http://tbank.ru/career/','https://tbank.ru:444/career/'])assert.equal(c.JobBoardAdapters.sameSource(url,other),false);
 assert.equal(c.JobBoards.identity('https://tbank.ru/career/service/vacancy/moscow/predstavitel/'+uuid+'/').id,'tbank_'+uuid);
});

test('T-Bank plain application container without textarea is read; city has a dedicated choice control and secrets stay out',()=>{
 const node=(type,label,role='')=>({tagName:'INPUT',type,name:label,labels:[{innerText:label}],value:'',disabled:false,required:false,getAttribute:k=>k==='role'?role:null,getBoundingClientRect:()=>({width:200,height:40})});
 const nodes=[node('text','Фамилия и имя','combobox'),node('text','Город','combobox'),node('text','Почта'),node('tel','Телефон'),node('file','Резюме'),node('text','Ссылка на резюме'),node('password','Password')];
 const form={tagName:'DIV',innerText:'Фамилия и имя Город Почта Телефон Резюме',parentElement:{tagName:'BODY'},contains:()=>false,querySelector:s=>s.includes('email')?null:s.includes('tel')?nodes[3]:s.includes('file')?nodes[4]:null,querySelectorAll:()=>nodes};
 const send={innerText:'Отправить',parentElement:form},document={body:{innerText:form.innerText},querySelectorAll:s=>s==='button,input[type="submit"]'?[send]:[]};
 const c=vm.createContext({document,URL,getComputedStyle:()=>({display:'block',visibility:'visible'})});for(const f of ['board-core.js','board-adapters.js','board-widget-core.js','career-form-core.js'])vm.runInContext(code(f),c);
 const result=c.CareerForms.inspect(document,url,()=>true).snapshot;
 assert.equal(result.fields.length,6);assert.equal(result.fields[1].manual_only,false);assert.equal(result.fields[1].control,'tbank_city');assert.equal(result.fields[5].purpose,'resume_url');assert.equal(result.execution_supported,false);assert.equal(result.fields[4].value,'');
});

test('T-Bank IT preset uses its observed direction URL and preserves city constraints',()=>{
 const {c}=extract(),source='https://tbank.ru/career/vacancies/all/moscow/?cityId=moscow';const prepared=new URL(c.JobBoardAdapters.filterURL(source,['IT-разработка']));assert.equal(prepared.searchParams.get('direction'),'it-razrabotka');assert.equal(prepared.searchParams.get('cityId'),'moscow');assert.equal(c.JobBoardAdapters.filterURL(source,[]),source);
});

test('ML profile first navigates to IT direction while preserving city and existing filters',()=>{
 const {c}=extract(),source='https://www.tbank.ru/career/vacancies/all/moscow/?cityId=moscow';
 const prepared=new URL(c.JobBoardAdapters.filterURL(source,['IT-разработка','Машинное обучение']));
 assert.equal(prepared.searchParams.get('direction'),'it-razrabotka');assert.equal(prepared.searchParams.get('cityId'),'moscow');
 // Both first-party query values were observed in Chrome; DOM is still verified.
 assert.equal(prepared.searchParams.get('profession'),'ml');assert.equal(prepared.searchParams.size,3);
});
