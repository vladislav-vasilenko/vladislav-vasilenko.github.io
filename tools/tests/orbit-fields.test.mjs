import test from 'node:test';
import assert from 'node:assert/strict';
import {binaryOrbit,binaryOrbitLayout} from '../../src/binaryOrbit.js';
import {orbitPoint} from '../../src/orbitFields.js';
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


test('DNA backbones pair at the same height and its crossbars meet both strands',()=>{
 for(const row of [0,30,60,119]){
  const a=orbitPoint({},row*10,0,layout,0,'dna');
  const b=orbitPoint({},row*10+1,0,layout,0,'dna');
  assert.equal(a.y,b.y);assert.ok(a.x*b.x<=0);
 }
 const rungs=[];
 for(let i=0;i<1200;i++)if(i%10>=6)rungs.push(orbitPoint({},i,0,layout,0,'dna'));
 assert.equal(new Set(rungs.map(p=>p.y)).size,24);
});


test('DNA rotates at the requested doubled rate without changing its vertical structure',()=>{
 const before=orbitPoint({},100,0,layout,0,'dna'),after=orbitPoint({},100,0,layout,1,'dna');
 assert.equal(before.y,after.y);
 const angle=Math.atan2(after.z,after.x)-Math.atan2(before.z,before.x);
 assert.ok(Math.abs(Math.abs(angle)-.28)<1e-8);
});
