const MODES = ['binary', 'galaxy', 'dna'];
const KEY = 'portfolio.intro-orbit';

/** A fresh composition per visit, without a timer or an immediate repeat in this tab. */
export function chooseVisitOrbit(storageProvider = () => window.sessionStorage, random = Math.random) {
  let storage, previous;
  try { storage = storageProvider(); previous = storage?.getItem(KEY); } catch { /* Private storage may be blocked. */ }
  const choices = MODES.filter(mode => mode !== previous);
  const mode = choices[Math.floor(random() * choices.length)];
  try { storage?.setItem(KEY, mode); } catch { /* The scene also works without persistence. */ }
  return mode;
}
