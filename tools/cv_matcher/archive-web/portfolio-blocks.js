'use strict';
// Reviews HH differences block by block. All text goes through textContent; no model is called.
const PortfolioBlocks=(()=>{
 const STATUS={changed:'Изменён в HH',added:'Только в HH',removed:'Только на сайте',same:'Совпадает'};
 const FIELDS=[['company','Компания'],['role','Роль'],['period','Период'],['duration','Продолжительность'],['description','Описание']];
 const ACTIONS={changed:[['keep','Оставить как на сайте'],['hh','Принять HH'],['rewrite','Переписать']],added:[['keep','Не добавлять'],['hh','Добавить из HH'],['rewrite','Добавить в своей редакции']],removed:[['keep','Оставить на сайте'],['hh','Убрать с сайта'],['rewrite','Переписать']]};
 const diffView=segments=>{const box=make('p','blockDiff');for(const part of segments)box.append(make(part.op==='add'?'ins':part.op==='del'?'del':'span','',part.text));return box;};
 function input(label,value,long,onchange){const row=make('label','',label),field=make(long?'textarea':'input');if(long)field.rows=8;else field.type='text';field.value=value||'';field.oninput=onchange;row.append(field);return {row,field};}
 function fieldSet(host,block,values,prefix,onchange){const inputs={};for(const [key,label] of block.kind==='experience'?FIELDS:[['text','Текст']]){const made=input(prefix+label,values?.[key],key==='description'||key==='text'&&block.kind==='about',onchange);inputs[key]=made.field;host.append(made.row);}return inputs;}
 function card(block,data,decisions,changed){
  const box=make('article','blockCard');box.append(make('h4','',block.label),make('p','blockStatus',STATUS[block.status]+(block.fields_changed.length?' · '+block.fields_changed.map(k=>Object.fromEntries(FIELDS)[k]||'текст').join(', '):'')));
  for(const [key,label] of block.kind==='experience'?FIELDS:[['text','Текст']]){if(block.status==='changed'&&!block.fields_changed.includes(key))continue;box.append(make('p','muted',label));box.append(diffView(block.diff[key]));}
  const choices=make('div','blockChoices'),editors=make('div'),name='block-'+block.key;let action='keep',inputs=null,translation=null;
  const render=()=>{editors.replaceChildren();inputs=translation=null;
   if(action==='rewrite')inputs=fieldSet(editors,block,block.hh||block.site,'Для сайта · ',changed);
   const removing=action==='hh'&&block.status==='removed',needs=action!=='keep'&&!removing&&data.translation_language&&(block.kind==='experience'||block.kind==='about'&&block.site_translation?.text);
   if(needs&&block.kind!=='title')translation=fieldSet(editors,block,block.site_translation||{period:'',duration:''},data.translation_language.toUpperCase()+' · ',changed);
  };
  for(const [value,label] of ACTIONS[block.status]){const row=make('label'),radio=make('input');radio.type='radio';radio.name=name;radio.value=value;radio.style.width='auto';radio.checked=value==='keep';radio.onchange=()=>{action=value;render();changed();};row.append(radio,document.createTextNode(' '+label));choices.append(row);}
  box.append(choices,editors);
  const collect=target=>target&&Object.fromEntries(Object.entries(target).map(([k,f])=>[k,f.value]));
  decisions.set(block.key,()=>({action,...(inputs?{value:collect(inputs)}:{}),...(translation?{translation:collect(translation)}:{})}));
  return box;
 }
 function modeToggle(root,data,refresh){
  const label=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';check.checked=data.block_review;
  label.append(check,document.createTextNode(' Обновлять опыт, заголовок и введение только по решениям в этих блоках'));
  check.onchange=async()=>{check.disabled=true;try{await api('portfolio-publication',{op:'block_mode',enabled:check.checked});await refresh();}catch(e){check.checked=!check.checked;notice(e.message);}finally{check.disabled=false;}};
  root.append(label);
  if(data.auto_publish&&!data.block_review)root.append(make('p','githubImportWarning','Сейчас автопубликация переносит на сайт весь текст HH без проверки. Включите режим блоков, чтобы изменения ждали вашего решения.'));
  if(!data.auto_publish&&!data.block_review)return;
  if(data.block_review)root.append(make('p','muted','Режим блоков включён: автопубликация обновляет только навыки и визуализации. Если отключить его, следующая публикация заменит правки сайта текстом HH.'));
 }
 function render(root,data,refresh){
  root.replaceChildren();root.append(make('p','muted','Снимок HH от '+date(data.captured_at)+'. Свежий снимок загружается через расширение Chrome со страницы резюме на HH; сервис не обращается к HH сам и не меняет резюме там.'));
  if(data.source_url)root.append(external(data.source_url,'Открыть резюме на HH ↗'));
  modeToggle(root,data,refresh);
  const pending=data.blocks.filter(b=>b.status!=='same'&&!b.acknowledged),decided=data.blocks.filter(b=>b.acknowledged);
  root.append(make('p','','Ждут решения: '+data.counts.pending+' · решение уже принято: '+data.counts.acknowledged+' · совпадают: '+data.counts.same));
  const decisions=new Map(),review=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';const changed=()=>{check.checked=false;};
  for(const block of pending)root.append(card(block,data,decisions,changed));
  if(decided.length){const fold=make('details');fold.append(make('summary','','Решение уже принято · '+decided.length));for(const block of decided)fold.append(card(block,data,decisions,changed));root.append(fold);}
  if(!pending.length&&!decided.length){root.append(make('p','muted','Сайт совпадает с основным резюме HH.'));return;}
  review.append(check,document.createTextNode(' Я проверил выбранные блоки, факты, даты и перевод для публикации'));
  const apply=make('button','secondary','Применить решения и опубликовать');apply.type='button';
  apply.onclick=async()=>{apply.disabled=true;try{const chosen=Object.fromEntries([...decisions].map(([key,get])=>[key,get()]));
   const value=await api('portfolio-publication',{op:'block_apply',basis:data.basis,decisions:chosen,reviewed:check.checked},180000);
   notice(value.phase==='published'?'Сайт обновлён. Страница пересоберётся через GitHub Pages.':'Решения сохранены. Текст сайта не изменился.');render(root,value.comparison,refresh);
  }catch(e){notice(e.message);}finally{apply.disabled=false;}};
  root.append(review,apply);
 }
 async function mount(root){const refresh=async()=>render(root,await api('portfolio-publication',{op:'block_compare'},120000),refresh);await refresh();}
 return {mount,render};
})();
