/* Company checkboxes select stored jobs. API work starts only from a preview. */
const EmbeddingBatchUI=(()=>{
 let timer,batch;
 function box(){let n=document.getElementById('embeddingBatchPanel');if(!n){n=make('section','analysis');n.id='embeddingBatchPanel';document.getElementById('rankingStatus').after(n);}return n;}
 function button(label,fn){const b=make('button','secondary',label);b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;}
 function render(){const n=box();n.replaceChildren(make('h3','','Embeddings по выбранным компаниям'),make('p','muted','Отметьте компании флажками, выберите CV и карьерную цель выше. text-embedding-3-small создаёт векторы; сходства с CV и целью рассчитываются отдельно. Готовые векторы используются повторно.'),button('Подготовить пакетный расчёт',async()=>{const companies=companyPicker.value;if(companies===null||!companies.length)throw Error('Отметьте конкретные компании, например Google и Meta.');batch=await api('embedding-batch',{op:'prepare',companies,resume_id:$('analysisCV').value,goal:$('rankingGoal').value,model:'text-embedding-3-small'});render();}));
 if(!batch)return;
 const states={prepared:'Готов к запуску',running:'Выполняется',pausing:'Завершаю текущую порцию',paused:'Приостановлен',complete:'Завершён',needs_input:'Нужна проверка'};
 n.append(make('p','',`${states[batch.state]||batch.state} · ${batch.result.processed} / ${batch.total} вакансий · API-запросов ${batch.result.api_requests} · из кэша ${batch.result.cache_reused}`),make('p','muted',`${batch.resume_title} · цель: ${batch.goal} · ${batch.model} · до ${batch.batch_size} вакансий за шаг, API получает до 64 текстовых фрагментов за запрос.`));
 if(batch.result.error)n.append(make('p','muted',batch.result.error));
 if(['prepared','paused','needs_input'].includes(batch.state))n.append(button('Запустить / продолжить через API',async()=>{if(!confirm(`Рассчитать embeddings и сходства для оставшихся ${batch.total-batch.result.processed} вакансий выбранных компаний через text-embedding-3-small? Будут использованы платные API-запросы только для недостающих векторов.`))return;batch=await api('embedding-batch',{op:'control',action:'start',id:batch.id,confirmed:true});render();poll();}));
 if(batch.state==='running')n.append(button('Пауза после текущей порции',async()=>{batch=await api('embedding-batch',{op:'control',action:'pause',id:batch.id});render();}));
 }
 function poll(){clearInterval(timer);timer=setInterval(async()=>{try{batch=(await api('embedding-batch')).batch;render();if(!['running','pausing'].includes(batch?.state)){clearInterval(timer);if(batch?.state==='complete'&&tab==='ranking')await loadList(true);}}catch(e){clearInterval(timer);notice(e.message);}},4000);}
 async function enter(){batch=(await api('embedding-batch')).batch;render();if(['running','pausing'].includes(batch?.state))poll();}
 return {enter};
})();
