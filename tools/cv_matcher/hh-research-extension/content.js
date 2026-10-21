/* Reads rendered vacancy content only, on an explicit popup action. */
(() => {
  "use strict";
  const clean = (text) => (text || "").replace(/\s+/g, " ").trim();
  const visible = (element) => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const text = (root, selector) => {
    const element = [...root.querySelectorAll(selector)].find(visible);
    return element ? clean(element.innerText) : "";
  };
  const descriptionText = element => {
    if(!element)return '';
    const tidy=value=>String(value||'').replace(/\r\n?/g,'\n').replace(/[^\S\n]+/g,' ').replace(/ *\n */g,'\n').replace(/\n{3,}/g,'\n\n').trim();
    const read=node=>{
      if(node.nodeType===3)return String(node.textContent||'').replace(/\s+/g,' ');
      if(node.nodeType!==1)return '';
      const tag=node.tagName,style=getComputedStyle(node);
      if(/^(SCRIPT|STYLE|FORM|INPUT|TEXTAREA|SELECT|BUTTON|NAV|FOOTER)$/.test(tag)||style.display==='none'||style.visibility==='hidden')return '';
      if(tag==='BR')return '\n';
      const value=[...node.childNodes].map(read).join('');
      if(tag==='LI')return '- '+value.trim()+'\n';
      if(/^H[1-6]$/.test(tag))return '\n\n## '+value.trim()+'\n\n';
      if(/^(P|DIV|SECTION|ARTICLE|UL|OL|BLOCKQUOTE)$/.test(tag))return '\n\n'+value+'\n\n';
      return value;
    };
    // Plain text fallback also preserves line breaks for older page structures.
    return tidy(element.childNodes?.length?read(element):element.innerText);
  };
  const vacancyUrl = (href) => {
    try {
      const url = new URL(href, location.href);
      if (!(url.hostname === "hh.ru" || url.hostname.endsWith(".hh.ru"))) return null;
      const match = url.pathname.match(/^\/vacancy\/(\d+)\/?$/);
      return match ? {id: `hh_${match[1]}`, link: `https://hh.ru/vacancy/${match[1]}`} : null;
    } catch { return null; }
  };
  const collectedAt = new Date().toISOString();
  if([...document.querySelectorAll('form[action*="captcha"], [data-qa="captcha"], [data-qa="account-login-form"], form[action*="/account/login"]')].some(visible) || /captcha|\/account\/login/.test(location.pathname) || /доступ ограничен|подтвердите, что вы не робот/i.test(document.querySelector('h1')?.innerText||"")) {
    return {vacancies:[],blocked:true,warning:"HH ограничил доступ или требует вход. Проверь открытую вкладку и запусти сбор снова вручную."};
  }
  const base = {source: "hh_browser", collector:"chrome_extension",adapter_id:"hh",adapter_version:"hh-dom-v2", collected_at: collectedAt, source_page: location.href,
    origin_query: new URL(location.href).searchParams.get("text") || ""};
  const own = vacancyUrl(location.href);
  if (own) {
    const archived=[...document.querySelectorAll('[data-qa="vacancy-archive-message"]')].some(visible);
    const title = text(document, '[data-qa="vacancy-title"], h1')||(archived?'Вакансия '+own.id.slice(3):'');
    const description = archived ? '' : descriptionText([...document.querySelectorAll('[data-qa="vacancy-description"], [itemprop="description"]')].find(visible));
    if (!title) return {vacancies: [], warning: "Название вакансии не найдено. Возможно, страница ещё не загрузилась."};
    const company = text(document, '[data-qa="vacancy-company-name"], [data-qa="vacancy-company-name-wrapper"]');
    const date = document.querySelector("time[datetime]")?.getAttribute("datetime") || "";
    return {page_kind:"detail",page_url:location.href,vacancies: [{...base, ...own, title, company: company || "HH.ru (работодатель не определён)",
      description, pub_date: date, description_quality: description ? "full" : "missing",
      locations: [text(document, '[data-qa="vacancy-view-raw-address"], [data-qa="vacancy-view-location"]')].filter(Boolean),
      archived}],
      warning: archived ? "Вакансия в архиве HH. Полное описание не собирается." : description ? "" : "Описание не найдено; запись требует повторного открытия полной вакансии."};
  }
  if (!location.pathname.startsWith("/search/vacancy") && !location.pathname.startsWith("/vacancies/")) {
    return {vacancies: [], warning: "Открой страницу поиска или полную вакансию. Другие страницы не читаются."};
  }
  const vacancies = new Map();
  for (const anchor of document.querySelectorAll('a[href*="/vacancy/"]')) {
    if (!visible(anchor)) continue;
    const job = vacancyUrl(anchor.href);
    const title = clean(anchor.innerText);
    if (!job || !title || vacancies.has(job.id)) continue;
    const card = anchor.closest('[data-qa="vacancy-serp__vacancy"], [data-qa="vacancy-serp__vacancy_standard"], [data-qa="vacancy-serp__vacancy-body"], article');
    const company = card ? text(card, '[data-qa="vacancy-serp__vacancy-employer"], [data-qa="vacancy-serp__vacancy-employer-text"], a[href*="/employer/"]') : "";
    const snippet = card ? text(card, '[data-qa="vacancy-serp__vacancy_snippet_requirement"], [data-qa="vacancy-serp__vacancy_snippet_responsibility"]') : "";
    vacancies.set(job.id, {...base, ...job, title, company: company || "HH.ru (работодатель не определён)",
      description: snippet, pub_date: "", description_quality: "snippet"});
  }
  const currentPage=Number(new URL(location.href).searchParams.get("page")||0);
  const next=[...document.querySelectorAll('a[href*="page="]')].filter(a=>{
    if(!visible(a)) return false;
    try {const u=new URL(a.href); return u.origin===location.origin&&u.pathname===location.pathname&&Number(u.searchParams.get("page"))===currentPage+1;} catch{return false;}
  });
  const empty=Boolean(document.querySelector('[data-qa="vacancy-serp__no-found"], [data-qa="vacancy-serp__no-vacancies"]'));
  return {page_kind:"listing",page_url:location.href,empty,layout_unknown:!empty&&!vacancies.size,diagnostics:{adapter_version:"hh-dom-v2",vacancies:vacancies.size,empty_marker:empty},next_page:next[0]?.href||null,next_pages:[...new Set(next.map(a=>a.href))],vacancies: [...vacancies.values()], warning: "Это карточки из загруженной выдачи. Открой нужные вакансии и сохрани полные описания перед оценкой по резюме."};
})();
