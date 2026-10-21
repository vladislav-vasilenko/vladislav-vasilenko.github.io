import test from 'node:test';
import assert from 'node:assert/strict';
import './board-core.js';
import './core.js';
import './board-adapters.js';
const {identity} = globalThis.JobBoards;
test('Ozon accepts cross-domain numeric IDs, UUIDs and fintech query IDs, excludes filters',()=>{
  assert.equal(identity('https://ozon.tech/vacancies/136375417/').id,'ozon_136375417');
  assert.equal(identity('https://ozon.tech/vacancies/1f05c7d4-fee8-41be-b8aa-1780551f9a2c-title/').id,'ozon_1f05c7d4-fee8-41be-b8aa-1780551f9a2c');
  assert.equal(identity('https://career.ozon.ru/fintech/vacancy?id=137587804').id,'ozon_137587804');
  assert.equal(identity('https://career.ozon.ru/vacancy/python/'),null);
});
test('new boards retain query IDs and remove tracking for stable identity',()=>{
  const a=identity('https://example.org/jobs/detail?id=1&utm_source=x');
  const b=identity('https://example.org/jobs/detail?id=1&utm_source=y');
  assert.equal(a.id,b.id);
  assert.notEqual(a.id,identity('https://example.org/jobs/detail?id=2').id);
  assert.equal(identity('javascript:alert(1)'),null);
});
test('different employer records survive merging and snippets cannot destroy a JD',()=>{
  const full={...identity('https://career.avito.com/vacancies/data-science/19450/'),description:'complete JD',description_quality:'full',collected_at:'now'};
  const ozon={...identity('https://ozon.tech/vacancies/136375417/'),description:'full Ozon',description_quality:'full',collected_at:'now'};
  let jobs=ResearchSearch.mergeVacancies([],[full,ozon]);
  jobs=ResearchSearch.mergeVacancies(jobs,[{...full,description:'',description_quality:'snippet'}]);
  assert.equal(jobs.length,2); assert.equal(jobs[0].description,'complete JD');
});
test('explicit adapters recognize all five employers, reject directories and keep stable cross-collector IDs',()=>{
 const cases=[['https://career.avito.com/vacancies/data-science/19450/','avito','avito_19450'],['https://ozon.tech/vacancies/136375417/','ozon','ozon_136375417'],['https://yandex.ru/jobs/vacancies/mlrazrabotchik-v-karti-20372','yandex','yandex_20372'],['https://rabota.sber.ru/search/ml-engineer-12345','sber','sber_12345'],['https://www.tbank.ru/career/it/vacancy/moscow/ml-engineer/0d772642-b21e-4529-a234-5e93b00210be/','tbank','tbank_0d772642-b21e-4529-a234-5e93b00210be']];
 for(const [url,adapter,id] of cases){assert.equal(JobBoardAdapters.resolve(url).id,adapter);assert.equal(identity(url).id,id);}
 for(const url of JobBoardAdapters.registry.map(r=>r.url))assert.equal(identity(url),null);
 assert.equal(JobBoardAdapters.resolve('https://tbank.ru.evil.test/career/'),null);
});
test('board pagination only follows observed same-origin listing links with unchanged search filters',()=>{
 const current='https://career.avito.com/vacancies/?direction=data-science&page=1',next=current.replace('page=1','page=2');assert.equal(JobBoardAdapters.nextURL(current,next),next);
 for(const value of [next.replace('data-science','marketing'),next.replace('career.avito.com','evil.test'),current,'https://career.avito.com/vacancies/data-science/19450/'])assert.equal(JobBoardAdapters.nextURL(current,value),null);
});
