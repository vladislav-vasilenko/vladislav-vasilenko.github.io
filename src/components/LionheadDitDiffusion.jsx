import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei';
import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

// Latent grid: 30x40 = 1200 tokens-as-cubes, one instancedMesh, one draw call.
const COLS = 30;
const ROWS = 40;
const COUNT = COLS * ROWS;
const PATCH = 4;
const PATCH_COLS = Math.ceil(COLS / PATCH); // 8 (the last column of patches is 2 cubes wide)
const PATCH_ROWS = Math.ceil(ROWS / PATCH); // 10
const PATCHES = PATCH_COLS * PATCH_ROWS;
const SPACING = 0.11;
const CUBE = 0.088;
const RADIUS = 0.05; // collision sphere; 2*RADIUS < SPACING so a settled portrait never jostles
const DEPTH = 0.9; // brightness -> relief depth
const GAMMA = 1.8;
const HIST = 12; // trajectory samples per patch
const HIST_HZ = 30;

// Physics tuning (units: world units, seconds).
const NOISE = 2.4;
const JITTER = 7;
const WELL = 0.35;
const QUAKE_RADIUS = 0.75;
const BLAST = 95;
const TREMOR = 1.4;
const SPIN_KICK = 28;
const VMAX = 14;
const RESTITUTION = 0.55;

const HASH_SIZE = 8192; // power of two
const INV_CELL = 1 / (2 * RADIUS);
const DIAM2 = 4 * RADIUS * RADIUS;

const DEFAULT_SOURCES = ['/avatar.jpg', '/profile.jpg'];

const gridX = (c) => (c - (COLS - 1) / 2) * SPACING;
const gridY = (r) => ((ROWS - 1) / 2 - r) * SPACING;
const hashCell = (x, y, z) => (Math.imul(x, 73856093) ^ Math.imul(y, 19349663) ^ Math.imul(z, 83492791)) & (HASH_SIZE - 1);

/** VAE "decoder" init: downsample the avatar to COLSxROWS grayscale bytes (0-255), contrast-stretched. */
async function loadBrightness(sources) {
  for (const src of sources) {
    try {
      const img = new Image();
      img.decoding = 'async';
      img.src = src;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = COLS;
      canvas.height = ROWS;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      // Center "cover" crop to the grid's 3:4 aspect.
      const aspect = COLS / ROWS;
      let sw = img.naturalWidth;
      let sh = img.naturalHeight;
      if (sw / sh > aspect) sw = sh * aspect;
      else sh = sw / aspect;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img, (img.naturalWidth - sw) / 2, (img.naturalHeight - sh) / 2, sw, sh, 0, 0, COLS, ROWS);
      const { data } = ctx.getImageData(0, 0, COLS, ROWS);
      const gray = new Float32Array(COUNT);
      for (let i = 0; i < COUNT; i++) gray[i] = 0.2126 * data[i * 4] + 0.7152 * data[i * 4 + 1] + 0.0722 * data[i * 4 + 2];
      // High contrast: stretch the 2nd-98th percentile range to 0-255, then a gamma curve so light
      // backgrounds and skin separate instead of collapsing into one white slab.
      const sorted = Float32Array.from(gray).sort();
      const lo = sorted[Math.floor(COUNT * 0.02)];
      const hi = sorted[Math.floor(COUNT * 0.98)];
      const range = Math.max(1, hi - lo);
      const out = new Uint8Array(COUNT);
      for (let i = 0; i < COUNT; i++) out[i] = 255 * Math.min(1, Math.max(0, (gray[i] - lo) / range)) ** GAMMA;
      return out;
    } catch {
      // Try the next source.
    }
  }
  return null;
}

