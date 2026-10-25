/** Playback waits for simulated, rendered motion rather than a wall-clock timeout. */
export function resetIntroPlayback(playback, active = false) {
  Object.assign(playback, {
    active, release: 0, releasing: false, handingOff: false, floor: null,
    formedSeconds: 0, formedFrames: 0, portraitReady: false,
    impacts: 0, bounceSeconds: 0, bounceFrames: 0, dropReady: false,
    waiting: null, onReady: null,
  });
  return playback;
}

export function waitForPlayback(playback, phase, onReady) {
  if (!playback.active) return;
  if (phase === 'portrait' ? playback.portraitReady : playback.dropReady) onReady();
  else { playback.waiting = phase; playback.onReady = onReady; }
}

export function reportPlaybackFrame(playback, { dt, formed, impacts = 0, total }) {
  if (!playback?.active || playback.handingOff) return;
  if (!playback.releasing) {
    playback.formedSeconds = formed ? playback.formedSeconds + dt : 0;
    playback.formedFrames = formed ? playback.formedFrames + 1 : 0;
    playback.portraitReady = playback.formedSeconds >= 0.25 && playback.formedFrames >= 3;
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
  const ready = playback.waiting === 'portrait' ? playback.portraitReady
    : playback.waiting === 'drop' && playback.dropReady;
  if (ready) {
    const callback = playback.onReady;
    playback.waiting = null; playback.onReady = null;
    callback?.();
  }
}
