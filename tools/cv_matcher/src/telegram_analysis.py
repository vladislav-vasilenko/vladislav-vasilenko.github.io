"""Read a recommendation in depth without creating an application or browser job."""
import asyncio
from .application_workflow import packed

STATUS={'confirmed':'✅ Подтверждено','partial':'🟡 Частично','studying':'📚 Изучение','not_evidenced':'❔ Нет подтверждения в CV','explicit_gap':'🔸 Явный пробел'}

async def card(bot,ref,analysis=None,page=0):
    data=bot.recommendation_context(ref)
    if analysis is None:analysis=bot.analyze(data['resume_id'],data['vacancy_id'],data['goal'])['analysis']
    text='🔎 Подробный разбор\n'+data['vacancy']['title'][:220]+'\nCV: '+data['resume']['title'][:140]+'\n\n'
    if not analysis:
        text+='Сохранённого разбора для текущих CV, вакансии и цели нет.\n\nLuna: один платный запрос с профессиональным текстом CV, вакансией и целью в OpenAI; готовый результат берётся из кэша.\nБез API: промпт для ChatGPT и импорт JSON.\n\nПисьмо, форма и отправка здесь не запускаются.'
        rows=[[('Разобрать · Luna API',f'w:rapi:{ref}'),('Без API',f'w:roff:{ref}')]]
    else:
        requirements=analysis.get('requirements',[]);pages=max(1,(len(requirements)+1)//2);page=max(0,min(page,pages-1))
        metric=analysis.get('metrics',{}).get('overall',{}).get('percent')
        text+='Подтверждение требований: '+(str(metric)+'%' if metric is not None else 'нет оценки')+' по рубрике; не вероятность найма.\n'+analysis.get('recommendation_reason','')[:250]+'\nЦель: '+analysis.get('goal_alignment','')[:250]+'\n'
        for row in requirements[page*2:page*2+2]:
            text+='\n'+STATUS.get(row.get('status'),'❔ Неизвестно')+' · '+row.get('requirement','')[:180]+'\n'+row.get('explanation','')[:240]+'\nВакансия: «'+row.get('job_quote','')[:220]+'»\n'
            if row.get('resume_quotes'):text+='CV: «'+row['resume_quotes'][0][:220]+'»\n'
            text+='Следующий шаг: '+row.get('action','')[:170]+'\n'
        if page==pages-1:
            if analysis.get('questions'):text+='\nЧто уточнить: '+'; '.join(q[:140] for q in analysis['questions'][:3])+'\n'
            if analysis.get('limitations'):text+='Ограничения: '+'; '.join(q[:100] for q in analysis['limitations'][:2])+'\n'
        text+='\nТребования · страница '+str(page+1)+' из '+str(pages)
        nav=[]
        if page:nav.append(('← Назад',f'w:rpage:{ref}@{page-1}'))
        if page+1<pages:nav.append(('Далее →',f'w:rpage:{ref}@{page+1}'))
        rows=[nav] if nav else []
    rows.append([('Подготовить отклик',f'w:pick:{ref}'),('К подборке','w:menu:results')])
    await bot.operator.send(text,rows)

async def recommendation_action(bot,op,value):
    ref=value;page=0
    if op=='rpage':ref,number=value.rsplit('@',1);page=int(number)
    data=bot.recommendation_context(ref)  # Same version guard for all modes.
    if op in ('rreview','rpage'):return await card(bot,ref,page=page)
    if op=='rapi':
        await bot.operator.send('⏳ Выполняю подробный разбор Luna. Результат сохранится в истории; отклик не отправляется.')
        result=await asyncio.to_thread(bot.analyze_context,data['resume_id'],data['vacancy_id'],data['goal'])
        return await card(bot,ref,result)
    if op=='roff':
        from .external_analysis import export_review
        exported=export_review(bot.archive,data['resume_id'],data['vacancy_id'],data['goal'])
        bot.store.setting('recommendation-analysis-export:'+ref,exported['export_id'])
        if hasattr(bot.operator,'send_prompt'):await bot.operator.send_prompt(exported['prompt'])
        else:await bot.operator.send(exported['prompt'])
        return await bot.operator.send('📋 Разбор без API\nПолучите JSON в ChatGPT по промпту и верните его сюда.',[[('Вставить JSON разбора',f'w:rimport:{ref}')]])
    export_id=bot.store.setting('recommendation-analysis-export:'+ref)
    if not export_id:raise ValueError('Сначала получите промпт разбора без API.')
    bot.store.setting('workflow_waiting',packed({'mode':'recommendation_analysis_import','ref':ref,'export_id':export_id}))
    await bot.operator.send('Пришлите JSON результата. /cancel — отмена.')

async def import_result(bot,p,text):
    bot.recommendation_context(p['ref'])
    from .external_analysis import import_review
    analysis=import_review(bot.archive,p['export_id'],text)
    bot.store.setting('workflow_waiting','')
    await card(bot,p['ref'],analysis)
