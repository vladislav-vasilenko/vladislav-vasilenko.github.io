import { createRoot } from 'react-dom/client';
import LionheadDitDiffusion from './components/LionheadDitDiffusion.jsx';
import './latentIntro.css';
import gsap from 'gsap';
import { resetIntroPlayback, waitForPlayback } from './introPlayback.js';
import { portraitScrollEnd } from './introScroll.js';
import { captureIntroText } from './introTextFragments.js';

/**
 * Lazy-loaded by main.ts. The finished portrait opens to the margins as the CV arrives.
 * The resume stays readable even during a fast scroll or a change of presentation style.
 */
export function mountLatentIntro(section) {
  const dock = { trigger: section.querySelector('.latent-intro-fade'), resume: '.minimal-portfolio', end: '.presentation-headline, .presentation-manifest-label, .minimal-intro' };
  const root = createRoot(section.querySelector('.latent-intro-stage'));
  const button = section.querySelector('[data-intro-play]');
  const track = section.querySelector('.latent-intro-track');
  const auxiliary = section.querySelectorAll?.('.latent-intro-print, .latent-intro-contacts') || [];
  const hideAuxiliary = hidden => {
    section.classList?.toggle('is-playing-intro',hidden);
    for(const element of auxiliary)element.inert=hidden;
  };
  const portraitEnd = () => portraitScrollEnd(window.scrollY + track.getBoundingClientRect().bottom, window.innerHeight);
  const playback = resetIntroPlayback({});

  let timeline = null;
  let manualConsumed = false;
  let destroyed = false;
  const draw = (playing) => root.render(<LionheadDitDiffusion trigger={section.querySelector('.latent-intro-track')} dock={dock} playing={playing} playback={playback} onStop={stop} />);
  const removeListeners = () => {
    window.removeEventListener('wheel', interrupt);
    window.removeEventListener('keydown', key);
  };
  function stop() {
    timeline?.kill(); timeline = null;
    resetIntroPlayback(playback);
    section.classList?.remove('is-text-burst');
    hideAuxiliary(false);
    removeListeners();
    button.disabled = false;
    button.removeAttribute('aria-busy');
    if (!destroyed) draw(false);
  }
  function finishManualDrop() {
    hideAuxiliary(false);
    playback.handingOff = true;
    button.disabled = false; button.removeAttribute('aria-busy');
    draw(false);
  }
  function drop(onReady) {
    playback.releasing = true; draw(true);
    timeline = gsap.to(playback, {
      release: 1, duration: 0.3, ease: 'power1.in',
      onComplete: () => waitForPlayback(playback, 'drop', onReady),
    });
  }
  function interrupt(event) {
    if (event?.target?.closest?.('.latent-controls')) return;
    if (playback.releasing && !playback.handingOff) {
      timeline?.kill(); timeline = null;
      removeListeners();
      playback.mode = 'manual'; playback.release = 1; manualConsumed = true;
      waitForPlayback(playback, 'drop', finishManualDrop);
    } else stop();
  }
  playback.onVerticalGesture=()=>{if(playback.active)interrupt();};
  function key(event) {
    if (event.key === 'Escape') stop();
    else if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) interrupt(event);
  }
  function play() {
    if (playback.active) return;
    resetIntroPlayback(playback, true);
    playback.mode = 'auto';
    hideAuxiliary(true);
    playback.textBurst = captureIntroText(section);
    playback.onTextStart = () => section.classList?.add('is-text-burst');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    const position = { y: window.scrollY };
    const move = () => window.scrollTo({ top: position.y, behavior: 'instant' });
    draw(true);
    window.addEventListener('wheel', interrupt, { passive: true });
    window.addEventListener('keydown', key);
    const handover = () => {
      playback.handingOff = true;
      timeline = gsap.to(position, {
        y: () => window.scrollY + document.getElementById('app').getBoundingClientRect().top,
        duration: 1.35, ease: 'power2.inOut', onUpdate: move, onComplete: stop,
      });
    };
    const approach = () => { timeline = gsap.to(position, {
      y: portraitEnd, duration: 5, ease: 'power1.inOut', onUpdate: move,
      onComplete: () => {
        timeline = gsap.delayedCall(0.35, () => {
          // Mobile browser chrome can change the viewport height during the approach.
          position.y = portraitEnd(); move();
          waitForPlayback(playback, 'portrait', () => drop(handover));
        });
      },
    }); };
    if (playback.textBurst) waitForPlayback(playback, 'text', approach);
    else approach();
  }
  function manualScroll() {
    if (destroyed || playback.mode === 'auto') return;
    const end = portraitEnd();
    if (window.scrollY < end - window.innerHeight * .15) {
      manualConsumed = false;
      if (playback.mode === 'manual') stop();
      return;
    }
    if (window.scrollY < end || manualConsumed || playback.active) return;
    manualConsumed = true;
    // A jump straight to the CV must not restart an invisible animation.
    if (document.getElementById('app').getBoundingClientRect().top <= 0) return;
    resetIntroPlayback(playback, true); playback.mode = 'manual';
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    draw(true);
    waitForPlayback(playback, 'portrait', () => drop(finishManualDrop));
  }
  function destroy() {
    destroyed = true;
    stop();
    window.removeEventListener('scroll', manualScroll);

    root.unmount();
  }
  window.addEventListener('scroll', manualScroll, {passive: true});
  draw(false);
  manualScroll();
  return { play, stop, destroy };
}
