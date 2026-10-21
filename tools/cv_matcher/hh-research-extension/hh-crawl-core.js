(function(root){
  function hhURL(value, kind) {
    const u=new URL(value);
    if(u.origin!=="https://hh.ru" || (kind==="search"?!/^\/search\/vacancy\/?$/.test(u.pathname):!/^\/vacancy\/\d+\/?$/.test(u.pathname))) throw new Error("Нужна страница поиска вакансий на https://hh.ru/search/vacancy");
    u.hash="";return u.href;
  }
  function limits(options={}) {
    const number=(v,def,max)=>Number.isInteger(Number(v))&&Number(v)>0?Math.min(Number(v),max):def;
    return {pages:number(options.pages,5,20),details:number(options.details,50,200),skip_closed:options.skip_closed!==false,force_details:options.force_details===true};
  }
  // HH adds a search session ID to pager links. It is analytics, not a user filter.
  const tracking=new Set(["page","from","hhtmFrom","hhtmFromLabel","search_session_id"]);
  function changedFilters(a,b) {
    a=new URL(hhURL(a,"search"));b=new URL(hhURL(b,"search"));
    return [...new Set([...a.searchParams.keys(),...b.searchParams.keys()])]
      .filter(key=>!tracking.has(key)&&JSON.stringify(a.searchParams.getAll(key).sort())!==JSON.stringify(b.searchParams.getAll(key).sort()));
  }
  function pageNumber(value) {
    const raw=new URL(hhURL(value,"search")).searchParams.get("page");
    if(raw!==null&&!/^\d+$/.test(raw)) throw new Error("Некорректный номер страницы HH.");
    const page=Number(raw||0);if(!Number.isSafeInteger(page)) throw new Error("Некорректный номер страницы HH.");return page;
  }
  function sameSearch(a,b) {try{return !changedFilters(a,b).length;}catch{return false;}}
  function samePage(a,b) {try{return sameSearch(a,b)&&pageNumber(a)===pageNumber(b);}catch{return false;}}
  function nextURL(current,candidate) {
    if(!candidate) return null;
    try {
      return sameSearch(current,candidate)&&pageNumber(candidate)===pageNumber(current)+1?hhURL(candidate,"search"):null;
    } catch{return null;}
  }
  const isClosed=row=>row?.archived===true||row?.availability==='closed';
  root.HHCrawl={isClosed,hhURL,limits,nextURL,sameSearch,samePage,changedFilters,pageNumber};
})(globalThis);
