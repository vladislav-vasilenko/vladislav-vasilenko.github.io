import { createRoot } from 'react-dom/client';
import LionheadDitDiffusion from './components/LionheadDitDiffusion.jsx';
import './latentIntro.css';
import gsap from 'gsap';
import { resetIntroPlayback, waitForPlayback } from './introPlayback.js';

/**
 * Lazy-loaded by main.ts. The finished portrait opens to the margins as the CV arrives.
 * The resume stays readable even during a fast scroll or a change of presentation style.
 */
export function mountLatentIntro(section) {
  const dock = { trigger: section.querySelector('.latent-intro-fade'), resume: '.minimal-portfolio', end: '.presentation-headline, .presentation-manifest-label, .minimal-intro' };
  const root = createRoot(section.querySelector('.latent-intro-stage'));
  const button = section.querySelector('[data-intro-play]');
  const playback = resetIntroPlayback({});
  let timeline = null;
  const draw = (playing) => root.render(<LionheadDitDiffusion trigger={section.querySelector('.latent-intro-track')} dock={dock} playing={playing} playback={playback} onStop={stop} />);
  const removeListeners = () => {
    window.removeEventListener('wheel', interrupt);
    window.removeEventListener('touchstart', interrupt);
    window.removeEventListener('keydown', key);
  };
  function stop() {
    timeline?.kill(); timeline = null;
    resetIntroPlayback(playback);
    removeListeners();
    button.disabled = false;
    button.removeAttribute('aria-busy');
    draw(false);
  }
  function interrupt(event) {
    if (!event.target.closest?.('.latent-controls')) stop();
  }
  function key(event) {
    if (['Escape', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) stop();
  }
  function play() {
    if (timeline) return;
    resetIntroPlayback(playback, true);
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    const track = section.querySelector('.latent-intro-track');
    const end = () => Math.max(0, window.scrollY + track.getBoundingClientRect().bottom - window.innerHeight);
    const position = { y: window.scrollY };
    const move = () => window.scrollTo({ top: position.y, behavior: 'instant' });
    draw(true);
    window.addEventListener('wheel', interrupt, { passive: true });
    window.addEventListener('touchstart', interrupt, { passive: true });
    window.addEventListener('keydown', key);
    timeline = gsap.timeline({ onComplete: stop })
      .to(position, { y: end, duration: 5, ease: 'power1.inOut', onUpdate: move })
      .addPause('+=0.35', () => {
        // Mobile browser chrome can change the viewport height during the approach.
        position.y = end(); move();
        waitForPlayback(playback, 'portrait', () => timeline?.resume());
      })
      .call(() => { playback.releasing = true; draw(true); })
      .to(playback, { release: 1, duration: 0.3, ease: 'power1.in' })
      .addPause('>', () => waitForPlayback(playback, 'drop', () => timeline?.resume()))
      .call(() => { playback.handingOff = true; })
      .to(position, { y: () => window.scrollY + document.getElementById('app').getBoundingClientRect().top, duration: 1.35, ease: 'power2.inOut', onUpdate: move });
  }
  draw(false);
  return { play, stop };
}
