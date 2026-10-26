export function swipeIntent(dx, dy, locked = 'pending') {
  if (locked !== 'pending') return locked;
  if (Math.hypot(dx, dy) < 10) return 'pending';
  return Math.abs(dx) > Math.abs(dy) * 1.25 ? 'horizontal' : 'vertical';
}

/** Horizontal play, native vertical scrolling, and taps share the same Intro surface. */
export function bindIntroPointer(stage, pointer) {
  const scope = stage.closest('#latent-intro') || stage;
  let gesture = null;
  let suppressClickUntil = 0;
  const leave = () => { pointer.active = false; pointer.touchBoost = 0; };
  const down = event => {
    if (event.pointerType === 'mouse') return;
    if (!scope.contains(event.target) || event.target.closest?.('.latent-controls')) return;
    if (gesture) { gesture = null; leave(); pointer.onVerticalGesture?.(); return; } // Leave pinch gestures to the browser.
    gesture = {id: event.pointerId, x: event.clientX, y: event.clientY, time: event.timeStamp, intent: 'pending'};
  };
  const move = event => {
    if (event.target.closest?.('.latent-controls')) { leave(); return; }
    if (event.pointerType !== 'mouse') {
      if (!gesture || gesture.id !== event.pointerId) return;
      const previousIntent = gesture.intent;
      gesture.intent = swipeIntent(event.clientX - gesture.x, event.clientY - gesture.y, gesture.intent);
      if (gesture.intent !== 'horizontal') {
        if (gesture.intent === 'vertical' && previousIntent !== 'vertical') pointer.onVerticalGesture?.();
        leave(); return;
      }
      // Capture only after direction is clear; taps and vertical drags stay native.
      if (!scope.hasPointerCapture?.(event.pointerId)) scope.setPointerCapture?.(event.pointerId);
      pointer.touchBoost = Math.min(1.8, Math.abs(event.clientX - gesture.x) / Math.max(16, event.timeStamp - gesture.time) * 1.4);
    }
    const box = stage.getBoundingClientRect();
    pointer.x = ((event.clientX - box.left) / box.width) * 2 - 1;
    pointer.y = -((event.clientY - box.top) / box.height) * 2 + 1;
    pointer.active = Math.abs(pointer.x) <= 1 && Math.abs(pointer.y) <= 1;
  };
  const up = event => {
    if (gesture?.id === event.pointerId) {
      if (gesture.intent === 'horizontal') suppressClickUntil = performance.now() + 500;
      if (scope.hasPointerCapture?.(event.pointerId)) scope.releasePointerCapture?.(event.pointerId);
      gesture = null;
    }
    if (event.pointerType !== 'mouse') leave();
  };
  const cancel = () => { if(gesture)pointer.onVerticalGesture?.(); gesture = null; leave(); };
  const click = event => {
    if (performance.now() < suppressClickUntil && event.detail !== 0) {
      suppressClickUntil = 0;
      event.preventDefault(); event.stopPropagation();
    }
  };
  window.addEventListener('pointerdown', down, {passive: true});
  window.addEventListener('pointermove', move, {passive: true});
  window.addEventListener('pointerup', up);
  window.addEventListener('pointercancel', cancel);
  window.addEventListener('blur', cancel);
  scope.addEventListener('click', click, true);
  document.documentElement.addEventListener('pointerleave', leave);
  return () => {
    window.removeEventListener('pointerdown', down);
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('pointercancel', cancel);
    window.removeEventListener('blur', cancel);
    scope.removeEventListener('click', click, true);
    document.documentElement.removeEventListener('pointerleave', leave);
    cancel();
  };
}
