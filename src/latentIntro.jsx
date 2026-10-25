import { createRoot } from 'react-dom/client';
import LionheadDitDiffusion from './components/LionheadDitDiffusion.jsx';
import './latentIntro.css';
import gsap from 'gsap';

/**
 * Lazy-loaded by main.ts. The finished portrait opens to the margins as the CV arrives.
 * The resume stays readable even during a fast scroll or a change of presentation style.
 */
export function mountLatentIntro(section) {
  const dock = { trigger: section.querySelector('.latent-intro-fade'), resume: '.minimal-portfolio', end: '.presentation-headline, .presentation-manifest-label, .minimal-intro' };
  const root = createRoot(section.querySelector('.latent-intro-stage'));
  const button = section.querySelector('[data-intro-play]');
  const playback = { release: 0, releasing: false };
  let timeline = null;
  const draw = (playing) => root.render(<LionheadDitDiffusion trigger={section.querySelector('.latent-intro-track')} dock={dock} playing={playing} playback={playback} onStop={stop} />);
  const removeListeners = () => {
    window.removeEventListener('wheel', interrupt);
    window.removeEventListener('touchstart', interrupt);
    window.removeEventListener('keydown', key);
  };
  function stop() {
    timeline?.kill(); timeline = null;
    playback.release = 0; playback.releasing = false;
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
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    const track = section.querySelector('.latent-intro-track');
    const end = Math.max(0, window.scrollY + track.getBoundingClientRect().bottom - window.innerHeight);
    const position = { y: window.scrollY };
    const move = () => window.scrollTo({ top: position.y, behavior: 'instant' });
    draw(true);
    window.addEventListener('wheel', interrupt, { passive: true });
    window.addEventListener('touchstart', interrupt, { passive: true });
    window.addEventListener('keydown', key);
    timeline = gsap.timeline({ onComplete: stop })
      .to(position, { y: end, duration: 5, ease: 'power1.inOut', onUpdate: move })
      .call(() => { playback.releasing = true; draw(true); }, [], '+=0.8')
      .to(playback, { release: 1, duration: 0.3, ease: 'power1.in' })
      .to(position, { y: () => window.scrollY + document.getElementById('app').getBoundingClientRect().top, duration: 1.35, ease: 'power2.inOut', onUpdate: move }, '+=1.2');
  }
  draw(false);
  return { play, stop };
}
