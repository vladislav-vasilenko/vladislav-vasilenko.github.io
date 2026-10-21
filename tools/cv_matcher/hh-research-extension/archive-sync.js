/* Background local-only synchronization. Raw API keys/browser storage never enter the archive. */
importScripts('local-service.js','archive-sync-core.js','archive-storage.js');
let archiveRunning=false,archiveRevision=0,archiveQueue=Promise.resolve();
const archiveKeys=['resume_bundle','resume_catalog','vacancies','hh_scan_runs','hh_crawl_status','ranking_goal','last_ranking'];
async function archiveState(data){await ArchiveStorage.write({archive_sync_status:{...data,updated_at:new Date().toISOString()}});}
async function archiveSync(force=false){
 if(archiveRunning)return {ok:true,running:true};
 const config=await ArchiveStorage.read(['archive_enabled','archive_pending','archive_outbox','archive_client_id']);
 if(!force&&(!config.archive_enabled||(!config.archive_pending&&!config.archive_outbox?.length)))return {ok:true,skipped:true};
 archiveRunning=true;
 try{
  await archiveQueue;const revision=archiveRevision;
  const state=await ArchiveStorage.read([...archiveKeys,'archive_outbox']);
  let client=config.archive_client_id;if(!client){client=crypto.randomUUID();await ArchiveStorage.write({archive_client_id:client});}
  await archiveState({state:'running',note:'Сохраняю изменения в локальном архиве…'});
  const manifest=await LocalResumeService.request('/archive/manifest',{client_id:client},20000);
  const records=[...(state.archive_outbox||[]),...await ArchiveSyncCore.snapshot(state,client)];
  const unique=new Map();for(const row of records)unique.set(row.kind+':'+row.id+':'+row.digest,row);
  const pending=[...unique.values()].filter(r=>manifest.records[r.kind+':'+r.id]!==r.digest),acknowledged=new Set();let sent=0,rejected=[];
  for(const batch of ArchiveSyncCore.batches(pending)){
   const reply=await LocalResumeService.request('/archive/sync',{client_id:client,records:batch},45000);
   for(const r of reply.accepted)acknowledged.add(r.kind+':'+r.id+':'+r.digest);
   sent+=reply.accepted.length;rejected.push(...reply.rejected);
  }
  // Entries equal to the server manifest have already been durably acknowledged.
  for(const row of records)if(manifest.records[row.kind+':'+row.id]===row.digest)acknowledged.add(row.kind+':'+row.id+':'+row.digest);
  await archiveQueue;
  archiveQueue=archiveQueue.catch(()=>{}).then(async()=>{
   const latest=await ArchiveStorage.read(['archive_outbox']);
   const remaining=(latest.archive_outbox||[]).filter(r=>!acknowledged.has(r.kind+':'+r.id+':'+r.digest));
   await ArchiveStorage.write({archive_outbox:remaining,archive_pending:archiveRevision!==revision||remaining.length>0||rejected.length>0});
  });await archiveQueue;
  await archiveState({state:rejected.length?'partial':'complete',sent,rejected:rejected.slice(0,10),note:rejected.length?'Часть записей требует проверки. Остальное сохранено.':'Архив синхронизирован.',completed_at:new Date().toISOString()});
  return {ok:true,sent,rejected};
 }catch(error){await ArchiveStorage.write({archive_pending:true});await archiveState({state:'pending',note:error.message});return {ok:false,error:error.message};}
 finally{archiveRunning=false;}
}
async function queueArchiveVersions(changes){
 const config=await ArchiveStorage.read(['archive_enabled','archive_outbox']);if(!config.archive_enabled)return;
 const outbox=config.archive_outbox||[],known=new Set(outbox.map(r=>r.kind+':'+r.id+':'+r.digest));
 if(changes.last_ranking)for(const item of [changes.last_ranking.oldValue,changes.last_ranking.newValue])if(item?.generated_at){
  const record=await ArchiveSyncCore.record('ranking','temporary',item);record.id=record.digest;const key='ranking:'+record.id+':'+record.digest;if(!known.has(key)){outbox.push(record);known.add(key);}
 }
 for(const [key,kind] of [['resume_bundle','resume'],['vacancies','vacancy']]){
  if(!changes[key])continue;
  const rows=value=>key==='resume_bundle'?value?.resumes||[]:value||[];
  const older=new Map(rows(changes[key].oldValue).map(r=>[r.id,r]));
  for(const row of rows(changes[key].newValue)){
   const before=older.get(row.id),content=r=>kind==='resume'?JSON.stringify([r.title,r.sections]):JSON.stringify([r.title,r.company,r.description,r.description_quality,r.archived]);
   if(before&&content(before)===content(row))continue;
   for(const item of [before,row])if(item?.id&&(kind!=='resume'||item.sections?.length)){
    const record=await ArchiveSyncCore.record(kind,item.id,item),key=kind+':'+item.id+':'+record.digest;if(!known.has(key)){outbox.push(record);known.add(key);}
   }
  }
  const currentIds=new Set(rows(changes[key].newValue).map(r=>r.id));
  for(const [id,item] of older)if(!currentIds.has(id)&&(kind!=='resume'||item.sections?.length)){
   const record=await ArchiveSyncCore.record(kind,id,item),key=kind+':'+id+':'+record.digest;if(!known.has(key)){outbox.push(record);known.add(key);}
  }
 }
 await ArchiveStorage.write({archive_outbox:outbox,archive_pending:true});
}
chrome.storage.onChanged?.addListener((changes,area)=>{
 if(area==='session'&&changes.resume_import_token){archiveSync().catch(()=>{});return;}
 if(area!=='local'||!archiveKeys.some(k=>k in changes))return;
 archiveRevision++;archiveQueue=archiveQueue.catch(()=>{}).then(()=>queueArchiveVersions(changes)).catch(error=>archiveState({state:'pending',note:'Не удалось сохранить очередь версий: '+error.message}));archiveQueue.then(()=>archiveSync()).catch(()=>{});
});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id||!['archive_sync_now','archive_open','archive_restore'].includes(message.type))return;
 (async()=>{
  if(message.type==='archive_sync_now'){await ArchiveStorage.write({archive_enabled:message.auto!==false,archive_pending:true});return archiveSync(true);}
  if(message.type==='archive_open'){const data=await LocalResumeService.request('/archive/open',{resume_id:message.resume_id||'',goal:message.goal??null,view:message.view||null},10000);await chrome.tabs.create({url:data.url});return {ok:true};}
  const backup=await LocalResumeService.request('/archive/restore',null,30000),current=await ArchiveStorage.read(['resume_bundle','vacancies','ranking_goal','last_ranking']);
  try{await chrome.storage.local.set(ArchiveSyncCore.restore(current,backup));}catch{throw Error('Архив сохранён в SQLite, но для копии в Chrome не хватает места. Откройте сайт анализа; данные сервера не изменены.');}return {ok:true,resumes:backup.resume_bundle.resumes.length,vacancies:backup.vacancies.length};
 })().then(reply,e=>reply({ok:false,error:e.message}));return true;
});
if(chrome.alarms?.create){(async()=>{if(!chrome.alarms.get||!await chrome.alarms.get('archive-retry'))await chrome.alarms.create('archive-retry',{periodInMinutes:1});})().catch(()=>{});chrome.alarms.onAlarm.addListener(a=>{if(a.name==='archive-retry')archiveSync().catch(()=>{});});}
chrome.runtime.onStartup?.addListener(async()=>{const {archive_enabled}=await ArchiveStorage.read('archive_enabled');if(archive_enabled)archiveSync(true).catch(()=>{});});
