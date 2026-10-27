import {binaryOrbit} from './binaryOrbit.js';
import {galaxyPoint} from './cosmicFields.js';

const axisLength = Math.hypot(.68,.67,.30), acrossLength = Math.hypot(.68,.67);
const axis = [.68 / axisLength,.67 / axisLength,-.30 / axisLength];
const across = [-.67 / acrossLength,.68 / acrossLength,0];
export const DNA_FRAME = {axis, across, depth: [-axis[2]*across[1],axis[2]*across[0],axis[0]*across[1]-axis[1]*across[0]]};

export function orbitPoint(out, index, patch, layout, time, mode) {
  if (mode !== 'galaxy' && mode !== 'dna') return binaryOrbit(out,index,patch,layout,time);
  if (mode === 'galaxy') return galaxyPoint(out,index,layout,time / .45);
  const phase = time * .28;
  {
    // Two continuous backbones and 24 regularly spaced crossbars, rather than alternating patches.
    const group = index % 10, row = Math.floor(index / 10);
    const backbone = group < 6;
    const rungIndex = row * 4 + group - 6;
    const along = backbone ? row / 119 * 2 - 1 : Math.floor(rungIndex / 20) / 23 * 2 - 1;
    const angle = along * Math.PI * 1.65 + phase;
    const radius = Math.min(layout.halfWidth * .25, layout.halfHeight * .15, .8);
    const cross = backbone ? (group % 2 ? 1 : -1) : (rungIndex % 20) / 19 * 2 - 1;
    const tube = backbone ? (Math.floor(group / 2) - 1) * .07 : 0;
    const length = Math.min(layout.halfHeight * .38, layout.halfWidth * 1.15);
    const distance = along * length;
    const u = Math.cos(angle) * (radius * cross + tube);
    const v = Math.sin(angle) * (radius * cross + tube);
    // Diagonal, receding axis: lower-left is near, upper-right is farther away.
    // The two transverse vectors and axis form an orthonormal frame.
    out.x = distance * axis[0] + u * across[0] + v * DNA_FRAME.depth[0];
    out.y = distance * axis[1] + u * across[1] + v * DNA_FRAME.depth[1] + layout.halfHeight * .34;
    out.z = distance * axis[2] + v * DNA_FRAME.depth[2];

  }
  out.z = Math.min(layout.cameraZ * .55, out.z);
  out.scale = .34 + (index % 9) / 8 * .12 + Math.max(0,out.z / layout.cameraZ) * .3;
  return out;
}
