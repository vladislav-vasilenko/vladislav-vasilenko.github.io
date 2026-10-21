(()=>{
 const result=state=>({state,url:location.href});
 const visible=n=>{const r=n.getBoundingClientRect(),s=getComputedStyle(n);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
 if([...document.querySelectorAll('input[name*="captcha"],iframe[src*="captcha"],[data-qa*="captcha"]')].some(visible)||[...document.querySelectorAll('h1')].some(n=>visible(n)&&/доступ ограничен|подтвердите, что вы не робот/i.test(n.innerText||'')))return result('captcha');
 if(/\/(?:account\/login|login)(?:\/|$)/.test(location.pathname)||[...document.querySelectorAll('input[type="password"]')].some(visible))return result('login');
 if([...document.querySelectorAll('a[href*="/applicant/resumes"],a[href*="/applicant/profile"],a[href*="/applicant/settings"],[data-qa="mainmenu_applicantProfile"],[data-qa="mainmenu_applicantResumes"]')].some(visible))return result('authenticated');
 if(location.pathname==='/applicant/negotiations'&&[...document.querySelectorAll('[data-qa="negotiations-item"],[data-qa="negotiations-list-item"],[data-qa="negotiations-list-item-wrapper"],[data-qa="negotiations-empty"],[data-qa="negotiations-list-empty"]')].some(visible))return result('authenticated');
 if(document.readyState!=='complete')return result('loading');
 return result('unknown');
})();
