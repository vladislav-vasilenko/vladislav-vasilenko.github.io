/* Editable catalog in SQLite; no model requests or employer-site navigation on save. */
const CompanySettings=(()=>{
 let snapshot=null,draft=[],dirty=false,editEpoch=0;
 const selectors={link_selector:'Ссылки вакансий',card_selector:'Контейнер карточки',title_selector:'Название в карточке',description_selector:'Полное описание'};
 const tiers={top:'Top Tier',second:'2nd Tier',others:'Other Tier'};
 async function profileForm(){
  const area=$('candidateProfile');if(!area)return;area.replaceChildren(make('h2','','Данные для автозаполнения'),make('p','muted','Контакты, город, соцсети и портфолио хранятся в SQLite отдельно от CV. Используются без LLM после предпросмотра. Для T-Bank «Москва» выбирается из списка как «Россия, г Москва».'));
  const status=make('p');status.setAttribute('role','status');area.append(status);
  try{
   const saved=await api('workflow',{op:'candidate_profile'}),grid=make('div','catalogGrid'),inputs=new Map();
   for(const [key,label] of Object.entries(saved.labels)){
    const wrap=make('label','catalogField',label),input=make('input');input.type=key==='email'?'email':key==='phone'?'tel':key.endsWith('_url')?'url':'text';input.value=saved.values[key]||'';input.autocomplete=({city:'address-level2',email:'email',phone:'tel',first_name:'given-name',last_name:'family-name'})[key]||'off';
    if(key==='telegram_url')input.placeholder='https://t.me/username';if(key==='portfolio_url')input.placeholder='https://github.com/username';wrap.append(input);grid.append(wrap);inputs.set(key,input);
   }
   const save=make('button','','Сохранить данные автозаполнения');save.onclick=async()=>{save.disabled=true;try{const updated=await api('workflow',{op:'candidate_profile_save',values:Object.fromEntries([...inputs].map(([key,input])=>[key,input.value])),revisions:saved.revisions});saved.revisions=updated.revisions;status.textContent='Сохранено в SQLite. Для уже открытой анкеты обновите предпросмотр переноса.';}catch(error){status.textContent=error.message;}finally{save.disabled=false;}};area.append(grid,save);
  }catch(error){status.textContent=error.message;}
 }
 const field=(label,value,onChange,multiline=false)=>{const wrap=make('label','catalogField',label),input=make(multiline?'textarea':'input');input.value=value||'';if(multiline)input.rows=3;input.oninput=()=>{onChange(input.value);dirty=true;$('catalogStatus').textContent='Есть несохранённые изменения.';};wrap.append(input);return wrap;};
 function render(){
  const area=$('catalogCompanies');area.replaceChildren();const query=$('catalogSearch').value.trim().toLocaleLowerCase('ru-RU');
  for(const [tier,label] of Object.entries(tiers)){
   const group=make('section','catalogTier'),rows=draft.filter(c=>c.tier===tier&&(!query||(c.label+' '+c.aliases.join(' ')).toLocaleLowerCase('ru-RU').includes(query)));
   group.append(make('h2','',label+' · '+rows.length));area.append(group);
   for(const c of rows){const details=make('details','catalogCompany');details.open=!!c._new;const heading=make('summary','',c.label),statusTag=make('span','tag');const boardsStatus=c.boards.length?(c.boards.some(b=>Object.keys(selectors).some(k=>b[k]))?'Ручные селекторы':c.boards.some(b=>{try{return !!snapshot.adapters?.[new URL(b.url).hostname];}catch{return false;}})?'Есть адаптер сбора':'Адаптер нужен'):'Job board не указан';statusTag.textContent=boardsStatus;heading.append(statusTag);details.append(heading);
    const general=make('div','catalogGrid'),tierLabel=make('label','catalogField','Приоритет'),select=make('select');for(const [id,label] of Object.entries(tiers)){const o=make('option','',label);o.value=id;select.append(o);}select.value=c.tier;select.onchange=()=>{c.tier=select.value;dirty=true;render();$('catalogStatus').textContent='Приоритет изменён. Сохраните настройки.';};tierLabel.append(select);
    const idField=field('Постоянный ID',c.id,v=>c.id=v);idField.querySelector('input').disabled=!c._new;
    const regionLabel=make('label','catalogField','Регион компании'),regionSelect=make('select');for(const [id,label]of Object.entries(snapshot.regions||{rus:'RUS',us_uk_eu:'US / UK / EU',china:'China',jp:'JP',au_nz:'Australia / New Zealand',other:'Другие'})){const o=make('option','',label);o.value=id;regionSelect.append(o);}regionSelect.value=c.region||'other';regionSelect.onchange=()=>{c.region=regionSelect.value;dirty=true;$('catalogStatus').textContent='Регион изменён. Сохраните настройки.';};regionLabel.append(regionSelect);general.append(regionLabel);
    general.append(field('Компания',c.label,v=>{c.label=v;heading.textContent=v||'Новая компания';}),tierLabel,idField,field('Варианты названия · по одному на строку',c.aliases.join('\n'),v=>c.aliases=v.split('\n').map(s=>s.trim()).filter(Boolean),true));details.append(general);
    const boards=make('div');details.append(boards);
    function boardRow(b){const box=make('section','catalogBoard'),status=make('p','tag');
     function updateStatus(){let host='';try{host=new URL(b.url).hostname;}catch{}const native=snapshot.adapters?.[host];status.textContent=Object.keys(selectors).some(k=>b[k])?'Ручные селекторы · нужна проверка текста':native?'Есть адаптер · '+native:'Адаптер нужен · задайте селекторы или разработайте';}
     box.append(field('Job board · ссылка HTTPS',b.url,v=>{b.url=v;updateStatus();}),status);
     const manual=make('details');manual.append(make('summary','','Ручные CSS-селекторы'));for(const [name,label] of Object.entries(selectors))manual.append(field(label,b[name],v=>{b[name]=v;updateStatus();}));manual.append(make('p','muted','Ручной сбор выполняется на открытой вкладке Chrome. Текст требует проверки перед анализом. Пустые поля используют встроенный адаптер, если он есть.'));box.append(manual);
     const remove=make('button','quiet','Убрать job board');remove.type='button';remove.onclick=()=>{c.boards=c.boards.filter(v=>v!==b);dirty=true;box.remove();};box.append(remove);boards.append(box);updateStatus();}
    c.boards.forEach(boardRow);const addBoard=make('button','secondary','Добавить job board');addBoard.onclick=()=>{const b={url:''};c.boards.push(b);dirty=true;boardRow(b);};
    const remove=make('button','quiet','Убрать компанию из списка');remove.onclick=()=>{if(!confirm('Убрать компанию из приоритетов? Вакансии и прежние настройки останутся в базе.'))return;draft=draft.filter(v=>v!==c);dirty=true;render();};details.append(addBoard,remove);group.append(details);
   }
  }
 }
 async function enter(){const run=++editEpoch;if(!dirty||!snapshot){const data=await api('company-settings');if(run!==editEpoch)return;snapshot=data;draft=structuredClone(data.companies);dirty=false;}$('catalogStatus').textContent=dirty?'Есть несохранённые изменения.':'Приоритеты и адаптеры хранятся в SQLite. Расширение получает тот же список.';render();await profileForm();}
 $('catalogSearch').oninput=render;
 $('catalogAdd').onclick=()=>{draft.unshift({id:'company-'+Date.now(),label:'Новая компания',tier:'others',aliases:['Новая компания'],boards:[],_new:true});dirty=true;$('catalogSearch').value='';render();};
 $('catalogSave').onclick=async()=>{const b=$('catalogSave');b.disabled=true;try{if(!snapshot)throw Error('Дождитесь загрузки настроек.');snapshot=await api('company-settings',{revision:snapshot.revision,companies:draft});draft=structuredClone(snapshot.companies);dirty=false;render();const data=await api('companies');companyOptions=data.items;fillCompanies();$('catalogStatus').textContent='Сохранено в SQLite. Расширение обновит настройки при следующем открытии / сборе.';}catch(e){$('catalogStatus').textContent=e.message;}finally{b.disabled=false;}};
 $('catalogReload').onclick=async()=>{if(dirty&&!confirm('Отменить несохранённые изменения?'))return;dirty=false;await enter();};
 return {enter};
})();
