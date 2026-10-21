/* Bounded navigation. Read workers need the committed document, not analytics. */
async function navigate(tabId, url, {readReady=true, shouldStop=()=>false, timeoutMs}={}) {
  await new Promise((resolve,reject)=>{
    let settled=false,poll,busy=false,accepted=false;
    const timeout=timeoutMs??(new URL(url).hostname==='hh.ru'?25000:readReady?60000:25000);
    const matches=value=>{
      try {
        if(!JobBoardAdapters.sameSource(url,value))return false;
        const a=new URL(url),b=new URL(value);
        // Verified Yandex migration preserves the single ML profession. Never
        // accept another profession, dropped filters, foreign origin or detail.
        const yandex=u=>{if(['yandex.ru','yandex.com'].includes(u.hostname)&&u.pathname==='/jobs/vacancies'&&[...u.searchParams].length===1&&u.searchParams.get('professions')==='ml-developer'){u.pathname='/jobs/professions/ml-developer';u.search='';}return u;};
        yandex(a);yandex(b);
        if(a.hostname==='hh.ru'&&/^\/search\/vacancy\/?$/.test(a.pathname))return HHCrawl.samePage(url,value);
        const expected=JobBoards.identity(a.href);
        return expected?JobBoards.identity(value)?.id===expected.id:a.pathname===b.pathname&&a.search===b.search;
      }catch{return false;}
    };
    const done=error=>{
      if(settled)return;settled=true;clearTimeout(timer);clearTimeout(poll);
      chrome.tabs.onUpdated.removeListener(listener);
      error?reject(error):resolve();
    };
    const probe=async()=>{
      if(settled||busy||!accepted)return;
      if(shouldStop()){done(new Error('Сбор остановлен или достигнут лимит времени.'));return;}
      busy=true;
      try {
        const tab=await chrome.tabs.get(tabId);
        if(settled)return;
        // A pending URL still belongs to the previous document.
        if(!tab.pendingUrl&&matches(tab.url)) {
          if(tab.status==='complete'){done();return;}
          if(readReady){
            const value=(await chrome.scripting.executeScript({target:{tabId},func:()=>{
              const body=document.body;
              const blocked=/captcha|\/account\/login/.test(location.pathname)||!!document.querySelector('form[action*="captcha"], [data-qa="captcha"]')||/доступ ограничен|подтвердите, что вы не робот/i.test(document.querySelector('h1')?.innerText||'');
              let ready=document.readyState!=='loading'&&!!body&&body.innerText.length>150;
              if(location.hostname==='hh.ru'){
                if(/^\/search\/vacancy\/?$/.test(location.pathname))ready=!!document.querySelector('a[data-qa*="serp-item__title"], [data-qa="vacancy-serp__vacancy"], [data-qa="vacancy-serp__vacancy-body"], [data-qa="vacancy-serp__no-found"], [data-qa="vacancy-serp__no-vacancies"]');
                else if(/^\/vacancy\/\d+\/?$/.test(location.pathname))ready=!!document.querySelector('[data-qa="vacancy-description"], [data-qa="vacancy-archive-message"]');
              }
              return {url:location.href,ready,text:!!body&&body.innerText.length>0,blocked};
            }}))[0]?.result;
            if(value?.blocked)throw new Error('HH ограничил доступ или требует вход. Проверьте открытую вкладку.');
            if(value?.ready&&value.text&&matches(value.url))done();
          }
        } else if(new URL(url).hostname==='hh.ru'&&/captcha|\/account\/login/.test(new URL(tab.url).pathname)) {
          done(new Error('HH ограничил доступ или требует вход. Проверьте открытую вкладку.'));
        }
      }catch(error){
        if(/HH ограничил|No tab with id|Invalid tab ID|No tab with given id/i.test(error.message))done(error);
        // A frame may disappear during a normal redirect; retry within the deadline.
      }finally{busy=false;}
    };
    const tick=()=>{
      if(settled)return;
      // Cancellation must work even when a Chrome API promise is pending.
      if(shouldStop()){done(new Error('Сбор остановлен или достигнут лимит времени.'));return;}
      void probe();poll=setTimeout(tick,400);
    };
    const listener=id=>{if(id===tabId)void probe();};
    const timer=setTimeout(()=>done(new Error('Страница не готова к чтению за '+timeout/1000+' секунд.')),timeout);
    chrome.tabs.onUpdated.addListener(listener);
    tick();
    chrome.tabs.update(tabId,{url}).then(()=>{accepted=true;void probe();}).catch(done);
  });
}
