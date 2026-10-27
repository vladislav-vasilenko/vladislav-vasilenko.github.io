import {smoothRange} from './introMotion.js';

export const ATTENTION_PERIOD = 3.2;
const TINTS = [[.25,.72,1], [1,.65,.24], [.66,.45,1], [.3,1,.72]];

/** Slow shared patch pulses: an attention metaphor, not real DiT attention weights. */
export function patchSignal(out, patch, seconds, noise, release = 0) {
  const wave = (.5 + .5 * Math.sin(seconds * Math.PI * 2 / ATTENTION_PERIOD - patch * 2.39996323)) ** 3;
  const amount = .34 * wave * smoothRange(.04,.3,noise) * (1 - release);
  const tint = TINTS[patch % TINTS.length];
  out[0] = tint[0] * amount; out[1] = tint[1] * amount; out[2] = tint[2] * amount;
  return out;
}

/** Per-instance emission reveals communicating patches even on the shaded cube faces. */
export function attentionMaterial(shader) {
  shader.vertexShader = 'attribute vec3 attentionSignal; varying vec3 vAttentionSignal;\n' + shader.vertexShader;
  shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvAttentionSignal = attentionSignal;');
  shader.fragmentShader = 'varying vec3 vAttentionSignal;\n' + shader.fragmentShader;
  shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += vAttentionSignal;');
}
