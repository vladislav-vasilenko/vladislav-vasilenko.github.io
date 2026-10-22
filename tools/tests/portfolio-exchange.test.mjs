import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

test('shared Markdown exchange preserves selected CV text, dates and evidence links', () => {
  const source = fs.readFileSync(new URL('../../src/export.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  }).outputText;
  const context = vm.createContext({exports: {}});
  vm.runInContext(code, context);
  const cv = {
    name: 'Candidate', title: 'Research Engineer',
    contact: {location: 'Remote', email: 'example@example.org', phone: '', relocation: ''},
    labels: {
      about: 'О себе', employment: 'Занятость', experience: 'Опыт',
      education: 'Образование', skills: 'Навыки', languages: 'Языки',
    },
    aboutMd: 'Проверенный проект [code](https://github.com/example/project)',
    employment: 'Full-time',
    experience: [{
      role: 'ML Engineer', company: 'Example', period: '2023–2025', duration: '2 года',
      descriptionMd: 'Воспроизведён эксперимент; метрики и ограничения.',
    }],
    education: [],
    techStack: {categories: [{label: {ru: 'ML'}, items: [{name: 'PyTorch'}]}]},
    languages: ['English'],
  };
  const before = structuredClone(cv);
  const markdown = context.exports.buildMarkdown(cv);
  assert.match(markdown, /2023–2025/);
  assert.match(markdown, /Воспроизведён эксперимент/);
  assert.match(markdown, /https:\/\/github.com\/example\/project/);
  assert.match(markdown, /PyTorch/);
  assert.deepEqual(cv, before);
});
