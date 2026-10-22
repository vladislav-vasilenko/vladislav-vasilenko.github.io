import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function load(name){const code=ts.transpileModule(fs.readFileSync(new URL('../../src/features/'+name+'.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;const context=vm.createContext({exports:{},URL,location:{href:'https://example.org/?lang=ru'},require:path=>load(path.replace('./',''))});vm.runInContext(code,context);return context.exports;}
const hh=load('hhExperience'),focus=load('experienceFocus');
const snapshot=()=>({schema_version:1,enabled:true,source:{label:'HH',language:'ru',captured_at:'2026-10-22T10:00:00Z'},experience:[{id:'hh-1',company:'Example',role:'Engineer',period:'2023–2025',duration:'2 years',description:'<script>alert(1)</script>\nPyTorch project'}],confirmed_skills:[{id:'pytorch',label:'PyTorch',links:[{url:'https://github.com/example/lab',label:'lab'}]}]});
test('HH experience renders escaped source text and exposes pending translation honestly',()=>{const data=snapshot();assert.ok(hh.validateSnapshot(data));const result=hh.applyHHSnapshot({experience:[]},data);assert.match(result.experience[0].descriptionHtml,/&lt;script&gt;/);assert.doesNotMatch(result.experience[0].descriptionHtml,/<script>/);assert.match(hh.renderHHSource(data,'en'),/Translation pending/);assert.doesNotMatch(hh.renderHHSource(data,'ru'),/Ожидается перевод/);data.confirmed_skills[0].links[0].url='https://github.com@evil.org/a/b';assert.equal(hh.validateSnapshot(data),null);});
test('all focus modes recognize actual matching work without requiring legacy IDs',()=>{for(const [profile,text] of Object.entries({vision:'Diffusion DiT',audio:'Whisper TTS',multimodal:'CLIP cross-modal',multiagent:'LangGraph agent orchestration',llm:'Llama Transformer',ios:'Swift UIKit'})){assert.ok(focus.experienceFocus({role:'Engineer',company:'Example',descriptionMd:text},profile,'en'),profile);assert.equal(focus.experienceFocus({role:'Engineer',company:'Example',descriptionMd:'Python REST API'},profile,'en'),null);}});

test('presentation styles preserve work facts and keep minimal as the default',()=>{
 const themes=load('presentationStyle'),minimal=load('minimalPortfolio');
 assert.equal(themes.presentationStyle('unknown'),'minimal');
 const data=snapshot(),cv={name:'Candidate',title:'Research Engineer<br><small>extra</small>',contact:{email:'public@example.org'},aboutMd:'Research and engineering.',experience:hh.applyHHSnapshot({experience:[]},data).experience,education:[]};
 const before=JSON.stringify(cv);
 for(const style of themes.presentationStyles){
  const html=minimal.renderMinimal(cv,'ru',data,'llm',style);
  assert.match(html,/2023–2025/);assert.match(html,/Engineer/);assert.match(html,/data-presentation/);
  assert.doesNotMatch(html,/&lt;br&gt;/);assert.doesNotMatch(html,/<script>/);
 }
 assert.match(minimal.renderMinimal(cv,'ru',data,'llm','macintosh'),/Создавать модели/);
 assert.equal(JSON.stringify(cv),before);
});

 test('full CV stays readable without the former tool dashboard',()=>{
 const minimal=load('minimalPortfolio'),themes=load('presentationStyle'),data=snapshot();
 const cv={name:'Candidate',title:'Engineer',contact:{email:'public@example.org'},aboutMd:'Research.',experience:hh.applyHHSnapshot({experience:[]},data).experience,education:[],techStack:{categories:[]}};
 for(const style of themes.presentationStyles){
  const html=minimal.renderMinimal(cv,'ru',data,'all',style,true);
  assert.match(html,/data-export="print"/);assert.match(html,/data-export="markdown"/);
  assert.match(html,/PyTorch project/);assert.doesNotMatch(html,/AI Tools|Technical|Product|Orbit/);
  assert.equal((html.match(/PyTorch project/g)||[]).length,1);
  const en=minimal.renderMinimal(cv,'en',data,'all',style,true);assert.match(en,/<details open><summary>Read original/);
 }
 const picker=themes.stylePicker('openai','en');assert.equal((picker.match(/data-presentation=/g)||[]).length,8);assert.doesNotMatch(picker,/data-presentation="calm"/);
 });

 test('HH source is linked and introduction follows reviewed source instead of stale template',()=>{
 const minimal=load('minimalPortfolio'),data=snapshot();data.source.url='https://hh.ru/resume/'+'a'.repeat(40);data.about={text:'Текущее исследование Flow Matching и воспроизводимых экспериментов.',language:'ru',origin:'reviewed'};
 const cv=hh.applyHHSnapshot({name:'Candidate',title:'Engineer',contact:{email:'public@example.org'},aboutMd:'STALE TEMPLATE',experience:[],education:[]},data);
 const html=minimal.renderMinimal(cv,'ru',data,'all');assert.doesNotMatch(html,/STALE TEMPLATE/);assert.match(html,/Текущее исследование/);assert.match(html,/https:\/\/hh.ru\/resume\/aaaa/);assert.match(minimal.renderMinimal(cv,'en',data,'all'),/Introduction: EN translation pending/);data.source.url='https://evil.org/resume/a';assert.equal(hh.validateSnapshot(data),null);
 });
