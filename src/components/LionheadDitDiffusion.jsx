import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei';
import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { collideWithFloor, handoffToken, impactFloor, resumeClip, smoothRange } from '../introMotion.js';
import { reportPlaybackFrame } from '../introPlayback.js';
import { asteroidEntrance, binaryOrbitLayout } from '../binaryOrbit.js';
import { orbitPoint } from '../orbitFields.js';
import { trailTokens, trailRing, writeTrailSample, anchorTrailHeads, playbackInteraction, TRAIL_VERTEX, TRAIL_FRAGMENT } from '../introTrails.js';
import { cubeTransformMaterial } from '../introCubes.js';
import { bindIntroPointer } from '../introPointer.js';
import { portraitScrollEnd } from '../introScroll.js';
import { chooseVisitOrbit } from '../introOrbitChoice.js';
import { biologySequence, createMoleculeClouds, moleculePoint, BIOLOGY_LABELS, molecules } from '../molecularFields.js';
import { patchSignal, attentionMaterial } from '../introAttention.js';
import { astronomySequence, astronomyPoint, initialAccretion, ACCRETION_SECONDS, COSMIC_LABELS } from '../cosmicFields.js';
import SupernovaPlasma from './SupernovaPlasma.jsx';
import { seedTextFragments, textVortex, swarmVortex, vortexStrength as swarmVortexStrength, fireSupernova, SUPERNOVA_AT, vortexCubeScale } from '../introTextFragments.js';
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
const DNA_TONES = [[.36,.74,1], [.98,.65,.42], [.65,.9,.65]];
const RGB_CHANNELS = ['r','g','b'];
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
    floorContact: new Uint8Array(COUNT),
    vel: new Float32Array(COUNT * 3),
    rot: new Float32Array(COUNT * 3),
    spin: new Float32Array(COUNT * 3),
    target: new Float32Array(COUNT * 3),
    lum: new Float32Array(COUNT).fill(0.5),
    textMask: new Uint8Array(COUNT), textAge: 10, textBurst: null,
    rgb: new Float32Array(COUNT * 3).fill(0.5),
    orbitColor: new Float32Array(COUNT * 3),
    orbitGlow: new Float32Array(COUNT),
    structureSeconds: 0, entranceSeconds: 0, reportedStructure: null,
    scale: new Float32Array(COUNT).fill(1),
    patchOf: new Uint16Array(COUNT),
    patchSize: new Uint16Array(PATCHES),
    phase: new Float32Array(PATCHES),
    head: new Int32Array(HASH_SIZE),
    next: new Int32Array(COUNT),
    cell: new Int32Array(COUNT * 3),
    trailToken: null,
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
  sim.trailToken=trailTokens(sim.patchOf,PATCHES);
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
function resolveCollisions(sim, skipLettering = false) {
  const { pos, vel, head, next, cell, scale } = sim;
  head.fill(-1);
  for (let i = 0; i < COUNT; i++) {
    if (skipLettering && sim.textMask[i]) continue;
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
    if (skipLettering && sim.textMask[i]) continue;
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

const cubeMaterial = (shader) => { cubeTransformMaterial(shader); attentionMaterial(shader); };

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

function IntroLight() {
  const width = useThree(state => state.size.width);
  const mapSize = width <= 600 ? 512 : 1024;
  return <spotLight position={[2.5,3.5,7]} angle={.6} penumbra={.12} intensity={3.4} decay={0} castShadow shadow-mapSize={[mapSize,mapSize]} shadow-bias={-.0004} shadow-normalBias={.01} />;
}

function Swarm({ field, pointerNdc, handoff, playback, orbitMode, onStructure, captionRef }) {
  const meshRef = useRef(null);
  const materialRef = useRef(null);
  const trailMaterialRef = useRef(null);
  const sim = useMemo(createSimulation, []);
  const moleculeClouds = useMemo(() => orbitMode === 'dna' ? createMoleculeClouds(COUNT) : null, [orbitMode]);
  const attentionAttribute = useMemo(() => new THREE.InstancedBufferAttribute(new Float32Array(COUNT * 3), 3).setUsage(THREE.DynamicDrawUsage), []);
  // The simulation arrays are the instance attributes: no per-frame copy, the vertex shader composes each cube.
  const cubeAttributes = useMemo(() => ({
    position: new THREE.InstancedBufferAttribute(sim.pos, 3).setUsage(THREE.DynamicDrawUsage),
    rotation: new THREE.InstancedBufferAttribute(sim.rot, 3).setUsage(THREE.DynamicDrawUsage),
    scale: new THREE.InstancedBufferAttribute(sim.scale, 1).setUsage(THREE.DynamicDrawUsage),
  }), [sim]);
  const depthMaterial = useMemo(() => {
    const material = new THREE.MeshDepthMaterial();
    material.onBeforeCompile = cubeTransformMaterial;
    material.customProgramCacheKey = () => 'cube-transform-v1';
    return material;
  }, []);
  const trailUniforms = useMemo(() => ({ opacity: { value: 1 }, head: { value: 0 }, history: { value: HIST } }), []);
  const scratch = useMemo(
    () => ({
      raycaster: new THREE.Raycaster(),
      ndc: new THREE.Vector2(),
      plane: new THREE.Plane(new THREE.Vector3(0, 0, 1), 0),
      pulse: new Float32Array(PATCHES),
      signals: Array.from({length: PATCHES}, () => new Float32Array(3)),
      biology: {}, molecule: {}, previousMolecule: {}, entrance: {},
      token: { x: 0, y: 0, z: 0, scale: 1 },
      orbit: {}, vortex: {}, vortexPoint: {}, vortexCore: {x:0,y:0}, rest: { x: 0, y: 0, z: 0, scale: 1 },
      view: { halfWidth: 0, halfHeight: 0, safeLeft: 0, safeRight: 0 },
    }),
    [],
  );

  const trailGeometry = useMemo(() => {
    // Ages and the fading gradient are derived on the GPU from the ring head; samples are never shifted.
    const { segment, end, index, vertices } = trailRing(PATCHES, HIST);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertices * 3), 3).setUsage(THREE.DynamicDrawUsage));
    geometry.setAttribute('trailSegment', new THREE.BufferAttribute(segment, 1));
    geometry.setAttribute('trailEnd', new THREE.BufferAttribute(end, 1));
    geometry.setIndex(new THREE.BufferAttribute(index, 1));
    return geometry;
  }, []);

  useEffect(() => () => { trailGeometry.dispose(); depthMaterial.dispose(); }, [trailGeometry, depthMaterial]);

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
    // A slow phone must not advance the playback clock faster than its falling cubes.
    const dt = Math.min(rawDt, playback?.releasing ? 0.1 : 1 / 30);
    const t = state.clock.elapsedTime * 0.45;
    const g = field.attraction;
    const release = playback?.release || 0;
    const { pos, vel, rot, spin, target, rgb, patchOf } = sim;
    const { pulse } = scratch;
    const worldPerPx = (2 * state.camera.position.z * Math.tan(THREE.MathUtils.degToRad(state.camera.fov / 2))) / state.size.height;
    scratch.view.halfWidth = state.size.width * worldPerPx / 2;
    scratch.view.halfHeight = state.size.height * worldPerPx / 2;
    scratch.view.width = state.size.width; scratch.view.height = state.size.height;
    scratch.view.cameraZ = state.camera.position.z;
    binaryOrbitLayout(scratch.orbit, scratch.view);
    // This clock pauses in a hidden tab, during playback and once the reader starts the CV.
    if (!playback?.active && g < .12 && field.dock < .02) {
      sim.entranceSeconds += Math.min(rawDt,.1);
      if (orbitMode !== 'binary' && (orbitMode !== 'galaxy' || sim.entranceSeconds >= ACCRETION_SECONDS)) sim.structureSeconds += Math.min(rawDt,.1);
    }
    const accretion = orbitMode === 'galaxy' && !playback?.active ? 1-smoothRange(2.3,ACCRETION_SECONDS,sim.entranceSeconds) : 0;
    const biology = orbitMode === 'dna' ? biologySequence(scratch.biology, sim.structureSeconds)
      : astronomySequence(scratch.biology, sim.structureSeconds);
    if (orbitMode !== 'binary' && sim.reportedStructure !== biology.id) {
      sim.reportedStructure = biology.id; onStructure(biology.id);
    }
    if (captionRef.current) {
      const alpha = !playback?.active && field.dock < .02 ? 1 - smoothRange(0,.18,g) : 0;
      captionRef.current.style.opacity = String(alpha);
      captionRef.current.style.visibility = alpha > .01 ? 'visible' : 'hidden';
      captionRef.current.dataset.morph = biology.mix >= .999 ? 'ready' : 'transition';
    }
    if (!sim.seeded) {
      for (let i = 0; i < COUNT; i++) {
        const origin = orbitMode === 'galaxy' ? initialAccretion(scratch.token,i,scratch.view,0)
          : asteroidEntrance(scratch.token, i, sim.patchOf[i], scratch.view);
        sim.pos[i * 3] = origin.x; sim.pos[i * 3 + 1] = origin.y; sim.pos[i * 3 + 2] = origin.z;
        sim.vel[i * 3] = origin.vx || 0; sim.vel[i * 3 + 1] = origin.vy || 0;
        sim.spin[i * 3] = origin.spinX || 0; sim.spin[i * 3 + 2] = origin.spinZ || 0;
      }
      sim.seeded = true;
    }

    if (playback?.textBurst && sim.textBurst !== playback.textBurst) {
      seedTextFragments(sim, playback.textBurst, scratch.view.halfHeight);
      sim.textBurst = playback.textBurst; sim.textAge = 0;
      playback.onTextStart?.();
    }
    sim.textAge += dt;
    if (playback?.active && sim.textBurst && sim.textAge >= SUPERNOVA_AT && sim.novaFor !== sim.textBurst) {
      fireSupernova(sim);sim.novaFor=sim.textBurst;playback.bursting=true;playback.supernova=true;playback.onPhase?.();
    }
    if(playback?.bursting && sim.textAge >= SUPERNOVA_AT+.6){playback.bursting=false;playback.onPhase?.();}
    const vortexStrength = playback?.active && sim.textBurst && !release ? swarmVortexStrength(sim.textAge) : 0;

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
        energy = Math.max(0.12 + Math.min(sim.pointerSpeed / 6, 1.5), pointerNdc.touchBoost || 0);
      }
    } else {
      sim.hadPointer = false;
      sim.pointerSpeed = 0;
    }
    energy *= playbackInteraction(sim.pointerSpeed,pointerNdc.touchBoost||0,!!playback?.active,release);
    // Hand over to the CV by clearing its column; the camera remains fixed.
    const d = playback?.active && !playback.handingOff ? 0 : field.dock;
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
    let minLock = 1;
    for (let k = 0; k < PATCHES; k++) {
      const lock = field.locks[k].v;
      minLock = Math.min(minLock, lock);
      pulse[k] = (0.1 + 0.55 * Math.sin(Math.PI * lock)) * (0.5 + 0.5 * Math.sin(t * 2.4 + sim.phase[k])) * (1-smoothRange(.9,1,lock));
      patchSignal(scratch.signals[k], k, sim.textAge - SUPERNOVA_AT,
        playback?.active && playback.supernova ? (1-smoothRange(.7,.98,g*lock)) * smoothRange(SUPERNOVA_AT+.1,SUPERNOVA_AT+.6,sim.textAge) : 0, release);
    }

    // A finished morph (mix = 1) never evaluates the previous structure.
    const orbitTarget = (i, ix) => {
      const mix = biology.mix, morphing = mix < 1;
      sim.orbitGlow[i] = 0;
      if (orbitMode === 'galaxy') {
        const current = astronomyPoint(scratch.molecule, i, scratch.view, sim.structureSeconds, biology.id);
        const previous = morphing ? astronomyPoint(scratch.previousMolecule, i, scratch.view, sim.structureSeconds, biology.previous) : current;
        const origin = scratch.token;
        origin.x = previous.x + (current.x - previous.x) * mix; origin.y = previous.y + (current.y - previous.y) * mix;
        origin.z = previous.z + (current.z - previous.z) * mix; origin.scale = previous.scale + (current.scale - previous.scale) * mix;
        for (let ch = 0; ch < 3; ch++) sim.orbitColor[ix + ch] = previous[RGB_CHANNELS[ch]] + (current[RGB_CHANNELS[ch]] - previous[RGB_CHANNELS[ch]]) * mix;
        sim.orbitGlow[i] = previous.glow + (current.glow - previous.glow) * mix;
        if (accretion > 0) {
          const entry = initialAccretion(scratch.entrance, i, scratch.view, sim.entranceSeconds);
          origin.x += (entry.x - origin.x) * accretion; origin.y += (entry.y - origin.y) * accretion;
          origin.z += (entry.z - origin.z) * accretion; origin.scale += (entry.scale - origin.scale) * accretion;
        }
        return origin;
      }
      if (orbitMode !== 'dna') return orbitPoint(scratch.token, i, patchOf[i], scratch.orbit, t, orbitMode);
      const tone = DNA_TONES[i % 10 < 6 ? i % 2 : 2];
      sim.orbitColor.set(tone, ix);
      const fromHelix = biology.previous === 'dna' && morphing;
      const origin = biology.id === 'dna' || fromHelix ? orbitPoint(scratch.token, i, patchOf[i], scratch.orbit, t, orbitMode) : scratch.token;
      if (biology.id === 'dna') return origin;
      const current = moleculePoint(scratch.molecule, i, moleculeClouds[biology.id], scratch.view, sim.structureSeconds);
      const previous = !morphing ? current : fromHelix ? origin
        : moleculePoint(scratch.previousMolecule, i, moleculeClouds[biology.previous], scratch.view, sim.structureSeconds);
      origin.x = previous.x + (current.x - previous.x) * mix;
      origin.y = previous.y + (current.y - previous.y) * mix;
      origin.z = previous.z + (current.z - previous.z) * mix;
      origin.scale = previous.scale + (current.scale - previous.scale) * mix;
      for (let ch = 0; ch < 3; ch++) {
        const channel = RGB_CHANNELS[ch];
        const before = fromHelix ? tone[ch] : previous[channel];
        sim.orbitColor[ix + ch] = before + (current[channel] - before) * mix;
      }
      return origin;
    };

    for (let i = 0; i < COUNT; i++) {
      const ix = i * 3;
      const iy = ix + 1;
      const iz = ix + 2;
      const lock = field.locks[patchOf[i]].v;
      const chaos = (1 - lock) * (1 - 0.65 * g);
      // Phase 2: flow-matching velocity field as a damped spring toward x0; patch locks stiffen it into a snap.
      const pull = g * (0.25 + 0.75 * lock);
      const k = (20 * pull + 20 * lock * lock) * (1 - release);
      const textFragment = sim.textMask[i] ? 1 - smoothRange(4.4, 6, sim.textAge) : 0;
      const edgeSpring = !release ? (orbitMode === 'dna' || orbitMode === 'galaxy' ? 18 : 5.5) * (1 - g) * (1 - lock) * (1 - textFragment) * (1 - vortexStrength) : 0;
      const c = 2.05 * Math.sqrt(k + edgeSpring) + 0.7;
      let tx = target[ix];
      let ty = target[iy];
      let tz = target[iz];
      // Orbit targets only act through (1 - g)(1 - lock): a formed patch skips the field entirely.
      const orbitWeight = (1 - g) * (1 - lock);
      const origin = orbitWeight > 0 ? orbitTarget(i, ix) : scratch.rest;
      let size = (1 + (origin.scale - 1) * orbitWeight) * (1 - .25 * textFragment);
      // handoffToken reuses the scratch object; keep the orbital coordinates locally.
      const ox = origin.x, oy = origin.y, oz = origin.z;
      if (dock) {
        const token = handoffToken(scratch.token, i, d, tx, ty, tz, scratch.view);
        if (!release) { tx = token.x; ty = token.y; tz = token.z; }
        size = token.scale;
      }
      if(playback?.active && sim.textBurst){
        size=vortexCubeScale(size,sim.textAge);
        const collapse=sim.textAge<SUPERNOVA_AT?smoothRange(3.7,SUPERNOVA_AT,sim.textAge):1-smoothRange(SUPERNOVA_AT,SUPERNOVA_AT+.4,sim.textAge);
        size*=1-.65*collapse;
      }
      sim.scale[i] = size;
      const px = pos[ix];
      const py = pos[iy];
      const pz = pos[iz];
      let ax = k * (tx - px) - c * vel[ix];
      let ay = k * (ty - py) - c * vel[iy];
      let az = k * (tz - pz) - c * vel[iz];
      // Playback finale: grid springs release and the portrait falls onto the temporary impact plane.
      ay -= 12 * release;

      if (chaos > 1e-3) {
        ax += edgeSpring * (ox - px);
        ay += edgeSpring * (oy - py);
        az += edgeSpring * (oz - pz);
        // Phase 1 (chaos): turbulent pseudo-curl noise + Brownian jitter, held in a weak harmonic well.
        const turbulence = chaos * (orbitMode === 'dna' || orbitMode === 'galaxy' ? .035 : 1) * (1 - vortexStrength);
        const s = i * 0.618;
        ax += turbulence * (NOISE * (Math.sin(1.3 * py + 0.8 * t + s) + Math.cos(1.7 * pz - 0.6 * t + 2 * s)) + JITTER * (Math.random() - 0.5) - WELL * px);
        ay += turbulence * (NOISE * (Math.sin(1.1 * pz + 0.7 * t + 3 * s) + Math.cos(1.5 * px + 0.9 * t)) + JITTER * (Math.random() - 0.5) - WELL * py);
        az += turbulence * (NOISE * (Math.sin(1.2 * px - 0.5 * t + s) + Math.cos(1.4 * py + 0.4 * t + s)) + JITTER * (Math.random() - 0.5) - WELL * pz);
        spin[ix] += (Math.random() - 0.5) * 1.4 * turbulence * dt;
        spin[iy] += (Math.random() - 0.5) * 1.4 * turbulence * dt;
        spin[iz] += (Math.random() - 0.5) * 1.4 * turbulence * dt;
      }

      if (vortexStrength > 0) {
        if (sim.textMask[i]) {
          const delay = 1.2 + (i % 17) / 17 * .9;
          const peel = smoothRange(delay, delay + .35, sim.textAge);
          const vortex = textVortex(scratch.vortex, px, py, pz, sim.textAge, scratch.vortexCore);
          ax = ax * (1 - vortexStrength) + (vortex.vx - vel[ix]) * vortexStrength * peel * 8;
          ay = ay * (1 - vortexStrength) + (vortex.vy - vel[iy]) * vortexStrength * peel * 8;
          az = az * (1 - vortexStrength) + (vortex.vz - vel[iz]) * vortexStrength * peel * 8;
        } else {
          const point = swarmVortex(scratch.vortexPoint, i, scratch.view, sim.textAge);
          ax += ((point.x - px) * 22 - vel[ix] * 5) * vortexStrength;
          ay += ((point.y - py) * 22 - vel[iy] * 5) * vortexStrength;
          az += ((point.z - pz) * 22 - vel[iz] * 5) * vortexStrength;
        }
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
      const maxVelocity = kicked || release > 0 || vortexStrength > 0 || accretion > 0 ? HOVER_VMAX : VMAX;
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
      const spinDamp = Math.exp(-(2.8 + 8 * lock * (1 - release)) * dt);
      const voxelAlignment = orbitMode === 'galaxy' && !playback?.active ? 2.2 : 0;
      const unwind = Math.min(1, (6 * lock + voxelAlignment) * (1 - release) * dt);
      for (let a = ix; a <= iz; a++) {
        spin[a] *= spinDamp;
        const r = wrapAngle(rot[a] + spin[a] * dt);
        rot[a] = r - r * unwind;
      }
    }

    // Atomic clusters are a voxel surface: contacts must not inflate their bonds into a cloud.
    const molecularSurface = (orbitMode === 'galaxy' || orbitMode === 'dna' && biology.id !== 'dna') && g < .2 && !playback?.active;
    if(!molecularSurface && !(playback?.active && sim.textBurst && sim.textAge>4.25 && sim.textAge<SUPERNOVA_AT)) resolveCollisions(sim, !!playback?.active && sim.textAge < 3.1);
    let impacts = 0;
    if (!release) sim.floorContact.fill(0);
    if (release && handoff) {
      // Keep the first impact visible, then lower the plane as the resume rises.
      playback.floor = Math.max(playback.floor ?? -Infinity, impactFloor(scratch.view.halfHeight, state.size.height, field.controlsTop));
      const floor = playback.floor - smoothRange(0, 0.65, d) * scratch.view.halfHeight * 2.2;
      impacts = collideWithFloor(sim, floor, RADIUS);
    }

    const colors = mesh.instanceColor.array;
    const measureError = playback?.active && !playback.releasing;
    const nova = playback?.bursting ? 1 - smoothRange(SUPERNOVA_AT, SUPERNOVA_AT + .35, sim.textAge) : 0;
    let portraitError = 0;
    for (let i = 0; i < COUNT; i++) {
      const ix = i * 3;
      if (measureError) {
        for (let a = ix; a < ix + 3; a++) portraitError += (pos[a] - target[a]) ** 2;
      }
      const k = patchOf[i];
      const lock = field.locks[k].v;
      const gain = 0.85 + .1 * lock + pulse[k];
      // Color resolves from the source photo; fresh lettering fragments start white.
      const mix = 0.25 + 0.75 * lock;
      const white = Math.max(nova,sim.textMask[i] ? 1 - smoothRange(1.4, 3.1, sim.textAge) : 0);
      for (let channel = 0; channel < 3; channel++) {
        let photo = Math.min(1, (0.5 + (rgb[ix + channel] - 0.5) * mix) * gain);
        if (orbitMode === 'dna' || orbitMode === 'galaxy') {
          photo += (sim.orbitColor[ix+channel] * gain - photo) * (1 - g) * (1 - lock);
        }
        colors[ix + channel] = photo + (1 - photo) * white;
        attentionAttribute.array[ix + channel] = scratch.signals[k][channel] + sim.orbitColor[ix+channel] * sim.orbitGlow[i] * (1-g) * (1-lock);
      }
    }
    cubeAttributes.position.needsUpdate = true;
    cubeAttributes.rotation.needsUpdate = true;
    cubeAttributes.scale.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
    attentionAttribute.needsUpdate = true;
    reportPlaybackFrame(playback, { dt, textActive: !!playback?.textBurst && sim.textBurst === playback.textBurst, formed: g > 0.995 && minLock > 0.995 && portraitError / COUNT < 0.0036, impacts, total: COUNT });
    materialRef.current.opacity = dock ? 1 - smoothRange(0.35, 1, d) : 1;
    const biologyTrails = orbitMode === 'dna' && biology.id !== 'dna' ? .08 : orbitMode === 'dna' ? .28 : orbitMode === 'galaxy' ? .055 : .65;
    trailMaterialRef.current.uniforms.opacity.value = biologyTrails * (dock ? 1 - smoothRange(0.02, 0.5, d) : 1);

    // ODE trajectories: a GPU ring of the last HIST samples per trail. Each sample is uploaded once,
    // plus the live head segment each frame; the shader ages and fades the rest.
    const trail = trailGeometry.attributes.position;
    const block = PATCHES * 3;
    const priming = !sim.histPrimed; // no update ranges: the whole buffer is uploaded once
    const upload = b => { if (!priming) trail.addUpdateRange(b * block, block); };
    sim.histClock += rawDt;
    if (priming) {
      // The first sample fills the whole history so trails grow out of a point instead of the origin.
      for (let h = 0; h < HIST; h++) writeTrailSample(trail.array, pos, sim.trailToken, HIST, h);
      sim.histPrimed = true; sim.histClock = 0; sim.histHead = 0;
    } else if (sim.histClock >= 1 / HIST_HZ) {
      sim.histClock = 0;
      writeTrailSample(trail.array, pos, sim.trailToken, HIST, sim.histHead).forEach(upload);
      sim.histHead = (sim.histHead + 1) % HIST;
    }
    // histHead now points at the oldest sample.
    // R3F copies uniform objects into the material, so live values go through the material itself.
    trailMaterialRef.current.uniforms.head.value = sim.histHead;
    upload(anchorTrailHeads(trail.array, pos, sim.trailToken, HIST));
    trail.needsUpdate = true;
  });

  return (
    <>
      {/* instanceMatrix stays identity: cubeTransformMaterial places each cube from the simulation arrays. */}
      <instancedMesh ref={meshRef} args={[undefined, undefined, COUNT]} castShadow receiveShadow frustumCulled={false} customDepthMaterial={depthMaterial}>
        <boxGeometry args={[CUBE, CUBE, CUBE]}>
          <primitive object={attentionAttribute} attach="attributes-attentionSignal" />
          <primitive object={cubeAttributes.position} attach="attributes-cubePosition" />
          <primitive object={cubeAttributes.rotation} attach="attributes-cubeRotation" />
          <primitive object={cubeAttributes.scale} attach="attributes-cubeScale" />
        </boxGeometry>
        <meshStandardMaterial ref={materialRef} color="#ffffff" roughness={0.95} metalness={0} transparent onBeforeCompile={cubeMaterial} customProgramCacheKey={() => 'patch-attention-cube-v2'} />
      </instancedMesh>
      <lineSegments geometry={trailGeometry} frustumCulled={false}>
        {/* Drawn over the relief: trails run through the cube layer and would otherwise be occluded. */}
        <shaderMaterial ref={trailMaterialRef} vertexShader={TRAIL_VERTEX} fragmentShader={TRAIL_FRAGMENT} uniforms={trailUniforms} transparent depthTest={false} depthWrite={false} />
      </lineSegments>
      <SupernovaPlasma playback={playback} simulation={sim} />
    </>
  );
}

