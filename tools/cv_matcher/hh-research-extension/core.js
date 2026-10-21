/* Shared pure helpers; also usable from Node for offline verification. */
(function (root) {
  "use strict";
  function quote(value) {
    return '"' + value.replace(/["\\]/g, " ").trim() + '"';
  }
  function buildQuery(profile, options) {
    const track = profile.tracks.find((item) => item.id === options.track);
    const companies = profile.companies.filter((item) =>
      options.company ? item.id === options.company : item.tier === options.tier);
    if (!track || !companies.length) throw new Error("Не выбран профиль поиска.");
    const aliases = [...new Set(companies.flatMap((item) => item.aliases))];
    return `COMPANY_NAME:(${aliases.map(quote).join(" OR ")}) AND (${track.query})`;
  }
  function buildUrl(profile, options) {
    const location = profile.locations.find((item) => item.id === options.location);
    if (!location) throw new Error("Не выбрано место работы.");
    const params = new URLSearchParams({
      text: buildQuery(profile, options), order_by: "publication_time", ...location.params
    });
    if (options.daily) params.set("search_period", "3");
    return "https://hh.ru/search/vacancy?" + params.toString();
  }
  const detailCacheMs=24*60*60*1000;
  const normalized=value=>String(value||'').replace(/\s+/g,' ').trim();
  function listingStamp(row) {
    return Object.fromEntries(['title','company','description','pub_date'].filter(k=>normalized(row?.[k])&&(k!=='company'||!/не определ[её]н/.test(row[k]))).map(k=>[k,normalized(row[k])]));
  }
  function detailFresh(row,{force=false,now=Date.now()}={}) {
    const at=Date.parse(row?.description_fetched_at||row?.collected_at),age=now-at;
    return !force&&row?.description_quality==='full'&&!!normalized(row.description)&&row.archived!==true&&row.availability!=='closed'&&!row.description_dirty&&Number.isFinite(at)&&age>=0&&age<detailCacheMs;
  }
  function mergeVacancies(existing, incoming) {
    const byId = new Map(existing.map((item) => [item.id, item]));
    for (const item of incoming) {
      if (!/^(hh_\d+|avito_\d+|ozon_[\w-]+|yandex_\d+|sber_\d+|tbank_[a-f\d-]+|board_.+)$/.test(item.id || "") || !item.link?.startsWith("https://")) continue;
      const previous = byId.get(item.id);
      // A SERP snippet must never replace a previously captured complete JD.
      const full = previous?.description_quality === "full" && item.description_quality !== "full";
      const merged = full ? {...previous, last_seen_at: item.collected_at,...(item.archived===true?{archived:true,availability_checked_at:item.availability_checked_at||item.collected_at,collected_at:item.collected_at,source_page:item.source_page}:{})} : {
        ...previous, ...item, first_seen: previous?.first_seen || item.collected_at,
        last_seen_at: item.collected_at
      };
      if(item.description_quality==='full'&&normalized(item.description)){
        merged.description_fetched_at=item.description_fetched_at||item.collected_at;
        merged.description_dirty=false;delete merged.listing_changed_at;
        if(item.listing_snapshot)merged.listing_snapshot=item.listing_snapshot;
      }else if(full&&item.archived!==true){
        // Seeing a snippet refreshes availability, never the full-text timestamp.
        merged.description_fetched_at=previous.description_fetched_at||previous.collected_at;
        if(item.listing_verified_at)merged.listing_verified_at=item.listing_verified_at;
        const incoming=listingStamp(item),baseline=previous.listing_snapshot||listingStamp({...previous,description:''});
        const changed=Object.keys(incoming).some(k=>baseline[k]&&baseline[k]!==incoming[k]);
        merged.listing_snapshot=incoming;
        if(changed){merged.description_dirty=true;merged.listing_changed_at=item.collected_at;}
      }
      const recommendedFor=[...new Set([...(previous?.recommended_for||[]),...(item.recommended_for||[])])];
      if(recommendedFor.length) merged.recommended_for=recommendedFor;
      byId.set(item.id, merged);
    }
    return [...byId.values()];
  }
  function recommendationUrl(resumeId) {
    if(!/^[a-f0-9]{38}$/i.test(resumeId||"")) throw new Error("Выберите резюме HH. Рекомендации HH недоступны для файлов и Google Docs.");
    return "https://hh.ru/search/vacancy?"+new URLSearchParams({resume:resumeId});
  }
  function recommendationResume(url) {
    try {const u=new URL(url);const id=u.searchParams.get('resume');return u.origin==='https://hh.ru'&&/^\/search\/vacancy\/?$/.test(u.pathname)&&/^[a-f0-9]{38}$/i.test(id||'')?id:null;}catch{return null;}
  }
  function markSearchSource(rows,url) {
    const resume=recommendationResume(url);
    return resume?rows.map(row=>({...row,recommended_for:[...new Set([...(row.recommended_for||[]),resume])]})):rows;
  }
  const api = {buildQuery, buildUrl, mergeVacancies,detailFresh,listingStamp,detailCacheMs,recommendationUrl,recommendationResume,markSearchSource};
  root.ResearchSearch = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
