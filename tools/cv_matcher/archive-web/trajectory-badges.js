/* Read-only vacancy ↔ trajectory projection; candidate fit is a separate measure. */
const TrajectoryBadges=(()=>{
 function render(projection,{detail=false}={}){
  const root=make('div','trajectoryBadges'),p=projection||{links:[],state:'unassigned'},links=p.links||[];
  if(!links.length){const label=p.state==='needs_description'?'Траектория: нужен полный текст':'Траектория не определена';const chip=make('span','trajectoryUnknown',label);chip.title='Связь с сохранёнными траекториями пока не определена. Это не оценка ваших навыков.';root.append(chip);return root;}
  const group=make('details','trajectoryLinks'),summary=make('summary','',links.length>1?'Пересечение '+links.length+' траекторий':links[0].label);group.append(summary);
  for(const route of links){const item=make('div','trajectoryLink'),a=make('a','',route.label);a.href='/?view=learning&path_id='+encodeURIComponent(route.path_id);item.append(a,make('span','trajectoryLinkKind',route.kind==='target'?'Целевая вакансия':'Совпадают требования'),make('p','',route.reason));if(route.skills?.length)item.append(make('p','',route.skills.join(' · ')));if(detail)for(const q of route.quotes||[])item.append(make('blockquote','',q));group.append(item);}
  root.append(group);return root;
 }
 return {render};
})();
