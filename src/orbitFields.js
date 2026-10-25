import {binaryOrbit} from './binaryOrbit.js';

export function orbitPoint(out, index, patch, layout, time, mode) {
  if (mode !== 'galaxy' && mode !== 'dna') return binaryOrbit(out,index,patch,layout,time);
  const lane = ((index * 73) % 1200) / 1199;
  const phase = time * .14;
  if (mode === 'galaxy') {
    const radius = (.12 + Math.sqrt(lane) * .88) * Math.min(layout.halfWidth * .92, layout.halfHeight * 1.4);
    const arm = patch % 3 * Math.PI * 2 / 3;
    const angle = arm + Math.log(.18 + lane) * 1.65 + phase;
    const spread = ((index * 37) % 17) / 16 * .14 - .07;
    out.x = radius * Math.cos(angle + spread);
    out.y = layout.halfHeight * .12 - radius * Math.sin(angle + spread) * .5;
    out.z = radius * Math.sin(angle + spread) * .866;
  } else {
    const along = patch / 79 * 2 - 1;
    const angle = along * Math.PI * 3 + phase;
    const radius = Math.min(layout.halfWidth * .64, 1.65);
    const rung = patch % 4 === 0;
    const cross = rung ? (index % 16) / 15 * 2 - 1 : patch % 2 ? 1 : -1;
    out.x = Math.cos(angle) * radius * cross;
    out.y = along * layout.halfHeight * .78 + ((index % 16) / 15 - .5) * .1;
    out.z = Math.sin(angle) * radius * cross;
  }
  out.z = Math.min(layout.cameraZ * .55, out.z);
  out.scale = .7 + (index % 9) / 8 * .3 + Math.max(0,out.z / layout.cameraZ) * .6;
  return out;
}
