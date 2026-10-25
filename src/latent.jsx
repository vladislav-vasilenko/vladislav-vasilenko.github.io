import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import LionheadDitDiffusion from './components/LionheadDitDiffusion.jsx';
import './latent.css';

const steps = [
  ['t = 1.00', 'Gaussian noise', 'Every cube is a latent token sampled from N(0, I). Move the cursor to perturb the field.'],
  ['dx/dt = vθ(x, t)', 'Flow matching', 'Scroll integrates the learned velocity field: straight ODE paths carry noise toward the data manifold.'],
  ['4 × 4 patches', 'DiT denoising', 'Patches attend jointly and lock in one step at a time, centre-out, until the latent decodes.'],
  ['t = 0.00', 'Decoded', 'A volumetric relief of the source frame. Shake it — the field pulls every token back.'],
];

function Page() {
  return (
    <main className="text-neutral-300">
      <LionheadDitDiffusion />
      {steps.map(([formula, title, body]) => (
        <section key={title} className="pointer-events-none relative z-[1] flex h-screen items-end px-4 pb-24 sm:px-10">
          <div className="max-w-xs">
            <p className="font-mono text-[11px] tracking-wide text-neutral-500">{formula}</p>
            <h2 className="mt-2 text-lg font-light tracking-tight text-neutral-100">{title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-neutral-400">{body}</p>
          </div>
        </section>
      ))}
      <a href="/" className="fixed top-4 left-4 z-10 font-mono text-[11px] tracking-wide text-neutral-500 transition-colors hover:text-neutral-100">
        &larr; Vladislav Vasilenko
      </a>
    </main>
  );
}

createRoot(document.getElementById('latent-root')).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
