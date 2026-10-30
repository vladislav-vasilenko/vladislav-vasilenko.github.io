const clamp = (v) => Math.max(0, Math.min(1, v));

export function smoothRange(start, end, value) {
  const t = clamp((value - start) / (end - start));
  return t * t * (3 - 2 * t);
}

/** Stable token paths: the portrait opens outwards; only a few small edge tokens linger. */
export function handoffToken(out, index, progress, x, y, z, view) {
  const spread = smoothRange(0, 0.58, progress);
  const lane = ((index * 73) % 1200) / 1199;
  const side = x < 0 ? -1 : 1;
  const edge = side < 0
    ? -view.halfWidth - 0.2 + lane * Math.max(0.1, view.halfWidth + view.safeLeft)
    : view.safeRight + 0.2 + lane * Math.max(0.1, view.halfWidth - view.safeRight);
  out.x = x + (edge - x) * spread;
  out.y = y + (Math.sin(index * 2.39996) * view.halfHeight * 0.2 - y * 0.16) * spread;
  out.z = z - 0.65 * spread;
  const lingering = index % 79 === 0;
  out.scale = lingering
    ? (1 - 0.7 * smoothRange(0.08, 0.48, progress)) * (1 - smoothRange(0.5, 0.94, progress))
    : 1 - smoothRange(0.12, 0.62, progress);
  return out;
}

/** Exclude the resume column from the overlay, even when a quick scroll outruns the physics. */
export function resumeClip(box, width, height) {
  const left = Math.max(0, Math.min(width, box.left - 12));
  const right = Math.max(left, Math.min(width, box.right + 12));
  const top = Math.max(0, Math.min(height, box.top - 12));
  return `polygon(0px 0px, ${width}px 0px, ${width}px ${height}px, ${right}px ${height}px, ${right}px ${top}px, ${left}px ${top}px, ${left}px ${height}px, 0px ${height}px)`;
}

/** Keep the impact and its rebound above a panel that spans the center of the screen. */
export function impactFloor(halfHeight, height, controlsTop = height, base = -halfHeight * 0.74) {
  const panelLimit = (1 - 2 * Math.max(0, controlsTop - 40) / height) * halfHeight;
  return Math.max(base, panelLimit);
}

/** One outward impulse on impact; later bounces lose energy instead of adding it repeatedly. */
export function floorImpact(velocity, spin, index, x, first) {
  const o = index * 3;
  if (velocity[o + 1] < 0) velocity[o + 1] *= first ? -0.68 : -0.42;
  if (!first) return;
  const side = x < 0 ? -1 : 1;
  velocity[o] += side * (1.8 + (index % 7) * 0.12);
  velocity[o + 2] += Math.sin(index * 2.39996) * 1.3;
  spin[o] += Math.sin(index * 1.7) * 5;
  spin[o + 2] += side * 4;
}

/** The floor is solid even if a low frame rate or a resize places a cube below it. */
export function collideWithFloor(sim, floor, radius) {
  const { pos, vel, spin, floorContact } = sim;
  let impacts = 0;
  for (let i = 0; i < floorContact.length; i++) {
    const o = i * 3;
    if (pos[o + 1] >= floor + radius) continue;
    pos[o + 1] = floor + radius;
    const first = !floorContact[i];
    floorImpact(vel, spin, i, pos[o], first);
    if (first) { floorContact[i] = 1; impacts++; }
  }
  return impacts;
}

// Per-index randomness never changes: tabulate it once instead of re-deriving sin/log every frame.
const TABLE = 4096;
const hashes = new Float64Array(TABLE).fill(-1), normals = new Float64Array(TABLE).fill(NaN);
const rawHash = n => {const v=Math.sin(n*127.1+311.7)*43758.5453;return v-Math.floor(v);};
const tabulated = n => n >= 0 && n < TABLE && n === (n | 0);

export function hash(n) {
  if (!tabulated(n)) return rawHash(n);
  if (hashes[n] < 0) hashes[n] = rawHash(n);
  return hashes[n];
}

/** Box-Muller sample from two stable hashes. */
export function normal(n) {
  if (tabulated(n) && !Number.isNaN(normals[n])) return normals[n];
  const v = Math.sqrt(-2*Math.log(Math.max(.001,hash(n))))*Math.cos(Math.PI*2*hash(n+63));
  if (tabulated(n)) normals[n] = v;
  return v;
}
