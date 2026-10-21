import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element{
 constructor(){this.children=[];this.value='';this.hidden=false;this.selected=false;}
 append(...children){this.children.push(...children);}setAttribute(k,v){this[k]=v;}focus(){this.focused=true;}select(){this.selected=true;}
}
function fixture({clipboardFails=false,changeDuringRead=false}={}){
 const ranking={resume_id:'chosen',resume_hash:'chosen-v2',goal:'Generative Modelling / DiT'},chosen={id:'chosen',title:'Research CV',content_hash:'chosen-v2',quality:'full',source_url:'https://hh.ru/resume/chosen?hhtmFrom=profile',checked_at:'2026-10-15T10:00:00Z',sections:[{key:'experience',heading:'Опыт',text:'Обучал Transformer на PyTorch в самостоятельном проекте. Конец CV.'},{key:'skills',heading:'Навыки',text:'Python, PyTorch, линейная алгебра.'},{key:'contacts',heading:'Контакты',text:'PRIVATE CONTACT BLOCK'}],api_key:'DO NOT EXPORT THIS KEY'};
 const storage={resume_bundle:{primary_id:'other',resumes:[{id:'other',quality:'full',sections:[{key:'experience',text:'OTHER RESUME SECRET'}]},chosen],token:'PAIRING SECRET'},vacancies:[{id:'hh_1',title:'Research Engineer',company:'Sber',link:'https://hh.ru/vacancy/1',description_quality:'full',description:'Исследовать диффузионные модели. Требуются PyTorch и математическая подготовка. Конец полной вакансии.'},{id:'hh_2',title:'Unrelated vacancy',description:'OTHER VACANCY SECRET'}]};
 const copied=[];let current=ranking,reads=0;
 const context=vm.createContext({URL,Date,document:{createElement:()=>new Element()},chrome:{storage:{local:{get:async()=>{reads++;if(changeDuringRead)current={...ranking};return storage;}}}},navigator:{clipboard:{writeText:async content=>{if(clipboardFails)throw Error('Denied');copied.push(content);}}}});
 vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),context);
 const article=new Element(),row={id:'hh_1',title:'Research Engineer'};context.ChatGPTExport.attach(article,row,()=>current);
 const build=(extra={})=>context.ChatGPTExport.buildPackage({ranking,bundle:storage.resume_bundle,vacancies:storage.vacancies,jobId:row.id,now:new Date('2026-10-15T12:00:00Z'),...extra});
 return {article,copied,storage,ranking,chosen,build,get reads(){return reads;},rerender:()=>{const next=new Element();context.ChatGPTExport.attach(next,row,()=>current);return next;}};
}
function data(text){return JSON.parse(text.split('```json\n')[1].split('\n```')[0]);}
test('package contains only the ranked CV, full vacancy, goal and optional recruiter question without credentials',()=>{
 const p=fixture(),content=p.build({comments:'Интерес к Flow Matching.',question:'Почему заинтересовала вакансия?'}),json=data(content);
 assert.equal(json.resume.id,'chosen');assert.equal(json.resume.content_hash,'chosen-v2');assert.equal(json.resume.source_url,'https://hh.ru/resume/chosen');assert.equal(json.search_goal,p.ranking.goal);
 assert.equal(json.vacancy.id,'hh_1');assert.ok(json.vacancy.description.endsWith('Конец полной вакансии.'));assert.equal(json.recruiter_question_or_conversation,'Почему заинтересовала вакансия?');
 for(const secret of ['OTHER RESUME SECRET','OTHER VACANCY SECRET','PAIRING SECRET','DO NOT EXPORT THIS KEY','PRIVATE CONTACT BLOCK'])assert.ok(!content.includes(secret));
 for(const instruction of ['не подтверждён в резюме','коммерческий опыт','не отправляй сообщения','ИИ-рекрутера'])assert.ok(content.includes(instruction));
});
test('export rejects a changed or missing selected CV and incomplete or archived vacancy instead of falling back',()=>{
 const p=fixture();p.chosen.content_hash='edited';assert.throws(()=>p.build(),/Версия выбранного CV/);p.chosen.content_hash='chosen-v2';
 p.chosen.quality='unavailable';assert.throws(()=>p.build(),/Версия выбранного CV/);p.chosen.quality='full';
 for(const update of [{description_quality:'snippet'},{description_quality:'full',archived:true}]){Object.assign(p.storage.vacancies[0],update);assert.throws(()=>p.build(),/Полное описание вакансии/);}
});
test('long professional texts are not truncated and ordinary numeric facts survive contact redaction',()=>{
 const p=fixture();p.chosen.sections[0].text='Опыт '.repeat(12000)+'2021–2024, 128 GPU, model +7 (999) 123-45-67, name@example.com. END CV';p.storage.vacancies[0].description='Полное описание '.repeat(2000)+'END JD';
 const json=data(p.build());assert.ok(json.resume.sections[0].text.endsWith('END CV'));assert.ok(json.vacancy.description.endsWith('END JD'));assert.ok(json.resume.sections[0].text.includes('2021–2024, 128 GPU'));assert.ok(!json.resume.sections[0].text.includes('name@example.com'));assert.ok(!json.resume.sections[0].text.includes('999'));
});
test('one click copies locally, includes editable extras and restores them after changing displayed result count',async()=>{
 const p=fixture(),[button,settings,notice,preview]=p.article.children,comments=settings.children[1].children[0],question=settings.children[2].children[0];
 assert.equal(p.reads,0);assert.equal(p.copied.length,0);comments.value='Сравни исследовательские задачи.';comments.oninput();question.value='Как вы обучали модель? Мой черновик: изучаю тему.';question.oninput();
 await button.onclick();assert.equal(p.reads,1);assert.equal(p.copied.length,1);assert.equal(data(p.copied[0]).my_preferences,comments.value);assert.equal(data(p.copied[0]).recruiter_question_or_conversation,question.value);assert.ok(notice.textContent.includes('Скопированы'));assert.equal(preview.children[1].value,p.copied[0]);
 const rerender=p.rerender();assert.equal(rerender.children[1].children[2].children[0].value,question.value);assert.equal(p.copied.length,1);
});
test('denied clipboard access offers the complete selectable package for manual copying',async()=>{
 const p=fixture({clipboardFails:true}),[button,settings,notice,preview]=p.article.children;await button.onclick();
 assert.equal(p.copied.length,0);assert.equal(preview.hidden,false);assert.equal(preview.open,true);assert.equal(preview.children[1].selected,true);assert.ok(preview.children[1].value.includes('Конец полной вакансии.'));assert.ok(notice.textContent.includes('Cmd+C'));assert.equal(button.disabled,false);
});
test('a changed ranking while storage is read cannot copy the previous context',async()=>{
 const p=fixture({changeDuringRead:true});await p.article.children[0].onclick();assert.equal(p.copied.length,0);assert.ok(p.article.children[2].textContent.includes('контекст изменился'));assert.equal(p.article.children[3].hidden,true);
});

