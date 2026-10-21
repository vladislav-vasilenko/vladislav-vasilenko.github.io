/* Reads a visible response form. Never selects a CV or submits an application. */
(function(root){
 'use strict';
 const clean=value=>String(value||'').normalize('NFKC').replace(/\s+/g,' ').trim();
 const validResume=value=>/^[a-f0-9]{38}$/i.test(value||'')?value:null;
 function selectedResume(scope,resumes,visible){
  const ids=new Set();
  for(const n of scope.querySelectorAll('input,select,[data-resume-id][aria-selected="true"],a[href*="/resume/"]')){
   if(n.tagName==='INPUT'&&n.type==='radio'&&!n.checked)continue;
   let id=null;
   if(n.tagName==='INPUT'&&(n.type==='radio'||/resume/i.test(n.name||'')))id=validResume(n.value);
   if(n.tagName==='SELECT'&&/resume/i.test(n.name||''))id=validResume(n.value);
   if(n.getAttribute('aria-selected')==='true')id=validResume(n.getAttribute('data-resume-id'));
   if(n.tagName==='A'&&visible(n)){try{id=validResume(new URL(n.href).pathname.match(/^\/resume\/([a-f0-9]+)$/i)?.[1]);}catch{}}
   if(id)ids.add(id);
  }
  if(ids.size===1)return [...ids][0];if(ids.size>1)return null;
  // Some HH forms expose the selected title only. Ambiguous titles never guess a CV.
  const text=clean(scope.innerText),matches=resumes.filter(r=>clean(r.title)&&text.includes(clean(r.title)));
  return matches.length===1?matches[0].id:null;
 }
 function detect(doc,url,{items=[],resumes=[],clicked=null,visible}){
  const fields=[...doc.querySelectorAll('textarea')].filter(n=>visible(n)&&/сопровод|cover.?letter|vacancy-response-letter/i.test([n.name,n.getAttribute('placeholder'),n.getAttribute('aria-label'),n.getAttribute('data-qa')].join(' ')));
  if(fields.length!==1)return null;const field=fields[0],scope=field.closest('[data-qa="vacancy-response-popup-form"],form,[data-qa="vacancy-response-popup"],[role="dialog"]');if(!scope||!visible(scope))return null;
  const u=new URL(url);let id=u.pathname.match(/^\/vacancy\/(\d+)\/?$/)?.[1]||u.searchParams.get('vacancyId')||u.searchParams.get('vacancy_id');
  if(!id){const input=scope.querySelector('input[name="vacancy_id"],input[name="vacancyId"]');if(/^\d+$/.test(input?.value||''))id=input.value;}
  let item=id?items.find(r=>r.id==='hh_'+id):null;
  if(!item){const content=clean(scope.innerText),matches=items.filter(r=>clean(r.title)&&content.includes(clean(r.title)));if(matches.length===1)item=matches[0];else if(clicked&&matches.some(r=>r.id===clicked))item=matches.find(r=>r.id===clicked);}
  if(!item)return null;
  const resume_id=selectedResume(scope,resumes,visible),cv=resumes.find(r=>r.id===resume_id);
  return {field,scope,id:item.id,title:item.title,full:!!item.full,closed:!!item.closed,resume_id:cv?.id||null,resume_title:cv?.title||'Не удалось определить выбранное в HH резюме'};
 }
 function insert(form,text){
  if(!form.field.isConnected)throw Error('Форма HH уже закрыта. Откройте её заново.');
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(form.field,text);
  form.field.dispatchEvent(new Event('input',{bubbles:true}));form.field.dispatchEvent(new Event('change',{bubbles:true}));form.field.focus();
 }
 root.HHFormAssist={detect,selectedResume,insert};
})(globalThis);
