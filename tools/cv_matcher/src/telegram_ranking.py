"""The web ranking in Telegram; no search, generation or browser command on read."""
import time
from .application_workflow import packed,hashed

def reference(bot,c):
    job=c['job'];ref=hashed(['ranking',c['resume']['id'],c['resume']['content_hash'],job['id'],job['description'],c['goal']])[:20]
    from .career_recommendations import explain
    bot.store.setting('recommendation:'+ref,packed({'resume_id':c['resume']['id'],'resume_hash':c['resume']['content_hash'],'vacancy_id':job['id'],'vacancy_hash':hashed(job['description']),'goal':c['goal'],'explanation':explain(bot,c)}))
    return ref

async def show_top(bot):
    candidates=bot.candidates()[:10];refs=[]
    await bot.operator.send('🎯 Топ-10 без откликов\nПолный сохранённый рейтинг для основного CV и цели · 3-small. Исключены существующие отклики, подтверждённо закрытые вакансии и «Не моё».\nПеред подготовкой проверим активность. Просмотр не вызывает API.\n'+('Найдено: '+str(len(candidates)) if candidates else 'Нет актуальных оценок для выбранных CV и цели. Обновите рейтинг в веб-сервисе или запустите поиск.'),[[('🔎 Найти новые вакансии','w:menu:today'),('Полный рейтинг','w:rank:0')]])
    for index,c in enumerate(candidates,1):
        ref=reference(bot,c);refs.append(ref);job=c['job'];r=c['ranking']
        await bot.operator.send('💼 '+str(index)+'. '+job['title']+' · '+job.get('company','')+'\nРейтинг: '+str(round(c['score'],3))+' · к CV: '+str(round(r.get('cv_similarity',c['score']),3))+'\n'+job['link'],[[('Подробный разбор',f'w:rreview:{ref}'),('Подготовить отклик',f'w:pick:{ref}')],[('Почему подходит',f'w:why:{ref}')]])
    bot.store.setting('last-selection',packed({'refs':refs,'created':time.time(),'ranked':True}))

async def show_page(bot,offset):
    offset=max(0,min(int(offset),100000));summary=bot.archive.summary();rid=summary.get('primary_id')
    if not rid:raise ValueError('Сначала выберите основное CV.')
    result=bot.archive.entities('vacancy',status='full',resume_id=rid,goal=summary.get('goal',''),model='text-embedding-3-small',ranked_only=True,exclude_closed=True,limit=5,offset=offset,include_payload=True)
    cv=bot.archive.detail('resume',rid)['payload'];lines=['📊 Полный сохранённый рейтинг','CV: '+cv['title'],'Цель: '+(summary.get('goal') or 'не указана'),'3-small · все компании · полные описания · закрытые исключены.','Уже существующие отклики здесь показаны, как в рейтинге веб-сервиса.'];rows=[]
    for i,row in enumerate(result['items'],offset+1):
        c={'job':row['payload'],'resume':cv,'goal':summary.get('goal',''),'ranking':row['ranking'],'score':row['ranking']['score']};ref=reference(bot,c)
        lines.append(str(i)+'. '+row['title']+' · '+str(round(c['score'],3))+(' · есть отклик/черновик' if row.get('application') or row.get('manual_application',{}).get('marked') else ''))
        rows.append([(str(i)+'. Подробный разбор',f'w:rreview:{ref}')])
    lines.append('Показано '+str(len(result['items']))+' из '+str(result['total']))
    nav=[]
    if offset:nav.append(('← Назад',f'w:rank:{max(0,offset-5)}'))
    if offset+5<result['total']:nav.append(('Далее →',f'w:rank:{offset+5}'))
    if nav:rows.append(nav)
    rows.append([('🎯 Топ-10 без откликов','w:menu:top'),('Главное меню','w:menu:home')])
    await bot.operator.send('\n'.join(lines),rows)
