import {binaryOrbit} from './binaryOrbit.js';

export function orbitPoint(out, index, patch, layout, time, mode) {
  if (mode !== 'galaxy' && mode !== 'dna') return binaryOrbit(out,index,patch,layout,time);
  const lane = ((index * 73) % 1200) / 1199;
  const phase = time * (mode === 'dna' ? .28 : .14);
  if (mode === 'galaxy') {
    // An expansive tilted disk: six arms, a central bulge and uneven stellar lanes.
    const extent = Math.max(layout.halfWidth * 1.15, layout.halfHeight * .72);
    const core = index % 11 < 2;
    const radius = core ? (.025 + lane * .18) * extent : (.16 + lane ** 1.25 * .84) * extent;
    const arm = index % 6 * Math.PI / 3;
    const angle = arm + Math.log(.14 + lane) * 1.6 + phase;
    const spread = Math.sin(index * 17.13) * (core ? .8 : .045);
    const warp = Math.sin(angle * 3 + lane * 4) * radius * .012;
    out.x = radius * Math.cos(angle + spread);
    out.y = layout.halfHeight * .08 - radius * Math.sin(angle + spread) * .55 + warp;
    out.z = radius * Math.sin(angle + spread) * .83;

  } else {
    // Two continuous backbones and 24 regularly spaced crossbars, rather than alternating patches.
    const group = index % 10, row = Math.floor(index / 10);
    const backbone = group < 6;
    const rungIndex = row * 4 + group - 6;
    const along = backbone ? row / 119 * 2 - 1 : Math.floor(rungIndex / 20) / 23 * 2 - 1;
    const angle = along * Math.PI * 1.65 + phase;
    const radius = Math.min(layout.halfWidth * .62, 1.65);
    const cross = backbone ? (group % 2 ? 1 : -1) : (rungIndex % 20) / 19 * 2 - 1;
    const tube = backbone ? (Math.floor(group / 2) - 1) * .07 : 0;
    out.x = Math.cos(angle) * (radius * cross + tube);
    out.y = along * layout.halfHeight * .78;
    out.z = Math.sin(angle) * (radius * cross + tube);

  }
  out.z = Math.min(layout.cameraZ * .55, out.z);
  out.scale = .7 + (index % 9) / 8 * .3 + Math.max(0,out.z / layout.cameraZ) * .6;
  return out;
}
