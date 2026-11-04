'use strict';
// Paid work never starts from a page view: this panel only reads status until the owner consents.
const AutoScoringUI=(()=>{
 const PHASE={off:'Выключен',waiting:'Ждёт следующей проверки',idle:'Новых вакансий для расчёта нет',cap_reached:'Месячный лимит исчерпан; расчёт продолжится в следующем месяце',needs_input:'Нужны основное резюме и цель',error:'Ошибка; повтор через час'};
 function box(){let n=document.getElementById('autoScoringPanel');if(!n){n=make('section','analysis');n.id='autoScoringPanel';document.getElementById('rankingStatus').after(n);}return n;}
 function render(n,data){
  n.replaceChildren(make('h3','','Автоматический расчёт новых вакансий'),make('p','muted','После импорта сервис сам рассчитывает embeddings и сходства для новых вакансий публичной выборки через '+data.model+'. Старые вакансии не затрагиваются, их можно рассчитать вручную. Работает, только пока запущен сервис.'));
  n.append(make('p','',(PHASE[data.phase]||data.phase)+' · потрачено в этом месяце $'+data.spent_usd.toFixed(4)+' из $'+Number(data.monthly_cap_usd).toFixed(2)+' · ждут расчёта: '+data.pending+' · старых без оценки: '+data.older_unscored));
  n.append(make('p','','Все embeddings за месяц, включая ручные: $'+data.embeddings_spent_usd.toFixed(4)+' из $'+Number(data.ceiling_usd).toFixed(2)+'. При достижении потолка запросы к OpenAI не отправляются.'));
  if(data.last_error)n.append(make('p','githubImportWarning',data.last_error));
  const capLabel=make('label','','Лимит в месяц, $ '),cap=make('input');cap.type='number';cap.min='0.01';cap.max=String(data.max_cap_usd);cap.step='0.01';cap.value=String(data.monthly_cap_usd);capLabel.append(cap);n.append(capLabel);
  const consent=make('label'),check=make('input');check.type='checkbox';check.style.width='auto';consent.append(check,document.createTextNode(' Разрешаю автоматические платные запросы к OpenAI в пределах этого лимита'));
  const action=make('button','secondary',data.enabled?'Сохранить лимит':'Включить автоматический расчёт');action.type='button';
  action.onclick=async()=>{action.disabled=true;try{render(n,await api('embedding-batch',{op:'auto_configure',enabled:true,confirmed:check.checked,monthly_cap_usd:Number(cap.value)}));notice('Настройка сохранена.');}catch(e){notice(e.message);}finally{action.disabled=false;}};
  cap.oninput=()=>{check.checked=false;};n.append(consent,action);
  const ceilingLabel=make('label','','Общий потолок embeddings в месяц, $ '),ceiling=make('input');ceiling.type='number';ceiling.min='0.01';ceiling.max=String(data.max_ceiling_usd);ceiling.step='0.01';ceiling.value=String(data.ceiling_usd);ceilingLabel.append(ceiling);
  const save=make('button','secondary','Сохранить потолок');save.type='button';ceiling.oninput=()=>{check.checked=false;};
  save.onclick=async()=>{save.disabled=true;try{render(n,await api('embedding-batch',{op:'spend_ceiling',ceiling_usd:Number(ceiling.value),confirmed:check.checked}));notice('Потолок сохранён.');}catch(e){notice(e.message);}finally{save.disabled=false;}};
  n.append(ceilingLabel,save);
  if(data.enabled){const off=make('button','secondary','Выключить');off.type='button';off.onclick=async()=>{off.disabled=true;try{render(n,await api('embedding-batch',{op:'auto_configure',enabled:false}));notice('Автоматический расчёт выключен.');}catch(e){notice(e.message);}finally{off.disabled=false;}};n.append(off);}
  if(data.history.length){const log=make('details');log.append(make('summary','','Журнал платных настроек · '+data.history.length));const names={auto_on:'Автоматический расчёт включён',auto_off:'Автоматический расчёт выключен',ceiling:'Изменён общий потолок'};for(const item of data.history){const amount=item.ceiling_usd??item.cap_usd;log.append(make('p','muted',item.at+' · '+(names[item.action]||item.action)+' · $'+Number(amount).toFixed(2)));}n.append(log);}
 }
 async function enter(){const n=box();render(n,await api('embedding-batch',{op:'auto_status'}));}
 return {enter,render};
})();
