(async()=>{try{
 const config=globalThis.__careerFieldAction;delete globalThis.__careerFieldAction;
 if(config?.action==='prepare_resume_link')return await CareerForms.prepareResumeLink(document,location.href);
 if(config?.action==='prepare_profile')return await CareerForms.prepareProfile(document,location.href,config);
 return config?.action==='fill'?await CareerForms.fillApproved(document,location.href,config):CareerForms.inspect(document,location.href).snapshot;
}catch(e){return {state:'read_error',error:e.message||'Не удалось распознать поля анкеты.',code:e.code||'form_read_failed',retryable:e.retryable===true};}})();
