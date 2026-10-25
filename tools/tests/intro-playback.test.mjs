import test from 'node:test';
import assert from 'node:assert/strict';
import { resetIntroPlayback, reportPlaybackFrame, waitForPlayback } from '../../src/introPlayback.js';
import { collideWithFloor } from '../../src/introMotion.js';

test('a long approach timeout cannot release a portrait that has not actually formed', () => {
  const playback = resetIntroPlayback({}, true);
  let released = 0;
  waitForPlayback(playback, 'portrait', () => released++);
  for (let i = 0; i < 300; i++) reportPlaybackFrame(playback, {dt: 1 / 30, formed: false, total: 1200});
  assert.equal(released, 0);
  for (let i = 0; i < 12; i++) reportPlaybackFrame(playback, {dt: 1 / 30, formed: true, total: 1200});
  assert.equal(released, 1);
});

test('resume handover waits for real contacts and rendered rebounds at 10, 15, 30 and 60 FPS', () => {
  for (const fps of [10, 15, 30, 60]) {
    const playback = resetIntroPlayback({}, true);
    playback.releasing = true;
    let handovers = 0;
    waitForPlayback(playback, 'drop', () => handovers++);
    for (let i = 0; i < fps * 3; i++) reportPlaybackFrame(playback, {dt: 1 / fps, impacts: 0, total: 1200});
    assert.equal(handovers, 0, 'wall-clock time without collisions must never hide the cubes');
    reportPlaybackFrame(playback, {dt: .1, impacts: 120, total: 1200});
    for (let i = 1; i < 8; i++) {
      assert.equal(handovers, 0, 'at least eight rebound frames must render');
      reportPlaybackFrame(playback, {dt: 1 / fps, total: 1200});
    }
    for (let i = 0; i < fps; i++) reportPlaybackFrame(playback, {dt: 1 / fps, total: 1200});
    assert.equal(handovers, 1);
  }
});

test('initial penetration, a large frame step and a raised floor cannot skip collisions', () => {
  const sim = {
    pos: new Float32Array([-1, -3, 0, 1, -5, 0]),
    vel: new Float32Array([0, -4, 0, 0, -6, 0]),
    spin: new Float32Array(6), floorContact: new Uint8Array(2),
  };
  assert.equal(collideWithFloor(sim, -2, .05), 2);
  assert.ok(sim.pos[1] >= -1.951 && sim.pos[4] >= -1.951);
  assert.ok(sim.vel[1] > 0 && sim.vel[4] > 0);
  assert.ok(sim.vel[0] < 0 && sim.vel[3] > 0);
  const outward = sim.vel[0];
  assert.equal(collideWithFloor(sim, -1.8, .05), 0, 'resizing must not count old contacts again');
  assert.equal(sim.vel[0], outward, 'resizing must not inject another outward impulse');
});

test('a pile standing on a few bottom cubes can finish without every cube touching the plane', () => {
  const playback = resetIntroPlayback({}, true);
  playback.releasing = true;
  let handovers = 0;
  waitForPlayback(playback, 'drop', () => handovers++);
  reportPlaybackFrame(playback, {dt: 1 / 30, impacts: 30, total: 1200});
  for (let i = 0; i < 30; i++) reportPlaybackFrame(playback, {dt: 1 / 30, impacts: 0, total: 1200});
  assert.equal(handovers, 1);
});

test('stopping playback cancels pending handover, and a new run has fresh collision state', () => {
  const playback = resetIntroPlayback({}, true);
  playback.releasing = true;
  let handovers = 0;
  waitForPlayback(playback, 'drop', () => handovers++);
  resetIntroPlayback(playback);
  for (let i = 0; i < 120; i++) reportPlaybackFrame(playback, {dt: 1 / 30, impacts: 1200, total: 1200});
  assert.equal(handovers, 0);
  resetIntroPlayback(playback, true);
  assert.equal(playback.impacts, 0);
  assert.equal(playback.bounceFrames, 0);
  assert.equal(playback.floor, null);
});
