import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const c={};vm.runInNewContext(fs.readFileSync(new URL('../career-charts.js',import.meta.url),'utf8'),c);const Charts=c.CareerCharts;
const rows=[{id:'a',company:'Yandex',category:'pretraining',tags:['pretraining','diffusion'],first_seen:'2026-10-01',availability:'unknown',fit:75,alignment:.5,stage:'none',work_format:'remote',region:'moscow'},{id:'b',company:'Ozon',category:'diffusion',tags:['diffusion'],first_seen:'2026-10-02',availability:'active',fit:null,alignment:null,stage:'applied',work_format:'hybrid',region:'spb'},{id:'c',company:'Ozon',category:'cuda',tags:['cuda'],first_seen:'2026-10-03',availability:'active',fit:25,alignment:.1,stage:'draft',work_format:'onsite',region:'rf'}];
const taxonomy=[{id:'pretraining',label:'Pretraining'},{id:'diffusion',label:'Flow / Diffusion'},{id:'cuda',label:'CUDA'}];
test('Sankey conserves every vacancy at each layer and every flow drills into exact unique IDs',()=>{
 const g=Charts.funnel(rows,taxonomy);for(let layer=0;layer<5;layer++){const nodes=g.nodes.filter(n=>n.layer===layer);assert.equal(nodes.reduce((n,v)=>n+v.ids.length,0),rows.length);assert.equal(new Set(nodes.flatMap(n=>n.ids)).size,rows.length);}
 for(const link of g.links){assert.equal(link.value,link.ids.length);assert.ok(!/NaN|Infinity/.test(link.path));const source=g.nodes.find(n=>n.id===link.source);assert.ok(link.ids.every(id=>source.ids.includes(id)));}
 assert.equal(g.nodes.find(n=>n.id==='2:unknown').ids[0],'b');assert.ok(g.nodes.some(n=>n.id==='4:none'));
});
test('Flow Matching filter retains jobs whose primary category is Pretraining; unknown is never zero fit',()=>{
 assert.equal(Charts.filters(rows,{category:'diffusion'}).length,2);assert.equal(Charts.filters(rows,{fit:'high',fitThreshold:60}).length,1);assert.equal(Charts.filters(rows,{fit:'unknown'}).length,1);
 assert.equal(Charts.filters(rows,{from:'2026-10-02',to:'2026-10-02'}).length,1);
 assert.equal(Charts.filters(rows,{workFormat:'remote'}).length,1);
 assert.equal(Charts.filters(rows,{region:'spb'}).length,1);
 assert.equal(Charts.filters(rows,{workFormat:'remote',region:'moscow'}).length,1);
 assert.equal(Charts.filters(rows,{workFormat:'remote',region:'spb'}).length,0);
});
test('focus is a union of selected tags without changing archive rows or double counting overlaps',()=>{
 const focused=Charts.filters(rows,{focus:true,focusCategories:['diffusion','pretraining']});assert.equal(focused.length,2);assert.equal(new Set(focused.map(r=>r.id)).size,2);
 assert.equal(Charts.filters(rows,{focus:true,focusCategories:[]}).length,0);assert.equal(Charts.filters(rows,{focus:false,focusCategories:[]}).length,3);assert.equal(rows.length,3);
});
test('tiny Sankey nodes keep label spacing while all widths use one proportional scale',()=>{
 const many=Array.from({length:1000},(_,i)=>({...rows[0],id:'big'+i}));for(let i=0;i<8;i++)many.push({...rows[0],id:'small'+i,category:'c'+i,tags:['c'+i]});
 const g=Charts.funnel(many,[...taxonomy,...Array.from({length:8},(_,i)=>({id:'c'+i,label:'Small '+i}))]);const nodes=g.nodes.filter(n=>n.layer===1).sort((a,b)=>a.y-b.y);
 for(let i=1;i<nodes.length;i++)assert.ok(nodes[i].y+nodes[i].h/2-(nodes[i-1].y+nodes[i-1].h/2)>=36);
 const scale=nodes[0].h/nodes[0].ids.length;for(const n of nodes)assert.ok(Math.abs(n.h-scale*n.ids.length)<1e-8);
});
test('history shares have a conserved denominator and clicks refer to real cohort IDs',()=>{
 const history=[{month:'2026-10',ids:{diffusion:['a','b'],cuda:['c']}}];const p=Charts.evolution(history,['a','c'],'',true)[0];assert.equal(p.total,2);assert.equal(p.values.diffusion,50);assert.equal(p.values.cuda,50);assert.equal(Charts.evolution(history,[],'',true)[0].total,0);
});
test('map switches cosine CV similarity versus actual Luna percentage without substituting unknowns',()=>{
 const input=[{id:'embed',similarity:.7,alignment:.4,fit:null},{id:'both',similarity:.5,alignment:.3,fit:80},{id:'negative',similarity:-.2,alignment:-.1,fit:0},{id:'missing',similarity:null,alignment:.5,fit:null},{id:'bad',similarity:Infinity,alignment:NaN,fit:100}];
 const overview=Charts.opportunityMap(input);assert.equal(overview.mode,'embeddings');assert.equal(overview.points.length,3);assert.equal(overview.missing,2);assert.equal(overview.min,-1);assert.equal(overview.formatX(.7),'0.70');
 const luna=Charts.opportunityMap(input,'luna',{fitThreshold:80});assert.equal(luna.points.length,2);assert.equal(luna.missing,3);assert.equal(luna.max,100);assert.equal(luna.xThreshold,80);assert.equal(luna.formatX(80),'80%');assert.ok(luna.points.some(p=>p.id==='negative'&&p.x===0));assert.equal(input[0].fit,null);
});
test('batch module is defined before analytics runs and diagnostics contain safe request context',()=>{
 const source=fs.readFileSync(new URL('../career-analytics.js',import.meta.url),'utf8');const sandbox={localStorage:{getItem:()=>null},CareerCharts:Charts};vm.runInNewContext(source+';globalThis.batchType=typeof CareerBatch.preview;',sandbox);assert.equal(sandbox.batchType,'function');
 const archive=fs.readFileSync(new URL('../archive.js',import.meta.url),'utf8');assert.ok(archive.includes('X-Career-Request-Id'));assert.ok(archive.includes("window.addEventListener('unhandledrejection'"));assert.ok(archive.includes('Техническая диагностика'));
});
test('linear zoom includes every point, preserves negative scores and handles single/identical points',()=>{
 for(const input of [[{similarity:.52,alignment:.21},{similarity:.7,alignment:.4}],[{similarity:0,alignment:0}],[{similarity:-1,alignment:1}],[{similarity:1,alignment:-1}],[]]){
  const view=Charts.opportunityMap(input),v=Charts.mapViewport(view);assert.ok(v.x.max>v.x.min);assert.ok(v.y.max>v.y.min);for(const p of view.points){assert.ok(p.x>=v.x.min&&p.x<=v.x.max);assert.ok(p.y>=v.y.min&&p.y<=v.y.max);}assert.ok(v.xTicks.every(Number.isFinite));assert.ok(v.yTicks.every(Number.isFinite));
  const full=Charts.mapViewport(view,'full');assert.equal(full.x.min,-1);assert.equal(full.x.max,1);assert.equal(full.y.min,-1);assert.equal(full.y.max,1);
 }
 const view=Charts.opportunityMap([{similarity:.52,alignment:.2},{similarity:.7,alignment:.4}]);const v=Charts.mapViewport(view);assert.ok(v.x.max-v.x.min<1);assert.ok(v.y.max-v.y.min<1);
});
test('many new market categories keep positive conserved flow widths within the SVG',()=>{
 const taxonomy=Array.from({length:40},(_,i)=>({id:'tag'+i,label:'Category '+i}));const input=taxonomy.map((t,i)=>({...rows[0],id:'v'+i,category:t.id,tags:[t.id]}));const g=Charts.funnel(input,taxonomy);assert.ok(g.height>650);for(const n of g.nodes){assert.ok(n.h>0);assert.ok(n.y>=0);assert.ok(n.y+n.h<=g.height);}assert.equal(g.links.filter(l=>l.source==='0:market').reduce((s,l)=>s+l.value,0),40);
});
test('wide fullscreen relayout spreads columns without stretching labels or altering flow values',()=>{
 const narrow=Charts.funnel(rows,taxonomy),wide=Charts.funnel(rows,taxonomy,{width:4000});assert.equal(wide.width,4000);assert.equal(wide.height,narrow.height);
 for(const n of wide.nodes){const old=narrow.nodes.find(v=>v.id===n.id);assert.equal(n.y,old.y);assert.equal(n.h,old.h);assert.equal(n.label,old.label);if(n.layer)assert.ok(n.x>old.x);assert.ok(n.x+20<4000);}
 assert.deepEqual(Array.from(wide.links,l=>l.value),Array.from(narrow.links,l=>l.value));
});
test('PNG export covers full SVG height with a caption and bounds memory for many categories',()=>{
 const normal=Charts.exportGeometry(1450,650);assert.equal(normal.width,2900);assert.equal(normal.height,1480);assert.equal(normal.padding,90);
 const large=Charts.exportGeometry(1450,15000);assert.ok(large.width*large.height<=20_000_000);assert.ok(large.scale>0);assert.throws(()=>Charts.exportGeometry(0,20));
});
test('funnel zoom preserves the pointer anchor and clamps repeated zoom at safe bounds',()=>{
 const p=Charts.zoomViewport(1,2,{x:100,y:80},{left:200,top:120});assert.equal(p.scale,2);assert.equal(p.left,500);assert.equal(p.top,320);
 const back=Charts.zoomViewport(p.scale,.5,{x:100,y:80},{left:p.left,top:p.top});assert.equal(back.left,200);assert.equal(back.top,120);
 assert.equal(Charts.zoomViewport(4,2,{x:0,y:0},{left:200,top:120}).scale,4);assert.equal(Charts.zoomViewport(.5,.1,{x:0,y:0},{left:0,top:0}).scale,.5);
});
test('fullscreen controls zoom with wheel, reset to fit, preserve source viewBox and restore page scrolling on exit',()=>{
 const events={},box={clientWidth:800,clientHeight:500,scrollLeft:0,scrollTop:0,classList:{add(){},remove(){}},addEventListener:(type,fn)=>{events[type]=fn;},getBoundingClientRect:()=>({left:20,top:30})},image={style:{},viewBox:{baseVal:{width:1450,height:1000}}};let reported,prevented=0;
 const zoom=Charts.funnelZoom(box,image,s=>reported=s);const wheel={deltaY:-100,deltaMode:0,clientX:220,clientY:130,preventDefault:()=>prevented++};events.wheel(wheel);assert.equal(prevented,0);
 zoom.setActive(true);assert.equal(image.style.width,'725px');assert.ok(parseFloat(image.style.width)*1000/1450<=box.clientHeight);zoom.zoomBy(2);assert.equal(reported,2);assert.equal(image.style.width,'1450px');assert.equal(box.scrollLeft,400);
 events.wheel(wheel);assert.equal(prevented,0);assert.equal(reported,2); // two-finger pan stays native
 events.wheel({...wheel,ctrlKey:true});assert.equal(prevented,1);assert.ok(reported>2);zoom.reset();assert.equal(reported,1);assert.equal(box.scrollTop,0);assert.equal(box.scrollLeft,0);
 zoom.setWheelZoom(true);events.wheel(wheel);assert.equal(prevented,2);assert.ok(reported>1);
 assert.equal(image.viewBox.baseVal.width,1450);assert.equal(image.viewBox.baseVal.height,1000);zoom.setActive(false);assert.equal(image.style.width,'');events.wheel({...wheel,ctrlKey:true});assert.equal(prevented,2);
});
test('dragging pans a zoomed funnel without activating a flow; ordinary clicks remain available',()=>{
 const events={},box={clientWidth:800,clientHeight:500,scrollLeft:0,scrollTop:0,classList:{add(){},remove(){}},addEventListener:(type,fn)=>events[type]=fn,setPointerCapture(){},hasPointerCapture:()=>true,releasePointerCapture(){}},zoom=Charts.funnelZoom(box,{style:{},viewBox:{baseVal:{width:1450,height:1000}}});zoom.setActive(true);zoom.zoomBy(2);let blocked=0;const click={preventDefault(){blocked++;},stopImmediatePropagation(){blocked++;}};
 events.pointerdown({button:0,pointerId:1,clientX:200,clientY:200});events.pointermove({pointerId:1,clientX:198,clientY:200});events.pointerup({pointerId:1});events.click(click);assert.equal(blocked,0);
 events.pointerdown({button:0,pointerId:2,clientX:200,clientY:200});events.pointermove({pointerId:2,clientX:150,clientY:170});events.pointerup({pointerId:2});assert.equal(box.scrollLeft,450);assert.equal(box.scrollTop,280);events.click(click);assert.equal(blocked,2);
});
