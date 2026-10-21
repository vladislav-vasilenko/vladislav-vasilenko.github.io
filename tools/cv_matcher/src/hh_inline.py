"""Small bridge to existing generators; no form submission or application creation."""
from datetime import datetime,timezone
import json,hashlib
from .resume_source import normalize
from .resume_source import content_hash,_load_resume_bundle,matching_text
from .resume_files import redact_contacts
from .skill_analysis import context,cached,analyze

def run(store,data,root):
    action=data.get('action')
    if action not in ('analysis_read','cover_read','analysis','cover','answer','analysis_export','analysis_import','cover_export','cover_save','answer_export'):raise ValueError('Неизвестное действие HH.')
    ctx=context(store,data.get('resume_id'),data.get('vacancy_id'),data.get('goal',''))
    if content_hash(ctx['cv'])!=data.get('resume_hash'):raise ValueError('Версия CV в расширении и SQLite различается. Выполните синхронизацию архива.')
    if action=='analysis_export':
        from .external_analysis import export_review
        result=export_review(store,ctx['resume_id'],ctx['vacancy_id'],ctx['goal'])
    elif action=='analysis_import':
        from .external_analysis import import_review
        result=import_review(store,data.get('export_id'),data.get('answer'))
        if result['resume_id']!=ctx['resume_id'] or result['vacancy_id']!=ctx['vacancy_id'] or result['goal']!=ctx['goal']:raise ValueError('Ответ сохранён в истории другой пары CV–вакансия. Откройте исходную вакансию.')
        if result['resume_hash']!=ctx['resume_hash'] or result['vacancy_hash']!=ctx['vacancy_hash']:raise ValueError('Разбор сохранён в истории прежних версий. CV или вакансия изменились; скопируйте новый промпт.')
    elif action in ('cover_export','cover_save','answer_export'):
        cv=ctx['cv'];job=ctx['job'];application_context={'resume_id':cv['id'],'resume_hash':cv['content_hash'],'resume_title':cv['title'],'resume_url':cv.get('source_url',''),'resume_text':ctx['cv_text'],'vacancy':{k:job.get(k,'') for k in ('id','title','company','link','description')},'goal':ctx['goal']}
        if action in ('cover_export','answer_export'):result={'context':application_context,'saved':read_cover(store,ctx,root) if action=='cover_export' else None,'vacancy_hash':ctx['vacancy_hash'],'api_requests':0}
        else:
            if job.get('archived'):raise ValueError('Вакансия закрыта. Письмо не сохраняется для нового отклика.')
            if data.get('resume_hash_at_export')!=cv['content_hash'] or data.get('vacancy_hash_at_export')!=ctx['vacancy_hash']:raise ValueError('После копирования промпта изменились исходные документы. Скопируйте новый промпт.')
            from .application_store import ApplicationStore
            apps=ApplicationStore(store.path)
            app=apps.create({'resume_id':cv['id'],'bundle':{'schema_version':2,'primary_id':cv['id'],'resumes':[cv]},'vacancy':job,'goal':ctx['goal'],'channel':'hh' if job['id'].startswith('hh_') else 'career'})
            actual=app['context']
            if normalize(actual['vacancy']['description'])!=normalize(redact_contacts(job['description'])) or actual['vacancy']['title']!=job['title']:raise ValueError('В CRM сохранён отклик по другой версии вакансии. Обновите его контекст на локальном сайте.')
            result=apps.save_letter(app['id'],data.get('text'),data.get('revision'))['workflow']
            result={'text':result['draft'],'revision':result['revision'],'source':'crm','api_requests':0,'application_id':app['id']}
    elif action=='analysis_read':result=cached(store,ctx)
    elif action=='cover_read':result=read_cover(store,ctx,root)
    elif action=='analysis':result=analyze(store,ctx['resume_id'],ctx['vacancy_id'],ctx['goal'],_context=ctx)
    else:
        if ctx['job'].get('archived'):raise ValueError('Вакансия закрыта. Черновик не создаётся.')
        bundle={'schema_version':2,'primary_id':ctx['resume_id'],'resumes':[ctx['cv']]}
        _load_resume_bundle(bundle,now=datetime.now(timezone.utc))
        if action=='cover':
            from .cover_letter import generate_cover_letter
            result=generate_cover_letter({'resume_id':ctx['resume_id'],'bundle':bundle,'vacancy':ctx['job'],'sentence_count':data.get('sentence_count',2),'comments':data.get('comments',''),**({'model':data['model']} if data.get('model') else {})},root/'.cache/cover_letters')
        else:
            from .recruiter_answers import draft_answer
            job={k:ctx['job'].get(k) for k in ('id','title','company','link','description')}
            from .candidate_facts import answer_context
            result=draft_answer(answer_context(store,{'resume_id':ctx['resume_id'],'resume_text':redact_contacts(matching_text(ctx['cv'])),'vacancy':job,'goal':ctx['goal'],'preferences':data.get('comments','')}),redact_contacts(str(data.get('question',''))),data.get('model','luna'),root/'.cache/recruiter_answers')
    return {'kind':action,'result':result,'resume_id':ctx['resume_id'],'resume_hash':data['resume_hash'],'vacancy_id':ctx['vacancy_id']}


def read_cover(store,ctx,root):
    """Only exact current versions; reading never invokes a generator."""
    cv=ctx['cv'];job=ctx['job']
    with store.connect() as db:
        available=db.execute("SELECT 1 FROM sqlite_master WHERE name='application_workflow'").fetchone()
        rows=db.execute("SELECT a.id,a.context,w.draft,w.revision FROM applications a JOIN application_workflow w ON w.app_id=a.id WHERE a.dedupe=? AND w.draft<>'' ORDER BY w.updated_at DESC",(('hh:' if ctx['vacancy_id'].startswith('hh_') else 'career:')+ctx['vacancy_id'],)).fetchall() if available else []
    for row in rows:
        c=json.loads(row['context'])
        if c['resume_id']==ctx['resume_id'] and c['resume_hash']==cv['content_hash'] and c.get('goal','').strip()==ctx['goal'].strip() and c['vacancy']['title']==job['title'] and normalize(c['vacancy']['description'])==normalize(redact_contacts(job['description'])):
            return {'text':row['draft'],'cached':True,'api_requests':0,'source':'crm','application_id':row['id'],'revision':row['revision'],'review_note':'Сохранённая редакция CRM. Проверьте её перед переносом в форму отклика.'}
    from .cover_letter import validate_draft
    text=redact_contacts(normalize(job['description']));jh=hashlib.sha256((normalize(job['title'])+'\n'+normalize(job.get('company'))+'\n'+text).encode()).hexdigest()
    directory=root/'.cache/cover_letters'
    for path in sorted(directory.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
        try:
            saved=json.loads(path.read_text());r=saved['result']
            if r['resume_id']!=ctx['resume_id'] or r['resume_hash']!=cv['content_hash'] or r['vacancy_id']!=ctx['vacancy_id'] or r['vacancy_hash']!=jh:continue
            checked=validate_draft(saved['raw'],redact_contacts(matching_text(cv)),text,sentence_count=r['sentence_count'],comments=r.get('comments',''))
            return {**r,**checked,'source':'cover_cache','cached':True,'api_requests':0}
        except (OSError,ValueError,KeyError,TypeError):continue
    return None
