import type {Lang} from '../i18n';

/** Explicit navigation wins; a first visit otherwise follows the browser's preferred language. */
export function portfolioLanguage(url: string, preferred: readonly string[] = []): Lang {
  const location = new URL(url);
  const selected = location.searchParams.get('lang');
  if (selected === 'en' || selected === 'ru') return selected;
  if (/^\/ru(?:\/|$)/.test(location.pathname)) return 'ru';
  const first = preferred[0] || 'en';
  return /^(?:ru|uk|be|kk|ka|hy|uz|tk|ky|tg)(?:-|$)/i.test(first) ? 'ru' : 'en';
}
