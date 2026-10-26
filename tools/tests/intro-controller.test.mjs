import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as physics from '../../src/introPlayback.js';
import * as scroll from '../../src/introScroll.js';
import * as fragments from '../../src/introTextFragments.js';

function fixture(textBurst = null) {
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
    if (name === 'react-dom/client') return {createRoot: () => ({render: node => {props = node.props;}, unmount() {}})};
    if (name === 'gsap') return {default: gsap};
    if (name === './introPlayback.js') return physics;
    if (name === './introScroll.js') return scroll;
    if (name === './introTextFragments.js') return {...fragments,captureIntroText:()=>textBurst};
    return {};
  };
  const context = vm.createContext({exports: {}, require, window, document: {getElementById: () => app}});
  const code = ts.transpileModule(fs.readFileSync(new URL('../../src/latentIntro.jsx', import.meta.url), 'utf8'),
    {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInContext(code, context);
  const controller = context.exports.mountLatentIntro(section);
  return {controller, pending, listeners, button, window, get playback() {return props.playback;}};
}

test('the actual Intro controller advances from physics callbacks without paused-timeline deadlocks', () => {
  const f = fixture();
  const {pending, button, window, listeners, controller} = f;
  controller.play();
  pending.shift().complete(); // Approach.
  pending.shift().complete(); // Brief portrait hold.
  assert.equal(pending.length, 0, 'formation must wait for rendered physics');
  for (let i = 0; i < 12; i++) physics.reportPlaybackFrame(f.playback, {dt: 1 / 30, formed: true, total: 1200});
  assert.equal(pending.length, 1);
  pending.shift().complete(); // Release springs.
  assert.equal(pending.length, 0, 'there is no scheduled scroll before impacts');
  for (let i = 0; i < 30; i++) physics.reportPlaybackFrame(f.playback, {dt: 1 / 30, impacts: i === 0 ? 30 : 0, total: 1200});
  assert.equal(pending.length, 1, 'real rebounds must schedule the resume handover');
  pending.shift().complete();
  assert.equal(window.scrollY, 2182);
  assert.equal(button.disabled, false);
  assert.equal(f.playback.active, false);
  assert.equal(listeners.size, 1); // Native manual-scroll watcher remains.
  controller.destroy();
  assert.equal(listeners.size, 0);
});

test('manual scrolling triggers the same release and impacts without moving the reader', () => {
  const f = fixture();
  f.window.scrollY = 800;
  f.listeners.get('scroll')();
  assert.equal(f.playback.mode, 'manual');
  for (let i = 0; i < 12; i++) physics.reportPlaybackFrame(f.playback, {dt: 1 / 30, formed: true, total: 1200});
  assert.equal(f.pending.length, 1);
  f.pending.shift().complete(); // Release only, no scroll tween.
  for (let i = 0; i < 30; i++) physics.reportPlaybackFrame(f.playback, {dt: 1 / 30, impacts: i === 0 ? 30 : 0, total: 1200});
  assert.equal(f.playback.handingOff, true);
  assert.equal(f.window.scrollY, 800);
  assert.equal(f.pending.length, 0);
  f.listeners.get('scroll')();
  assert.equal(f.pending.length, 0, 'continuing down must not replay the fall');
  f.window.scrollY = 200; f.listeners.get('scroll')();
  assert.equal(f.playback.active, false);
  f.window.scrollY = 800; f.listeners.get('scroll')();
  assert.equal(f.playback.mode, 'manual', 'scrolling back re-arms a new descent');
  assert.equal(f.playback.impacts, 0);
  f.controller.destroy();
});

test('jumping directly into the resume does not start a hidden fall', () => {
  const f = fixture();
  f.window.scrollY = 2182; f.listeners.get('scroll')();
  assert.equal(f.playback.active, false);
  assert.equal(f.pending.length, 0);
  f.controller.destroy();
});

test('interrupting button playback during the fall hands it to native scrolling', () => {
  const f = fixture();
  f.controller.play(); f.pending.shift().complete(); f.pending.shift().complete();
  for (let i = 0; i < 12; i++) physics.reportPlaybackFrame(f.playback, {dt: 1 / 30, formed: true, total: 1200});
  f.pending.shift().complete();
  const y = f.window.scrollY;
  f.listeners.get('wheel')({target: {closest: () => null}});
  assert.equal(f.playback.mode, 'manual');
  for (let i = 0; i < 30; i++) physics.reportPlaybackFrame(f.playback, {dt: 1 / 30, impacts: i === 0 ? 30 : 0, total: 1200});
  assert.equal(f.playback.handingOff, true);
  assert.equal(f.window.scrollY, y);
  assert.equal(f.pending.length, 0);
  f.controller.destroy();
});


test('clicking the actual combined name/action waits for the swarm vortex before the scroll approach',()=>{
 const f=fixture({points:[{x:1,y:1}],width:390,height:844});
 f.controller.play();assert.equal(f.pending.length,0);
 for(let i=0;i<100;i++)physics.reportPlaybackFrame(f.playback,{dt:1/30,formed:false,total:1200,textActive:true});
 assert.equal(f.pending.length,1);f.pending.shift().complete();
 f.controller.stop();assert.equal(f.playback.textBurst,null);assert.equal(f.playback.active,false);
 f.controller.destroy();
});
