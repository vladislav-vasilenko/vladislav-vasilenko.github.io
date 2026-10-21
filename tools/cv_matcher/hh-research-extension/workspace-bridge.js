(()=>{
 if(location.origin!=='http://127.0.0.1:8788'||!['/','/archive'].includes(location.pathname)||globalThis.cvWorkspaceBridge)return;
 globalThis.cvWorkspaceBridge=true;
 window.addEventListener('message',event=>{
  if(event.source!==window||event.origin!==location.origin||event.data?.channel!=='cv-workspace-request'||event.data.action!=='open_setup'||typeof event.data.id!=='string'||event.data.id.length>80)return;
  const id=event.data.id;chrome.runtime.sendMessage({type:'workspace_setup'}).then(result=>window.postMessage({channel:'cv-workspace-response',id,ok:!!result?.ok},location.origin)).catch(()=>window.postMessage({channel:'cv-workspace-response',id,ok:false},location.origin));
 });
 document.documentElement.dataset.cvMatcherConnected='true';
})();
