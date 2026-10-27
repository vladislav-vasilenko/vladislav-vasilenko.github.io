import test from 'node:test';
import assert from 'node:assert/strict';
import {patchSignal,ATTENTION_PERIOD} from '../../src/introAttention.js';
import {resetIntroPlayback,reportPlaybackFrame,waitForPlayback} from '../../src/introPlayback.js';
import {vortexCubeScale} from '../../src/introTextFragments.js';

test('the funnel equalizes every cube smoothly, then restores the portrait scale after the burst',()=>{
 for(const size of [.1,.4,1,1.8]) {
  assert.equal(vortexCubeScale(size,0),size);
  assert.ok(Math.abs(vortexCubeScale(size,1)-.85)<1e-8);
  assert.ok(Math.abs(vortexCubeScale(size,4.8)-.85)<1e-8);
  assert.equal(vortexCubeScale(size,6),size);
 }
});

test('noisy-cloud patch signals are coherent within a patch, phase-shifted and smoothly bounded',()=>{
  assert.ok(ATTENTION_PERIOD>=3);
  let maxStep=0, last=0;
  for(let frame=0;frame<600;frame++){
    const now=patchSignal([],4,frame/60,1);
    assert.deepEqual(now,patchSignal([],4,frame/60,1));
    assert.notDeepEqual(now,patchSignal([],5,frame/60,1));
    assert.ok(now.every(v=>v>=0&&v<=.34));
    maxStep=Math.max(maxStep,Math.abs(now[0]-last));last=now[0];
  }
  assert.ok(maxStep<.035,'no abrupt flashing');
  assert.deepEqual(patchSignal([],3,1,0),[0,0,0]);
  assert.deepEqual(patchSignal([],3,1,1,1),[0,0,0]);
});

test('a completed portrait keeps the normal hold without prolonging colored attention',()=>{
  const playback=resetIntroPlayback({},true);playback.supernova=true;
  let ready=0;waitForPlayback(playback,'portrait',()=>ready++);
  reportPlaybackFrame(playback,{dt:1/60,formed:false,total:1200});
  assert.equal(playback.communicating,true);
  for(let i=0;i<30;i++)reportPlaybackFrame(playback,{dt:1/60,formed:true,total:1200});
  assert.equal(ready,1);
  assert.equal(playback.communicating,false);
  resetIntroPlayback(playback);assert.equal(playback.supernova,false);
});
