(async()=>{
  try {
    const source=ResumeImports.googleDoc(location.href);
    let response;
    try {response=await fetch(source.export_url,{credentials:"include",cache:"no-store",signal:AbortSignal.timeout(20000)});}
    catch {response=await fetch(source.export_url,{credentials:"omit",cache:"no-store",signal:AbortSignal.timeout(20000)});}
    if(!response.ok) throw new Error(`Google Docs: HTTP ${response.status}. Проверь доступ к документу.`);
    const mime=response.headers.get("content-type")||"";
    if(!/text\/plain/i.test(mime)) throw new Error("Google вернул не текст документа. Войди в аккаунт или скачай документ как TXT и загрузи файлом.");
    const text=await response.text();
    if(text.length<100||text.length>250000) throw new Error("Не удалось получить полный текст резюме допустимого размера.");
    const title=document.title.replace(/\s*[-–]\s*Google (?:Docs|Документы).*$/i,"").trim();
    return {candidate:{...source,title,source_url:source.url,text:ResumeImports.redactContacts(text),
      captured_at:new Date().toISOString(),extraction_method:"google_docs_txt_export",warnings:[]}};
  } catch(error) {return {error:error.message};}
})();
