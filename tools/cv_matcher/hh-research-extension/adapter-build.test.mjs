import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {buildAdapters,validateDefinitions,extensionRoot} from './scripts/build-adapters.mjs';

const generated=buildAdapters();
const context=vm.createContext({URL});vm.runInContext(generated,context);
const definitions=JSON.parse(JSON.stringify(context.JobBoardAdapters.registry));
test('checked-in injected bundle matches editable adapter sources',()=>{
  assert.equal(fs.readFileSync(extensionRoot+'board-adapters.js','utf8'),generated);
});
test('all declared board hosts resolve through the generated bundle and have optional permissions',()=>{
  const manifest=JSON.parse(fs.readFileSync(extensionRoot+'manifest.json','utf8'));
  assert.equal(definitions.length,5);
  for(const a of definitions)for(const host of a.hosts){
    assert.equal(context.JobBoardAdapters.resolve('https://'+host+'/').id,a.id);
    assert.ok(manifest.optional_host_permissions.includes('https://'+host+'/*'),host);
  }
  assert.equal(context.JobBoardAdapters.resolve('http://tbank.ru/career/'),null);
});
test('invalid adapter definitions fail before overwriting a usable bundle',()=>{
  const valid={id:'example',label:'Example',hosts:['jobs.example.org'],url:'https://jobs.example.org/jobs/',pages:'^/jobs/'};
  for(const patch of [{url:'http://jobs.example.org/jobs/'},{hosts:['*.example.org']},{url:'https://other.example.org/jobs/'},{description:''},{pages:'['},{layouts:{'other.example.org':{card:'.card'}}}])assert.throws(()=>validateDefinitions([{...valid,...patch}]));
  assert.throws(()=>validateDefinitions([valid,valid]));
  assert.throws(()=>validateDefinitions([valid,{...valid,id:'other'}]));
});
test('host-specific layouts and custom recipes survive the split',()=>{
  const adapters=context.JobBoardAdapters;
  assert.equal(adapters.resolve('https://ozon.tech/vacancies/123').board_id,'ozon-tech');
  assert.equal(adapters.resolve('https://career.ozon.ru/vacancies/123').board_id,'ozon-career');
  adapters.configure([{id:'yandex',boards:[{url:'https://yandex.ru/jobs/',description_selector:'.custom-body'}]}]);
  assert.equal(adapters.resolve('https://yandex.ru/jobs/vacancies/123').description,'.custom-body');
  assert.equal(adapters.resolve('https://not-yandex.test/jobs/'),null);
});
