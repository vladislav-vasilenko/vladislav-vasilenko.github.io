import test from 'node:test';import assert from 'node:assert/strict';import './hh-form-assist.js';
const cv='a'.repeat(38),other='b'.repeat(38),resumes=[{id:cv,title:'Research CV'},{id:other,title:'NLP CV'}],items=[{id:'hh_1',title:'Senior ML Engineer',full:true}];
function form({text='Senior ML Engineer Research CV',radios=[],url='https://hh.ru/vacancy/1',fields=1}={}){
 const scope={innerText:text,querySelectorAll:()=>radios,querySelector:()=>null};const field={name:'letter',getAttribute:k=>k==='placeholder'?'Сопроводительное письмо':null,closest:()=>scope};const doc={querySelectorAll:()=>Array.from({length:fields},()=>field)};
 return HHFormAssist.detect(doc,url,{items,resumes,visible:()=>true});
}
const radio=(value,checked)=>({tagName:'INPUT',type:'radio',value,checked,getAttribute:()=>null});
test('response form reads the actual selected CV, never defaults to extension primary',()=>{
 assert.equal(form({radios:[radio(cv,false),radio(other,true)]}).resume_id,other);
 assert.equal(form().resume_id,cv);assert.equal(form({text:'Senior ML Engineer Research CV NLP CV'}).resume_id,null);
});
test('ambiguous vacancy or multiple letter fields cannot offer a wrong-context shortcut',()=>{
 assert.equal(form({fields:2}),null);assert.equal(form({url:'https://hh.ru/search/vacancy',text:'Unrelated modal Research CV'}),null);
 assert.equal(form({url:'https://hh.ru/search/vacancy'}).id,'hh_1');
});
