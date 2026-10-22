import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {staticHTML,origin} from '../portfolio-static.mjs';
const template='<!doctype html><html><head><title>Placeholder</title><!--portfolio:seo--></head><body><div id="app"></div></body></html>';
const snapshot=JSON.parse(fs.readFileSync(new URL('../../public/hh-experience.json',import.meta.url),'utf8'));
test('indexable bilingual HTML contains the same HH work and reviewed bio without JavaScript',()=>{
 for(const lang of ['en','ru']){
  const html=staticHTML(template,lang,snapshot),url=origin+(lang==='ru'?'/ru/':'/');
  assert.match(html,new RegExp('<html lang="'+lang+'"'));assert.ok(html.includes('rel="canonical" href="'+url+'"'));
  assert.equal((html.match(/class="minimal-entry/g)||[]).length,snapshot.experience.length);
  assert.ok(html.includes(snapshot.experience[0].period));assert.match(html,/hreflang="en"/);assert.match(html,/hreflang="ru"/);
  const structured=JSON.parse(html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s)[1]);
  assert.equal(structured['@type'],'ProfilePage');assert.equal(structured.mainEntity['@type'],'Person');
  assert.equal(structured.url,url);assert.doesNotMatch(JSON.stringify(structured),/aggregateRating|award|Research Scientist/);
  assert.match(html,/portfolio-snapshot/);assert.doesNotMatch(html,/turnstile|<div id="app"><\/div>/);
 }
});
