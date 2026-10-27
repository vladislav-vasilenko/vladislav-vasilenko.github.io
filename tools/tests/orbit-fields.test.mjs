import test from 'node:test';
import assert from 'node:assert/strict';
import {binaryOrbit,binaryOrbitLayout} from '../../src/binaryOrbit.js';
import {orbitPoint,DNA_FRAME} from '../../src/orbitFields.js';
const layout=binaryOrbitLayout({}, {width:390,height:844,halfWidth:1.95,halfHeight:4.22,cameraZ:11.6});
test('Binary remains the default, including unknown orbit choices', () => {
 const expected=binaryOrbit({},5,7,layout,3);
 assert.deepEqual(orbitPoint({},5,7,layout,3,'binary'),expected);
 assert.deepEqual(orbitPoint({},5,7,layout,3,'unknown'),expected);
});
test('Galaxy and DNA produce distinct finite, rotating 3D fields within camera depth', () => {
 for(const mode of ['galaxy','dna']) {
  let near=false,far=false;
  for(let i=0;i<1200;i++){
   const patch=Math.floor(i/16)%80;
   const p=orbitPoint({},i,patch,layout,0,mode),later=orbitPoint({},i,patch,layout,4,mode);
   assert.ok(Number.isFinite(p.x+p.y+p.z+p.scale));assert.ok(p.z<layout.cameraZ*.6);
   near ||= p.z>.4;far ||=p.z<-.4;
   assert.ok(Math.abs(p.x-later.x)+Math.abs(p.z-later.z)>.00001);
  }
  assert.ok(near&&far);
 }
 assert.notDeepEqual(orbitPoint({},8,7,layout,2,'galaxy'),orbitPoint({},8,7,layout,2,'dna'));
});


test('DNA has a diagonal receding axis and 24 crossbars between opposite backbones',()=>{
 const project=(p,v)=>p.x*v[0]+p.y*v[1]+p.z*v[2];
 const axis=p=>project(p,DNA_FRAME.axis);
 for(const row of [0,30,60,119]){
  const a=orbitPoint({},row*10,0,layout,0,'dna');
  const b=orbitPoint({},row*10+1,0,layout,0,'dna');
  assert.ok(Math.abs(axis(a)-axis(b))<.001);
 }
 const rungs=[];
 for(let i=0;i<1200;i++)if(i%10>=6)rungs.push(axis(orbitPoint({},i,0,layout,0,'dna')).toFixed(2));
 assert.equal(new Set(rungs).size,24);
 const near=orbitPoint({},0,0,layout,0,'dna'),far=orbitPoint({},1191,0,layout,0,'dna');
 assert.ok(near.x<far.x&&near.y<far.y&&near.z>far.z);
});


test('DNA rotates at the requested doubled rate around its tilted axis',()=>{
 const radial=time=>{
  const a=orbitPoint({},100,0,layout,time,'dna'),b=orbitPoint({},101,0,layout,time,'dna');
  return {x:a.x-b.x,y:a.y-b.y,z:a.z-b.z};
 };
 const before=radial(0),after=radial(1);
 const project=(p,v)=>p.x*v[0]+p.y*v[1]+p.z*v[2];
 const angle=p=>Math.atan2(project(p,DNA_FRAME.depth),project(p,DNA_FRAME.across));
 assert.ok(Math.abs(Math.abs(angle(after)-angle(before))-.28)<.001);
});
