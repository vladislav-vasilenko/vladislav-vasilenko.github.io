import molecules from './data/intro-molecules.json' with {type: 'json'};
import {smoothRange} from './introMotion.js';

export {molecules};
export const MOLECULE_ORDER = ['dopamine', 'serotonin', 'oxytocin', 'adrenaline'];
export const STRUCTURE_SECONDS = 7;
export const MORPH_SECONDS = 1.6;
const GOLDEN = 2.399963229728653;
const hash = n => {const v=Math.sin(n*127.1+311.7)*43758.5453;return v-Math.floor(v);};
const TONES = {C: [.72,.8,.86], N: [.3,.55,1], O: [1,.25,.2], S: [1,.79,.17]};

/** DNA is an opening only. Subsequent laps contain the four molecules. */
export function biologySequence(out, seconds) {
  const step = Math.max(0, Math.floor(seconds / STRUCTURE_SECONDS));
  out.id = step === 0 ? 'dna' : MOLECULE_ORDER[(step - 1) % 4];
  out.previous = step < 2 ? 'dna' : MOLECULE_ORDER[(step - 2) % 4];
  out.mix = step === 0 ? 1 : smoothRange(0, MORPH_SECONDS, seconds % STRUCTURE_SECONDS);
  return out;
}

/** Heavy-atom conformers and bond orders, voxelized once for the existing 1200 instances. */
export function createMoleculeClouds(count = 1200) {
  return Object.fromEntries(MOLECULE_ORDER.map(id => {
    const {atoms, bonds} = molecules[id];
    const points = new Float32Array(count * 3), colors = new Float32Array(count * 3);
    // Simple rings need far fewer voxels than a 69-heavy-atom peptide.
    const activeCount = Math.min(count, Math.min(1080,atoms.length * 10 + bonds.length * 8));
    const atomCount = Math.round(activeCount * .54);
    let maxX = 0, maxY = 0, maxZ = 0;
    for (let i = 0; i < activeCount; i++) {
      let x, y, z, tone;
      if (i < atomCount) {
        const atom = i % atoms.length, sample = Math.floor(i / atoms.length);
        const samples = Math.ceil((atomCount - atom) / atoms.length);
        const a = atoms[atom], u = (sample + .5) / samples;
        const height = 1 - 2 * u, circle = Math.sqrt(1 - height * height);
        const radius = (a[0] === 'S' ? .52 : .40) * (.64 + .36 * ((sample * 7) % 11) / 10);
        x = a[1] + Math.cos(sample * GOLDEN) * circle * radius;
        y = a[2] + height * radius;
        z = a[3] + Math.sin(sample * GOLDEN) * circle * radius;
        tone = TONES[a[0]];
      } else {
        const n = i - atomCount, edge = n % bonds.length, sample = Math.floor(n / bonds.length);
        const samples = Math.ceil((activeCount - atomCount - edge) / bonds.length);
        const [from, to, order] = bonds[edge], a = atoms[from], b = atoms[to];
        const u = (sample + .5) / samples;
        // Two separate tracks preserve double bonds and the recognizable ring skeleton.
        const dx = b[1] - a[1], dy = b[2] - a[2], length = Math.max(.01, Math.hypot(dx,dy));
        const shift = order === 2 ? (sample % 2 ? .14 : -.14) : 0;
        x = a[1] + dx * u - dy / length * shift;
        y = a[2] + dy * u + dx / length * shift;
        z = a[3] + (b[3] - a[3]) * u;
        // Split-color bonds make O/N/S attachments legible, including the sulfur bridge.
        tone = TONES[u < .5 ? a[0] : b[0]];
      }
      points.set([x,y,z], i * 3); colors.set(tone, i * 3);
      maxX = Math.max(maxX,Math.abs(x)); maxY = Math.max(maxY,Math.abs(y)); maxZ = Math.max(maxZ,Math.abs(z));
    }
    return [id, {points, colors, maxX, maxY, maxZ, activeCount}];
  }));
}

