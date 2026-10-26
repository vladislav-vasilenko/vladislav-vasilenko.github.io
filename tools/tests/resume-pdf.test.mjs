import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const code=ts.transpileModule(fs.readFileSync(new URL('../../src/features/resumePdf.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context=vm.createContext({exports:{}});vm.runInContext(code,context);

test('local PDF generation embeds Cyrillic and preserves dated public work with no phone number',async()=>{
 const cv={name:'Владислав Василенко',title:'Research Engineer',contact:{email:'public@example.org',phone:'+1 555 0100'},aboutMd:'Исследую генеративные модели.',experience:[{company:'Компания',role:'Инженер',period:'2024 — 2025',duration:'1 год',descriptionMd:'Полное описание работы.\nРезультат: воспроизводимый эксперимент.'}],techStack:{categories:[]},education:[{year:'2024',institution:'Университет',program:'Исследования'}],languages:['Русский']};
 const definition=context.exports.resumePDFDefinition(cv,'ru',null,'data:image/jpeg;base64,'+fs.readFileSync(new URL('../../public/profile.jpg',import.meta.url)).toString('base64')),json=JSON.stringify(definition);
 assert.match(json,/2024 — 2025/);assert.match(json,/воспроизводимый эксперимент/);assert.match(json,/huggingface.co/);assert.doesNotMatch(json,/555 0100|tel:/);
 const pdf=require('pdfmake/build/pdfmake');pdf.addVirtualFileSystem(require('pdfmake/build/vfs_fonts'));
 const buffer=await pdf.createPdf(definition).getBuffer();assert.match(buffer.toString('ascii',0,8),/%PDF-/);assert.ok(buffer.length>10000);
 fs.writeFileSync('/tmp/portfolio-pwa-ru-test.pdf',buffer);
});
