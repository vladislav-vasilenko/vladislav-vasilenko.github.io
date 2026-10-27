import {VORTEX_APPROACH_AFTER} from './introTextFragments.js';

/** Playback waits for simulated, rendered motion rather than a wall-clock timeout. */
export function resetIntroPlayback(playback, active = false) {
  Object.assign(playback, {
    active, mode: null, bursting: false, textBurst: null, textSeconds: 0, textReady: false, onTextStart: null, release: 0, releasing: false, handingOff: false, floor: null,
    formedSeconds: 0, formedFrames: 0, portraitReady: false, supernova: false, communicating: false,
    impacts: 0, bounceSeconds: 0, bounceFrames: 0, dropReady: false,
    waiting: null, onReady: null,
  });
  return playback;
}

export function waitForPlayback(playback, phase, onReady) {
  if (!playback.active) return;
  if (phase === 'text' ? playback.textReady : phase === 'portrait' ? playback.portraitReady : playback.dropReady) onReady();
  else { playback.waiting = phase; playback.onReady = onReady; }
}

export function reportPlaybackFrame(playback, { dt, formed, impacts = 0, total, textActive = false }) {
  if (!playback?.active || playback.handingOff) return;
  if (textActive && playback.textBurst) {
    playback.textSeconds += dt;
    const wasReady = playback.textReady;
    playback.textReady = playback.textSeconds >= VORTEX_APPROACH_AFTER;
    if (playback.textReady && !wasReady) playback.onPhase?.();
  }
  if (!playback.releasing) {
    playback.formedSeconds = formed ? playback.formedSeconds + dt : 0;
    playback.formedFrames = formed ? playback.formedFrames + 1 : 0;
    playback.portraitReady = playback.formedSeconds >= .25 && playback.formedFrames >= 3;
    const communicating = playback.supernova && !formed;
    if (communicating !== playback.communicating) { playback.communicating=communicating; playback.onPhase?.(); }
  } else {
    playback.impacts += impacts;
    // A pile may stand on a few bottom cubes; upper cubes need not touch the floor themselves.
    if (playback.impacts >= Math.min(8, total)) {
      const firstBounce = playback.bounceFrames === 0;
      playback.bounceSeconds += dt;
      playback.bounceFrames++;
      playback.dropReady = playback.bounceSeconds >= 0.6 && playback.bounceFrames >= 8;
      if (firstBounce) playback.onPhase?.();
    }
  }
  const ready = playback.waiting === 'text' ? playback.textReady
    : playback.waiting === 'portrait' ? playback.portraitReady
    : playback.waiting === 'drop' && playback.dropReady;
  if (ready) {
    const callback = playback.onReady;
    playback.waiting = null; playback.onReady = null;
    callback?.();
  }
}
