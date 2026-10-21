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
        rows=db.execute("SELECT a.id,a.status,a.context,w.draft,w.state,w.revision,c.stage,c.work_status,c.next_action,c.follow_up_at FROM applications a LEFT JOIN application_workflow w ON w.app_id=a.id LEFT JOIN application_crm c ON c.app_id=a.id ORDER BY a.created DESC LIMIT 100").fetchall()
        reviews=db.execute('SELECT COUNT(*) FROM skill_analyses').fetchone()[0]
        ranks=db.execute('SELECT payload FROM ranking_runs WHERE resume_id=? ORDER BY generated_at DESC',(summary['primary_id'],)).fetchall() if cv else []
    ranked=next((json.loads(r[0]) for r in ranks if json.loads(r[0]).get('resume_hash')==cv.get('content_hash') and json.loads(r[0]).get('goal','')==summary['goal']),None) if cv else None
    items=[]
    for row in rows:
        c=json.loads(row['context']);state=row['state'] or 'draft';stage=row['stage'] or 'preparing'
        if row['status']=='superseded' or store.case_id(row['id'])!=row['id']:continue
        next_step='Проверить ответы и разрешить действие' if state=='needs_approval' else 'Сверить результат с HH' if state=='uncertain' else 'Дождаться результата HH' if state in ('approved','sending') else 'Следить за ответом' if row['status'] in ('submitted','viewed','invited','rejected','withdrawn') or stage!='preparing' else 'Подготовить форму HH' if row['draft'] else 'Составить сопроводительное письмо'
        if state not in ('needs_approval','uncertain','approved','sending') and row['work_status']:
            next_step=(row['next_action'] or WORK_STATUSES[row['work_status']])
        items.append({'resume_id':c.get('resume_id'),'resume_title':c.get('resume_title',''),'state':state,'status':row['status'],'stage_key':stage,'work_status':WORK_STATUSES.get(row['work_status'],''),'follow_up_at':row['follow_up_at'],'id':row['id'],'title':c['vacancy']['title'],'company':c['vacancy']['company'],'stage':CRM_STAGES[stage],'next':next_step,'needs_attention':state in ('needs_approval','uncertain','needs_input'),'channel':c['channel']})
    items=sorted(items,key=lambda i:not i['needs_attention'])
    step=0 if not cv else 1 if not summary['full_descriptions'] else 2 if not ranked else 3 if not items or any(i['stage']==CRM_STAGES['preparing'] for i in items) else 4
    with store.connect() as db:appointments=[dict(r) for r in db.execute("SELECT a.*,json_extract(b.context,'$.vacancy.company') company,json_extract(b.context,'$.vacancy.title') vacancy_title FROM application_appointments a JOIN applications b ON b.id=a.app_id WHERE a.status='scheduled' AND a.end_at>? ORDER BY a.start_at LIMIT 20",(datetime.now(timezone.utc).isoformat(),))]
    browser=store.browser_status()
    return {'appointments':appointments,'steps':STEPS,'step':step,'cv':{'id':cv['id'],'title':cv['title'],'checked_at':cv.get('checked_at'),'quality':cv['quality']} if cv else None,'goal':summary['goal'],'summary':summary,'ranked':len(ranked.get('all',[])) if ranked else 0,'reviews':reviews,'browser':browser,'items':items,'next':items[0]['next'] if items else ['Выберите резюме и цель','Соберите полные вакансии','Оцените вакансии для выбранного CV','Выберите вакансию и подготовьте письмо','Следите за ответами'][step]}