/**
 * Fixed full-viewport background: noise -> flow-matching ODE -> DiT-patch denoised portrait, driven by page scroll.
 * `trigger` is the scroll element whose top-to-bottom range maps t = 1 -> 0 (defaults to the whole document).
 * `dock` ({ trigger, resume, end }): clear the resume column and finish as its first paragraph enters.
 */
export default function LionheadDitDiffusion({ trigger, dock, playing = false, playback, onStop }) {
  const [orbitMode] = useState(chooseVisitOrbit);
  const [structure, setStructure] = useState(() => orbitMode === 'galaxy' ? 'solar' : 'dna');
  const captionRef = useRef(null);
  const [docked, setDocked] = useState(false);
  const [language, setLanguage] = useState(() => document.documentElement.lang === 'ru' ? 'ru' : 'en');
  const stageRef = useRef(null);
  const uiRef = useRef(null);
  const dockSyncRef = useRef(null);
  const [visible, setVisible] = useState(() => !document.hidden);
  const [dpr, setDpr] = useState(() => Math.min(window.devicePixelRatio || 1, 1.75));
  const readoutRef = useRef(null);
  const phaseRef = useRef(null);
  const progressRef = useRef(null);
  const readout = useRef(1);
  const text = language === 'ru'
    ? { stop: 'Остановить показ', attention: 'Attention · патчи', vortex: 'Вихрь', nova: 'Сверхновая', fall: 'Падение', bounce: 'Разлёт', progress: 'Формирование портрета', settings: 'Ход анимации', phases: ['Шум', 'Поток', 'Сборка', 'Портрет'] }
    : { stop: 'Stop playback', attention: 'Attention · patches', vortex: 'Vortex', nova: 'Supernova', fall: 'Falling', bounce: 'Scattering', progress: 'Portrait formation', settings: 'Intro progress', phases: ['Noise', 'Flow', 'Forming', 'Portrait'] };
  const textRef = useRef(text);
  textRef.current = text;
  const field = useMemo(() => ({ attraction: 0, dock: 0, controlsTop: window.innerHeight, bounds: { left: 0, right: window.innerWidth }, locks: Array.from({ length: PATCHES }, () => ({ v: 0 })) }), []);
  const labels = (orbitMode === 'dna' ? BIOLOGY_LABELS : COSMIC_LABELS)[language][structure];
  const pointerNdc = useMemo(() => ({ x: 0, y: 0, active: false }), []);

  const setReadout = (t) => {
    readout.current = t;
    const p = Math.max(0, Math.min(1, 1 - t));
    if (readoutRef.current) readoutRef.current.textContent = `${Math.round(p * 100)}%`;
    if (phaseRef.current) phaseRef.current.textContent = playback?.bursting ? textRef.current.nova : playback?.textBurst && !playback.textReady ? textRef.current.vortex : playback?.releasing ? (playback.bounceFrames ? textRef.current.bounce : textRef.current.fall) : playback?.communicating ? textRef.current.attention : textRef.current.phases[p < 0.12 ? 0 : p < 0.55 ? 1 : p < 0.94 ? 2 : 3];
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
  useLayoutEffect(() => dockSyncRef.current?.(), [playing, playback?.handingOff]);
  useEffect(() => {
    const change = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', change);
    return () => document.removeEventListener('visibilitychange', change);
  }, []);
  useLayoutEffect(() => {
    if (!playback) return;
    playback.onPhase = () => setReadout(readout.current);
    return () => { playback.onPhase = null; };
  }, [playback]);

  useLayoutEffect(() => {
    const panel = uiRef.current;
    const measure = () => {
      if (panel.hidden) { field.controlsTop=window.innerHeight; return; }
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

  useEffect(() => {pointerNdc.onVerticalGesture=()=>playback?.onVerticalGesture?.();return bindIntroPointer(stageRef.current, pointerNdc);}, [pointerNdc,playback]);

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
            end: dock ? () => portraitScrollEnd(trigger.getBoundingClientRect().bottom + window.scrollY, window.innerHeight) : 'bottom bottom',
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
        const now = d >= 0.999 && (!playback?.active || playback.handingOff);
        if (now !== wasDocked) {
          wasDocked = now;
          setDocked(now);
        }
      };
      dockSyncRef.current = applyDock;
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
      dockSyncRef.current = null;
      ctx.revert();
    };
  }, [field, trigger, dock]);

  return (
    <>
      {/* With `dock` the canvas is transparent: the page supplies the black, so cubes can fly over the CV. */}
      <div ref={stageRef} className={`latent-scene ${dock ? 'is-intro' : 'is-standalone'} ${docked ? 'is-complete' : ''}`} aria-hidden="true">
        <Canvas
          frameloop={docked || !visible ? 'never' : 'always'}
          shadows="percentage"
          dpr={dpr}
          gl={{ antialias: true, powerPreference: 'high-performance' }}
          camera={{ fov: 40, near: 0.1, far: 60, position: [0, 0, 8] }}
        >
          <PerformanceMonitor onDecline={() => setDpr(1)} onIncline={() => setDpr(Math.min(window.devicePixelRatio || 1, 1.75))} />
          {!dock && <color attach="background" args={['#000000']} />}
          <CameraRig />
          <ambientLight intensity={0.05} />
          <IntroLight />
          <directionalLight position={[-4, 1, -3]} intensity={0.25} />
          <Swarm field={field} pointerNdc={pointerNdc} handoff={!!dock} playback={playback} orbitMode={orbitMode} onStructure={setStructure} captionRef={captionRef} />
        </Canvas>
      </div>
      {orbitMode !== 'binary' && <aside ref={captionRef} className={`latent-structure-caption${orbitMode === 'galaxy' ? ' is-cosmic' : ''}`} data-structure={structure} aria-label={language === 'ru' ? 'Текущая структура' : 'Current structure'}>
        <div key={`${structure}-${language}`} className="latent-structure-copy">
          <strong>{labels?.[0]}</strong>
          <span className="latent-structure-formula">{labels?.[1]}</span>
          {molecules[structure] && <span className="latent-structure-association">{labels?.[2]}</span>}
          {molecules[structure] && <a href={molecules[structure].source} target="_blank" rel="noopener noreferrer"><span className="latent-structure-source-full">{language === 'ru' ? 'Образ поп-культуры · модель без H · источник' : 'Pop-culture association · H omitted · source'}</span><span className="latent-structure-source-short">{language === 'ru' ? 'Источник' : 'Source'}</span><span aria-hidden="true">➤</span></a>}
        </div>
      </aside>}
      <div ref={uiRef} className={`latent-controls${playing ? ' is-playing' : ''}`} hidden={!playing} data-orbit={orbitMode} role="group" aria-label={text.settings}>
        <div className="latent-meter">
          <div className="latent-controls-heading">
            <span ref={phaseRef} className="latent-phase">{playback?.releasing ? (playback.bounceFrames ? text.bounce : text.fall) : text.phases[0]}</span>
            <span ref={readoutRef} className="latent-readout">0%</span>
          </div>
          <div ref={progressRef} className="latent-progress" role="progressbar" aria-label={text.progress} aria-valuemin={0} aria-valuemax={100} aria-valuenow={0}><span /></div>
        </div>
        {playing && <button className="latent-stop" type="button" onClick={onStop} aria-label={text.stop} title={text.stop}><span aria-hidden="true">■</span></button>}
      </div>
    </>
  );
}
