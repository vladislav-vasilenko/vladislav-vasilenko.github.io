export const VORTEX_APPROACH_AFTER = 3.2;
export const VORTEX_END = 6;
export const SUPERNOVA_AT = 4.8;

export function vortexStrength(age) {
  if (age >= SUPERNOVA_AT) return 0;
  const ramp = Math.min(1, Math.max(0, age / .85));
  const fade = Math.min(1, Math.max(0, (VORTEX_END - age) / 1.4));
  return ramp * ramp * (3 - 2 * ramp) * fade;
}

/** Integrated angular velocity: starts at rest and reaches cruise speed without a jump. */
export function vortexTurn(age) {
  const duration = 2.2, speed = 3;
  const q = Math.min(1, Math.max(0, age / duration));
  return speed * duration * (q ** 3 - .5 * q ** 4) + speed * Math.max(0, age - duration);
}

/** Read the actual, localized HTML lettering into a small temporary glyph mask. */
export function captureIntroText(section) {
  try {
    const labels = [...section.querySelectorAll('.latent-intro-name, [data-intro-action]')];
    const visible = labels.map(element => ({element, box: element.getBoundingClientRect(), style: getComputedStyle(element)}))
      .filter(({box}) => box.width > 0 && box.height > 0 && box.bottom > 0 && box.top < innerHeight);
    if (!visible.length) return null;
    const left = Math.floor(Math.min(...visible.map(({box}) => box.left)));
    const top = Math.floor(Math.min(...visible.map(({box}) => box.top)));
    const right = Math.ceil(Math.max(...visible.map(({box}) => box.right)));
    const bottom = Math.ceil(Math.max(...visible.map(({box}) => box.bottom)));
    const canvas = document.createElement('canvas');
    canvas.width = Math.min(2048, right - left + 4); canvas.height = Math.min(512, bottom - top + 4);
    const context = canvas.getContext('2d', {willReadFrequently: true});
    if (!context) return null;
    context.fillStyle = '#fff'; context.textAlign = 'center'; context.textBaseline = 'middle';
    for (const {element, box, style} of visible) {
      context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      if ('letterSpacing' in context) context.letterSpacing = style.letterSpacing;
      context.fillText(element.textContent.trim(), box.left - left + box.width / 2 + 2, box.top - top + box.height / 2 + 2, box.width);
    }
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const glyphs = [];
    for (let y = 0; y < canvas.height; y += 2) for (let x = 0; x < canvas.width; x += 2) {
      if (pixels[(y * canvas.width + x) * 4 + 3] > 100) glyphs.push({x: left + x - 2, y: top + y - 2});
    }
    if (!glyphs.length) return null;
    const count = Math.min(64, glyphs.length);
    return {width: innerWidth, height: innerHeight, points: Array.from({length: count}, (_, i) => glyphs[Math.floor(i * glyphs.length / count)])};
  } catch { return null; } // A failed glyph capture must never block access to the resume.
}

/** Reuse portrait instances: the text fragments become actual face pixels later. */
export function seedTextFragments(sim, burst, halfHeight) {
  const units = halfHeight * 2 / burst.height;
  sim.textMask.fill(0); sim.textAge = 0; sim.textBurst = burst;
  sim.textCenter = {x:0,y:0};
  burst.points.forEach((point, n) => {
    const i = (n * 37) % sim.scale.length, ix = i * 3;
    const x = (point.x - burst.width / 2) * units, y = (burst.height / 2 - point.y) * units;
    sim.textCenter.x += x / burst.points.length; sim.textCenter.y += y / burst.points.length;
    sim.pos[ix] = x; sim.pos[ix + 1] = y; sim.pos[ix + 2] = 0;
    sim.vel.fill(0, ix, ix + 3);
    sim.rot.fill(0, ix, ix + 3);
    sim.spin[ix] = Math.sin(n) * 5; sim.spin[ix + 1] = Math.cos(n) * 5; sim.spin[ix + 2] = Math.sin(n * .7) * 4;
    sim.textMask[i] = 1;
  });
}

/** Suction into the main swarm’s core; the glyphs do not define their own whirlpool. */
export function textVortex(out, x, y, z, age, center) {
  const u = x - center.x;
  const yOffset = y - center.y, zOffset = z - (center.z || 0);
  // Same tilted basis as swarmVortex: no second, screen-perpendicular text disk.
  const v = yOffset * .55 + zOffset * .83;
  const normal = -yOffset * .83 + zOffset * .55;
  const radius = Math.max(.3, Math.hypot(u, v));
  const speed = 1.2 + Math.min(1, age / 2.2) * 2.2;
  const du = v / radius * speed - u * 1.1;
  const dv = -u / radius * speed - v * 1.1;
  const dn = -normal * 2;
  out.vx = du;
  out.vy = dv * .55 - dn * .83;
  out.vz = dv * .83 + dn * .55;
  out.strength = Math.max(0, Math.min(1, (VORTEX_END - age) / 1.4));
  return out;
}

/** A tilted accretion disk made from the existing main cubes, narrowing toward its dark core. */
export function swarmVortex(out, index, view, age) {
  const lane = ((index * 73) % 1200) / 1199;
  const shrink = 1 - .9 * Math.min(1, Math.max(0, (age - 1.8) / 2.8));
  const radius = (.22 + Math.sqrt(lane) * .78) * Math.min(view.halfWidth * .94, view.halfHeight * .8) * shrink;
  const angle = index * 2.39996323 - vortexTurn(age);
  out.x = Math.cos(angle) * radius;
  out.y = Math.sin(angle) * radius * .55;
  out.z = Math.sin(angle) * radius * .83 - .2 + (1 - lane) * .45;
  return out;
}

/** One outward impulse preserves the disk’s momentum, then the existing portrait springs take over. */
export function fireSupernova(sim) {
  for(let i=0;i<sim.scale.length;i++){
    const ix=i*3, angle=i*2.39996323, z=((i*73)%1199)/1198*2-1;
    const radial=Math.sqrt(1-z*z), distance=Math.max(.05,Math.hypot(sim.pos[ix],sim.pos[ix+1],sim.pos[ix+2]));
    const dx=sim.pos[ix]/distance*.6+Math.cos(angle)*radial*.4;
    const dy=sim.pos[ix+1]/distance*.6+Math.sin(angle)*radial*.4;
    const dz=sim.pos[ix+2]/distance*.6+z*.4;
    sim.vel[ix]+=dx*6;sim.vel[ix+1]+=dy*6;sim.vel[ix+2]+=dz*6;
    sim.spin[ix]+=Math.sin(angle)*8;sim.spin[ix+2]+=Math.cos(angle)*8;
  }
}
