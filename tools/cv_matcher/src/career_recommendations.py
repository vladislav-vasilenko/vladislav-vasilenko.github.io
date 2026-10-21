"""Explanations and explicit owner feedback, independent of transport/model calls."""
import json,time
from .application_workflow import packed,hashed

def explain(service,candidate):
    c=candidate;r=c.get('ranking',{});job=c['job']
    from .skill_analysis import context,cached
    analysis=cached(service.archive,context(service.archive,c['resume']['id'],job['id'],c['goal']))
    feedback=json.loads(service.store.setting('career-feedback:'+hashed([c['resume']['id'],job['id']])) or '{}')
    priority=c['score']
    return {'qualification_fit':{'semantic_similarity':r.get('cv_similarity',c['score']),'meaning':'Семантическая близость к CV; не доля подтверждённых навыков.','requirements':analysis.get('metrics',{}).get('overall') if analysis else None},'career_alignment':{'semantic_similarity':r.get('goal_similarity'),'goal':c['goal'],'explanation':analysis.get('goal_alignment') if analysis else None},'application_priority':{'value':round(priority,4),'rule':'Сохранённый рейтинг выбранных CV, цели и модели. ⭐ — ваша пометка; порядок топ-10 по близости не меняет.','feedback':feedback.get('choice'),'recommendation':analysis.get('recommendation') if analysis else None},'analysis_key':analysis['key'] if analysis else None,'source':{'vacancy_id':job['id'],'url':job['link'],'resume_hash':c['resume']['content_hash'],'ranked_at':r.get('ranked_at'),'listing_verified_at':job.get('listing_verified_at'),'description_fetched_at':job.get('description_fetched_at') or job.get('collected_at')}}

def feedback(service,ref,choice):
    if choice not in ('interesting','uninteresting','priority'):raise ValueError('Неизвестная оценка рекомендации.')
    item=json.loads(service.store.setting('recommendation:'+ref) or '{}')
    if not item:raise ValueError('Рекомендация не найдена.')
    cv=service.archive.detail('resume',item['resume_id'])['payload']
    if item.get('resume_hash') and cv['content_hash']!=item['resume_hash']:raise ValueError('CV изменилось. Оцените новую подборку.')
    service.store.setting('career-feedback:'+hashed([item['resume_id'],item['vacancy_id']]),packed({'choice':choice,'resume_hash':cv['content_hash'],'at':time.time()}))
    return item
