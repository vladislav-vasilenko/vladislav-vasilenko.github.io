import test from 'node:test';
import assert from 'node:assert/strict';
import {biologySequence, createMoleculeClouds, moleculePoint, molecules, MOLECULE_ORDER} from '../../src/molecularFields.js';

test('DNA opens for seven seconds, then four molecules repeat without returning to DNA', () => {
  assert.equal(biologySequence({}, 6.99).id,'dna');
  for (let lap=0;lap<20;lap++) for(let n=0;n<4;n++) {
    const state=biologySequence({},7+(lap*4+n)*7);
    assert.equal(state.id,MOLECULE_ORDER[n]);
    assert.equal(state.previous,lap===0&&n===0?'dna':MOLECULE_ORDER[(n+3)%4]);
    assert.equal(state.mix,0);
    assert.equal(biologySequence({},8.7+(lap*4+n)*7).mix,1);
  }
});

test('the stored molecular graphs preserve composition, ring count and the oxytocin sulfur bridge', () => {
  const expected={dopamine:[8,1,2,0,1],serotonin:[10,2,1,0,2],oxytocin:[43,12,12,2,3],adrenaline:[9,1,3,0,1]};
  for (const [id,molecule] of Object.entries(molecules)) {
    const count=element=>molecule.atoms.filter(a=>a[0]===element).length;
    assert.deepEqual(['C','N','O','S'].map(count),expected[id].slice(0,4));
    assert.equal(molecule.bonds.length-molecule.atoms.length+1,expected[id][4]);
    const visited=new Set([0]);
    for(let pass=0;pass<molecule.atoms.length;pass++) for(const [a,b] of molecule.bonds){
      if(visited.has(a))visited.add(b);if(visited.has(b))visited.add(a);
      assert.ok(molecule.atoms[a]&&molecule.atoms[b]);
      const distance=Math.hypot(...molecule.atoms[a].slice(1).map((v,i)=>v-molecule.atoms[b][i+1]));
      assert.ok(distance>.9&&distance<2.2,`${id}: implausible covalent bond ${distance}`);
    }
    assert.equal(visited.size,molecule.atoms.length,'one connected molecule');
  }
  assert.equal(molecules.oxytocin.bonds.filter(([a,b])=>molecules.oxytocin.atoms[a][0]==='S'&&molecules.oxytocin.atoms[b][0]==='S').length,1);
});

test('molecules reuse all 1200 targets, with a sparse structure and spare cubes waiting outside', () => {
  const clouds=createMoleculeClouds();
  for (const cloud of Object.values(clouds)) {
    assert.equal(cloud.points.length,3600);
    for (const view of [{halfWidth:1.95,halfHeight:4.22},{halfWidth:7.5,halfHeight:4.2}]) {
      for(let i=0;i<1200;i++)for(const time of [0,14,80]) {
        const p=moleculePoint({},i,cloud,view,time);
        assert.ok(Number.isFinite(p.x+p.y+p.z+p.scale+p.r+p.g+p.b));
        if (i < cloud.activeCount) {
          assert.ok(Math.abs(p.x)<view.halfWidth*.99,'keep the ring skeleton in the viewport');
          assert.ok(p.y>view.halfHeight*.05&&p.y<view.halfHeight*.95,'the molecule has its own upper exhibition area');
        } else {
          assert.ok(Math.hypot(p.x/view.halfWidth,p.y/view.halfHeight)>.9,'eccentric spares stay outside the structure');
        }
        assert.ok(p.scale>0&&p.scale<1.1);
      }
    }
  }
  assert.ok(clouds.dopamine.activeCount<=250);
  assert.ok(clouds.serotonin.activeCount<=250);
  assert.ok(clouds.adrenaline.activeCount<=250);
  assert.ok(clouds.oxytocin.activeCount>=1000);
});

test('spare cubes have different phases, eccentricities and variable orbital speed',()=>{
 const cloud=createMoleculeClouds().dopamine,view={halfWidth:2,halfHeight:4};
 const speeds=[];
 for(let i=300;i<360;i++){
  const a=moleculePoint({},i,cloud,view,2),b=moleculePoint({},i,cloud,view,2.1);
  speeds.push(Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z));
 }
 assert.ok(Math.max(...speeds)>Math.min(...speeds)*2);
 assert.ok(new Set(speeds.map(v=>v.toFixed(3))).size>20,'no synchronized concentric bands');
});

test('a molecule rotates around its own axis without losing its covalent geometry',()=>{
 const cloud=createMoleculeClouds().oxytocin,view={halfWidth:4.5,halfHeight:4};
 const a=moleculePoint({},1,cloud,view,0),b=moleculePoint({},120,cloud,view,0);
 const laterA=moleculePoint({},1,cloud,view,4),laterB=moleculePoint({},120,cloud,view,4);
 assert.ok(Math.hypot(a.x-laterA.x,a.y-laterA.y,a.z-laterA.z)>.1);
 const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z);
 assert.ok(Math.abs(distance(a,b)/distance(laterA,laterB)-1)<.04,'rotation and gentle breathing preserve the structure');
});
