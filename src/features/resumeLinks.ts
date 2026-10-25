import type {Lang} from '../i18n';

/** Printing has a stable destination independent of the current theme, focus or scroll anchor. */
export function printResumeURL(href:string, lang:Lang):string {
 const url=new URL('/',href);
 url.searchParams.set('print','true');
 url.searchParams.set('lang',lang);
 return url.href;
}

export function introURL(href:string, lang:Lang):string {
 const url=new URL('/',href);
 url.searchParams.set('lang',lang);
 return url.href;
}
