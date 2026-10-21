(()=>{
 const config=globalThis.__hhApplyAction;delete globalThis.__hhApplyAction;
 if(!config||!HHApply.verifyURL(location.href,config.vacancy_id))throw new Error('Открыта другая вакансия/страница. Операция отменена.');
 const visible=el=>el&&!el.hidden&&el.getBoundingClientRect().width>0&&el.getBoundingClientRect().height>0;
 if([...document.querySelectorAll('[data-qa=vacancy-archive-message], [data-qa=vacancy-archive-banner], [data-qa=vacancy-archived], [data-qa=vacancy-archive-wrapper]')].some(visible))throw Error('Вакансия в архиве. Отклик остановлен.');
 const success=[...document.querySelectorAll('[data-qa="vacancy-response-success"], [data-qa="vacancy-response-letter-success"], [data-qa="vacancy-response-link-top"]')].find(el=>visible(el)&&/вы откликнулись|отклик отправлен|успешно отправлен/i.test(el.innerText));
 if(success)return {state:'submitted',fields:[],selected_resume_id:config.resume_id,submit_label:'',fingerprint:'',source_url:location.href,evidence:success.innerText};
 if(document.querySelector('input[name*="captcha"], iframe[src*="captcha"]'))throw new Error('Пройдите CAPTCHA на HH вручную.');
 const scopes=[...document.querySelectorAll('[data-qa="vacancy-response-popup-form"], [data-qa="vacancy-response-popup"], form')].filter(el=>visible(el)&&
  (/^vacancy-response-popup/.test(el.getAttribute('data-qa')||'')||el.querySelector('[name*="resume"], [data-qa*="vacancy-response"]')||location.pathname==='/applicant/vacancy_response'));
 if(scopes.filter(el=>el.tagName==='FORM').length>1)throw new Error('Найдено несколько форм HH. Продолжите нужную форму на сайте вручную.');
 const scope=scopes.find(el=>el.tagName==='FORM')||scopes[0];
 if(!scope)throw new Error('Откройте форму отклика кнопкой HH «Откликнуться», затем нажмите «Продолжить отклик HH» в расширении.');
 const radios=[...scope.querySelectorAll('input[type="radio"]')];
 const resumeId=el=>el.getAttribute('data-resume-id')||(/^[a-f0-9]{38}$/i.test(el.value||'')?el.value:null);
 const controls=[...scope.querySelectorAll('input, textarea, select')].filter(el=>visible(el)&&!['hidden','password','submit','button'].includes(el.type)&&!resumeId(el)&&!/captcha/i.test(el.name||''));
 const label=el=>(el.labels?.[0]?.innerText||el.getAttribute('aria-label')||el.getAttribute('placeholder')||el.name||'Поле').trim();
 const fields=controls.map((el,i)=>({id:'f'+i,label:label(el),purpose:/сопровод|cover.?letter|vacancy-response-letter/i.test([label(el),el.name,el.getAttribute('data-qa')].join(' '))?'cover':'answer',type:el.tagName==='SELECT'?'select':el.type||'text',group:el.name||'f'+i,required:!!el.required,
  value:['checkbox','radio'].includes(el.type)?el.checked:el.value,options:el.tagName==='SELECT'?[...el.options].map(o=>({value:o.value,text:o.textContent})):[]}));
 const selected=radios.find(el=>el.checked&&resumeId(el));
 const selectedId=selected?resumeId(selected):scope.querySelector('[data-resume-id][aria-selected="true"]')?.getAttribute('data-resume-id')||null;
 const submitters=[...scope.querySelectorAll('button, input[type="submit"]')].filter(el=>visible(el)&&!el.disabled&&/^(отправить|откликнуться|далее|продолжить)/i.test((el.innerText||el.value||'').trim()));
 const snapshot={state:'form',fields,selected_resume_id:selectedId,submit_label:submitters.length===1?(submitters[0].innerText||submitters[0].value).trim():'',fingerprint:HHApply.signature(fields,selectedId)};
 if(config.action==='inspect')return snapshot;
 if(snapshot.fingerprint!==config.fingerprint)throw new Error('Форма HH изменилась. Прочитайте её снова, чтобы не перезаписать новые данные.');
 if(config.action==='fill'){
  const choice=radios.find(el=>resumeId(el)===config.resume_id);
  if(choice&&!choice.checked)choice.click();
  for(const field of fields){
   if(!Object.hasOwn(config.answers||{},field.id))continue;
   const el=controls[Number(field.id.slice(1))],value=config.answers[field.id];
   if(field.type==='select'&&!field.options.some(o=>o.value===value))throw new Error('Недоступный вариант поля: '+field.label);
   if(field.type==='checkbox'){if(el.checked!==!!value)el.click();}
   else if(field.type==='radio'){if(value&&!el.checked)el.click();}
   else {
    const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(el,String(value));
    el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
   }
  }
  return {state:'filled'};
 }
 if(config.action==='submit'){
  HHApply.canSubmit(snapshot,config.resume_id);
  if(scope.checkValidity&&!scope.checkValidity())throw new Error('HH сообщает об ошибке заполнения формы. Исправьте её на сайте.');
  submitters[0].click();return {state:'sent_unconfirmed'};
 }
 throw new Error('Неизвестное действие HH.');
})();
