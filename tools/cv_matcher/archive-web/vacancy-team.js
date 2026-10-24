/* Teams belong to vacancies; LinkedIn and Hugging Face are collection sources. */
const VacancyTeam=(()=>{
 'use strict';
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 function mount(root,vacancy){
  root.classList.add('vacancyTeam');let state,stream='';
  const call=(op,data={})=>api('vacancy-team',{op,vacancy_id:vacancy.id,...data});
  const btn=(label,fn)=>{const b=el('button',label,'secondary');b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;};
  const field=(label,value='',type='text')=>{const wrap=el('label',label),input=el(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.value=value;wrap.append(input);return {wrap,input};};
  async function refresh(){state=await call('view');render();}
  function render(){
   root.replaceChildren(el('h3','Команда и контакты'),el('p','Контакты из источников и связи со стримами. Список участников организации не подтверждает полный состав команды вакансии.','muted'));
   if(!state){root.append(btn('Показать команды вакансии',refresh));return;}
   const name=field('Команда / лаборатория',vacancy.payload.company||'');const binding=el('details');binding.open=!state.teams.length;binding.append(el('summary','Добавить или привязать команду'),name.wrap,btn('Привязать команду',async()=>{await call('bind',{name:name.input.value});await refresh();}));root.append(binding);
   const filter=el('select');filter.setAttribute('aria-label','Фильтр участников по стриму');for(const value of ['',...state.streams]){const o=el('option',value||'Все стримы');o.value=value;filter.append(o);}filter.value=stream;filter.onchange=()=>{stream=filter.value;render();};root.append(filter,btn('Обновить участников и статус',refresh));
   for(const command of state.commands)root.append(el('p',(command.state==='completed'?'Сбор завершён':command.state==='queued'?'В очереди':command.state==='running'?'Читается LinkedIn':'Требует проверки')+(command.result?.message?' · '+command.result.message:''),'muted'));
   for(const team of state.teams){
    const box=el('section',undefined,'liCard');box.append(el('h3',team.name),el('p',team.members.length+' контактов · источник и роли указаны у каждого','muted'));
    const url=field('Вакансия LinkedIn для чтения Hiring team',vacancy.payload.source==='linkedin'?vacancy.payload.link:'' ,'url'),org=field('Организация Hugging Face');
    const sources=el('details');sources.append(el('summary','Обновить участников из источников'));sources.append(url.wrap,btn('Собрать показанную команду из LinkedIn',async()=>{await call('linkedin',{team_id:team.id,url:url.input.value});notice('Чтение участников поставлено в очередь расширения.');await refresh();}),org.wrap,btn('Собрать публичных участников Hugging Face',async()=>{const result=await call('huggingface',{team_id:team.id,organization:org.input.value});notice('Участников организации: '+result.count+'. Роли и стримы требуют подтверждения.');await refresh();}));box.append(sources);
    const members=team.members.filter(p=>!stream||p.streams.some(s=>s.name===stream));
    for(const person of members){
     const card=el('article',undefined,'liRow');card.append(external(person.url,person.name+' ↗'),el('p',person.role||person.observed_role||'Роль не установлена'),el('p',person.source+' · '+(person.relationship==='organization_member'?'публичный участник организации':'контакт, указанный рядом с вакансией'),'muted'));
     const tags=el('div',undefined,'liJobTags');if(!person.streams.length)tags.append(el('span','Стрим не установлен','liJobTag'));for(const item of person.streams)tags.append(el('span',item.name+' · '+(item.status==='confirmed'?'подтверждено':'гипотеза'),'liJobTag'));for(const badge of person.badges||[])tags.append(el('span',badge,'liJobTag'));card.append(tags,external(person.evidence_url,'Источник связи ↗'));
     const edit=el('details');edit.append(el('summary','Уточнить роль и стримы'));const role=field('Роль',person.role||person.observed_role||''),evidence=field('Ссылка на подтверждение',person.evidence_url,'url'),quote=field('Основание: цитата / пояснение',person.evidence_quote||'','textarea'),status=el('select');status.setAttribute('aria-label','Статус связи со стримами');for(const [id,label]of [['hypothesis','Гипотеза'],['confirmed','Подтверждено источником']]){const o=el('option',label);o.value=id;status.append(o);}const checks=[];edit.append(role.wrap,evidence.wrap,quote.wrap,status);for(const label of state.streams){const f=field(label,'','checkbox');f.input.checked=person.streams.some(s=>s.name===label);checks.push([label,f.input]);edit.append(f.wrap);}edit.append(btn('Сохранить роль и связи со стримами',async()=>{await call('annotate',{team_id:team.id,person_id:person.id,revision:person.revision,role:role.input.value,status:status.value,streams:checks.filter(([,n])=>n.checked).map(([name])=>name),evidence_url:evidence.input.value,evidence_quote:quote.input.value});await refresh();}));card.append(edit);box.append(card);
    }
    if(!members.length)box.append(el('p','Участники с выбранным стримом пока не установлены.','muted'));root.append(box);
   }
  }
  render();
 }
 return {mount};
})();
