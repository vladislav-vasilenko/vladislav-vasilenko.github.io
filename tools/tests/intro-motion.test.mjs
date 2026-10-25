import test from 'node:test';
import assert from 'node:assert/strict';
import { floorImpact, handoffToken, impactFloor, resumeClip } from '../../src/introMotion.js';

const view = { halfWidth: 6, halfHeight: 3.5, safeLeft: -3, safeRight: 3 };
const origin = i => [(i % 30 - 14.5) * .11, (19.5 - Math.floor(i / 30)) * .11, .2];

test('handoff leaves the formed portrait unchanged at the start and is reversible', () => {
  for (let i = 0; i < 1200; i++) {
    const xyz = origin(i), out = {};
    handoffToken(out, i, 1, ...xyz, view);
    assert.equal(out.scale, 0);
    handoffToken(out, i, 0, ...xyz, view);
    assert.deepEqual(out, { x: xyz[0], y: xyz[1], z: xyz[2], scale: 1 });
  }
});

test('by header arrival only a small, shrunken set of tokens remains, all outside the reading column', () => {
  for (const geometry of [view, { halfWidth: 1.8, halfHeight: 3.5, safeLeft: -1.8, safeRight: 1.8 }]) {
    let visible = 0;
    for (let i = 0; i < 1200; i++) {
      const token = handoffToken({}, i, .65, ...origin(i), geometry);
      if (token.scale <= 0) continue;
      visible++;
      assert.ok(token.scale <= .3);
      assert.ok(token.x < geometry.safeLeft || token.x > geometry.safeRight);
    }
    assert.ok(visible > 0 && visible <= 16);
  }
});

function inside(polygon, x, y) {
  const pairs = [...polygon.matchAll(/(-?[\d.]+)px (-?[\d.]+)px/g)].map(match => [Number(match[1]), Number(match[2])]);
  let result = false;
  for (let i = 0, j = pairs.length - 1; i < pairs.length; j = i++) {
    const [xi, yi] = pairs[i], [xj, yj] = pairs[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) result = !result;
  }
  return result;
}

test('the overlay masks the resume text even when fast scrolling outruns particle motion', () => {
  const desktop = resumeClip({ left: 250, right: 1090, top: 240 }, 1440, 900);
  assert.equal(inside(desktop, 720, 500), false);
  assert.equal(inside(desktop, 100, 500), true);
  assert.equal(inside(desktop, 720, 100), true);
  const phone = resumeClip({ left: 0, right: 390, top: -100 }, 390, 844);
  assert.equal(inside(phone, 195, 400), false);
  const beforeResume = resumeClip({ left: 250, right: 1090, top: 1400 }, 1440, 900);
  assert.equal(inside(beforeResume, 720, 500), true);
});

test('mobile impacts stay above the controls, including the taller playback panel', () => {
  for (const height of [667, 844]) {
    for (const panelHeight of [118, 164]) {
      const controlsTop = height - 16 - panelHeight;
      const floor = impactFloor(3.5, height, controlsTop);
      const screenY = (1 - floor / 3.5) * height / 2;
      assert.ok(screenY <= controlsTop - 39.99);
      assert.ok(screenY > height / 2);
    }
  }
  assert.equal(impactFloor(3.5, 900), -3.5 * .74);
});

test('floor contact rebounds a falling cube and gives only its first impact an outward kick', () => {
  const velocity = new Float32Array([0, -6, 0]), spin = new Float32Array(3);
  floorImpact(velocity, spin, 0, -1, true);
  assert.ok(velocity[0] < 0 && velocity[1] > 0 && velocity[1] < 6);
  assert.ok(spin[2] < 0);
  const sideways = velocity[0];
  velocity[1] = -2;
  floorImpact(velocity, spin, 0, -1, false);
  assert.equal(velocity[0], sideways);
  assert.ok(velocity[1] > 0 && velocity[1] < 2);
});
