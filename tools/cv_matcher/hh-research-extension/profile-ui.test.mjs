import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
class Element {constructor(text=''){this.textContent=text;this.children=[];this.value='';}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}setAttribute(){} }
test('web settings expose editable city/social/portfolio and save revisions without model calls',async()=>{
 const ids=new Map(),calls=[],$=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};
 const profile={labels:{city:'Город',telegram_url:'Соцсети · Telegram',portfolio_url:'Портфолио'},values:{city:'Москва',telegram_url:'https://t.me/vsvladis',portfolio_url:'https://github.com/vladislav-vasilenko'},revisions:{city:1,telegram_url:1,portfolio_url:1}};
 const c=vm.createContext({structuredClone,URL,make:(_tag,_cls,text)=>new Element(text),$,api:async(path,data)=>{calls.push({path,data});return path==='company-settings'?{companies:[],adapters:{}}:structuredClone(profile);}});
 vm.runInContext(fs.readFileSync(new URL('../archive-web/company-settings.js',import.meta.url),'utf8')+'\nglobalThis.settings=CompanySettings;',c);await c.settings.enter();
 const root=$('candidateProfile'),grid=root.children.find(n=>n.children.length===3),labels=grid.children;
 assert.deepEqual(labels.map(n=>n.textContent),['Город','Соцсети · Telegram','Портфолио']);assert.equal(labels[0].children[0].value,'Москва');
 labels[2].children[0].value='https://example.test/portfolio';const save=root.children.find(n=>n.textContent==='Сохранить данные автозаполнения');await save.onclick();
 const written=calls.at(-1);assert.equal(written.path,'workflow');assert.equal(written.data.op,'candidate_profile_save');assert.equal(written.data.values.portfolio_url,'https://example.test/portfolio');assert.equal(written.data.revisions.city,1);assert.ok(calls.every(x=>['company-settings','workflow'].includes(x.path)));
});
