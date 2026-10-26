import test from 'node:test';
import assert from 'node:assert/strict';
import {chooseVisitOrbit} from '../../src/introOrbitChoice.js';
import {seedTextFragments,captureIntroText,textVortex,swarmVortex,vortexTurn,vortexStrength,fireSupernova} from '../../src/introTextFragments.js';
import {resetIntroPlayback,waitForPlayback,reportPlaybackFrame} from '../../src/introPlayback.js';

test('a reload picks another orbit, while blocked storage still yields a valid scene',()=>{
 let previous=null;
 const storage={getItem:()=>previous,setItem:(_,value)=>{previous=value;}};
 const modes=new Set();
 for(const random of [0,0,.99,0,.99]){
  const last=previous;
  const mode=chooseVisitOrbit(()=>storage,()=>random);
  assert.notEqual(mode,last);assert.ok(['binary','galaxy','dna'].includes(mode));modes.add(mode);
 }
 assert.equal(modes.size,3);
 assert.equal(chooseVisitOrbit(()=>{throw Error('blocked');},()=>.99),'dna');
 assert.equal(chooseVisitOrbit(()=>({getItem:()=> 'unknown',setItem(){throw Error('full');}}),()=>0),'binary');
});

test('lettering fragments reuse unique portrait instances and preserve every portrait target',()=>{
 const n=1200;
 const sim={scale:new Float32Array(n),pos:new Float32Array(n*3),vel:new Float32Array(n*3),rot:new Float32Array(n*3),spin:new Float32Array(n*3),target:new Float32Array(n*3).fill(.5),textMask:new Uint8Array(n)};
 const before=sim.target.slice();
 const burst={width:400,height:800,points:Array.from({length:600},(_,i)=>({x:100+i/6,y:200}))};
 seedTextFragments(sim,burst,4);
 assert.equal(sim.textMask.reduce((a,b)=>a+b,0),600);
 assert.equal(sim.pos[0],-1);assert.equal(sim.pos[1],2);assert.equal(sim.pos[2],0);
 assert.deepEqual(sim.target,before);assert.equal(sim.textBurst,burst);
 assert.ok(sim.vel.every(Number.isFinite));
 assert.equal(captureIntroText({querySelectorAll(){throw Error('no canvas');}}),null);
});

test('the text burst waits for rendered frames before scrolling and cancellation resets it',()=>{
 const playback=resetIntroPlayback({},true);playback.textBurst={points:[{x:1,y:1}]};
 let ready=0;waitForPlayback(playback,'text',()=>ready++);
 for(let i=0;i<30;i++)reportPlaybackFrame(playback,{dt:1/30,formed:false,total:1200});
 assert.equal(ready,0,'a hidden or unavailable canvas cannot skip the effect');
 for(let i=0;i<100;i++)reportPlaybackFrame(playback,{dt:1/30,formed:false,total:1200,textActive:true});
 assert.equal(ready,1);assert.equal(playback.textReady,true);
 resetIntroPlayback(playback);assert.equal(playback.textBurst,null);assert.equal(playback.onTextStart,null);assert.equal(playback.textReady,false);
});


test('the text whirlpool turns clockwise, draws inward, has depth, and decays before the portrait locks',()=>{
 const p=textVortex({},1,0,0,0,{x:0,y:0});
 assert.ok(p.vx<0);assert.ok(p.vy<0);assert.ok(p.strength>0);
 for(const age of [0,.5,1.5,4.5,10]){
  const flow=textVortex({},0,0,0,age,{x:0,y:2});
  assert.ok(Object.values(flow).every(Number.isFinite));
 }
 assert.notEqual(textVortex({},1,1,0,.5,{x:0,y:2}).vz,0);
 assert.equal(textVortex({},1,1,0,6,{x:0,y:2}).strength,0);
});


test('the main cube vortex rotates in depth and contracts before portrait assembly',()=>{
 const view={halfWidth:3,halfHeight:4};
 const first=swarmVortex({},19,view,0),later=swarmVortex({},19,view,3.7);
 assert.ok(Math.hypot(later.x,later.y/.55)<Math.hypot(first.x,first.y/.55));
 assert.notEqual(swarmVortex({},19,view,.3).z,first.z);
});


test('the main vortex accelerates from rest smoothly and fades before resume reading',()=>{
 const first=vortexTurn(.1)-vortexTurn(0);
 const middle=vortexTurn(1.1)-vortexTurn(1);
 const cruise=vortexTurn(3.1)-vortexTurn(3);
 assert.ok(first<middle&&middle<cruise);
 assert.ok(Math.abs(cruise-.3)<1e-8);
 assert.equal(vortexStrength(0),0);assert.equal(vortexStrength(6),0);assert.ok(vortexStrength(1)>.99);
});


test('supernova adds outward momentum to the main cubes without changing portrait destinations',()=>{
 const sim={scale:new Float32Array(1200),pos:new Float32Array(3600).fill(.1),vel:new Float32Array(3600),spin:new Float32Array(3600),target:new Float32Array(3600).fill(.4)};
 const before=sim.target.slice();fireSupernova(sim);
 assert.deepEqual(sim.target,before);assert.ok(sim.vel.every(Number.isFinite));
 assert.ok(sim.vel.some(v=>v>1)&&sim.vel.some(v=>v<0));
});

test('glyph suction shares the main disk plane rather than creating a perpendicular screen vortex',()=>{
 const flow=textVortex({},1,.55,.83,2,{x:0,y:0});
 assert.ok(Math.abs(-flow.vy*.83+flow.vz*.55)<1e-8);
});
