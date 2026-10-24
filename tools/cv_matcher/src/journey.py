"""Shared read-only progress for website and Telegram. No collection, generation or sending."""
import json
from datetime import datetime,timezone
from .archive_store import ArchiveStore
from .application_workflow import CRM_STAGES,WORK_STATUSES

STEPS=['Резюме и цель','Сбор вакансий','Оценка соответствия','Письмо и отправка','Ответы и этапы']

def overview(store):
    archive=ArchiveStore(store.path);summary=archive.summary();cv=None
    if summary['primary_id']:
        try:cv=archive.detail('resume',summary['primary_id'])['payload']
        except ValueError:pass
    with store.connect() as db:
        reviews=db.execute('SELECT COUNT(*) FROM skill_analyses').fetchone()[0]
        ranks=db.execute('SELECT payload FROM ranking_runs WHERE resume_id=? ORDER BY generated_at DESC',(summary['primary_id'],)).fetchall() if cv else []
    ranked=next((json.loads(r[0]) for r in ranks if json.loads(r[0]).get('resume_hash')==cv.get('content_hash') and json.loads(r[0]).get('goal','')==summary['goal']),None) if cv else None
    from .application_attention import items as attention_items
    items=attention_items(store)
    step=0 if not cv else 1 if not summary['full_descriptions'] else 2 if not ranked else 3 if not items or any(i['stage']==CRM_STAGES['preparing'] for i in items) else 4
    with store.connect() as db:appointments=[dict(r) for r in db.execute("SELECT a.*,json_extract(b.context,'$.vacancy.company') company,json_extract(b.context,'$.vacancy.title') vacancy_title FROM application_appointments a JOIN applications b ON b.id=a.app_id WHERE a.status='scheduled' AND a.end_at>? ORDER BY a.start_at LIMIT 20",(datetime.now(timezone.utc).isoformat(),))]
    browser=store.browser_status()
    from .career_notifications import status
    from .career_application import CareerApplication
    return {'notifications':status(CareerApplication(store)),'appointments':appointments,'steps':STEPS,'step':step,'cv':{'id':cv['id'],'title':cv['title'],'checked_at':cv.get('checked_at'),'quality':cv['quality']} if cv else None,'goal':summary['goal'],'summary':summary,'ranked':len(ranked.get('all',[])) if ranked else 0,'reviews':reviews,'browser':browser,'items':items,'next':items[0]['next'] if items else ['Выберите резюме и цель','Соберите полные вакансии','Оцените вакансии для выбранного CV','Выберите вакансию и подготовьте письмо','Следите за ответами'][step]}
