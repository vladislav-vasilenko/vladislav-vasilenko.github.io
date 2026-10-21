(function(root){
 function verifyURL(value,vacancyId){
  const u=new URL(value),id=String(vacancyId).replace(/^hh_/,'');
  if(!/^\d+$/.test(id))return false;
  return u.origin==='https://hh.ru'&&(/^\/vacancy\/\d+\/?$/.test(u.pathname)?u.pathname.split('/')[2]===id:
   /^\/applicant\/vacancy_response\/?$/.test(u.pathname)&&['vacancyId','vacancy_id'].some(k=>u.searchParams.get(k)===id));
 }
 function signature(fields,resume){return JSON.stringify([resume,fields.map(f=>[f.id,f.label,f.type,f.group,f.required,f.value,f.options,f.purpose||''])]);}
 function canSubmit(snapshot,resumeId){
  if(snapshot.state==='submitted')throw new Error('Отклик уже отправлен. Повтор не выполняется.');
  if(snapshot.selected_resume_id!==resumeId)throw new Error('Сначала выберите в форме именно это HH-резюме. Его ID пока не подтверждён.');
  if(snapshot.fields.some(f=>f.required&&(f.type==='radio'?!snapshot.fields.some(o=>o.type==='radio'&&o.group===f.group&&o.value):f.type==='checkbox'?!f.value:!String(f.value||'').trim())))throw new Error('В форме остались обязательные поля.');
  if(!snapshot.submit_label)throw new Error('Кнопка отправки/перехода не распознана. Продолжите в HH вручную.');
 }
 function verifyApproved(intent,before,after){
  if(before.fingerprint!==intent.form_fingerprint||after.selected_resume_id!==intent.resume_id||after.submit_label!==intent.submit_label)throw Error('Форма не совпадает с согласованной.');
  const shape=f=>JSON.stringify([f.id,f.label,f.type,f.group,f.required,f.options,f.purpose||'']);
  if(after.fields.length!==before.fields.length||after.fields.some((f,i)=>shape(f)!==shape(before.fields[i])||f.value!==intent.answers[f.id]))throw Error('HH изменил поля или значения ответов. Нужно новое разрешение.');
  canSubmit(after,intent.resume_id);
 }
 root.HHApply={verifyURL,signature,canSubmit,verifyApproved};
})(globalThis);
