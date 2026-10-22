interface InstallPrompt extends Event{prompt():Promise<void>;userChoice:Promise<{outcome:string}>}
let prompt:InstallPrompt|null=null,registration:ServiceWorkerRegistration|null=null,started=false;

function refresh(){
 const install=document.querySelector<HTMLButtonElement>('[data-pwa-install]'),update=document.querySelector<HTMLButtonElement>('[data-pwa-update]');
 if(install){install.hidden=!prompt||matchMedia('(display-mode: standalone)').matches;install.onclick=async()=>{if(!prompt)return;await prompt.prompt();await prompt.userChoice;prompt=null;refresh();};}
 if(update){update.hidden=!registration?.waiting;update.onclick=()=>{navigator.serviceWorker.addEventListener('controllerchange',()=>location.reload(),{once:true});registration?.waiting?.postMessage({type:'ACTIVATE_PORTFOLIO_UPDATE'});};}
}
export function initializePWA():void{
 refresh();if(started||!import.meta.env.PROD||!('serviceWorker' in navigator))return;started=true;
 window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();prompt=event as InstallPrompt;refresh();});window.addEventListener('appinstalled',()=>{prompt=null;refresh();});
 void navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'}).then(value=>{registration=value;refresh();value.addEventListener('updatefound',()=>{const worker=value.installing;worker?.addEventListener('statechange',()=>{if(worker.state==='installed')refresh();});});}).catch(()=>{/* Reading the portfolio never depends on PWA support. */});
}
