(function(root){
  async function call(path,body,token,timeout) {
    if(!["/health","/rank","/extract","/cover-letter","/applications","/answer-draft","/archive/company-settings","/archive/manifest","/archive/sync","/archive/open","/archive/restore","/archive/hh-badges","/archive/hh-inline","/archive/workflow"].includes(path)) throw new Error("Неизвестный метод локального сервиса.");
    let response;
    try {response=await fetch("http://127.0.0.1:8788"+path,{method:body?"POST":"GET",headers:{"Content-Type":"application/json","X-Resume-Import-Token":token},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(timeout)});}
    catch {throw new Error("Нет ответа локального сервиса. Запустите resume_import_server.py и оставьте эту вкладку открытой до завершения.");}
    const data=await response.json();if(response.status===404&&["/cover-letter","/archive/hh-inline","/archive/hh-badges"].includes(path)) throw new Error("Перезапустите resume_import_server.py: новые функции ещё не подключены к запущенному сервису.");if(!response.ok) throw new Error(typeof data.detail==="string"?data.detail:"Ошибка локального сервиса.");return data;
  }
  async function request(path,body,timeout=25000) {
    let {resume_import_token:token}=await chrome.storage.session.get("resume_import_token");
    if(!token){const saved=await chrome.storage.local?.get("remembered_resume_import_token");token=saved?.remembered_resume_import_token;}
    if(!token) throw new Error("Сначала подключите локальный сервис кодом из .cache/resume_import/token.txt.");
    return call(path,body,token,timeout);
  }
  async function connect(token,{remember=false}={}) {
    token=String(token||"").trim();if(!/^[A-Za-z0-9_-]{43}$/.test(token)) throw new Error("Скопируйте 43-символьный локальный код из token.txt. Ключ OpenAI здесь не используется.");
    if(!await chrome.permissions.request({origins:["http://127.0.0.1/*"]})) throw new Error("Доступ к локальному сервису не предоставлен.");
    const data=await call("/health",null,token,10000);
    if(!data.ok||data.service!=="cv-matcher-local") throw new Error("На порту 8788 отвечает другой сервис.");
    await chrome.storage.session.set({resume_import_token:token});
    if(remember)await chrome.storage.local.set({remembered_resume_import_token:token});
    else await chrome.storage.local?.remove("remembered_resume_import_token");
    chrome.runtime?.sendMessage({type:"workspace_bridge_register"}).catch(()=>{});return data;
  }
  root.LocalResumeService={connect,request};
})(globalThis);
