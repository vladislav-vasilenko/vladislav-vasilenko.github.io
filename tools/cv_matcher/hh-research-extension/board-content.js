/* Runs only after the user clicks Collect. Never reads inputs or response forms. */
(() => {
  const config = globalThis.__jobBoardConfig || {};
  const clean = s => (s || "").replace(/\s+/g, " ").trim();
  const visible = e => e && getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility !== "hidden" && e.getClientRects().length > 0;
  const text = (selector, root = document) => [...root.querySelectorAll(selector)].filter(visible).map(e => clean(e.innerText)).filter(Boolean).join("\n\n");
  const host = location.hostname;
  if (host === "hh.ru" || host.endsWith(".hh.ru")) return {vacancies: [], warning: "Для HH используется отдельный адаптер."};
  const adapter=globalThis.JobBoardAdapters?.resolve(location.href);
  const known=!!adapter,native=!!adapter&&JobBoardAdapters.registry.some(a=>a.id===adapter.id);
  const pageText=clean(document.body?.innerText);
  if(/captcha|доступ ограничен|access denied|проверка браузера/i.test(document.title)||/^(?:Подтвердите, что вы не робот|Доступ ограничен)/i.test(pageText))return {vacancies:[],blocked:true,warning:"Источник ограничил доступ. Проверьте открытую вкладку."};
  const company = config.company || adapter?.label || host;
  const base = {source: "job_board_browser", source_page: location.href, collected_at: new Date().toISOString(), company, pub_date: "", collector:"chrome_extension", adapter_id:adapter?.id||"generic",board_id:adapter?.board_id||"generic",adapter_version:globalThis.JobBoardAdapters?.version||"generic-v1"};
  const own = JobBoards.identity(location.href);
  const locationRows=(obj)=>[obj.jobLocation||[]].flat().map(item=>{const a=item?.address||item;return typeof a==='string'?a:[a?.addressLocality,a?.addressRegion,typeof a?.addressCountry==='string'?a.addressCountry:a?.addressCountry?.name].filter(Boolean).join(', ');}).filter(Boolean);
  if(own){
    base.locations=[...new Set([...document.querySelectorAll('[itemprop="jobLocation"],[data-qa*="vacancy-location"],[class*="vacancy-location" i]')].filter(visible).map(n=>clean(n.innerText)).filter(v=>v&&v.length<500))];
    for(const node of document.querySelectorAll('script[type="application/ld+json"]')){try{const walk=obj=>{if(!obj||typeof obj!=='object')return;if([obj['@type']].flat().includes('JobPosting')){const same=JobBoards.identity(obj.url||location.href,location.href);if(same?.id===own.id){const loc=locationRows(obj);if(loc.length)base.locations=loc;if(obj.jobLocationType==='TELECOMMUTE')base.work_formats=['remote'];}}if(Array.isArray(obj))obj.forEach(walk);else Object.values(obj).filter(v=>typeof v==='object').forEach(walk);};walk(JSON.parse(node.textContent));}catch{}}
  }
  if(own&&/вакансия (?:закрыта|в архиве|неактуальна)|при[её]м откликов (?:заверш[её]н|закрыт)/i.test(pageText))return {page_kind:'detail',page_url:location.href,vacancies:[{...base,...own,title:text('h1')||'Закрытая вакансия',description:'',description_quality:'snippet',archived:true,availability_checked_at:new Date().toISOString()}]};
  if(own){base.archived=false;base.availability_checked_at=new Date().toISOString();}
  let selector = config.description_selector || adapter?.description || "";
  const title = text(config.title_selector || "h1") || (adapter?.id==='tbank'?clean(document.title).match(/^Вакансия\s+(.+?)\s*\|\s*Т[‑-]Банк/i)?.[1]||'':'');
  // T-Bank's current hero is not an h1. Read bounded named sections,
  // stopping at the next heading so the application and related jobs stay out.
  if(adapter?.id==='tbank'&&own&&title&&config.mode!=='listing'&&!config.description_selector){
    const headings=[...document.querySelectorAll('h2,h3')].filter(visible),parts=[],labels=new Set();
    for(let i=0;i<headings.length;i++){
      const label=clean(headings[i].innerText);if(!/^(?:Описание|Обязанности|Требования|Мы предлагаем)$/i.test(label))continue;
      if(!headings[i+1])continue;
      const range=document.createRange();range.setStartAfter(headings[i]);range.setEndBefore(headings[i+1]);
      const block=document.createElement('div');block.append(range.cloneContents());block.querySelectorAll('form,input,textarea,select,button,nav,footer,script,style,[data-cv-matcher-badges]').forEach(n=>n.remove());
      const value=clean(block.textContent);if(value.length<30)continue;labels.add(label.toLowerCase());parts.push(label+'\n'+value);
    }
    if(labels.has('обязанности')&&labels.has('требования')&&parts.join('\n').length>150)return {adapter:adapter.id,page_kind:'detail',page_url:location.href,vacancies:[{...base,...own,title,description:parts.join('\n\n'),description_quality:labels.has('описание')&&labels.has('мы предлагаем')?'full':'needs_review',extraction_method:'tbank_named_sections',...(/\/moscow\//.test(location.pathname)?{locations:['Москва']}:{})}]};
  }
  if (selector && title && (known ? own : config.mode === "detail")) {
    // A configured element can accidentally include a form: strip those before reading.
    const descriptions = [...document.querySelectorAll(selector)].filter(visible).map(e => {
      const clone = e.cloneNode(true);
      clone.querySelectorAll("form,input,textarea,select,button,nav,footer,script,style").forEach(n => n.remove());
      return clean(clone.textContent);
    }).filter(Boolean);
    const description = descriptions.join("\n\n");
    if (description.length > 150) return {adapter:adapter?.id,page_kind:"detail",page_url:location.href,vacancies: [{...base, ...own, title, description,
      description_quality: known && !config.description_selector && !adapter.custom_selectors ? "full" : "needs_review",
      extraction_method: "dom_selector", extraction_selector: selector}], warning: known && !config.description_selector && !adapter.custom_selectors ? "" : "Проверь границы описания: пользовательский селектор требует проверки перед ранжированием."};
  }
  // Structured JobPosting also supports first-party boards when their DOM changes.
  // Generic structural schema works for many ATS boards without a custom adapter.
  if (config.mode !== "listing") {
    const jobs = [];
    const walk = obj => {
      if (!obj || typeof obj !== "object") return;
      if ([obj["@type"]].flat().includes("JobPosting") && obj.title && obj.description) {
        const parsed = new DOMParser().parseFromString(obj.description, "text/html");
        parsed.querySelectorAll("script,style,form").forEach(n=>n.remove());
        const job = JobBoards.identity(obj.url || location.href, location.href);
        if (job && (!known||(own&&job.id===own.id&&clean(obj.title).toLowerCase()===title.toLowerCase()))) jobs.push({...base, ...job, title: clean(obj.title), company: clean(obj.hiringOrganization?.name) || company,
          description: clean(parsed.body.textContent), description_quality: known&&pageText.includes(clean(parsed.body.textContent).slice(0,80))&&pageText.includes(clean(parsed.body.textContent).slice(-80))?"full":"needs_review", extraction_method: "schema_jobposting", pub_date: obj.datePosted || "", locations: locationRows(obj), ...(obj.jobLocationType==='TELECOMMUTE'?{work_formats:['remote']}: {})});
      }
      if (Array.isArray(obj)) obj.forEach(walk); else Object.values(obj).filter(v=>typeof v === "object").forEach(walk);
    };
    document.querySelectorAll('script[type="application/ld+json"]').forEach(e=>{try {walk(JSON.parse(e.textContent));} catch {}});
    if (jobs.length) return {adapter:adapter?.id,page_kind:"detail",page_url:location.href,vacancies: jobs, warning: "JobPosting извлечён. Сверь описание с видимой вакансией; до проверки он не участвует в оценке."};
  }
  if(known&&own&&!own.id.startsWith("board_")&&title&&config.mode!=="listing"){
    const sections=new Set();
    for(const heading of document.querySelectorAll('h2,h3')){
      if(!visible(heading)||!/(?:описание|обязанност|требован|мы ждем|мы ждём|задачи|предстоит|заниматься|ожидаем|requirements|responsibilities)/i.test(clean(heading.innerText)))continue;
      let block=heading.parentElement;
      for(let depth=0;block&&depth<4;depth++,block=block.parentElement){
        if(/^(?:BODY|MAIN|FORM)$/.test(block.tagName)||block.querySelectorAll('h2,h3').length>3)break;
        if(clean(block.innerText).length<150)continue;
        const clone=block.cloneNode(true);clone.querySelectorAll('form,input,textarea,select,button,nav,footer,script,style').forEach(n=>n.remove());sections.add(clean(clone.textContent));break;
      }
    }
    const description=[...sections].join('\n\n');
    if(description.length>150)return {adapter:adapter.id,page_kind:'detail',page_url:location.href,vacancies:[{...base,...own,title,description,description_quality:'needs_review',extraction_method:'semantic_sections'}],warning:'Разделы вакансии прочитаны. Проверьте полноту текста и подтвердите описание перед ранжированием.'};
    return {adapter:adapter.id,page_kind:'detail',page_url:location.href,vacancies:[],warning:'Страница вакансии распознана, но полное описание не найдено. Возможно, структура изменилась или текст ещё не загрузился.'};
  }
  if(adapter?.id==='ozon'&&!own&&/Найдено:\s*0\s*ваканси/i.test(pageText))return {adapter:adapter.id,page_kind:'listing',page_url:location.href,empty:true,vacancies:[],next_pages:[]};
  const rows = new Map();
  const anchors = document.querySelectorAll(config.link_selector || adapter?.linkSelector || 'a[href]');
  for (const a of anchors) {
    if (!visible(a) || a.closest("nav,footer,form")) continue;
    const job = JobBoards.identity(a.href, location.href);
    const heading=JobBoardAdapters.titleNode(a,adapter);
    const title = clean((heading||a).innerText);
    const genericCandidate = /\/(?:vacanc(?:y|ies)|jobs?|positions?|careers?|openings?)\/.+/i.test(new URL(a.href, location.href).pathname);
    if (known&&JobBoardAdapters.resolve(job?.link)?.id!==adapter.id)continue;
    if (!job || !title || (!known && !config.link_selector && !genericCandidate)) continue;
    if (native && job.id.startsWith("board_")) continue;
    rows.set(job.id, {...base, ...job, title, description: "", description_quality: "snippet", extraction_method: "listing_link"});
  }
  const nextPages=[...document.querySelectorAll('a[rel="next"],a[aria-label*="следующ" i],a[aria-label*="next" i],a[class*="next" i]')].filter(visible).map(a=>a.href).filter(url=>globalThis.JobBoardAdapters?.nextURL(location.href,url));
  return {adapter:adapter?.id,page_kind:'listing',page_url:location.href,next_pages:nextPages,vacancies: [...rows.values()], warning: rows.size ? "Сохранены ссылки из загруженной выдачи. Открой полные вакансии и собери описания." : "Вакансии не распознаны. Укажи CSS-селекторы ссылок/описания для этого сайта. В iframe открой источник в отдельной вкладке."};
})();
