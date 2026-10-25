import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei';
import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { orbitOrigin, floorImpact, handoffToken, impactFloor, resumeClip, smoothRange } from '../introMotion.js';
import '../sceneControls.css';

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
const HIST = 32; // longer patch trails make the motion field visible
const HIST_HZ = 24;

// Physics tuning (units: world units, seconds).
const NOISE = 0.95;
const JITTER = 1.8;
const WELL = 0.35;
const QUAKE_RADIUS = 1.05;
const BLAST = 80;
const TREMOR = 0.7;
const SPIN_KICK = 12;
const VMAX = 4.2;
const HOVER_VMAX = 7;
const RESTITUTION = 0.55;
// Gravity mode: tokens rain into a bin below the portrait, then the flow field lifts them out.
const GRAVITY = 4.5;
const FLOOR_Y = -(ROWS * SPACING) / 2 - 0.2;
const BIN_X = 1.7;
const BIN_Z = 0.7;
const FLOOR_BOUNCE = 0.3;
const FLOOR_FRICTION = 0.85;
const SATURATION = 1.8; // the source photo is muted; push its hues so they read on cubes

const HASH_SIZE = 8192; // power of two
const INV_CELL = 1 / (2 * RADIUS);

const DEFAULT_SOURCES = ['/avatar.jpg', '/profile.jpg'];

const gridX = (c) => (c - (COLS - 1) / 2) * SPACING;
const gridY = (r) => ((ROWS - 1) / 2 - r) * SPACING;
const hashCell = (x, y, z) => (Math.imul(x, 73856093) ^ Math.imul(y, 19349663) ^ Math.imul(z, 83492791)) & (HASH_SIZE - 1);

/**
 * VAE "decoder" init: downsample the avatar to COLSxROWS grayscale bytes (0-255), contrast-stretched,
 * plus the matching RGB (0-1) at that stretched brightness.
 */
async function loadImage(sources) {
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
      const brightness = new Uint8Array(COUNT);
      const rgb = new Float32Array(COUNT * 3);
      for (let i = 0; i < COUNT; i++) {
        const stretched = Math.min(1, Math.max(0, (gray[i] - lo) / range)) ** GAMMA;
        brightness[i] = 255 * stretched;
        // Rescale the pixel to the stretched luma (same albedo range as monochrome), then boost saturation.
        const luma = 0.06 + 0.9 * stretched;
        const gain = luma / Math.max(gray[i] / 255, 0.02);
        for (let ch = 0; ch < 3; ch++) {
          const v = (data[i * 4 + ch] / 255) * gain;
          rgb[i * 3 + ch] = Math.min(1, Math.max(0, luma + (v - luma) * SATURATION));
        }
      }
      return { brightness, rgb };
    } catch {
      // Try the next source.
    }
  }
  return null;
}

function createSimulation() {
  const sim = {
    pos: new Float32Array(COUNT * 3),
    previousY: new Float32Array(COUNT),
    floorContact: new Uint8Array(COUNT),
    vel: new Float32Array(COUNT * 3),
    rot: new Float32Array(COUNT * 3),
    spin: new Float32Array(COUNT * 3),
    target: new Float32Array(COUNT * 3),
    lum: new Float32Array(COUNT).fill(0.5),
    rgb: new Float32Array(COUNT * 3).fill(0.5),
    scale: new Float32Array(COUNT).fill(1),
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
    seeded: false,
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
  for (let k = 0; k < PATCHES; k++) {
    sim.phase[k] = k * 2.39996;
  }
  return sim;
}

function applyImage(sim, { brightness, rgb }) {
  sim.rgb.set(rgb);
  for (let i = 0; i < COUNT; i++) {
    sim.lum[i] = brightness[i] / 255;
    sim.target[i * 3 + 2] = (sim.lum[i] - 0.5) * DEPTH;
  }
}

/** Sphere-sphere collisions over a spatial hash: O(N) instead of O(N^2) pair checks. */
function resolveCollisions(sim) {
  const { pos, vel, head, next, cell, scale } = sim;
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
            // Contact distance follows each cube's scale, so the shrunken docked portrait does not explode.
            const reach = RADIUS * (scale[i] + scale[j]);
            if (d2 >= reach * reach || d2 < 1e-12) continue;
            const d = Math.sqrt(d2);
            const nx = dx / d;
            const ny = dy / d;
            const nz = dz / d;
            // Split the overlap evenly, then exchange momentum along the contact normal.
            const push = (reach - d) * 0.5;
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
    const fitH = (ROWS * SPACING) / 2 + 0.65;
    const fitW = (COLS * SPACING) / 2 + 0.3;
    camera.position.set(0, 0, Math.max(fitH / tan, fitW / (tan * aspect)));
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [camera, width, height]);
  return null;
}

