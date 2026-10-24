/* URL identity shared by the popup and DOM collector. No network calls. */
(function (root) {
  function identity(href, base) {
    try {
      const u = new URL(href, base);
      if (u.protocol !== "https:") return null;
      const host = u.hostname.toLowerCase();
      const spa=(host==='app.mokahr.com'&&/^\/(social-recruitment|apply)\/[\w-]+\/\d+\/?$/.test(u.pathname)&&/^#\/job\/[a-f\d-]{36}$/i.test(u.hash))||(host==='zhaopin.kuaishou.cn'&&/^#\/official\/social\/job-info\/\d+$/.test(u.hash));
      if(spa){u.search='';u.pathname=u.pathname.replace(/\/$/,'')||'/';u.hash=u.hash.toLowerCase();return {id:'board_'+encodeURIComponent(u.href),link:u.href};}
      u.hash = "";
      let match;
      if (host === "hh.ru" || host.endsWith(".hh.ru")) {
        match = u.pathname.match(/^\/vacancy\/(\d+)\/?$/);
        return match ? {id: `hh_${match[1]}`, link: `https://hh.ru/vacancy/${match[1]}`} : null;
      }
      if (host === "career.avito.com") {
        match = u.pathname.match(/^\/vacancies\/[^/]+\/(\d+)\/?$/);
        return match ? {id: `avito_${match[1]}`, link: `${u.origin}${u.pathname.replace(/\/?$/, "/")}`} : null;
      }
      if (host === "ozon.tech") {
        match = u.pathname.match(/^\/vacancies\/([\da-f-]{36}|\d+)(?:-[^/]*)?\/?$/i);
        return match ? {id: `ozon_${match[1]}`, link: `${u.origin}${u.pathname}`} : null;
      }
      if (host === "career.ozon.ru") {
        const id = u.searchParams.get("id") || u.pathname.match(/-(\d+)\/?$/)?.[1];
        return id && /\/vacancy(?:\/|$)/.test(u.pathname) ? {id: `ozon_${id}`, link: u.href} : null;
      }
      if(host==='yandex.ru'||host==='yandex.com'){
        match=u.pathname.match(/^\/jobs\/vacancies\/(?:[^/]+-)?(\d+)\/?$/);
        return match?{id:'yandex_'+match[1],link:u.origin+u.pathname.replace(/\/$/,'')}:null;
      }
      if(host==='tbank.ru'||host==='www.tbank.ru'){
        match=u.pathname.match(/^\/career\/(?:(?:it|back-office|service)\/)?vacancy\/(?:[^/]+\/)*([a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12})\/?$/i);
        return match?{id:'tbank_'+match[1].toLowerCase(),link:'https://www.tbank.ru'+u.pathname}:null;
      }
      if(host==='rabota.sber.ru'){
        match=u.pathname.match(/^\/search\/(?:[^/]*-)?(\d{4,})\/?$/);
        return match?{id:'sber_'+match[1],link:u.origin+u.pathname.replace(/\/$/,'')}:null;
      }
      // Unknown boards use the whole canonical URL. Keep query identifiers.
      for (const key of [...u.searchParams.keys()]) {
        if (/^(utm_|hhtm|__rr|abt_)/.test(key)) u.searchParams.delete(key);
      }
      u.searchParams.sort();
      u.pathname = u.pathname.replace(/\/$/, "") || "/";
      const link = u.href;
      return {id: "board_" + encodeURIComponent(link), link};
    } catch { return null; }
  }
  async function canonicalRows(rows){return Promise.all(rows.map(async row=>{if(!row.id?.startsWith('board_'))return row;const job=identity(row.link);if(!job)return row;const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(job.link));return {...row,id:'board_'+[...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('').slice(0,24),link:job.link};}));}
  root.JobBoards = {identity,canonicalRows};
  if (typeof module !== "undefined" && module.exports) module.exports = root.JobBoards;
})(globalThis);
