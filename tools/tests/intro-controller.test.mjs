import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as physics from '../../src/introPlayback.js';

test('the actual Intro controller advances from physics callbacks without paused-timeline deadlocks', () => {
  const pending = [], listeners = new Map();
  let props;
  const button = {disabled: false, setAttribute() {}, removeAttribute() {}};
  const window = {scrollY: 0, innerHeight: 844,
    scrollTo({top}) {this.scrollY = top;},
    addEventListener(name, fn) {listeners.set(name, fn);},
    removeEventListener(name) {listeners.delete(name);},
  };
  const app = {getBoundingClientRect: () => ({top: 2182 - window.scrollY})};
  const track = {getBoundingClientRect: () => ({bottom: 2200 - window.scrollY})};
  const section = {querySelector: selector => selector === '[data-intro-play]' ? button : selector === '.latent-intro-track' ? track : {}};
  const tween = (target, options) => {
    const animation = {kill() {}, complete() {
      if (options.y !== undefined) target.y = typeof options.y === 'function' ? options.y() : options.y;
      if (options.release !== undefined) target.release = options.release;
      options.onUpdate?.(); options.onComplete?.();
    }};
    pending.push(animation); return animation;
  };
  const gsap = {to: tween, delayedCall: (_, callback) => tween({}, {onComplete: callback})};
  const require = name => {
    if (name === 'react/jsx-runtime') return {jsx: (_, value) => ({props: value})};
    if (name === 'react-dom/client') return {createRoot: () => ({render: node => {props = node.props;}})};
    if (name === 'gsap') return {default: gsap};
    if (name === './introPlayback.js') return physics;
    return {};
  };
  const context = vm.createContext({exports: {}, require, window, document: {getElementById: () => app}});
  const code = ts.transpileModule(fs.readFileSync(new URL('../../src/latentIntro.jsx', import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInContext(code, context);
  context.exports.mountLatentIntro(section).play();
  pending.shift().complete(); // Approach.
  pending.shift().complete(); // Brief portrait hold.
  assert.equal(pending.length, 0, 'formation must wait for rendered physics');
  for (let i = 0; i < 12; i++) physics.reportPlaybackFrame(props.playback, {dt: 1 / 30, formed: true, total: 1200});
  assert.equal(pending.length, 1);
  pending.shift().complete(); // Release springs.
  assert.equal(pending.length, 0, 'there is no scheduled scroll before impacts');
  for (let i = 0; i < 30; i++) physics.reportPlaybackFrame(props.playback, {dt: 1 / 30, impacts: i === 0 ? 30 : 0, total: 1200});
  assert.equal(pending.length, 1, 'real rebounds must schedule the resume handover');
  pending.shift().complete();
  assert.equal(window.scrollY, 2182);
  assert.equal(button.disabled, false);
  assert.equal(props.playback.active, false);
  assert.equal(listeners.size, 0);
});
