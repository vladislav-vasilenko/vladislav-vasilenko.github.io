import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {swipeIntent} from '../../src/introPointer.js';

test('gesture direction locks after the tap threshold and ambiguous diagonals favor scrolling', () => {
  assert.equal(swipeIntent(4, 3), 'pending');
  assert.equal(swipeIntent(35, 4), 'horizontal');
  assert.equal(swipeIntent(-35, 4), 'horizontal');
  assert.equal(swipeIntent(4, 35), 'vertical');
  assert.equal(swipeIntent(12, 13), 'vertical');
  assert.equal(swipeIntent(80, 130, 'horizontal'), 'horizontal');
  assert.equal(swipeIntent(120, 80, 'vertical'), 'vertical');
});

test('a swipe starting on a link scatters cubes without activating it; taps and vertical drags stay native', () => {
  const events = new Map(), clicks = new Map(), captures = new Set();
  const target = {closest: () => null};
  const scope = {
    contains: () => true, addEventListener: (key, fn) => clicks.set(key, fn), removeEventListener: key => clicks.delete(key),
    hasPointerCapture: id => captures.has(id), setPointerCapture: id => captures.add(id), releasePointerCapture: id => captures.delete(id),
  };
  const stage = {closest: () => scope, getBoundingClientRect: () => ({left: 0, top: 0, width: 390, height: 844})};
  const window = {addEventListener: (key, fn) => events.set(key, fn), removeEventListener: key => events.delete(key)};
  const document = {documentElement: {addEventListener() {}, removeEventListener() {}}};
  let now = 0;
  const context = vm.createContext({exports: {}, window, document, performance: {now: () => now}});
  const code = ts.transpileModule(fs.readFileSync(new URL('../../src/introPointer.js', import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  vm.runInContext(code, context);
  let verticalGestures=0;
  const pointer = {onVerticalGesture:()=>verticalGestures++}, cleanup = context.exports.bindIntroPointer(stage, pointer);
  const pointerEvent = (x, y) => ({target, pointerType: 'touch', pointerId: 1, clientX: x, clientY: y, timeStamp: now += 50});
  const click = () => {
    let prevented = false;
    clicks.get('click')({detail: 1, preventDefault() {prevented = true;}, stopPropagation() {}});
    return prevented;
  };
  events.get('pointerdown')(pointerEvent(90, 150));
  events.get('pointermove')(pointerEvent(140, 155));
  assert.equal(pointer.active, true);
  assert.equal(captures.has(1), true);
  events.get('pointerup')(pointerEvent(170, 155));
  assert.equal(click(), true, 'lifting after a horizontal swipe must not open the link');
  events.get('pointerdown')(pointerEvent(90, 150));
  events.get('pointerup')(pointerEvent(90, 150));
  assert.equal(click(), false, 'a tap must remain clickable');
  events.get('pointerdown')(pointerEvent(90, 150));
  events.get('pointermove')(pointerEvent(95, 220));
  assert.equal(pointer.active, false);
  assert.equal(verticalGestures,1);
  assert.equal(captures.size, 0, 'vertical scrolling must not capture the pointer');
  events.get('pointerup')(pointerEvent(95, 260));
  assert.equal(click(), false);
  cleanup();
  assert.equal(events.size, 0);
});
