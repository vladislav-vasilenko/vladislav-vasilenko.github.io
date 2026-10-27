import test from 'node:test';
import assert from 'node:assert/strict';
import {astronomySequence,astronomyPoint,galaxyPoint,initialAccretion,ACCRETION_SECONDS} from '../../src/cosmicFields.js';
import {plasmaPoint,PLASMA_SECONDS} from '../../src/supernovaPlasma.js';
const view={halfWidth:2,halfHeight:4.2,cameraZ:11.6};

test('the solar entrance starts beyond the screen and contracts through a rotating funnel',()=>{
 for(let i=0;i<1200;i++){
  const a=initialAccretion({},i,view,0),b=initialAccretion({},i,view,ACCRETION_SECONDS);
  assert.ok(Math.abs(a.x)>view.halfWidth||Math.abs(a.y)>view.halfHeight,'initially outside the viewport');
  const radius=p=>Math.hypot(p.x/view.halfWidth,(p.y-view.halfHeight*.34)/(view.halfHeight*.72));
  assert.ok(radius(b)<radius(a)*.1);
 }
 const a=initialAccretion({},0,view,1),b=initialAccretion({},0,view,2);
 assert.notEqual(Math.atan2(a.y-view.halfHeight*.34,a.x).toFixed(2),Math.atan2(b.y-view.halfHeight*.34,b.x).toFixed(2));
});

test('the cosmic visit holds the solar system for 14s, Saturn for 7s and the galaxy for 21s',()=>{
 for(const [time,id] of [[0,'solar'],[13.99,'solar'],[14,'saturn'],[20.99,'saturn'],[21,'galaxy'],[41.99,'galaxy'],[42,'solar'],[56,'saturn']]){
  const state=astronomySequence({},time);assert.equal(state.id,id);
 }
 assert.equal(astronomySequence({},14).mix,0);
 assert.equal(astronomySequence({},15.7).mix,1);
 assert.equal(astronomySequence({},42).mix,0);
});

test('all 1200 cubes have finite moving targets in all three astronomical structures',()=>{
 for(const id of ['solar','saturn','galaxy'])for(let i=0;i<1200;i++)for(const t of [0,7,24]){
  const p=astronomyPoint({},i,view,t,id);
  assert.ok(Number.isFinite(p.x+p.y+p.z+p.scale+p.r+p.g+p.b+p.glow));
  assert.ok(p.scale>0&&p.scale<2);
  assert.ok(p.z<view.cameraZ*.6);
 }
 const a=astronomyPoint({},250,view,0,'solar'),b=astronomyPoint({},250,view,2,'solar');
 assert.ok(Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)>.05,'the planets orbit');
 const moon=astronomyPoint({},1100,view,0,'saturn'),later=astronomyPoint({},1100,view,2,'saturn');
 assert.ok(Math.hypot(moon.x-later.x,moon.y-later.y,moon.z-later.z)>.05,'the moons orbit');
});

test('galactic stars are fine-grained, irregularly dispersed and have multiple spectral colors',()=>{
 const colors=new Set(),angles=new Set();
 for(let i=0;i<1200;i++){
  const p=galaxyPoint({},i,view,0);
  assert.ok(p.scale<=.4,'avoid thick cube ropes');
  colors.add([p.r,p.g,p.b].join(','));angles.add(Math.atan2(p.y-view.halfHeight*.34,p.x).toFixed(2));
 }
 assert.ok(colors.size>100);assert.ok(angles.size>200);
});

test('supernova plasma expands in a shell and opposing jets, then fully dissipates',()=>{
 for(let i=0;i<192;i++){
  const early=plasmaPoint({},i,.2),late=plasmaPoint({},i,1.8);
  assert.ok(Math.hypot(late.x,late.y,late.z)>Math.hypot(early.x,early.y,early.z));
  assert.ok(late.alpha<early.alpha);
  assert.equal(plasmaPoint({},i,PLASMA_SECONDS).alpha,0);
 }
 assert.ok(plasmaPoint({},0,1).y<0&&plasmaPoint({},4,1).y>0);
});
