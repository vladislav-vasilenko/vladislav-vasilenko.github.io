import { createRoot } from 'react-dom/client';
import LionheadDitDiffusion from './components/LionheadDitDiffusion.jsx';
import './latentIntro.css';

/**
 * Lazy-loaded by main.ts: the track scrolls noise into the portrait, then across the fade the cubes fly into
 * the CV header avatar (the same photo), so the intro hands over to the resume without a hard cut.
 */
export function mountLatentIntro(section) {
  const dock = { trigger: section.querySelector('.latent-intro-fade'), endTrigger: document.getElementById('app'), target: '.minimal-header img' };
  createRoot(section.querySelector('.latent-intro-stage')).render(<LionheadDitDiffusion trigger={section.querySelector('.latent-intro-track')} dock={dock} />);
}
