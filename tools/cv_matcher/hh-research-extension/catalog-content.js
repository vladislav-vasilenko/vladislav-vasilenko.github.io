(() => {
  if (location.hostname !== "hh.ru" || location.pathname.replace(/\/$/, "") !== "/applicant/profile/me") {
    return {error:"Открой каталог резюме https://hh.ru/applicant/profile/me."};
  }
  const visible=e=>e&&getComputedStyle(e).display!=="none"&&getComputedStyle(e).visibility!=="hidden"&&e.getClientRects().length>0;
  const entries=[];
  for (const anchor of document.querySelectorAll('a[href*="/resume/"],a[href*="resume="]')) {
    if (!visible(anchor) || anchor.closest('nav,footer,header,form')) continue;
    const link=ResumeCatalog.resumeLink(anchor.href);
    if (!link) continue;
    let title=String(anchor.innerText||"").replace(/\s+/g," ").trim();
    if (new URL(anchor.href).pathname.replace(/\/$/, "")==="/search/vacancy") {
      title="";
      // Current HH catalog renders the title as a button and keeps the resume ID
      // in the adjacent 'N vacancies' link. Stay inside one card, never read profile text.
      let card=anchor.parentElement;
      for(let depth=0;card&&depth<12;depth++,card=card.parentElement) {
        const ids=new Set([...card.querySelectorAll('a[href*="resume="],a[href*="/resume/"]')]
          .map(a=>ResumeCatalog.resumeLink(a.href)?.id).filter(Boolean));
        if(ids.size>1) break;
        const button=[...card.querySelectorAll('button,[role="button"]')].filter(visible)
          .find(e=>/^(?:постоянная работа|подработка)(?:\s|,|$)/i.test(String(e.innerText||"").trim()));
        if(button) {title=ResumeCatalog.cardTitle(button.innerText);break;}
      }
    }
    if (title) entries.push({...link,title});
  }
  const more=[...document.querySelectorAll('button,a,[role="button"]')].some(e=>visible(e)&&/^(показать ещё|показать еще|загрузить ещё|загрузить еще|следующая страница)$/i.test(String(e.innerText||'').trim()));
  const loading=Boolean(document.querySelector?.('[aria-busy="true"]'));
  return entries.length?{entries,catalog_complete:!more&&!loading,checked_at:new Date().toISOString(),source_url:ResumeCatalog.CATALOG_URL}
    :{error:"Ссылки резюме не найдены в загруженном каталоге. Проверь вход в HH и загрузку страницы."};
})();