function createSimulation() {
  const sim = {
    pos: new Float32Array(COUNT * 3),
    vel: new Float32Array(COUNT * 3),
    rot: new Float32Array(COUNT * 3),
    spin: new Float32Array(COUNT * 3),
    target: new Float32Array(COUNT * 3),
    lum: new Float32Array(COUNT).fill(0.5),
    patchOf: new Uint16Array(COUNT),
    patchSize: new Uint16Array(PATCHES),
    phase: new Float32Array(PATCHES),
    head: new Int32Array(HASH_SIZE),
    next: new Int32Array(COUNT),
    cell: new Int32Array(COUNT * 3),
    centers: new Float32Array(PATCHES * 3),
    hist: new Float32Array(PATCHES * HIST * 3),
    histHead: 0,
    histPrimed: false,
    histClock: 0,
    pointer: new THREE.Vector3(),
    prevPointer: new THREE.Vector3(),
    pointerSpeed: 0,
    hadPointer: false,
  };
  for (let i = 0; i < COUNT; i++) {
    const c = i % COLS;
    const r = (i / COLS) | 0;
    sim.patchOf[i] = ((r / PATCH) | 0) * PATCH_COLS + ((c / PATCH) | 0);
    sim.patchSize[sim.patchOf[i]]++;
    sim.target[i * 3] = gridX(c);
    sim.target[i * 3 + 1] = gridY(r);
    // Phase 1: t = 1, pure noise.
    sim.pos[i * 3] = (Math.random() - 0.5) * 6;
    sim.pos[i * 3 + 1] = (Math.random() - 0.5) * 5.2;
    sim.pos[i * 3 + 2] = (Math.random() - 0.5) * 4;
    sim.rot[i * 3] = Math.random() * Math.PI * 2;
    sim.rot[i * 3 + 1] = Math.random() * Math.PI * 2;
    sim.rot[i * 3 + 2] = Math.random() * Math.PI * 2;
  }
  // Golden-angle phases keep neighbouring patches out of sync while each patch pulses as one.
  for (let k = 0; k < PATCHES; k++) sim.phase[k] = k * 2.39996;
  return sim;
}

function applyBrightness(sim, bytes) {
  for (let i = 0; i < COUNT; i++) {
    sim.lum[i] = bytes[i] / 255;
    sim.target[i * 3 + 2] = (sim.lum[i] - 0.5) * DEPTH;
  }
}

/** Sphere-sphere collisions over a spatial hash: O(N) instead of O(N^2) pair checks. */
function resolveCollisions(sim) {
  const { pos, vel, head, next, cell } = sim;
  head.fill(-1);
  for (let i = 0; i < COUNT; i++) {
    const cx = Math.floor(pos[i * 3] * INV_CELL);
    const cy = Math.floor(pos[i * 3 + 1] * INV_CELL);
    const cz = Math.floor(pos[i * 3 + 2] * INV_CELL);
    cell[i * 3] = cx;
    cell[i * 3 + 1] = cy;
    cell[i * 3 + 2] = cz;
    const h = hashCell(cx, cy, cz);
    next[i] = head[h];
    head[h] = i;
  }
  for (let i = 0; i < COUNT; i++) {
    const cx = cell[i * 3];
    const cy = cell[i * 3 + 1];
    const cz = cell[i * 3 + 2];
    for (let ox = -1; ox <= 1; ox++) {
      for (let oy = -1; oy <= 1; oy++) {
        for (let oz = -1; oz <= 1; oz++) {
          for (let j = head[hashCell(cx + ox, cy + oy, cz + oz)]; j !== -1; j = next[j]) {
            if (j <= i) continue;
            const dx = pos[i * 3] - pos[j * 3];
            const dy = pos[i * 3 + 1] - pos[j * 3 + 1];
            const dz = pos[i * 3 + 2] - pos[j * 3 + 2];
            const d2 = dx * dx + dy * dy + dz * dz;
            if (d2 >= DIAM2 || d2 < 1e-12) continue;
            const d = Math.sqrt(d2);
            const nx = dx / d;
            const ny = dy / d;
            const nz = dz / d;
            // Split the overlap evenly, then exchange momentum along the contact normal.
            const push = (2 * RADIUS - d) * 0.5;
            pos[i * 3] += nx * push;
            pos[i * 3 + 1] += ny * push;
            pos[i * 3 + 2] += nz * push;
            pos[j * 3] -= nx * push;
            pos[j * 3 + 1] -= ny * push;
            pos[j * 3 + 2] -= nz * push;
            const vn = (vel[i * 3] - vel[j * 3]) * nx + (vel[i * 3 + 1] - vel[j * 3 + 1]) * ny + (vel[i * 3 + 2] - vel[j * 3 + 2]) * nz;
            if (vn >= 0) continue;
            const impulse = (-(1 + RESTITUTION) * vn) / 2;
            vel[i * 3] += nx * impulse;
            vel[i * 3 + 1] += ny * impulse;
            vel[i * 3 + 2] += nz * impulse;
            vel[j * 3] -= nx * impulse;
            vel[j * 3 + 1] -= ny * impulse;
            vel[j * 3 + 2] -= nz * impulse;
          }
        }
      }
    }
  }
}