/** A complete axial turn, slow precession and slight breathing keep the conformer alive. */
export function moleculePoint(out, index, cloud, view, seconds) {
  if (index >= cloud.activeCount) {
    // Spare portrait pixels wait in a slowly moving peripheral volume, ready for the next shape.
    const lane=hash(index+3),eccentricity=.12+hash(index+19)*.48;
    const mean=hash(index+41)*Math.PI*2-seconds*(.07+hash(index+23)*.19);
    let eccentric=mean;
    for(let n=0;n<3;n++)eccentric-=(eccentric-eccentricity*Math.sin(eccentric)-mean)/(1-eccentricity*Math.cos(eccentric));
    const major=(1.02+lane*.3)/(1-eccentricity),turn=hash(index+47)*Math.PI*2+seconds*.012;
    const x=major*(Math.cos(eccentric)-eccentricity),y=major*Math.sqrt(1-eccentricity**2)*Math.sin(eccentric);
    const curl=Math.sin(seconds*.6+index*1.37)*.055;
    out.x=(x*Math.cos(turn)-y*Math.sin(turn)+curl)*view.halfWidth;
    out.y=(x*Math.sin(turn)+y*Math.cos(turn)+Math.cos(seconds*.41+index)*.045)*view.halfHeight;
    out.z=-.7-lane*2+Math.sin(eccentric+turn)*(.3+hash(index+11)*.8);
    out.scale=.24+hash(index+53)*.32;
    out.r=.20;out.g=.27;out.b=.38;
    return out;
  }
  const i = index * 3, yaw = .32 + Math.sin(seconds * .12) * .26;
  const roll = seconds * .42, tilt = -.18 + Math.sin(seconds * .14) * .12;
  const transverse = Math.hypot(cloud.maxY,cloud.maxZ);
  const fit = Math.min(view.halfWidth * .84 / (cloud.maxX + transverse * .55),
    view.halfHeight * .4 / (transverse + cloud.maxX * .32));
  const breathing = 1 + Math.sin(seconds * 1.3) * .015;
  const y = cloud.points[i+1] * Math.cos(roll) - cloud.points[i+2] * Math.sin(roll);
  const depth = cloud.points[i+1] * Math.sin(roll) + cloud.points[i+2] * Math.cos(roll);
  const x = cloud.points[i] * Math.cos(yaw) + depth * Math.sin(yaw);
  const z = -cloud.points[i] * Math.sin(yaw) + depth * Math.cos(yaw);
  out.x = (x * Math.cos(tilt) - y * Math.sin(tilt)) * fit * breathing;
  out.y = (x * Math.sin(tilt) + y * Math.cos(tilt)) * fit * breathing + view.halfHeight * .34 + Math.sin(seconds * .7) * .025;
  out.z = z * fit * breathing;
  out.scale = Math.max(.23,Math.min(1.05,fit * .21 / .088));
  out.r = cloud.colors[i]; out.g = cloud.colors[i+1]; out.b = cloud.colors[i+2];
  return out;
}

export const BIOLOGY_LABELS = {
  ru: {
    dna: ['ДНК', 'Двойная спираль', 'Схема структуры'],
    dopamine: ['Дофамин', 'C₈H₁₁NO₂', '«Молекула удовольствия»'],
    serotonin: ['Серотонин', 'C₁₀H₁₂N₂O', '«Гормон счастья»'],
    oxytocin: ['Окситоцин', 'C₄₃H₆₆N₁₂O₁₂S₂', '«Молекула любви»'],
    adrenaline: ['Адреналин', 'C₉H₁₃NO₃', 'Экстрим · скорость'],
  },
  en: {
    dna: ['DNA', 'Double helix', 'Structural illustration'],
    dopamine: ['Dopamine', 'C₈H₁₁NO₂', '“The pleasure molecule”'],
    serotonin: ['Serotonin', 'C₁₀H₁₂N₂O', '“The happiness hormone”'],
    oxytocin: ['Oxytocin', 'C₄₃H₆₆N₁₂O₁₂S₂', '“The love molecule”'],
    adrenaline: ['Adrenaline', 'C₉H₁₃NO₃', 'Thrill · speed'],
  },
};
