import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const code = ts.transpileModule(fs.readFileSync(new URL('../../src/features/locale.ts', import.meta.url), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const context = vm.createContext({exports: {}, URL});
vm.runInContext(code, context);
const {portfolioLanguage} = context.exports;

test('browser locale is used on a first visit and explicit EN/RU navigation overrides it', () => {
  assert.equal(portfolioLanguage('https://example.org/', ['ru-RU', 'en']), 'ru');
  assert.equal(portfolioLanguage('https://example.org/', ['en-GB', 'ru']), 'en');
  assert.equal(portfolioLanguage('https://example.org/', ['de-DE']), 'en');
  assert.equal(portfolioLanguage('https://example.org/', []), 'en');
  assert.equal(portfolioLanguage('https://example.org/ru/', ['en-US']), 'ru');
  assert.equal(portfolioLanguage('https://example.org/?lang=en', ['ru-RU']), 'en');
  assert.equal(portfolioLanguage('https://example.org/?lang=ru', ['en-US']), 'ru');
  assert.equal(portfolioLanguage('https://example.org/ru/?lang=en', ['ru-RU']), 'en');
});