test('application export immediately asks for a cover letter using frozen CV, vacancy, length, wishes and manual draft',()=>{
 const context=vm.createContext({URL,Date});vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),context);
 const app={resume_id:'frozen-cv',resume_hash:'frozen-hash',resume_title:'Research CV',resume_text:'Самостоятельный проект PyTorch. END CV',resume_url:'https://hh.ru/resume/cv?tracking=secret',goal:'Flow Matching',vacancy:{id:'hh_1',title:'Researcher',company:'Sber',link:'https://hh.ru/vacancy/1',description:'Diffusion, Transformers. END JD'},token:'MUST NOT EXPORT'};
 const packet=context.ChatGPTExport.buildApplicationPackage({context:app,sentences:50,comments:'Мотивация: математика стохастических процессов.',draft:'Ручная редакция письма.'}),json=data(packet);
 assert.ok(packet.startsWith('Сгенерируй сопроводительное письмо'));assert.ok(packet.includes('Длина: 50 предложений'));assert.ok(packet.includes('Не начинай с таблицы'));assert.equal(json.task,'generate_cover_letter');assert.equal(json.sentence_count,50);
 assert.equal(json.resume.content_hash,'frozen-hash');assert.equal(json.resume.text,app.resume_text);assert.equal(json.vacancy.description,app.vacancy.description);assert.equal(json.search_goal,app.goal);assert.equal(json.current_draft,'Ручная редакция письма.');assert.equal(json.my_preferences,'Мотивация: математика стохастических процессов.');assert.ok(!packet.includes('MUST NOT EXPORT'));assert.ok(!packet.includes('tracking=secret'));
 for(const sentences of [0,51,1.5,'bad'])assert.throws(()=>context.ChatGPTExport.buildApplicationPackage({context:app,sentences}),/1 до 50/);
 assert.throws(()=>context.ChatGPTExport.buildApplicationPackage({context:{...app,resume_text:''}}),/сохранённые тексты/);
});

