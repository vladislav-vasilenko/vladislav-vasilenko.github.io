/** One real cube per trail; patch averages are not trajectories in multi-arm fields. */
export function trailTokens(patchOf, patches) {
  const tokens = new Int32Array(patches).fill(-1);
  for(let i=0;i<patchOf.length;i++)if(tokens[patchOf[i]]<0)tokens[patchOf[i]]=i;
  return tokens;
}

/**
 * Static GPU ring: vertex block 2s+e is the end e of segment s (history slot s -> s+1) for every trail,
 * and the last two blocks are a live segment from the newest sample to the cube itself.
 * Each sample is written once into its slot; the vertex shader derives its age from the ring head.
 */
export function trailRing(trails, historyLength) {
  const blocks = historyLength * 2 + 2, vertices = blocks * trails;
  const segment = new Float32Array(vertices), end = new Float32Array(vertices);
  for (let b = 0; b < blocks; b++) {
    segment.fill(b < historyLength * 2 ? b >> 1 : -1, b * trails, (b + 1) * trails);
    end.fill(b & 1, b * trails, (b + 1) * trails);
  }
  const index = new (vertices > 65535 ? Uint32Array : Uint16Array)((historyLength + 1) * trails * 2);
  for (let s = 0, w = 0; s <= historyLength; s++) for (let k = 0; k < trails; k++) {
    index[w++] = s * 2 * trails + k; index[w++] = (s * 2 + 1) * trails + k;
  }
  return {segment, end, index, vertices};
}

function copyTokens(out, positions, tokens, block) {
  for (let k = 0, w = block * tokens.length * 3; k < tokens.length; k++, w += 3) {
    const source = tokens[k] * 3;
    out[w] = positions[source]; out[w + 1] = positions[source + 1]; out[w + 2] = positions[source + 2];
  }
}

/** Store one sample in its ring slot; returns the vertex blocks touched, for partial GPU uploads. */
export function writeTrailSample(out, positions, tokens, historyLength, slot) {
  const blocks = [slot * 2, ((slot + historyLength - 1) % historyLength) * 2 + 1, historyLength * 2];
  for (const block of blocks) copyTokens(out, positions, tokens, block);
  return blocks;
}

/** The newest endpoint follows its cube every render, even between history samples. */
export function anchorTrailHeads(out, positions, tokens, historyLength) {
  const block = historyLength * 2 + 1;
  copyTokens(out, positions, tokens, block);
  return block;
}

/** Age 0 is the oldest sample, 1 the newest; the segment that wraps from newest to oldest is hidden. */
export const TRAIL_VERTEX = `
attribute float trailSegment; attribute float trailEnd;
uniform float head; uniform float history;
varying vec4 vTrail;
void main(){
  float age=1.0, visible=1.0;
  if(trailSegment>=0.0){
    float rank=mod(trailSegment-head+history,history);
    visible=step(rank,history-1.5);
    age=(rank+trailEnd)/(history-1.0);
  }
  vTrail=vec4(vec3(.55+.45*age),.85*age*age*visible);
  gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
}`;

export const TRAIL_FRAGMENT = `
varying vec4 vTrail; uniform float opacity;
void main(){
  gl_FragColor=vec4(vTrail.rgb,vTrail.a*opacity);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

export function playbackInteraction(pointerSpeed,touchBoost,active,release) {
  const motion=active?Math.min(1,Math.max(0,pointerSpeed)*.55+Math.max(0,touchBoost)*.5):1;
  return motion*(1-Math.min(1,Math.max(0,release))*.7);
}
