import test from 'node:test';
import assert from 'node:assert/strict';
import {trailTokens,anchorTrailHeads,playbackInteraction} from '../../src/introTrails.js';

test('every trail follows a real token and its head stays attached between history samples',()=>{
 const tokens=trailTokens(new Uint16Array([0,1,0,1,2]),3);
 assert.deepEqual([...tokens],[0,1,4]);
 const positions=new Float32Array([1,2,3,4,5,6,100,100,100,200,200,200,7,8,9]);
 const out=new Float32Array(3*3*6);
 anchorTrailHeads(out,positions,tokens,4);
 assert.deepEqual([...out.slice(15,18)],[1,2,3]);
 assert.deepEqual([...out.slice(33,36)],[4,5,6]);
 positions[0]=12;anchorTrailHeads(out,positions,tokens,4);
 assert.equal(out[15],12);assert.deepEqual([...out.slice(51,54)],[7,8,9]);
});

test('playback allows motion and swipes without perpetual stationary hover or excessive fall impulses',()=>{
 assert.equal(playbackInteraction(0,0,true,0),0);
 assert.ok(playbackInteraction(2,0,true,0)>0);
 assert.ok(playbackInteraction(0,1,true,0)>0);
 assert.ok(playbackInteraction(10,2,true,1)>0);
 assert.ok(playbackInteraction(10,2,true,1)<playbackInteraction(10,2,true,0));
 assert.equal(playbackInteraction(0,0,false,0),1);
});
