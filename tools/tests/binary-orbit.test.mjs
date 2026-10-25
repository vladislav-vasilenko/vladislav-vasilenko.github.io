import test from 'node:test';
import assert from 'node:assert/strict';
import { asteroidEntrance, binaryOrbit, binaryOrbitLayout } from '../../src/binaryOrbit.js';

const views = [
  {width: 1440, height: 900, halfWidth: 4.64, halfHeight: 2.9, cameraZ: 8},
  {width: 390, height: 844, halfWidth: 1.95, halfHeight: 4.22, cameraZ: 11.6},
  {width: 320, height: 667, halfWidth: 1.95, halfHeight: 4.06, cameraZ: 11.2},
];

test('the entrance starts outside both side edges and flies inward and downward', () => {
  for (const view of views) {
    for (let patch = 0; patch < 80; patch++) {
      const p = asteroidEntrance({}, patch * 16, patch, view);
      assert.ok(Math.abs(p.x) > view.halfWidth);
      assert.ok(p.x * p.vx < 0 && p.vy < 0 && p.y > view.halfHeight * .69);
      assert.ok(Math.abs(p.spinX) > 2 && Math.abs(p.spinZ) >= 3);
    }
  }
});

test('the gravity centres follow the measured controls instead of drifting with the orbits', () => {
  const view = views[0];
  const main = {x: 440, y: 410, width: 500, height: 200};
  const links = {x: 1110, y: 450, width: 300, height: 100};
  const layout = binaryOrbitLayout({}, view, {main, links});
  const units = view.halfHeight * 2 / view.height;
  assert.equal(layout.mainX, (440 - 720) * units);
  assert.equal(layout.linksX, (1110 - 720) * units);
  assert.ok(layout.major > layout.minor);
});

test('local asteroids travel clockwise around both invisible centres', () => {
  for (const view of views) {
    const layout = binaryOrbitLayout({}, view);
    for (const patch of [0, 5]) {
      const a = binaryOrbit({}, 0, patch, layout, 0);
      const b = binaryOrbit({}, 0, patch, layout, .1);
      const cx = patch === 0 ? layout.mainX : layout.linksX;
      const cy = patch === 0 ? layout.mainY : layout.linksY;
      assert.ok((a.x - cx) * (b.y - cy) - (a.y - cy) * (b.x - cx) < 0);
    }
  }
});

test('the transfer stream visits both wells and crosses between them in depth', () => {
  for (const view of views) {
    const layout = binaryOrbitLayout({}, view);
    let major = false, minor = false, near = false, far = false;
    for (let t = 0; t < 100; t += .25) {
      const p = binaryOrbit({}, 0, 7, layout, t);
      const side = (p.x - layout.bridgeX) * layout.ux + (p.y - layout.bridgeY) * layout.uy;
      major ||= side < -layout.major * .7;
      minor ||= side > layout.minor * .7;
      near ||= p.z > .5;
      far ||= p.z < -.5;
      assert.ok(Number.isFinite(p.x + p.y + p.z));
      assert.ok(p.z < view.cameraZ * .55 && p.scale > 0 && p.scale < 2.5);
    }
    assert.ok(major && minor && near && far);
  }
});

test('the orbital plane is viewed at 30 degrees and foreground passes increase apparent size', () => {
  const layout = binaryOrbitLayout({}, views[0]);
  const p = binaryOrbit({}, 0, 0, layout, 1);
  const across = (p.x - layout.mainX) * layout.px + (p.y - layout.mainY) * layout.py;
  assert.ok(Math.abs((p.z + .1) / across - Math.sqrt(3)) < 1e-8);
  const near = Array.from({length: 100}, (_, t) => binaryOrbit({}, 0, 0, layout, t)).find(p => p.z > .5);
  const far = Array.from({length: 100}, (_, t) => binaryOrbit({}, 0, 0, layout, t)).find(p => p.z < -.5);
  assert.ok(near && far && near.scale > far.scale);
});