test('discussion export includes optional current draft only with its checkbox and asks for editorial dialogue first',()=>{
 const ctx=vm.createContext({URL,Date});vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),ctx);
 const context={resume_id:'cv',resume_hash:'hash',resume_title:'CV',resume_text:'Профессиональный текст CV',goal:'Generative research',vacancy:{id:'hh_1',title:'Researcher',description:'Полная вакансия'}};
 for(const includeDraft of [true,false]){const packet=ctx.ChatGPTExport.buildApplicationPackage({context,draft:'LATEST MANUAL LETTER',comments:'Подчеркни исследовательский интерес',sentences:4,task:'discuss_cover_letter',includeDraft});assert.ok(packet.startsWith('Помоги мне обсудить'));assert.ok(!packet.includes('В первом ответе дай готовый текст'));assert.equal(data(packet).task,'discuss_cover_letter');assert.equal(data(packet).current_draft,includeDraft?'LATEST MANUAL LETTER':'');assert.equal(packet.includes('LATEST MANUAL LETTER'),includeDraft);assert.equal(data(packet).sentence_count,4);}
});

test('answer export includes question, wishes, draft and context without credentials or model access',()=>{
 const ctx=vm.createContext({URL,Date});vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),ctx);
 const context={resume_id:'chosen',resume_hash:'v2',resume_title:'CV',resume_text:'CV END',goal:'DiT',vacancy:{id:'hh_1',title:'Researcher',description:'JD END',secret:'NEVER EXPORT'},token:'PRIVATE TOKEN'};
 const prompt=ctx.ChatGPTExport.buildAnswerPackage({context,question:'Что вы обучали?',comments:'Подчеркни личный проект',draft:'Мой черновик',history:[{question:'Предыдущий вопрос',answer:'Утверждённый ответ'}]});
 for(const value of ['CV END','JD END','DiT','Что вы обучали?','Подчеркни личный проект','Мой черновик','Утверждённый ответ'])assert.ok(prompt.includes(value));
 for(const value of ['NEVER EXPORT','PRIVATE TOKEN'])assert.ok(!prompt.includes(value));assert.throws(()=>ctx.ChatGPTExport.buildAnswerPackage({context,question:''}),/вопрос/);
});
test('editor export contains latest unsent message and conversation separately from CV evidence',()=>{
 const ctx=vm.createContext({URL,Date});vm.runInContext(fs.readFileSync(new URL('chatgpt-export.js',import.meta.url),'utf8'),ctx);
 const context={resume_id:'cv',resume_hash:'v1',resume_text:'CV',vacancy:{description:'JD'}};
 const packet=ctx.ChatGPTExport.buildApplicationPackage({context,task:'discuss_cover_letter',message:'Сократи и убери общие слова.',history:[{role:'user',text:'Интересует исследовательская работа.'}]});
 assert.equal(data(packet).last_user_message,'Сократи и убери общие слова.');assert.equal(data(packet).conversation.length,1);
});
