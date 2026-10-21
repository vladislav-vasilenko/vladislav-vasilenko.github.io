import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
class Element {
 constructor(){this.children=[];this.value='';this.listeners={};this.disabled=false;}
 replaceChildren(...children){this.children=children;this.value=children[0]?.value||'';}
 addEventListener(name,fn){this.listeners[name]=fn;}
 get options(){return this.children;}
}
async function popup({otherTab=false,file=false}={}) {
 const id='a'.repeat(38),other='b'.repeat(38),elements={};
 const html=fs.readFileSync(new URL('popup.html',import.meta.url),'utf8');
 for(const [,name] of html.matchAll(/id="([^"]+)"/g))elements[name]=new Element();
 elements.crawlPages.value='2';elements.crawlDetails.value='5';
 const storage={resume_bundle:{primary_id:id,resumes:[{id,title:'Research CV',quality:'full',source_type:file?'file':'hh',checked_at:new Date().toISOString()}]},
 vacancies:[{id:'hh_1',description_quality:'full',recommended_for:[id]}],ranking_goal:'DiT / Flow matching'};
 const urls=[],messages=[];
 const chrome={runtime:{id:'fixture',getURL:p=>'chrome-extension://fixture/'+p,sendMessage:async message=>{messages.push(message);return {ok:true};}},
 tabs:{query:async()=>[{id:1,url:'https://hh.ru/search/vacancy?resume='+(otherTab?other:id)}],create:async({url})=>urls.push(url)},
 storage:{local:{get:async()=>storage,set:async data=>Object.assign(storage,data)},onChanged:{addListener:()=>{}}}};
 const ctx=vm.createContext({chrome,URL,URLSearchParams,Date,setTimeout,clearTimeout,document:{getElementById:id=>elements[id],createElement:()=>new Element()},
 fetch:async url=>({ok:!url.includes('resume-profile.local.json'),json:async()=>JSON.parse(fs.readFileSync(new URL('search-profile.json',import.meta.url),'utf8'))})});
 for(const file of ['core.js','collection-storage.js','popup.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),ctx);
 await new Promise(resolve=>setImmediate(resolve));
 return {id,elements,urls,messages,storage};
}
test('recommendation controls carry the selected HH CV and saved goal to the scoped ranking',async()=>{
 const p=await popup();assert.equal(p.elements.openRecommendations.disabled,false);assert.equal(p.elements.crawlRecommendations.disabled,false);
 assert.equal(p.elements.rankRecommendations.disabled,false);assert.equal(p.elements.searchGoal.value,'DiT / Flow matching');
 await p.elements.openRecommendations.onclick();assert.equal(new URL(p.urls[0]).searchParams.get('resume'),p.id);
 await p.elements.rankRecommendations.onclick();const ranking=new URL(p.urls[1]);
 assert.equal(ranking.searchParams.get('resume'),p.id);assert.equal(ranking.searchParams.get('goal'),'DiT / Flow matching');assert.equal(ranking.searchParams.get('source'),'hh_recommended');
 await p.elements.crawlRecommendations.onclick();assert.equal(p.messages[0].recommended_resume_id,p.id);assert.equal(p.messages[0].options.pages,'2');assert.equal(p.messages[0].options.details,'5');
});
test('recommendation collection rejects a different active CV and disables file-only HH actions',async()=>{
 const wrong=await popup({otherTab:true});assert.equal(wrong.elements.crawlRecommendations.disabled,true);await wrong.elements.crawlRecommendations.onclick();assert.equal(wrong.messages.length,0);
 const file=await popup({file:true});assert.equal(file.elements.openRecommendations.disabled,true);assert.equal(file.elements.crawlRecommendations.disabled,true);
});

test('closed-vacancy filter is enabled by default and its explicit override reaches every collector',async()=>{
 const p=await popup();await p.elements.crawlHH.onclick();assert.equal(p.messages.at(-1).options.skip_closed,true);
 p.elements.skipClosed.checked=false;await p.elements.crawlHH.onclick();assert.equal(p.messages.at(-1).options.skip_closed,false);
 await p.elements.crawlRecommendations.onclick();assert.equal(p.messages.at(-1).options.skip_closed,false);
 await p.elements.crawlBoard.onclick();assert.equal(p.messages.at(-1).type,'crawl_board');assert.equal(p.messages.at(-1).options.skip_closed,false);
});


test('force-details option is explicit and reaches both HH and company collectors',async()=>{
 const p=await popup();await p.elements.crawlHH.onclick();assert.equal(p.messages.at(-1).options.force_details,false);
 p.elements.forceDetails.checked=true;await p.elements.crawlHH.onclick();assert.equal(p.messages.at(-1).options.force_details,true);
 await p.elements.crawlRecommendations.onclick();assert.equal(p.messages.at(-1).options.force_details,true);
 await p.elements.crawlBoard.onclick();assert.equal(p.messages.at(-1).options.force_details,true);
});
