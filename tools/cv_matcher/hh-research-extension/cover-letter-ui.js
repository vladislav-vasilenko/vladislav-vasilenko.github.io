(function(root){
  let generating=false;
  const drafts=new WeakMap(),preferences=new WeakMap();
  async function bounded(promise,ms,message) {
    let timer;
    try {return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);})]);}
    finally {clearTimeout(timer);}
  }
  function attach(article,row,getRanking) {
    const button=document.createElement('button'),notice=document.createElement('p'),box=document.createElement('div'),text=document.createElement('textarea'),copy=document.createElement('button'),sources=document.createElement('details'),summary=document.createElement('summary');
    const settings=document.createElement('details'),settingsTitle=document.createElement('summary'),commentsLabel=document.createElement('label'),comments=document.createElement('textarea'),lengthLabel=document.createElement('label'),length=document.createElement('input'),hint=document.createElement('p');
    settingsTitle.textContent='Настроить письмо: комментарий и длина';
    commentsLabel.textContent='Мои пожелания к письму';comments.rows=3;comments.maxLength=2000;comments.placeholder='Например: выдели исследовательские проекты, избегай общих фраз.';comments.setAttribute('aria-label',`Пожелания к письму: ${row.title}`);commentsLabel.append(comments);
    lengthLabel.textContent='Предложений основного текста';length.setAttribute('aria-label',`Число предложений: ${row.title}`);
    length.type='number';length.min='1';length.max='50';length.step='1';
    length.value='2';lengthLabel.append(length);hint.className='hint';
    hint.textContent='От 1 до 50 предложений, без приветствия и завершающей фразы. Укажите акценты и личную мотивацию; опыт берётся из выбранного CV. Изменение настроек само по себе не вызывает OpenAI. Длинное письмо требует больше времени и токенов.';
    settings.append(settingsTitle,commentsLabel,lengthLabel,hint);
    button.className='secondary';button.textContent='Сопроводительный текст · API';button.setAttribute('aria-label',`Сопроводительный текст: ${row.title}`);
    notice.className='hint';notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
    box.hidden=true;text.rows=4;text.setAttribute('aria-label',`Черновик для вакансии ${row.title}`);copy.textContent='Скопировать текст';copy.className='secondary';
    summary.textContent='Источники: опыт и мотивация';sources.append(summary);box.append(text,copy,sources);
    const offline=document.createElement('button'),prompt=document.createElement('textarea');offline.className='secondary';offline.textContent='Письмо без API · скопировать промпт';prompt.readOnly=true;prompt.rows=10;prompt.hidden=true;prompt.setAttribute('aria-label','Промпт сопроводительного письма без API');article.append(settings,button,offline,prompt,notice,box);
    offline.onclick=async()=>{offline.disabled=true;try{const selected=getRanking();if(!selected)throw Error('Выберите CV.');const {resume_bundle,vacancies=[]}=await chrome.storage.local.get(['resume_bundle','vacancies']);const resume=resume_bundle?.resumes?.find(r=>r.id===selected.resume_id&&r.content_hash===selected.resume_hash),job=vacancies.find(v=>v.id===row.id&&!v.archived);if(getRanking()!==selected)throw Error('Выбранный CV изменился. Скопируйте промпт заново.');const context=ChatGPTExport.applicationContext(resume,job,selected.goal||'');prompt.value=ChatGPTExport.buildApplicationPackage({context,comments:comments.value,sentences:length.value,draft:text.value});try{await navigator.clipboard.writeText(prompt.value);notice.textContent='Промпт скопирован. Вставьте в ChatGPT, затем вставьте готовое письмо в поле ниже. Вызовов API: 0.';}catch{prompt.hidden=false;prompt.focus();prompt.select();notice.textContent='Промпт выделен: Cmd+C / Ctrl+C.';}box.hidden=false;sources.hidden=true;text.placeholder='Вставьте и отредактируйте письмо из ChatGPT.';}catch(e){notice.textContent=e.message;}finally{offline.disabled=false;}};
    const initialContext=getRanking(),saved=preferences.get(initialContext)?.get(row.id);
    if(saved){length.value=String(saved.sentence_count);comments.value=saved.comments;}
    const values=()=>({sentence_count:Number(length.value),comments:comments.value.trim()});
    const variant=()=>JSON.stringify([row.id,Number(length.value),comments.value.trim()]);
    let visibleDraft=null;
    function paint(draft) {
      visibleDraft=draft;sources.hidden=false;box.hidden=false;text.value=draft.text;text.rows=Math.min(24,Math.max(4,(draft.sentence_count??Number(length.value))*2));
      const words=draft.word_count,seconds=`${Math.max(5,Math.round(words/3.5))}–${Math.max(6,Math.ceil(words/2.5))}`;
      notice.textContent=`${draft.sentence_count??Number(length.value)} предл. основного текста · ${words} слов · около ${seconds} секунд чтения. ${draft.cached?'Из кэша, без нового запроса OpenAI. ':`Запросов OpenAI: ${draft.api_requests??1}. `}${draft.review_note}`;
      sources.replaceChildren(summary);
      for(const item of draft.evidence||[]) {
        const claim=document.createElement('p'),cvLabel=document.createElement('p'),cv=document.createElement('blockquote'),jdLabel=document.createElement('p'),jd=document.createElement('blockquote');
        claim.textContent=item.claim;cvLabel.textContent=item.source_type==='comment'?'Из вашей мотивации (комментарий)':'Из выбранного резюме';cv.textContent=item.source_type==='comment'?item.comment_quote:item.resume_quote;jdLabel.textContent='Из вакансии';jd.textContent=item.vacancy_quote;
        sources.append(claim,cvLabel,cv,jdLabel,jd);
      }
    }
    function changed(){
      const context=getRanking();if(!context)return;
      if(!preferences.has(context))preferences.set(context,new Map());preferences.get(context).set(row.id,values());
      visibleDraft=null;box.hidden=true;
      const restored=drafts.get(context)?.get(variant());
      if(restored)paint(restored);else notice.textContent='Настройки изменены. Нажмите «Сопроводительный текст», чтобы составить новый вариант.';
    }
    comments.oninput=changed;length.onchange=changed;
    text.oninput=()=>{
      if(!visibleDraft)return;
      visibleDraft={...visibleDraft,text:text.value,word_count:text.value.trim().split(/\s+/).filter(Boolean).length};
      drafts.get(getRanking())?.set(variant(),visibleDraft);
    };
    const restored=drafts.get(initialContext)?.get(variant());if(restored) paint(restored);
    copy.onclick=async()=>{
      try {await navigator.clipboard.writeText(text.value.trim());notice.textContent='Сопроводительный текст скопирован. Перед отправкой проверьте факты.';}
      catch {text.focus();text.select();notice.textContent='Текст выделен. Скопируйте его сочетанием Cmd+C / Ctrl+C.';}
    };
    button.onclick=async()=>{
      if(generating){notice.textContent='Дождитесь завершения текущего письма.';return;}
      const context=getRanking();if(!context){notice.textContent='Сначала выберите резюме и получите рейтинг.';return;}
      const requested=values(),key=variant();
      if(!Number.isInteger(requested.sentence_count)||requested.sentence_count<1||requested.sentence_count>50){notice.textContent='Введите целое число предложений от 1 до 50.';return;}
      const serviceTimeout=Math.max(90000,(2*(requested.sentence_count<=5?35:Math.min(180,35+3*requested.sentence_count))+15)*1000);
      generating=true;button.disabled=true;comments.disabled=true;length.disabled=true;notice.textContent='Читаю выбранное резюме и полную вакансию…';
      try {
        const {resume_bundle:bundle,vacancies=[],cover_model='luna'}=await bounded(chrome.storage.local.get(['resume_bundle','vacancies','cover_model']),10000,'Расширение не ответило при чтении сохранённых данных. Перезагрузите страницу рейтинга и повторите.');
        const chosen=bundle?.resumes?.find(r=>r.id===context.resume_id);
        if(!chosen||chosen.content_hash!==context.resume_hash||chosen.quality!=='full') throw new Error('Версия резюме изменилась. Сначала пересчитайте рейтинг по актуальному CV.');
        const vacancy=vacancies.find(v=>v.id===row.id&&v.description_quality==='full'&&!v.archived);
        if(!vacancy) throw new Error('Полное описание вакансии недоступно. Обновите её сбором.');
        notice.textContent=`Готовлю черновик: ${requested.sentence_count} предл. по выбранному CV и этой вакансии…`;
        const response=await bounded(LocalResumeService.request('/cover-letter',{resume_id:chosen.id,bundle:{...bundle,primary_id:chosen.id,resumes:[chosen]},vacancy,...requested,model:['luna','terra','sol'].includes(cover_model)?cover_model:'luna'},serviceTimeout),serviceTimeout+5000,'Генерация не завершилась за отведённое время. Проверьте локальный сервис и повторите: готовый текст будет взят из кэша.');
        if(response.resume_id!==context.resume_id||response.resume_hash!==context.resume_hash||response.vacancy_id!==row.id) throw new Error('Ответ не соответствует выбранным CV и вакансии.');
        if(response.sentence_count!==requested.sentence_count)throw new Error('Сервис вернул другую длину письма. Перезапустите локальный сервис и повторите.');
        if(getRanking()!==context) return;
        if(!drafts.has(context)) drafts.set(context,new Map());drafts.get(context).set(key,response);if(variant()===key)paint(response);
      } catch(error) {notice.textContent=error.message;}
      finally {generating=false;button.disabled=false;comments.disabled=false;length.disabled=false;}
    };
  }
  root.CoverLetters={attach};
})(globalThis);
