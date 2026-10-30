import test from 'node:test';
import assert from 'node:assert/strict';
import {trailTokens,trailRing,writeTrailSample,anchorTrailHeads,playbackInteraction} from '../../src/introTrails.js';

test('every trail follows a real token and its head stays attached between history samples',()=>{
 const tokens=trailTokens(new Uint16Array([0,1,0,1,2]),3);
 assert.deepEqual([...tokens],[0,1,4]);
 const positions=new Float32Array([1,2,3,4,5,6,100,100,100,200,200,200,7,8,9]);
 const history=4,{vertices}=trailRing(3,history),out=new Float32Array(vertices*3);
 const live=anchorTrailHeads(out,positions,tokens,history);
 assert.equal(live,history*2+1);
 assert.deepEqual([...out.slice(live*9,live*9+9)],[1,2,3,4,5,6,7,8,9]);
 positions[0]=12;anchorTrailHeads(out,positions,tokens,history);
 assert.equal(out[live*9],12);
});

test('a history sample is written once into its ring slot and joins both neighbouring segments',()=>{
 const history=4,trails=2,{segment,end,index,vertices}=trailRing(trails,history);
 assert.equal(vertices,(history*2+2)*trails);
 assert.equal(index.length,(history+1)*trails*2);
 const positions=new Float32Array([1,2,3,4,5,6]),out=new Float32Array(vertices*3);
 const blocks=writeTrailSample(out,positions,new Int32Array([0,1]),history,0);
 // Slot 0 starts segment 0, ends the wrapping segment 3, and starts the live segment.
 assert.deepEqual(blocks,[0,7,8]);
 for(const b of blocks)assert.deepEqual([...out.slice(b*6,b*6+6)],[1,2,3,4,5,6]);
 assert.deepEqual([segment[0],end[0],segment[7*trails],end[7*trails],segment[8*trails]],[0,0,3,1,-1]);
 // Each index pair connects the two ends of the same segment for the same trail.
 for(let n=0;n<index.length;n+=2){
  assert.equal(segment[index[n]],segment[index[n+1]]);
  assert.deepEqual([end[index[n]],end[index[n+1]]],[0,1]);
  assert.equal(index[n]%trails,index[n+1]%trails);
 }
});

test('playback allows motion and swipes without perpetual stationary hover or excessive fall impulses',()=>{
 assert.equal(playbackInteraction(0,0,true,0),0);
 assert.ok(playbackInteraction(2,0,true,0)>0);
 assert.ok(playbackInteraction(0,1,true,0)>0);
 assert.ok(playbackInteraction(10,2,true,1)>0);
 assert.ok(playbackInteraction(10,2,true,1)<playbackInteraction(10,2,true,0));
 assert.equal(playbackInteraction(0,0,false,0),1);
});
