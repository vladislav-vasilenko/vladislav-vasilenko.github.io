(function(root){
 'use strict';
 const fields={resume:['id','title','source_type','source_url','quality','sections','content_hash','file_hash','filename','captured_at','checked_at','reviewed_at','changed_at','extraction_method','warnings'],vacancy:['id','title','company','link','source','source_page','search_page','origin_query','description','description_quality','locations','location','city','pub_date','collected_at','last_seen_at','first_seen','reviewed_at','review_method','recommended_for','archived','availability_checked_at','listing_verified_at','description_fetched_at','description_dirty','listing_changed_at','listing_snapshot','collector','board_id','adapter_id','adapter_version','extraction_method'],scan:['id','scan_kind','scope_url','started_at','completed_at','ids','listing_complete','state','pages','start_page','error'],profile:['primary_id','goal']};
 const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])):value;
 fields.ranking=['generated_at','model','resume_id','resume_title','resume_hash','input_count','ranked_count','excluded','goal','method','score_warning','usage_tokens','api_requests','company_filter','companies_filter','cache_reused','new_compared','cached','requested_count','processed_count','batches_completed','partial','all'];
 function clean(kind,data){
  const out=Object.fromEntries(fields[kind].filter(k=>data[k]!==undefined).map(k=>[k,data[k]]));
  if(kind==='resume')out.sections=(data.sections||[]).filter(s=>!['contacts','contact','personal'].includes(s.key)).map(s=>Object.fromEntries(['key','heading','text'].filter(k=>s[k]!==undefined).map(k=>[k,s[k]])));
  if(kind==='ranking')out.all=(data.all||data.top||[]).map(row=>Object.fromEntries(['id','title','company','link','score','cv_similarity','goal_similarity','evidence','collected_at','vacancy_hash','ranked_at'].filter(k=>row[k]!==undefined).map(k=>[k,row[k]])));
  return out;
 }
 async function record(kind,id,data){const value=clean(kind,data),bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(stable(value))));return {kind,id,data:value,digest:[...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('')};}
 async function snapshot(data,client){
  const records=[];
  for(const cv of data.resume_bundle?.resumes||[])if(cv.id&&cv.sections?.length)records.push(await record('resume',cv.id,cv));
  for(const job of data.vacancies||[])if(job.id&&job.title&&job.description_quality)records.push(await record('vacancy',job.id,job));
  const catalog=data.resume_catalog;
  if(catalog?.checked_at&&catalog.resumes?.length){
   const id=client+'_catalog_'+catalog.checked_at;
   records.push(await record('scan',id,{id,scan_kind:'resume_catalog',scope_url:'https://hh.ru/applicant/profile/me',started_at:catalog.checked_at,completed_at:catalog.checked_at,ids:catalog.resumes.map(r=>r.id).sort(),listing_complete:catalog.listing_complete===true,state:'complete',pages:1,start_page:0}));
  }
  for(const scan of data.hh_scan_runs||[]){const id=client+'_'+scan.id;records.push(await record('scan',id,{...scan,id}));}
  if(data.hh_crawl_status?.completed_at&&!data.hh_scan_runs?.some(r=>r.id===data.hh_crawl_status.run_id)){
   const status=data.hh_crawl_status;if(status.start_url){const id=client+'_legacy_'+status.completed_at;records.push(await record('scan',id,{id,scan_kind:'vacancy_search',scope_url:status.start_url,started_at:status.started_at,completed_at:status.completed_at,ids:[],listing_complete:false,state:status.state,pages:status.pages||0,start_page:0}));}
  }
  if(data.last_ranking?.generated_at){const ranking=await record('ranking','temporary',data.last_ranking);ranking.id=ranking.digest;records.push(ranking);}
  records.push(await record('profile','profile',{primary_id:data.resume_bundle?.primary_id||null,goal:data.ranking_goal??data.last_ranking?.goal??''}));return records;
 }
 function batches(records,maxBytes=2*1024*1024){
  const result=[];let current=[],bytes=0;
  for(const record of records){const size=new TextEncoder().encode(JSON.stringify(record)).length;if(current.length&&(bytes+size>maxBytes||current.length===100)){result.push(current);current=[];bytes=0;}current.push(record);bytes+=size;}
  if(current.length)result.push(current);return result;
 }
 function restore(current,backup){
  const byId=new Map((backup.resume_bundle?.resumes||[]).map(r=>[r.id,r]));
  for(const cv of current.resume_bundle?.resumes||[]){const old=byId.get(cv.id),stamp=r=>Math.max(...['checked_at','captured_at','reviewed_at'].map(k=>Date.parse(r[k])||0));if(!old||stamp(cv)>=stamp(old))byId.set(cv.id,cv);}
  const primary=current.resume_bundle?.primary_id||backup.resume_bundle?.primary_id;
  const jobs=new Map((backup.vacancies||[]).map(r=>[r.id,r]));
  for(const row of current.vacancies||[]){const saved=jobs.get(row.id);if(!saved){jobs.set(row.id,row);continue;}const ordered=(Date.parse(row.collected_at)||0)>=(Date.parse(saved.collected_at)||0)?[saved,row]:[row,saved];jobs.set(row.id,ResearchSearch.mergeVacancies([ordered[0]],[ordered[1]])[0]);}
  const ranking=(Date.parse(current.last_ranking?.generated_at)||0)>=(Date.parse(backup.last_ranking?.generated_at)||0)?current.last_ranking:backup.last_ranking;
  return {resume_bundle:{...backup.resume_bundle,...current.resume_bundle,schema_version:2,primary_id:primary,resumes:[...byId.values()]},vacancies:[...jobs.values()],ranking_goal:current.ranking_goal??backup.ranking_goal??'',...(ranking?{last_ranking:ranking}:{})};
 }
 root.ArchiveSyncCore={record,snapshot,batches,clean,restore};
})(globalThis);
