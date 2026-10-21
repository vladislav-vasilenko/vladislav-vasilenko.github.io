(function(root) {
  const CATALOG_URL = "https://hh.ru/applicant/profile/me";
  function resumeLink(href, base=CATALOG_URL) {
    try {
      const u = new URL(href, base);
      const direct = u.pathname.match(/^\/resume\/([a-f0-9]{32,64})\/?$/i)?.[1];
      const queryId = u.pathname.replace(/\/$/, "") === "/search/vacancy" ? u.searchParams.get("resume") : "";
      const idValue = direct || queryId || "";
      const m = idValue.match(/^([a-f0-9]{32,64})$/i);
      if (u.protocol !== "https:" || u.hostname !== "hh.ru" || !m) return null;
      const id=m[1].toLowerCase();
      return {id,url:`https://hh.ru/resume/${id}`};
    } catch {return null;}
  }
  function cardTitle(raw) {
    return String(raw||"").replace(/\s+/g," ").trim()
      .replace(/^(?:постоянная работа(?:,\s*подработка)?|подработка)\s*/i,"")
      .split(/Уровень дохода|Многие не видят ваше резюме|Гибрид,|На месте работодателя|Можно удалённо/i)[0].trim();
  }
  function cleanCatalog(entries, policy) {
    const rows=new Map();
    for (const e of entries) {
      const link=resumeLink(e.url);
      const title=String(e.title||"").replace(/\s+/g," ").trim();
      if (!link || !title || /^(редактировать|поднять|просмотры|приглашения|edit|views)$/i.test(title)) continue;
      const row={...link,title,label:title,source_type:"hh",role:link.id===policy.primary_id?'primary':'secondary',enabled:true};
      const previous=rows.get(link.id);
      if (!previous || title.length > previous.title.length) rows.set(link.id,row);
    }
    if (!rows.size) throw new Error("В каталоге не найдены резюме. Проверь вход в HH и загрузку раздела «Мои резюме».");
    return [...rows.values()];
  }
  function syncPlan(catalog, policy) {
    const primary=catalog.find(r=>r.id===policy.primary_id);
    return [...(primary?[primary]:[]),...catalog.filter(r=>r.id!==primary?.id)];
  }
  root.ResumeCatalog={CATALOG_URL,resumeLink,cardTitle,cleanCatalog,syncPlan};
})(globalThis);
