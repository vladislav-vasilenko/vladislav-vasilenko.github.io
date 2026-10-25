import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function load(name) {
 const source=fs.readFileSync(new URL('../../src/features/'+name+'.ts',import.meta.url),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const context=vm.createContext({exports:{},URL,location:{href:'https://example.org/?print=true&lang=ru'},require:path=>load(path.replace('./',''))});
 vm.runInContext(code,context);return context.exports;
}
const {renderPrintResume}=load('printResume');
const cv={
 name:'Candidate',title:'Engineer<br><small>Legacy subtitle</small>',aboutMd:'Full biography.',
 contact:{phone:'+1 555 0100',email:'public@example.org',location:'City',relocation:'Remote'},
 experience:[{id:'one',company:'Employer',role:'Engineer',period:'2023–2025',duration:'2 years',descriptionMd:'Full responsibilities.\n\n<script>alert(1)</script> **Result:** shipped.',location:''},
 {id:'two',company:'Another employer',role:'Researcher',period:'2025–now',duration:'1 year',descriptionMd:'A second complete role.',location:''}],
 education:[{year:'2020',institution:'University',program:'Computer Science'}],
 techStack:{categories:[{label:{ru:'Инструменты',en:'Tools'},items:[{name:'PyTorch'}]}]},languages:['English','Русский'],
};
const snapshot={
 source:{language:'ru',url:'https://hh.ru/resume/'+'a'.repeat(40)},about:{text:'Биография из локального сервиса',language:'ru'},
 confirmed_skills:[{label:'PyTorch',links:[{url:'https://github.com/example/lab',label:'Research lab'}]}],
};
test('print view exposes complete dated experience and evidence with no interactive resume dashboard', () => {
 const original=JSON.stringify(cv);
 const html=renderPrintResume(cv,'ru',snapshot);
 assert.equal((html.match(/class="print-experience-entry"/g)||[]).length,2);
 for(const text of ['2023–2025','2 years','A second complete role.','Computer Science','Research lab','Биография из локального сервиса']) assert.ok(html.includes(text));
 assert.doesNotMatch(html,/<script>|<details|<select|<canvas|presentation-picker|portfolio-pwa/);
 assert.match(html,/&lt;script&gt;alert/);
 assert.doesNotMatch(html,/Legacy subtitle|\*\*Result/);
 assert.match(html,/data-print-document/);assert.match(html,/resumeView=true/);
 assert.ok(html.includes(snapshot.source.url));assert.ok(html.includes('https://github.com/example/lab'));
 assert.equal(JSON.stringify(cv),original);
});
test('English print view discloses untranslated source blocks; no-snapshot rendering keeps the full bio', () => {
 const html=renderPrintResume(cv,'en',snapshot);
 assert.match(html,/Translation pending/);assert.match(html,/Original experience text · RU/);
 const fallback=renderPrintResume(cv,'en',null);
 assert.match(fallback,/Full biography\./);assert.match(fallback,/Work experience/);
 assert.doesNotMatch(fallback,/primary HH resume|Translation pending/);
});
