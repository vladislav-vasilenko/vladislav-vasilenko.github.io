/* Deterministic layouts shared by the UI and tests; no remote chart dependency. */
(function(root){
 'use strict';
 const stageLabels={none:'Нет отклика в CRM',draft:'Черновик',applied:'Отклик / общение',interview:'Интервью',rejected:'Отказ',offer:'Оффер'};
 const categoryColors=["#7665b7", "#ac6b39", "#297f96", "#5078b6", "#4c7963", "#6870a4", "#a7667c", "#7b8650", "#697983", "#945a47", "#474b94", "#629447", "#944778", "#478f94", "#948347", "#6d4794", "#479456", "#94474f", "#476594", "#7b9447", "#944792", "#479480", "#946947", "#534794", "#529447", "#944768", "#477f94", "#949347", "#7c4794", "#479466", "#945047", "#475594", "#6c9447", "#944782", "#47948f", "#96a09c"];
 function bucket(value,threshold,high,low,unknown){return value===null||value===undefined?unknown:value>=threshold?high:low;}
 function filters(rows,f){return rows.filter(r=>(!f.focus||r.tags.some(tag=>(f.focusCategories||[]).includes(tag)))&&(!f.company||r.company===f.company)&&(!f.category||r.tags.includes(f.category))&&(!f.workFormat||r.work_format===f.workFormat)&&(!f.region||r.region===f.region)&&(!f.from||r.first_seen.slice(0,10)>=f.from)&&(!f.to||r.first_seen.slice(0,10)<=f.to)&&(!f.availability||r.availability===f.availability)&&(!f.fit||f.fit==='known'&&r.fit!==null||f.fit==='unknown'&&r.fit===null||f.fit==='high'&&r.fit!==null&&r.fit>=f.fitThreshold));}
 function funnel(rows,taxonomy,{fitThreshold=60,alignmentThreshold=.4,width=1450}={}){
  const labels=Object.fromEntries(taxonomy.map(t=>[t.id,t.label])),nodes=new Map(),edges=new Map();
  const paths=rows.map(r=>[{key:'market',label:'Собранная выборка'},{key:r.category,label:labels[r.category]},
   {key:bucket(r.fit,fitThreshold,'high','low','unknown'),label:bucket(r.fit,fitThreshold,'От '+fitThreshold+'% требований','Менее '+fitThreshold+'%','Разбора нет')},
   {key:bucket(r.alignment,alignmentThreshold,'high','low','unknown'),label:bucket(r.alignment,alignmentThreshold,'Цель ≥ '+alignmentThreshold,'Цель < '+alignmentThreshold,'Оценки цели нет')},
   {key:r.stage,label:stageLabels[r.stage]||r.stage}].map((p,layer)=>{
    const id=layer+':'+p.key;if(!nodes.has(id))nodes.set(id,{id,layer,label:p.label,key:p.key,ids:[]});nodes.get(id).ids.push(r.id);return id;
   }));
  paths.forEach((path,index)=>path.slice(1).forEach((target,j)=>{const source=path[j],id=source+'>'+target;if(!edges.has(id))edges.set(id,{id,source,target,ids:[]});edges.get(id).ids.push(rows[index].id);}));
  const pad=14,top=52,bottom=35,minSlot=36,columns=Array.from({length:5},(_,i)=>[...nodes.values()].filter(n=>n.layer===i));
  const height=Math.max(650,...columns.map(c=>top+bottom+c.length*minSlot+Math.max(0,c.length-1)*pad+150));
  // Keep flow widths proportional; reserve separate label space for tiny nodes.
  const available=height-top-bottom;let low=0,high=rows.length?available/rows.length:0;
  for(let i=0;i<45;i++){const mid=(low+high)/2;const used=Math.max(0,...columns.map(c=>c.reduce((sum,n)=>sum+Math.max(minSlot,n.ids.length*mid),0)+Math.max(0,c.length-1)*pad));if(used<=available)low=mid;else high=mid;}
  const scale=low;
  for(const [i,column] of columns.entries()){
   const used=column.reduce((sum,n)=>sum+Math.max(minSlot,n.ids.length*scale),0)+Math.max(0,column.length-1)*pad;let y=top+(available-used)/2;
   for(const n of column){const h=n.ids.length*scale,slot=Math.max(minSlot,h);Object.assign(n,{x:25+i*(width-318)/4,y:y+(slot-h)/2,h,out:0,in:0});y+=slot+pad;}
  }
  const links=[...edges.values()].map(e=>{
   const a=nodes.get(e.source),b=nodes.get(e.target),h=e.ids.length*scale,sy=a.y+a.out,ty=b.y+b.in,x=a.x+20,z=b.x,m=(x+z)/2;a.out+=h;b.in+=h;
   return {...e,value:e.ids.length,path:`M${x},${sy} C${m},${sy} ${m},${ty} ${z},${ty} L${z},${ty+h} C${m},${ty+h} ${m},${sy+h} ${x},${sy+h} Z`};
  });
  return {width,height,nodes:[...nodes.values()],links};
 }
 function evolution(history,ids,category='',share=false){
  const keep=new Set(ids);return history.map(p=>{const values=Object.fromEntries(Object.entries(p.ids).filter(([key])=>!category||key===category).map(([key,list])=>[key,list.filter(id=>keep.has(id)).length])),total=Object.values(values).reduce((a,b)=>a+b,0);return {...p,total,values:Object.fromEntries(Object.entries(values).map(([key,n])=>[key,share&&total?100*n/total:n]))};});
 }
 function opportunityMap(rows,mode='embeddings',thresholds={}){
  const luna=mode==='luna',field=luna?'fit':'similarity',min=luna?0:-1,max=luna?100:1;
  const valid=(v,a,b)=>typeof v==='number'&&Number.isFinite(v)&&v>=a&&v<=b;
  const points=rows.filter(r=>valid(r[field],min,max)&&valid(r.alignment,-1,1)).map(r=>({...r,x:r[field],y:r.alignment}));
  return {mode:luna?'luna':'embeddings',points,total:rows.length,missing:rows.length-points.length,min,max,
   xThreshold:luna?(thresholds.fitThreshold??60):.6,ticks:luna?[0,20,40,60,80,100]:[-1,-.5,0,.5,1],
   xLabel:luna?'Подтверждение требований CV, по рубрике Luna':'Близость к CV, embeddings (косинус)',
   formatX:v=>luna?v+'%':v.toFixed(2)};
 }
 function mapViewport(view,scale='data'){
  function axis(values,lo,hi,minSpan){
   if(scale==='full'||!values.length)return {min:lo,max:hi};
   const first=Math.min(...values),last=Math.max(...values),span=Math.max(last-first,minSpan),padding=span*.12,center=(first+last)/2;
   return {min:Math.max(lo,Math.min(first-padding,center-span/2-padding)),max:Math.min(hi,Math.max(last+padding,center+span/2+padding))};
  }
  function ticks(a){const raw=(a.max-a.min)/5,power=10**Math.floor(Math.log10(raw)),ratio=raw/power,step=(ratio<=1?1:ratio<=2?2:ratio<=2.5?2.5:ratio<=5?5:10)*power,out=[];for(let i=Math.ceil((a.min-1e-10)/step);i*step<=a.max+1e-10;i++)out.push(Number((i*step).toFixed(6)));return out;}
  const x=axis(view.points.map(p=>p.x),view.min,view.max,view.mode==='luna'?10:.1),y=axis(view.points.map(p=>p.y),-1,1,.1);
  return {x,y,xTicks:scale==='full'?view.ticks:ticks(x),yTicks:scale==='full'?[-1,-.5,0,.5,1]:ticks(y)};
 }
 function exportGeometry(width,height){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw Error('Некорректный размер диаграммы.');
  const padding=90,scale=Math.min(2,Math.sqrt(20_000_000/(width*(height+padding))));
  return {width:Math.max(1,Math.floor(width*scale)),height:Math.max(1,Math.floor((height+padding)*scale)),scale,padding};
 }
 // Scroll offsets keep the point under the mouse stationary while zooming.
 function zoomViewport(current,factor,anchor,scroll){
  const scale=Math.max(.5,Math.min(4,current*factor)),ratio=scale/current;
  return {scale,left:Math.max(0,(scroll.left+anchor.x)*ratio-anchor.x),top:Math.max(0,(scroll.top+anchor.y)*ratio-anchor.y)};
 }
 function funnelZoom(box,image,onChange=()=>{}){
  let active=false,wheelZoom=false,scale=1,baseWidth=0,drag=null,suppressClick=false;
  function apply(){image.style.width=baseWidth*scale+'px';image.style.minWidth='0';image.style.maxWidth='none';onChange(scale);}
  function zoomBy(factor,anchor={x:box.clientWidth/2,y:box.clientHeight/2}){
   if(!active)return;
   const next=zoomViewport(scale,factor,anchor,{left:box.scrollLeft,top:box.scrollTop});scale=next.scale;apply();box.scrollLeft=next.left;box.scrollTop=next.top;
  }
  function reset(){scale=1;if(active){const view=image.viewBox.baseVal;baseWidth=Math.min(box.clientWidth,box.clientHeight*view.width/view.height);apply();}box.scrollLeft=0;box.scrollTop=0;}
  function setActive(value){active=value;drag=null;box.classList.remove('acDragging');if(active)reset();else{scale=1;for(const key of ['width','minWidth','maxWidth'])image.style[key]='';onChange(scale);}}
  // Chromium exposes trackpad pinch as ctrl+wheel. Ordinary two-finger scroll
  // stays native, including horizontal movement and momentum.
  box.addEventListener('wheel',e=>{if(!active||!(e.ctrlKey||e.metaKey||wheelZoom))return;e.preventDefault();const r=box.getBoundingClientRect(),delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?box.clientHeight:1);zoomBy(Math.exp(-Math.max(-200,Math.min(200,delta))*.002),{x:e.clientX-r.left,y:e.clientY-r.top});},{passive:false});
  box.addEventListener('pointerdown',e=>{if(!active||e.button!==0||e.pointerType==='touch')return;suppressClick=false;drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:box.scrollLeft,top:box.scrollTop,moved:false};});
  box.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(!drag.moved&&Math.hypot(dx,dy)<6)return;drag.moved=true;suppressClick=true;box.classList.add('acDragging');box.setPointerCapture(e.pointerId);box.scrollLeft=drag.left-dx;box.scrollTop=drag.top-dy;});
  function release(e){if(!drag||e.pointerId!==drag.id)return;if(box.hasPointerCapture(e.pointerId))box.releasePointerCapture(e.pointerId);drag=null;box.classList.remove('acDragging');}
  box.addEventListener('pointerup',release);box.addEventListener('pointercancel',release);
  box.addEventListener('click',e=>{if(suppressClick){e.preventDefault();e.stopImmediatePropagation();suppressClick=false;}},true);
  return {zoomBy,reset,setActive,setWheelZoom:value=>{wheelZoom=!!value;}};
 }
 const api={stageLabels,categoryColors,filters,funnel,evolution,opportunityMap,mapViewport,exportGeometry,zoomViewport,funnelZoom};root.CareerCharts=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
