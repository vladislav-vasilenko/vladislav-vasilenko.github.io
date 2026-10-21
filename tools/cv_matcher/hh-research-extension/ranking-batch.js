/* One selected collection, bounded requests, one globally sorted result. No retries. */
(function(root){
 'use strict';
 const maxVacancies=2000,batchSize=200;
 const rows=result=>Array.isArray(result.all)?result.all:result.top||[];
 function merge(parts,requested,processed){
  const all=[...new Map(parts.flatMap(rows).map(row=>[row.id,row])).values()];
  all.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
  const result={...parts[0],generated_at:parts.at(-1).generated_at,all,top:all.slice(0,10),ranked_count:all.length,
   requested_count:requested,processed_count:processed,batches_completed:parts.length,partial:processed<requested,cached:parts.every(p=>p.cached===true)};
  for(const key of ['input_count','excluded','usage_tokens','api_requests','cache_reused','new_compared'])result[key]=parts.reduce((sum,p)=>sum+(Number(p[key])||0),0);
  return result;
 }
 async function run(request,call,progress=()=>{}){
  if(!Array.isArray(request.vacancies)||!request.vacancies.length||request.vacancies.length>maxVacancies)throw Error('Выберите от 1 до 2000 вакансий.');
  const parts=[];let processed=0;
  try{
   for(let start=0;start<request.vacancies.length;start+=batchSize){
    const batch=request.vacancies.slice(start,start+batchSize);
    progress({processed,total:request.vacancies.length,batch:parts.length+1,batches:Math.ceil(request.vacancies.length/batchSize)});
    const part=await call({...request,vacancies:batch});
    const first=parts[0];
    if(part.resume_id!==request.resume_id||part.resume_hash!==request.bundle.resumes[0].content_hash||part.model!==request.model||
       first&&['resume_id','resume_hash','model','goal'].some(k=>part[k]!==first[k]))throw Error('Контекст пакета рейтинга изменился. Расчёт остановлен.');
    parts.push(part);processed+=batch.length;
   }
   return merge(parts,request.vacancies.length,processed);
  }catch(error){
   if(parts.length)error.partial_ranking=merge(parts,request.vacancies.length,processed);
   throw error;
  }
 }
 root.RankingBatch={maxVacancies,batchSize,run};
})(globalThis);