const wrapAngle = (a) => a - Math.PI * 2 * Math.floor((a + Math.PI) / (Math.PI * 2));

function CameraRig() {
  const camera = useThree((s) => s.camera);
  const width = useThree((s) => s.size.width);
  const height = useThree((s) => s.size.height);
  useLayoutEffect(() => {
    // Fit the finished portrait (plus a margin) on any viewport, portrait phones included.
    const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const aspect = width / height;
    const fitH = (ROWS * SPACING) / 2 + 0.5;
    const fitW = (COLS * SPACING) / 2 + 0.3;
    camera.position.set(0, 0, Math.max(fitH / tan, fitW / (tan * aspect)));
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [camera, width, height]);
  return null;
}

function Swarm({ field, pointerNdc, showTrajectories }) {
  const meshRef = useRef(null);
  const linesRef = useRef(null);
  const sim = useMemo(createSimulation, []);
  const scratch = useMemo(
    () => ({
      matrix: new THREE.Matrix4(),
      position: new THREE.Vector3(),
      quaternion: new THREE.Quaternion(),
      euler: new THREE.Euler(),
      scale: new THREE.Vector3(1, 1, 1),
      raycaster: new THREE.Raycaster(),
      ndc: new THREE.Vector2(),
      plane: new THREE.Plane(new THREE.Vector3(0, 0, 1), 0),
      pulse: new Float32Array(PATCHES),
    }),
    [],
  );

  const trailGeometry = useMemo(() => {
    const segments = PATCHES * (HIST - 1);
    const geometry = new THREE.BufferGeometry();
    const position = new THREE.BufferAttribute(new Float32Array(segments * 2 * 3), 3);
    position.setUsage(THREE.DynamicDrawUsage);
    // RGBA vertex colors: three.js enables per-vertex alpha for itemSize 4, giving a fading gradient for free.
    const color = new Float32Array(segments * 2 * 4);
    for (let k = 0; k < PATCHES; k++) {
      for (let s = 0; s < HIST - 1; s++) {
        for (let e = 0; e < 2; e++) {
          const age = (s + e) / (HIST - 1); // 0 = oldest, 1 = newest
          const o = ((k * (HIST - 1) + s) * 2 + e) * 4;
          color[o] = color[o + 1] = color[o + 2] = 0.55 + 0.45 * age;
          color[o + 3] = 0.85 * age * age;
        }
      }
    }
    geometry.setAttribute('position', position);
    geometry.setAttribute('color', new THREE.BufferAttribute(color, 4));
    return geometry;
  }, []);

  useEffect(() => () => trailGeometry.dispose(), [trailGeometry]);

  useLayoutEffect(() => {
    // Allocate instanceColor before the first frame so the shader compiles with instance colors.
    const mesh = meshRef.current;
    const gray = new THREE.Color(0.5, 0.5, 0.5);
    for (let i = 0; i < COUNT; i++) mesh.setColorAt(i, gray);
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadBrightness(DEFAULT_SOURCES).then((bytes) => {
      if (!cancelled && bytes) applyBrightness(sim, bytes);
    });
    return () => {
      cancelled = true;
    };
  }, [sim]);

  useFrame((state, rawDt) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const dt = Math.min(rawDt, 1 / 30);
    const t = state.clock.elapsedTime;
    const g = field.attraction;
    const { pos, vel, rot, spin, target, lum, patchOf } = sim;
    const { pulse } = scratch;

    // Phase 3 input: project the cursor onto the z = 0 plane and estimate its world-space speed.
    let energy = 0;
    if (pointerNdc.active) {
      scratch.ndc.set(pointerNdc.x, pointerNdc.y);
      scratch.raycaster.setFromCamera(scratch.ndc, state.camera);
      if (scratch.raycaster.ray.intersectPlane(scratch.plane, sim.pointer)) {
        if (!sim.hadPointer) sim.prevPointer.copy(sim.pointer);
        sim.hadPointer = true;
        const speed = sim.pointer.distanceTo(sim.prevPointer) / Math.max(rawDt, 1e-3);
        sim.prevPointer.copy(sim.pointer);
        sim.pointerSpeed += (speed - sim.pointerSpeed) * 0.3;
        energy = 0.2 + Math.min(sim.pointerSpeed / 4, 2.5);
      }
    } else {
      sim.hadPointer = false;
      sim.pointerSpeed = 0;
    }
    const wx = sim.pointer.x;
    const wy = sim.pointer.y;
    const quakeR2 = QUAKE_RADIUS * QUAKE_RADIUS;

    // Self-attention stand-in: one shared pulse per 4x4 patch, strongest mid-denoising.
    for (let k = 0; k < PATCHES; k++) {
      const lock = field.locks[k].v;
      pulse[k] = (0.1 + 0.55 * Math.sin(Math.PI * lock)) * (0.5 + 0.5 * Math.sin(t * 2.4 + sim.phase[k]));
    }

    for (let i = 0; i < COUNT; i++) {
      const ix = i * 3;
      const iy = ix + 1;
      const iz = ix + 2;
      const lock = field.locks[patchOf[i]].v;
      const chaos = (1 - lock) * (1 - 0.65 * g);
      // Phase 2: flow-matching velocity field as a damped spring toward x0; patch locks stiffen it into a snap.
      const pull = g * (0.25 + 0.75 * lock);
      const k = 30 * pull + 30 * lock * lock;
      const c = 1.6 * Math.sqrt(k) + 0.4;
      const px = pos[ix];
      const py = pos[iy];
      const pz = pos[iz];
      let ax = k * (target[ix] - px) - c * vel[ix];
      let ay = k * (target[iy] - py) - c * vel[iy];
      let az = k * (target[iz] - pz) - c * vel[iz];

      // Phase 1: turbulent pseudo-curl noise + Brownian jitter, held in a weak harmonic well.
      if (chaos > 1e-3) {
        const s = i * 0.618;
        ax += chaos * (NOISE * (Math.sin(1.3 * py + 0.8 * t + s) + Math.cos(1.7 * pz - 0.6 * t + 2 * s)) + JITTER * (Math.random() - 0.5) - WELL * px);
        ay += chaos * (NOISE * (Math.sin(1.1 * pz + 0.7 * t + 3 * s) + Math.cos(1.5 * px + 0.9 * t)) + JITTER * (Math.random() - 0.5) - WELL * py);
        az += chaos * (NOISE * (Math.sin(1.2 * px - 0.5 * t + s) + Math.cos(1.4 * py + 0.4 * t + s)) + JITTER * (Math.random() - 0.5) - WELL * pz);
        spin[ix] += (Math.random() - 0.5) * 6 * chaos * dt;
        spin[iy] += (Math.random() - 0.5) * 6 * chaos * dt;
        spin[iz] += (Math.random() - 0.5) * 6 * chaos * dt;
      }

      // Phase 3: earthquake — radial blast away from the cursor column, a kick toward the viewer and a tremor.
      if (energy > 0) {
        const dx = px - wx;
        const dy = py - wy;
        const d2 = dx * dx + dy * dy;
        if (d2 < quakeR2) {
          const d = Math.sqrt(d2) + 1e-4;
          const f = (1 - d / QUAKE_RADIUS) ** 2 * energy;
          ax += (dx / d) * BLAST * f;
          ay += (dy / d) * BLAST * f;
          az += BLAST * f * (0.35 + 0.8 * Math.random());
          vel[ix] += (Math.random() - 0.5) * TREMOR * f;
          vel[iy] += (Math.random() - 0.5) * TREMOR * f;
          vel[iz] += (Math.random() - 0.5) * TREMOR * f;
          spin[ix] += (Math.random() - 0.5) * SPIN_KICK * f * dt * 10;
          spin[iy] += (Math.random() - 0.5) * SPIN_KICK * f * dt * 10;
        }
      }

      let vx = vel[ix] + ax * dt;
      let vy = vel[iy] + ay * dt;
      let vz = vel[iz] + az * dt;
      const v2 = vx * vx + vy * vy + vz * vz;
      if (v2 > VMAX * VMAX) {
        const s = VMAX / Math.sqrt(v2);
        vx *= s;
        vy *= s;
        vz *= s;
      }
      vel[ix] = vx;
      vel[iy] = vy;
      vel[iz] = vz;
      pos[ix] = px + vx * dt;
      pos[iy] = py + vy * dt;
      pos[iz] = pz + vz * dt;

      // Tumble while noisy; unwind to grid-aligned as the patch locks.
      const spinDamp = Math.exp(-(1.5 + 6 * lock) * dt);
      const unwind = Math.min(1, 6 * lock * dt);
      for (let a = ix; a <= iz; a++) {
        spin[a] *= spinDamp;
        const r = wrapAngle(rot[a] + spin[a] * dt);
        rot[a] = r - r * unwind;
      }
    }

    // Phase 4: elastic sphere-sphere contacts.
    resolveCollisions(sim);

    const matrices = mesh.instanceMatrix.array;
    const colors = mesh.instanceColor.array;
    const { matrix, position, quaternion, euler, scale } = scratch;
    for (let i = 0; i < COUNT; i++) {
      const ix = i * 3;
      position.set(pos[ix], pos[ix + 1], pos[ix + 2]);
      euler.set(rot[ix], rot[ix + 1], rot[ix + 2]);
      quaternion.setFromEuler(euler);
      matrix.compose(position, quaternion, scale);
      matrix.toArray(matrices, i * 16);
      const k = patchOf[i];
      const lock = field.locks[k].v;
      const base = 0.5 + (0.06 + 0.9 * lum[i] - 0.5) * lock;
      const v = Math.min(1, base * (0.85 + pulse[k]));
      colors[ix] = colors[ix + 1] = colors[ix + 2] = v;
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;

    // ODE trajectories: ring buffer of the last HIST patch-center positions.
    sim.histClock += rawDt;
    if (sim.histClock >= 1 / HIST_HZ || !sim.histPrimed) {
      sim.histClock = 0;
      const { centers, hist, patchSize } = sim;
      centers.fill(0);
      for (let i = 0; i < COUNT; i++) {
        const o = patchOf[i] * 3;
        centers[o] += pos[i * 3];
        centers[o + 1] += pos[i * 3 + 1];
        centers[o + 2] += pos[i * 3 + 2];
      }
      for (let k = 0; k < PATCHES; k++) {
        const n = patchSize[k];
        const o = k * 3;
        centers[o] /= n;
        centers[o + 1] /= n;
        centers[o + 2] /= n;
        // The first sample fills the whole history so trails grow out of a point instead of the origin.
        for (let h = sim.histPrimed ? sim.histHead : 0; h < (sim.histPrimed ? sim.histHead + 1 : HIST); h++) {
          const w = (k * HIST + h) * 3;
          hist[w] = centers[o];
          hist[w + 1] = centers[o + 1];
          hist[w + 2] = centers[o + 2];
        }
      }
      sim.histPrimed = true;
      sim.histHead = (sim.histHead + 1) % HIST;

      if (showTrajectories && linesRef.current) {
        const attribute = trailGeometry.attributes.position;
        const out = attribute.array;
        let w = 0;
        for (let k = 0; k < PATCHES; k++) {
          for (let s = 0; s < HIST - 1; s++) {
            // histHead now points at the oldest sample.
            const a = (k * HIST + ((sim.histHead + s) % HIST)) * 3;
            const b = (k * HIST + ((sim.histHead + s + 1) % HIST)) * 3;
            out[w++] = hist[a];
            out[w++] = hist[a + 1];
            out[w++] = hist[a + 2];
            out[w++] = hist[b];
            out[w++] = hist[b + 1];
            out[w++] = hist[b + 2];
          }
        }
        attribute.needsUpdate = true;
      }
    }
  });

  return (
    <>
      <instancedMesh ref={meshRef} args={[undefined, undefined, COUNT]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[CUBE, CUBE, CUBE]} />
        <meshStandardMaterial color="#ffffff" roughness={0.95} metalness={0} />
      </instancedMesh>
      <lineSegments ref={linesRef} geometry={trailGeometry} visible={showTrajectories} frustumCulled={false}>
        {/* Drawn over the relief: trails run through the cube layer and would otherwise be occluded. */}
        <lineBasicMaterial vertexColors transparent depthTest={false} depthWrite={false} />
      </lineSegments>
    </>
  );
}

/**
 * Fixed full-viewport background: noise -> flow-matching ODE -> DiT-patch denoised portrait, driven by page scroll.
 * `trigger` is the scroll element whose top-to-bottom range maps t = 1 -> 0 (defaults to the whole document).
 */
export default function LionheadDitDiffusion({ trigger }) {
  const [showTrajectories, setShowTrajectories] = useState(false);
  const [dpr, setDpr] = useState(() => Math.min(window.devicePixelRatio || 1, 1.75));
  const readoutRef = useRef(null);
  const field = useMemo(() => ({ attraction: 0, locks: Array.from({ length: PATCHES }, () => ({ v: 0 })) }), []);
  const pointerNdc = useMemo(() => ({ x: 0, y: 0, active: false }), []);

  useEffect(() => {
    const move = (e) => {
      pointerNdc.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointerNdc.y = -(e.clientY / window.innerHeight) * 2 + 1;
      pointerNdc.active = true;
    };
    const leave = () => {
      pointerNdc.active = false;
    };
    const release = (e) => {
      if (e.pointerType !== 'mouse') leave();
    };
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('pointerup', release);
    window.addEventListener('pointercancel', leave);
    window.addEventListener('blur', leave);
    document.documentElement.addEventListener('pointerleave', leave);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', release);
      window.removeEventListener('pointercancel', leave);
      window.removeEventListener('blur', leave);
      document.documentElement.removeEventListener('pointerleave', leave);
    };
  }, [pointerNdc]);

  useEffect(() => {
    const setReadout = (t) => {
      if (readoutRef.current) readoutRef.current.textContent = `t = ${t.toFixed(2)}`;
    };
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      field.attraction = 1;
      for (const lock of field.locks) lock.v = 1;
      setReadout(0);
      return undefined;
    }
    const ctx = gsap.context(() => {
      gsap
        .timeline({
          defaults: { ease: 'none' },
          scrollTrigger: {
            trigger: trigger ?? document.documentElement,
            start: 'top top',
            end: 'bottom bottom',
            scrub: 0.8,
            onUpdate: (self) => setReadout(1 - self.progress),
          },
        })
        // Global flow-field strength ramps up first...
        .to(field, { attraction: 1, duration: 0.55, ease: 'power2.in' }, 0)
        // ...then patches lock center-out, one denoising step at a time.
        .to(field.locks, { v: 1, duration: 0.3, ease: 'power3.inOut', stagger: { amount: 0.55, grid: [PATCH_ROWS, PATCH_COLS], from: 'center' } }, 0.25);
    });
    return () => ctx.revert();
  }, [field, trigger]);

  return (
    <>
      <div className="pointer-events-none fixed inset-0 z-0 bg-black" aria-hidden="true">
        <Canvas
          shadows="percentage"
          dpr={dpr}
          gl={{ antialias: true, powerPreference: 'high-performance' }}
          camera={{ fov: 40, near: 0.1, far: 60, position: [0, 0, 8] }}
        >
          <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(Math.min(window.devicePixelRatio || 1, 1.75))} />
          <color attach="background" args={['#000000']} />
          <CameraRig />
          <ambientLight intensity={0.05} />
          <spotLight
            position={[2.5, 3.5, 7]}
            angle={0.42}
            penumbra={0.12}
            intensity={3.4}
            decay={0}
            castShadow
            shadow-mapSize={[1024, 1024]}
            shadow-bias={-0.0004}
            shadow-normalBias={0.01}
          />
          <directionalLight position={[-4, 1, -3]} intensity={0.25} />
          <Swarm field={field} pointerNdc={pointerNdc} showTrajectories={showTrajectories} />
        </Canvas>
      </div>
      <div className="fixed right-4 bottom-4 z-10 flex flex-col items-end gap-2 font-mono text-[11px] leading-none tracking-wide text-neutral-500">
        <span ref={readoutRef} className="tabular-nums">
          t = 1.00
        </span>
        <label className="flex cursor-pointer items-center gap-2 transition-colors select-none hover:text-neutral-100">
          <input type="checkbox" className="peer sr-only" checked={showTrajectories} onChange={(e) => setShowTrajectories(e.target.checked)} />
          <span aria-hidden="true" className="text-neutral-300 peer-focus-visible:outline peer-focus-visible:outline-1 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-neutral-300">
            {showTrajectories ? '[x]' : '[ ]'}
          </span>
          <span>Visualize Latent Vector Field / ODE Trajectories</span>
        </label>
      </div>
    </>
  );
}