function Swarm({ field, pointerNdc, gravity, color, handoff, playback }) {
  const meshRef = useRef(null);
  const materialRef = useRef(null);
  const linesRef = useRef(null);
  const lineMaterialRef = useRef(null);
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
      token: { x: 0, y: 0, z: 0, scale: 1 },
      view: { halfWidth: 0, halfHeight: 0, safeLeft: 0, safeRight: 0 },
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
    loadImage(DEFAULT_SOURCES).then((image) => {
      if (!cancelled && image) applyImage(sim, image);
    });
    return () => {
      cancelled = true;
    };
  }, [sim]);

  useFrame((state, rawDt) => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const dt = Math.min(rawDt, 1 / 30);
    const t = state.clock.elapsedTime * 0.45;
    const g = field.attraction;
    const release = playback?.release || 0;
    const { pos, vel, rot, spin, target, lum, rgb, patchOf } = sim;
    const { pulse } = scratch;
    const worldPerPx = (2 * state.camera.position.z * Math.tan(THREE.MathUtils.degToRad(state.camera.fov / 2))) / state.size.height;
    scratch.view.halfWidth = state.size.width * worldPerPx / 2;
    scratch.view.halfHeight = state.size.height * worldPerPx / 2;
    if (!sim.seeded) {
      if (!gravity) for (let i = 0; i < COUNT; i++) {
        const origin = orbitOrigin(scratch.token, i, sim.patchOf[i], scratch.view);
        sim.pos[i * 3] = origin.x; sim.pos[i * 3 + 1] = origin.y; sim.pos[i * 3 + 2] = origin.z;
      }
      sim.seeded = true;
    }

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
        sim.pointerSpeed += (speed - sim.pointerSpeed) * 0.12;
        energy = 0.12 + Math.min(sim.pointerSpeed / 6, 1.5);
      }
    } else {
      sim.hadPointer = false;
      sim.pointerSpeed = 0;
    }
    energy *= 1 - release;
    // Hand over to the CV by clearing its column; the camera remains fixed.
    const d = field.dock;
    const dock = handoff && d > 0;
    if (handoff && (d > 0 || release > 0)) {
      const { width, height } = state.size;
      const view = scratch.view;
      view.halfWidth = width * worldPerPx / 2;
      view.halfHeight = height * worldPerPx / 2;
      view.safeLeft = (field.bounds.left - width / 2) * worldPerPx;
      view.safeRight = (field.bounds.right - width / 2) * worldPerPx;
      energy *= 1 - smoothRange(0, 0.18, d);
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
      const k = (20 * pull + 20 * lock * lock) * (1 - release);
      const edgeSpring = !gravity && !release ? 5.5 * (1 - g) * (1 - lock) : 0;
      const c = 2.05 * Math.sqrt(k + edgeSpring) + 0.7;
      let tx = target[ix];
      let ty = target[iy];
      let tz = target[iz];
      let size = 1;
      if (dock) {
        const token = handoffToken(scratch.token, i, d, tx, ty, tz, scratch.view);
        if (!release) { tx = token.x; ty = token.y; tz = token.z; }
        size = token.scale;
      }
      sim.scale[i] = size;
      const px = pos[ix];
      const py = pos[iy];
      const pz = pos[iz];
      sim.previousY[i] = py;
      let ax = k * (tx - px) - c * vel[ix];
      let ay = k * (ty - py) - c * vel[iy];
      let az = k * (tz - pz) - c * vel[iz];
      // Playback finale: grid springs release and the portrait falls onto the temporary impact plane.
      ay -= 12 * release;

      // Phase 1 (gravity): free fall into the bin; fades as the flow field takes over, so the pile is lifted out.
      const heavy = gravity ? (1 - lock) * (1 - g) : 0;
      if (gravity) {
        ay -= GRAVITY * heavy;
        if (heavy > 0.02) {
          // Soft bin walls keep the pile under the portrait instead of spreading across the floor.
          if (px < -BIN_X) ax += (-BIN_X - px) * 80;
          else if (px > BIN_X) ax += (BIN_X - px) * 80;
          if (pz < -BIN_Z) az += (-BIN_Z - pz) * 80;
          else if (pz > BIN_Z) az += (BIN_Z - pz) * 80;
        }
      } else if (chaos > 1e-3) {
        const origin = orbitOrigin(scratch.token, i, patchOf[i], scratch.view, t);
        ax += edgeSpring * (origin.x - px);
        ay += edgeSpring * (origin.y - py);
        az += edgeSpring * (origin.z - pz);
        // Phase 1 (chaos): turbulent pseudo-curl noise + Brownian jitter, held in a weak harmonic well.
        const s = i * 0.618;
        ax += chaos * (NOISE * (Math.sin(1.3 * py + 0.8 * t + s) + Math.cos(1.7 * pz - 0.6 * t + 2 * s)) + JITTER * (Math.random() - 0.5) - WELL * px);
        ay += chaos * (NOISE * (Math.sin(1.1 * pz + 0.7 * t + 3 * s) + Math.cos(1.5 * px + 0.9 * t)) + JITTER * (Math.random() - 0.5) - WELL * py);
        az += chaos * (NOISE * (Math.sin(1.2 * px - 0.5 * t + s) + Math.cos(1.4 * py + 0.4 * t + s)) + JITTER * (Math.random() - 0.5) - WELL * pz);
        spin[ix] += (Math.random() - 0.5) * 1.4 * chaos * dt;
        spin[iy] += (Math.random() - 0.5) * 1.4 * chaos * dt;
        spin[iz] += (Math.random() - 0.5) * 1.4 * chaos * dt;
      }

      // Phase 3: earthquake — radial blast away from the cursor column, a kick toward the viewer and a tremor.
      let kicked = false;
      if (energy > 0) {
        const dx = px - wx;
        const dy = py - wy;
        const d2 = dx * dx + dy * dy;
        if (d2 < quakeR2) {
          kicked = true;
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
      const maxVelocity = kicked || release > 0 ? HOVER_VMAX : VMAX;
      if (v2 > maxVelocity * maxVelocity) {
        const s = maxVelocity / Math.sqrt(v2);
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
      const spinDamp = Math.exp(-(2.8 + 8 * lock) * dt);
      const unwind = Math.min(1, 6 * lock * dt);
      for (let a = ix; a <= iz; a++) {
        spin[a] *= spinDamp;
        const r = wrapAngle(rot[a] + spin[a] * dt);
        rot[a] = r - r * unwind;
      }
    }

    // Phase 4: elastic sphere-sphere contacts.
    resolveCollisions(sim);
    if (!release) sim.floorContact.fill(0);
    if (release && handoff) {
      // Keep the first impact visible, then lower the plane as the resume rises.
      const floor = impactFloor(scratch.view.halfHeight, state.size.height, field.controlsTop) - smoothRange(0, 0.65, d) * scratch.view.halfHeight * 2.2;
      for (let i = 0; i < COUNT; i++) {
        const o = i * 3, y = o + 1;
        if (pos[y] >= floor + RADIUS || (!sim.floorContact[i] && sim.previousY[i] < floor + RADIUS)) continue;
        pos[y] = floor + RADIUS;
        floorImpact(vel, spin, i, pos[o], !sim.floorContact[i]);
        sim.floorContact[i] = 1;
      }
    }
    if (gravity && !dock && !release) {
      // Floor contact after collisions, so the pile cannot be pushed through it.
      const floor = impactFloor(scratch.view.halfHeight, state.size.height, field.controlsTop, FLOOR_Y);
      for (let i = 0; i < COUNT; i++) {
        const iy = i * 3 + 1;
        if (pos[iy] >= floor + RADIUS) continue;
        pos[iy] = floor + RADIUS;
        if (vel[iy] < 0) vel[iy] *= -FLOOR_BOUNCE;
        vel[iy - 1] *= FLOOR_FRICTION;
        vel[iy + 1] *= FLOOR_FRICTION;
        spin[iy - 1] *= FLOOR_FRICTION;
        spin[iy] *= FLOOR_FRICTION;
        spin[iy + 1] *= FLOOR_FRICTION;
      }
    }

    const matrices = mesh.instanceMatrix.array;
    const colors = mesh.instanceColor.array;
    const { matrix, position, quaternion, euler, scale } = scratch;
    for (let i = 0; i < COUNT; i++) {
      const ix = i * 3;
      position.set(pos[ix], pos[ix + 1], pos[ix + 2]);
      scale.setScalar(sim.scale[i]);
      euler.set(rot[ix], rot[ix + 1], rot[ix + 2]);
      quaternion.setFromEuler(euler);
      matrix.compose(position, quaternion, scale);
      matrix.toArray(matrices, i * 16);
      const k = patchOf[i];
      const lock = field.locks[k].v;
      const gain = 0.85 + pulse[k];
      if (color) {
        // Noise carries a faint tint of its token's colour; locking resolves it fully.
        const mix = 0.25 + 0.75 * lock;
        colors[ix] = Math.min(1, (0.5 + (rgb[ix] - 0.5) * mix) * gain);
        colors[ix + 1] = Math.min(1, (0.5 + (rgb[ix + 1] - 0.5) * mix) * gain);
        colors[ix + 2] = Math.min(1, (0.5 + (rgb[ix + 2] - 0.5) * mix) * gain);
      } else {
        const base = 0.5 + (0.06 + 0.9 * lum[i] - 0.5) * lock;
        colors[ix] = colors[ix + 1] = colors[ix + 2] = Math.min(1, base * gain);
      }
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
    materialRef.current.opacity = dock ? 1 - smoothRange(0.35, 1, d) : 1;
    lineMaterialRef.current.opacity = 0.65 * (dock ? 1 - smoothRange(0.02, 0.5, d) : 1);

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

      if (linesRef.current) {
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
        <meshStandardMaterial ref={materialRef} color="#ffffff" roughness={0.95} metalness={0} transparent />
      </instancedMesh>
      <lineSegments ref={linesRef} geometry={trailGeometry} frustumCulled={false}>
        {/* Drawn over the relief: trails run through the cube layer and would otherwise be occluded. */}
        <lineBasicMaterial ref={lineMaterialRef} vertexColors transparent depthTest={false} depthWrite={false} />
      </lineSegments>
    </>
  );
}

function Toggle({ checked, onChange, icon, disabled = false, children }) {
  return (
    <button type="button" className="latent-control" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)}>
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
        {icon === 'gravity'
          ? <><path d="M10 3v10m-3-3 3 3 3-3M4 16h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></>
          : <><circle cx="7" cy="8" r="3.3" fill="currentColor" opacity=".5" /><circle cx="13" cy="8" r="3.3" fill="currentColor" opacity=".75" /><circle cx="10" cy="13" r="3.3" fill="currentColor" /></>}
      </svg>
      <span>{children}</span>
      <span className="latent-control-indicator" aria-hidden="true" />
    </button>
  );
}

/**
 * Fixed full-viewport background: noise -> flow-matching ODE -> DiT-patch denoised portrait, driven by page scroll.
 * `trigger` is the scroll element whose top-to-bottom range maps t = 1 -> 0 (defaults to the whole document).
 * `dock` ({ trigger, resume, end }): clear the resume column and finish as its first paragraph enters.
 */
export default function LionheadDitDiffusion({ trigger, dock, playing = false, playback, onStop }) {
  const [gravity, setGravity] = useState(false);
  const [color, setColor] = useState(true);
  const [docked, setDocked] = useState(false);
  const [language, setLanguage] = useState(() => document.documentElement.lang === 'ru' ? 'ru' : 'en');
  const stageRef = useRef(null);
  const uiRef = useRef(null);
  const [dpr, setDpr] = useState(() => Math.min(window.devicePixelRatio || 1, 1.75));
  const readoutRef = useRef(null);
  const phaseRef = useRef(null);
  const progressRef = useRef(null);
  const readout = useRef(1);
  const text = language === 'ru'
    ? { title: 'Шум → портрет', gravity: 'Гравитация', color: 'Цвет', stop: 'Остановить показ', fall: 'Падение', progress: 'Формирование портрета', settings: 'Настройки вступления', phases: ['Шум', 'Поток', 'Сборка', 'Портрет'] }
    : { title: 'Noise → portrait', gravity: 'Gravity', color: 'Color', stop: 'Stop playback', fall: 'Falling', progress: 'Portrait formation', settings: 'Intro settings', phases: ['Noise', 'Flow', 'Forming', 'Portrait'] };
  const textRef = useRef(text);
  textRef.current = text;
  const field = useMemo(() => ({ attraction: 0, dock: 0, controlsTop: window.innerHeight, bounds: { left: 0, right: window.innerWidth }, locks: Array.from({ length: PATCHES }, () => ({ v: 0 })) }), []);
  const pointerNdc = useMemo(() => ({ x: 0, y: 0, active: false }), []);

  const setReadout = (t) => {
    readout.current = t;
    const p = Math.max(0, Math.min(1, 1 - t));
    if (readoutRef.current) readoutRef.current.textContent = `${Math.round(p * 100)}%`;
    if (phaseRef.current) phaseRef.current.textContent = playback?.releasing ? textRef.current.fall : textRef.current.phases[p < 0.12 ? 0 : p < 0.55 ? 1 : p < 0.94 ? 2 : 3];
    if (progressRef.current) {
      progressRef.current.style.setProperty('--progress', p);
      progressRef.current.setAttribute('aria-valuenow', Math.round(p * 100));
    }
  };

  useEffect(() => {
    const observer = new MutationObserver(() => setLanguage(document.documentElement.lang === 'ru' ? 'ru' : 'en'));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => setReadout(readout.current), [language, playing, playback?.releasing]);

  useLayoutEffect(() => {
    const panel = uiRef.current;
    const measure = () => {
      const box = panel.getBoundingClientRect();
      field.controlsTop = box.left < window.innerWidth / 2 && box.right > window.innerWidth / 2
        ? box.top : window.innerHeight;
    };
    const observer = new ResizeObserver(measure);
    observer.observe(panel);
    window.addEventListener('resize', measure);
    measure();
    return () => { observer.disconnect(); window.removeEventListener('resize', measure); };
  }, [field]);

  useEffect(() => {
    const move = (e) => {
      if (e.target.closest?.('.latent-controls')) { pointerNdc.active = false; return; }
      const box = stageRef.current.getBoundingClientRect();
      pointerNdc.x = ((e.clientX - box.left) / box.width) * 2 - 1;
      pointerNdc.y = -((e.clientY - box.top) / box.height) * 2 + 1;
      pointerNdc.active = pointerNdc.x >= -1 && pointerNdc.x <= 1 && pointerNdc.y >= -1 && pointerNdc.y <= 1;
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
            scrub: 1.25,
            onUpdate: (self) => setReadout(1 - self.progress),
          },
        })
        // Global flow-field strength ramps up first...
        .to(field, { attraction: 1, duration: 0.55, ease: 'power2.in' }, 0)
        // ...then patches lock center-out, one denoising step at a time.
        .to(field.locks, { v: 1, duration: 0.3, ease: 'power3.inOut', stagger: { amount: 0.55, grid: [PATCH_ROWS, PATCH_COLS], from: 'center' } }, 0.25);
      if (!dock) return;
      let wasDocked = false;
      const applyDock = () => {
        const d = field.dock;
        const resume = document.querySelector(dock.resume);
        if (resume && stageRef.current) {
          const box = resume.getBoundingClientRect();
          const { innerWidth: width, innerHeight: height } = window;
          field.bounds.left = box.left; field.bounds.right = box.right;
          stageRef.current.style.clipPath = resumeClip(box, width, height);
        }
        if (uiRef.current) {
          const hidden = d > 0.2;
          uiRef.current.style.opacity = String(1 - smoothRange(0, 0.2, d));
          uiRef.current.style.visibility = hidden ? 'hidden' : '';
          uiRef.current.inert = hidden;
        }
        // Fully docked: stop rendering; the real avatar has taken over.
        const now = d >= 0.999;
        if (now !== wasDocked) {
          wasDocked = now;
          setDocked(now);
        }
      };
      applyDock();
      gsap.to(field, {
        dock: 1,
        ease: 'none',
        onUpdate: applyDock,
        scrollTrigger: {
          trigger: dock.trigger, start: 'top bottom', scrub: 0.9,
          end: () => {
            const copy = document.querySelector(dock.end);
            const start = dock.trigger.getBoundingClientRect().top + window.scrollY - window.innerHeight;
            return Math.max(start + 100, (copy?.getBoundingClientRect().top ?? 0) + window.scrollY - window.innerHeight);
          },
          onRefresh: applyDock,
        },
      });
    });
    // Keep the protection mask in step with fast scrolls, independent of the scrubbed scene.
    const protectResume = () => {
      if (!dock || !stageRef.current) return;
      const resume = document.querySelector(dock.resume);
      if (resume) stageRef.current.style.clipPath = resumeClip(resume.getBoundingClientRect(), window.innerWidth, window.innerHeight);
    };
    window.addEventListener('scroll', protectResume, { passive: true });
    const resize = new ResizeObserver(() => ScrollTrigger.refresh());
    if (dock && document.getElementById('app')) resize.observe(document.getElementById('app'));
    return () => {
      window.removeEventListener('scroll', protectResume);
      resize.disconnect();
      ctx.revert();
    };
  }, [field, trigger, dock]);

  return (
    <>
      {/* With `dock` the canvas is transparent: the page supplies the black, so cubes can fly over the CV. */}
      <div ref={stageRef} className={`latent-scene ${dock ? 'is-intro' : 'is-standalone'} ${docked ? 'is-complete' : ''}`} aria-hidden="true">
        <Canvas
          frameloop={docked ? 'never' : 'always'}
          shadows="percentage"
          dpr={dpr}
          gl={{ antialias: true, powerPreference: 'high-performance' }}
          camera={{ fov: 40, near: 0.1, far: 60, position: [0, 0, 8] }}
        >
          <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(Math.min(window.devicePixelRatio || 1, 1.75))} />
          {!dock && <color attach="background" args={['#000000']} />}
          <CameraRig />
          <ambientLight intensity={0.05} />
          <spotLight
            position={[2.5, 3.5, 7]}
            angle={0.6}
            penumbra={0.12}
            intensity={3.4}
            decay={0}
            castShadow
            shadow-mapSize={[1024, 1024]}
            shadow-bias={-0.0004}
            shadow-normalBias={0.01}
          />
          <directionalLight position={[-4, 1, -3]} intensity={0.25} />
          <Swarm field={field} pointerNdc={pointerNdc} gravity={gravity} color={color} handoff={!!dock} playback={playback} />
        </Canvas>
      </div>
      <div ref={uiRef} className="latent-controls" role="group" aria-label={text.settings}>
        <div className="latent-controls-heading">
          <div><span className="latent-controls-title">{text.title}</span><span ref={phaseRef} className="latent-phase">{playback?.releasing ? text.fall : text.phases[0]}</span></div>
          <span ref={readoutRef} className="latent-readout">0%</span>
        </div>
        <div ref={progressRef} className="latent-progress" role="progressbar" aria-label={text.progress} aria-valuemin={0} aria-valuemax={100} aria-valuenow={0}><span /></div>
        <div className="latent-controls-actions">
          <Toggle checked={gravity || !!playback?.releasing} onChange={setGravity} icon="gravity" disabled={!!playback?.releasing}>{text.gravity}</Toggle>
          <Toggle checked={color} onChange={setColor} icon="color">{text.color}</Toggle>
        </div>
        {playing && <button className="latent-stop" type="button" onClick={onStop}><span aria-hidden="true">■</span>{text.stop}</button>}
      </div>
    </>
  );
}
