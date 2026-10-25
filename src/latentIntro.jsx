import { createRoot } from 'react-dom/client';
import LionheadDitDiffusion from './components/LionheadDitDiffusion.jsx';
import './latentIntro.css';

/** Lazy-loaded by main.ts: mounts the animation into the static #latent-intro section above the CV. */
export function mountLatentIntro(section) {
  createRoot(section.querySelector('.latent-intro-stage')).render(<LionheadDitDiffusion contained trigger={section} />);
}
