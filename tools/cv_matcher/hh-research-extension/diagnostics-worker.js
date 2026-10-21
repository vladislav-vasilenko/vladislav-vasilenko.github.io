/* Read-only diagnostics. Never resolves/creates a worker tab or dequeues a task. */
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.type !== 'diagnostics_snapshot' || sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL('diagnostics.html')) return;
  (async () => {
    const [saved, worker, health, grants, storageBytes] = await Promise.all([
      chrome.storage.local.get(['resume_bundle','vacancies','hh_managed_enabled','resume_sync_status','hh_crawl_status','board_crawl_status','hh_workflow_status']),
      inspectWorker().catch(()=>({exists:false})),
      LocalResumeService.request('/health',null,4000).catch(()=>null),
      Promise.all(JobBoardAdapters.registry.flatMap(a=>a.hosts).map(async host=>[host,await chrome.permissions.contains({origins:['https://'+host+'/*']})])),
      chrome.storage.local.getBytesInUse ? chrome.storage.local.getBytesInUse(null).catch(()=>null) : Promise.resolve(null)
    ]);
    return ExtensionDiagnostics.snapshot({version:chrome.runtime.getManifest().version,adapters:JobBoardAdapters.registry,
      saved,worker,health,storage:{bytes:storageBytes,limit_bytes:chrome.storage.local.QUOTA_BYTES},permissions:Object.fromEntries(grants),busy:{hh:hhWorkflowBusy,career:careerWorkflowBusy,collection:collectionBusy}});
  })().then(report=>reply({ok:true,report}),()=>reply({ok:false,error:'Не удалось прочитать диагностику. Перезагрузите расширение.'}));
  return true;
});
