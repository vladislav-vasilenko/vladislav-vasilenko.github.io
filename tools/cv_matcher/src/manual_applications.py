"""Reversible owner-reported application marks. Never fabricate a site receipt."""
import json
from datetime import datetime,timezone
PREFIX='manual-application:'

def all_marks(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='archive_meta'").fetchone():return {}
    return {r['key'][len(PREFIX):]:json.loads(r['value']) for r in db.execute('SELECT key,value FROM archive_meta WHERE key LIKE ?',(PREFIX+'%',))}

def set_mark(archive,vacancy_id,marked,revision):
    if not isinstance(vacancy_id,str) or type(marked) is not bool or type(revision) is not int:raise ValueError('Нужны вакансия, флаг отметки и её версия.')
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM entities WHERE kind='vacancy' AND id=?",(vacancy_id,)).fetchone():raise ValueError('Вакансия не найдена.')
        key=PREFIX+vacancy_id;old=db.execute('SELECT value FROM archive_meta WHERE key=?',(key,)).fetchone();old=json.loads(old[0]) if old else {'marked':False,'revision':0}
        if old['marked']==marked:return old
        if old['revision']!=revision:raise ValueError('Отметка уже изменилась. Обновите карточку.')
        if marked and db.execute("SELECT 1 FROM sqlite_master WHERE name='browser_commands'").fetchone():
            commands=db.execute("SELECT b.id,b.app_id,b.state FROM browser_commands b JOIN applications a ON a.id=b.app_id WHERE json_extract(a.context,'$.vacancy.id')=? AND b.kind IN ('execute','career_fill') AND b.state IN ('queued','running')",(vacancy_id,)).fetchall()
            if any(c['state']=='running' for c in commands):raise ValueError('Для этой вакансии уже выполняется действие в браузере. Дождитесь результата перед ручной отметкой.')
            for c in commands:
                db.execute("UPDATE browser_commands SET state='cancelled' WHERE id=?",(c['id'],))
                db.execute("UPDATE application_approvals SET status='revoked' WHERE app_id=? AND status='approved'",(c['app_id'],))
                db.execute("UPDATE application_workflow SET state='needs_input' WHERE app_id=?",(c['app_id'],))
        now=datetime.now(timezone.utc).isoformat();value={'marked':marked,'revision':old['revision']+1,'marked_at':now,'source':'user','site_confirmed':False}
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
        archive._event(db,'vacancy',vacancy_id,'manual_applied' if marked else 'manual_unmarked',now,{'source':'user','revision':value['revision']})
    return value

def listing(store):
    with store.connect() as db:
        marks=all_marks(db);rows=db.execute("SELECT id,title,company,payload FROM entities WHERE kind='vacancy'").fetchall()
    return [{'vacancy_id':r['id'],'title':r['title'],'company':r['company'],'url':json.loads(r['payload']).get('link'),**marks[r['id']]} for r in rows if marks.get(r['id'],{}).get('marked')]
