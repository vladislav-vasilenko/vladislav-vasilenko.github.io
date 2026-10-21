// Isolated browser boundary for Python integration tests. Runs the actual worker;
// only Chrome DOM/transport are fixtures. No network, click, approval or submit.
import fs from 'node:fs';import vm from 'node:vm';
const command=JSON.parse(fs.readFileSync(0,'utf8'));let snapshot=null,filled=0,submitted=0;
const form={state:'form',source_url:'https://hh.ru/applicant/vacancy_response?vacancyId='+command.application.context.vacancy.id.slice(3),selected_resume_id:command.application.context.resume_id,fingerprint:'e2e-form',submit_label:'Отправить',fields:[{id:'cover',label:'Сопроводительное письмо',purpose:'cover',type:'textarea',required:false,value:'',options:[]}]};
const ctx=vm.createContext({chrome:{runtime:{onMessage:{addListener(){}}},tabs:{get:async()=>({url:form.source_url})},scripting:{executeScript:async()=>[{result:[]}]}},URL,Set,Map,Error,HHApply:{verifyURL:()=>true},LocalResumeService:{request:async(_url,data)=>{if(data.op!=='prepared')throw Error('Unexpected operation');snapshot=data.snapshot;return {ok:true};}}});
vm.runInContext(fs.readFileSync(new URL('../hh-workflow.js',import.meta.url),'utf8'),ctx);
ctx.wfCurrentSync=async()=>({observed_statuses:[]});ctx.wfApply=async(_tab,data)=>{if(data.action==='submit'){submitted++;throw Error('Submit forbidden in E2E');}if(data.action==='fill'){filled++;form.fields[0].value=data.answers.cover;}return structuredClone(form);};
const result=await ctx.wfPrepare(7,command,'e2e-reader');
process.stdout.write(JSON.stringify({result,snapshot,filled,submitted}));
