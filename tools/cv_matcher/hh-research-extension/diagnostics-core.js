/* Explicit projection: never export raw storage, errors, URLs, text or credentials. */
(function(root) {
  const states = new Set(['idle','running','complete','partial','failed','needs_input','stopped','cancelled','connected','disconnected','offline','loading','loading_stalled','unknown','authenticated','login','captcha']);
  const state = value => states.has(value) ? value : 'unknown';
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;
  function snapshot({version, adapters = [], permissions = {}, saved = {}, worker = {}, health = null, busy = {}, storage = {}}) {
    const rows = saved.vacancies || [];
    const workers = {};
    for (const name of ['hh','career','collection','giga']) {
      const value = health?.connections?.workers?.[name];
      workers[name] = {connected:value?.connected === true, queued:count(value?.queued), running:count(value?.running)};
    }
    const tasks = {};
    for (const key of ['resume_sync_status','hh_crawl_status','board_crawl_status','hh_workflow_status']) {
      const value = saved[key];
      tasks[key] = {state:state(value?.state)};
      for (const field of ['pages','found','loaded','errors','skipped_closed']) if (Number.isSafeInteger(value?.[field])) tasks[key][field] = count(value[field]);
    }
    return {
      storage:{bytes:Number.isSafeInteger(storage.bytes)&&storage.bytes>=0?storage.bytes:null,limit_bytes:Number.isSafeInteger(storage.limit_bytes)&&storage.limit_bytes>0?storage.limit_bytes:null,near_limit:Number.isSafeInteger(storage.bytes)&&Number.isSafeInteger(storage.limit_bytes)&&storage.limit_bytes>0&&storage.bytes/storage.limit_bytes>=0.85},
      version, service:{reachable:health?.service === 'cv-matcher-local', protocol:count(health?.version)},
      hh:{enabled:saved.hh_managed_enabled === true, tab_exists:worker.exists === true, page_state:state(worker.state)},
      workers, busy:{hh:busy.hh === true, career:busy.career === true, collection:busy.collection === true}, tasks,
      cache:{resumes:count(saved.resume_bundle?.resumes?.length), vacancies:count(rows.length), full:rows.filter(v=>v.description_quality === 'full').length, needs_review:rows.filter(v=>v.description_quality === 'needs_review').length, closed:rows.filter(v=>v.archived === true).length},
      adapters:adapters.map(a=>({id:a.id,label:a.label,hosts:[...a.hosts],access:a.hosts.map(host=>({host,granted:permissions[host] === true}))}))
    };
  }
  root.ExtensionDiagnostics = {snapshot};
})(globalThis);
