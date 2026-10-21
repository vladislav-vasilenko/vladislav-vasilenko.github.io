(function(root){
 function badges(item,{cv_ready=true,title=''}={}){
  if(!item)return [{text:'Нет в локальной БД',kind:'neutral'}];
  const rows=[{text:'Сохранено в БД',kind:'saved'}];
  if(item.closed)rows.push({text:'Закрыта по данным БД',kind:'warning'});
  if(!cv_ready)return [...rows,{text:'Синхронизируйте выбранное CV',kind:'warning'}];
  const clean=s=>String(s||'').replace(/\s+/g,' ').trim().toLowerCase();
  if(title&&clean(title)!==clean(item.title))return [...rows,{text:'Название изменилось · обновите вакансию',kind:'warning'}];
  if(typeof item.score==='number')rows.push({text:'Близость: '+item.score.toFixed(3),kind:'score'});
  else if(item.ranking_stale)rows.push({text:'Рейтинг требует обновления',kind:'warning'});
  if(typeof item.coverage==='number'){
   rows.push({text:'Покрытие: '+item.coverage+'%',kind:'coverage'});
   for(const skill of (item.missing_skills||[]).slice(0,3))rows.push({text:'Не подтверждено: '+skill,kind:'missing'});
   if(item.missing_count>3)rows.push({text:'Ещё '+(item.missing_count-3)+' без подтверждения',kind:'missing'});
  }else rows.push({text:item.analysis_stale?'Разбор для другой версии / цели':'Разбор Luna не выполнен',kind:'neutral'});
  return rows;
 }
 root.HHBadges={badges};
})(globalThis);
