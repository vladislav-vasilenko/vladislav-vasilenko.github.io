import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
test('quick mark is one local action, stops opening the card, and undo uses latest revision',async()=>{
 const source=fs.readFileSync(new URL('../archive.js',import.meta.url),'utf8'),buttons=[],calls=[];let saved={marked:false,revision:0},changed=0,stopped=0;
 const context={Map,document:{querySelectorAll:()=>buttons},date:()=> 'today',notice:()=>{},make:()=>({dataset:{},setAttribute(){}}),api:async(path,body)=>{calls.push({path,body});assert.equal(path,'workflow');assert.equal(body.op,'manual_application');assert.equal(body.revision,saved.revision);saved={marked:body.marked,revision:saved.revision+1,source:'user',site_confirmed:false};return saved;}};
 vm.runInNewContext(source.slice(source.indexOf('const manualApplicationState'),source.indexOf('function external('))+';globalThis.create=manualApplicationButton;',context);
 const b=context.create({id:'hh_123',manual_application:saved},async()=>{changed++;});buttons.push(b);assert.equal(b.textContent,'Отклик сделан');
 await b.onclick({stopPropagation(){stopped++;}});assert.ok(b.textContent.includes('✓'));assert.equal(b.disabled,false);assert.equal(changed,1);
 await b.onclick({stopPropagation(){stopped++;}});assert.equal(b.textContent,'Отклик сделан');assert.equal(stopped,2);assert.equal(calls.length,2);assert.equal(calls[0].body.marked,true);assert.equal(calls[1].body.marked,false);assert.ok(!('resume_id' in calls[0].body));
});
