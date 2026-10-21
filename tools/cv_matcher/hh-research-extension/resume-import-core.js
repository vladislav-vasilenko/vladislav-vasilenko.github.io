(function(root) {
  const googleDoc = value => {
    const u=new URL(value);
    const m=u.pathname.match(/^\/document\/d\/([A-Za-z0-9_-]{10,200})(?:\/|$)/);
    if(u.protocol!=="https:"||u.hostname!=="docs.google.com"||!m) throw new Error("Нужна ссылка docs.google.com/document/d/…");
    return {id:`gdoc_${m[1]}`,source_type:"google_docs",url:`https://docs.google.com/document/d/${m[1]}/edit`,export_url:`https://docs.google.com/document/d/${m[1]}/export?format=txt`};
  };
  function redactContacts(text) {
    return String(text||"").replace(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g,"[email скрыт]")
      .replace(/(?:\+\d[\d ()–-]{8,}\d)/g,m=>{const n=m.replace(/\D/g,"").length;return n>=10&&n<=15?"[телефон скрыт]":m;});
  }
  async function documentSnapshot(candidate,text,title) {
    text=redactContacts(text).trim();title=String(title||candidate.title||"").trim();
    if(!title||ResumeSync.normalize(text).length<100) throw new Error("В резюме слишком мало текста. Проверь извлечение.");
    if(text.length>250000) throw new Error("Документ слишком велик для резюме.");
    const now=new Date().toISOString();
    return {...candidate,title,sections:[{key:"document",heading:"Резюме",text}],quality:"full",
      source_type:candidate.source_type,source_url:candidate.source_url||candidate.url||"",
      captured_at:candidate.captured_at||now,checked_at:candidate.captured_at||now,reviewed_at:now,
      content_hash:await ResumeSync.contentHash({title,sections:[{key:"document",heading:"Резюме",text}]})};
  }
  function selectPrimary(bundle,id) {
    if(!bundle?.resumes?.some(r=>r.id===id&&r.quality==="full")) throw new Error("Сначала загрузите и проверьте это резюме.");
    return {...bundle,schema_version:2,primary_id:id,primary_selection:"user",resumes:bundle.resumes.map(r=>({...r,role:r.id===id?"primary":"secondary"}))};
  }
  root.ResumeImports={googleDoc,redactContacts,documentSnapshot,selectPrimary};
})(globalThis);
