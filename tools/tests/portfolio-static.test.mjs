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
  const rendered=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
  const expected=lang==='en'?snapshot.experience_translations?.en?.items:snapshot.experience;
  assert.ok(rendered.includes(expected[0].period));assert.ok(rendered.includes(expected[0].role));assert.match(html,/hreflang="en"/);assert.match(html,/hreflang="ru"/);
  const structured=JSON.parse(html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s)[1]);
  assert.equal(structured['@type'],'ProfilePage');assert.equal(structured.mainEntity['@type'],'Person');
  assert.equal(structured.url,url);assert.doesNotMatch(JSON.stringify(structured),/aggregateRating|award|Research Scientist/);
  assert.match(html,/portfolio-snapshot/);assert.doesNotMatch(html,/turnstile|<div id="app"><\/div>/);
 }
});

test('prerendered Intro labels and the fixed public Email link follow the page language', () => {
 const template = fs.readFileSync(new URL('../../index.html',import.meta.url),'utf8');
 for (const lang of ['en','ru']) {
  const html = staticHTML(template,lang,snapshot);
  assert.ok(html.includes(lang==='ru'?'Посмотреть резюме':'View resume'));
  assert.ok(html.includes(lang==='ru'?'data-intro-email-label>Почта':'data-intro-email-label>Email'));
  assert.ok(html.includes(lang==='ru'?'data-intro-print-label>Резюме для печати':'data-intro-print-label>Print-friendly resume'));
  assert.ok(html.includes('/?print=true&amp;lang='+lang+'" data-intro-print'));
  assert.match(html,/class="minimal-print-link"/);
  assert.ok(html.includes('mailto:mr.vasilenko.vlad@yandex.ru'));
  assert.ok(html.includes(lang==='ru'?'aria-label="Связаться с Владиславом"':'aria-label="Contact Vladislav"'));
 }
});
