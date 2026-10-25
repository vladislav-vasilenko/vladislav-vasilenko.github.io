import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function module() {
  let timeout;
  const context = vm.createContext({exports: {}, setTimeout: fn => {timeout = fn; return 1;}, clearTimeout() {}});
  const code = ts.transpileModule(fs.readFileSync(new URL('../../src/features/introPower.ts', import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  vm.runInContext(code, context);
  return {...context.exports, timeout: () => timeout?.()};
}
const motion = matches => Object.assign(new EventTarget(), {matches});
const battery = (level, charging) => Object.assign(new EventTarget(), {level, charging});

test('only known low charge off the charger disables 3D; unknown battery is not low', () => {
  const {introPowerReason: reason} = module();
  assert.equal(reason(false, false), null);
  assert.equal(reason(false, false, {level: .2, charging: false}), 'low-battery');
  assert.equal(reason(false, false, {level: 0, charging: false}), 'low-battery');
  assert.equal(reason(false, false, {level: .2, charging: true}), null);
  assert.equal(reason(false, false, {level: .21, charging: false}), null);
  assert.equal(reason(false, false, {level: NaN, charging: false}), null);
  assert.equal(reason(true, false), 'reduced-motion');
  assert.equal(reason(false, true), 'save-data');
});

test('battery changes disable the mounted scene once and clean up their listeners', async () => {
  const m = module(), b = battery(.6, false), reasons = [];
  const guard = m.watchIntroPower({getBattery: async () => b}, motion(false), reason => reasons.push(reason));
  await guard.ready;
  assert.deepEqual(reasons, []);
  b.level = .19; b.dispatchEvent(new Event('levelchange'));
  assert.deepEqual(reasons, ['low-battery']);
  b.dispatchEvent(new Event('chargingchange'));
  assert.equal(reasons.length, 1);
});

test('unsupported and policy-blocked battery APIs preserve the normal Intro', async () => {
  for (const nav of [{}, {getBattery: async () => {throw Error('Permissions-Policy');}}]) {
    const m = module(), reasons = [];
    const guard = m.watchIntroPower(nav, motion(false), reason => reasons.push(reason));
    await guard.ready;
    assert.deepEqual(reasons, []);
    guard.dispose();
  }
});

test('Save-Data and reduced motion skip battery lookup and the heavy loading path', async () => {
  for (const saveData of [true, false]) {
    const m = module(), reasons = [];
    let lookups = 0;
    const nav = {connection: Object.assign(new EventTarget(), {saveData}), getBattery: async () => {lookups++; return battery(.8, false);}};
    await m.watchIntroPower(nav, motion(!saveData), reason => reasons.push(reason)).ready;
    assert.equal(lookups, 0);
    assert.deepEqual(reasons, [saveData ? 'save-data' : 'reduced-motion']);
  }
});

test('a slow API cannot delay the Intro indefinitely; a late low-battery signal still disables it', async () => {
  const m = module(), reasons = [];
  let resolveBattery;
  const guard = m.watchIntroPower({getBattery: () => new Promise(resolve => {resolveBattery = resolve;})}, motion(false), reason => reasons.push(reason));
  await Promise.resolve();
  m.timeout();
  await guard.ready;
  assert.deepEqual(reasons, []);
  resolveBattery(battery(.1, false));
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(reasons, ['low-battery']);
});
