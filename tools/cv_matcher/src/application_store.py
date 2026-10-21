"""Private durable application/answer queue shared by extension and Telegram runner."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from datetime import datetime,timezone
from .board_import import identity
from .resume_source import _load_resume_bundle, matching_text
from .resume_files import redact_contacts

from .application_workflow import WorkflowMixin

class ApplicationStore(WorkflowMixin):
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);os.chmod(self.path.parent,0o700)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS applications(id TEXT PRIMARY KEY,dedupe TEXT UNIQUE,context TEXT,status TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY,app_id TEXT,source_id INTEGER,fingerprint TEXT,question TEXT,buttons TEXT,draft TEXT DEFAULT '',model TEXT DEFAULT '',status TEXT,created REAL,UNIQUE(app_id,source_id,fingerprint));
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);''')
            self.init_workflow(db)
            from .collection_backfill import init as init_backfill
            init_backfill(db)
        os.chmod(self.path,0o600)
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;return db
    def create(self,payload,*,now=None):
        now=now or datetime.now(timezone.utc)
        selected=payload.get('resume_id');bundle=payload['bundle']
        cv=_load_resume_bundle({**bundle,'primary_id':selected},now=now)['primary']
        job=payload['vacancy'];valid=identity(job.get('link',''))
        if not valid or job.get('id')!=valid['id'] or job.get('description_quality')!='full' or job.get('archived'):
            raise ValueError('Нужна полная актуальная вакансия.')
        channel=payload.get('channel','hh')
        if channel not in {'hh','telegram','career'}:raise ValueError('Неизвестный канал отклика.')
        if channel=='hh' and not valid['id'].startswith('hh_'):raise ValueError('Для отклика HH нужна вакансия HH. Сайт компании использует отдельный канал.')
        if channel=='career' and valid['id'].startswith('hh_'):raise ValueError('Для вакансии HH используйте канал HH.')
        if channel=='hh' and (cv.get('source_type') or 'hh')!='hh':raise ValueError('Для отклика HH выберите HH-резюме.')
        goal=str(payload.get('goal') or '').strip()
        if len(goal)>2000:raise ValueError('Карьерная цель слишком длинная.')
        context={'resume_id':selected,'resume_hash':cv['content_hash'],'resume_title':cv['title'],
            'resume_url':cv.get('source_url'),'resume_text':redact_contacts(matching_text(cv)),
            'vacancy':{**valid,'title':job['title'],'company':job.get('company',''),'description':redact_contacts(job['description'])},
            'goal':goal,'channel':channel}
        if len(json.dumps(context))>300000:raise ValueError('Контекст отклика слишком велик.')
        dedupe=channel+':'+valid['id']
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM applications WHERE dedupe=?',(dedupe,)).fetchone()
            if row:
                old=json.loads(row['context'])
                untouched=not db.execute('SELECT 1 FROM application_workflow WHERE app_id=? AND form IS NOT NULL',(row['id'],)).fetchone() and not db.execute('SELECT 1 FROM application_drafts WHERE app_id=?',(row['id'],)).fetchone() and not db.execute('SELECT 1 FROM application_discussion WHERE app_id=?',(row['id'],)).fetchone() and row['status']=='queued' and not db.execute('SELECT 1 FROM turns WHERE app_id=? LIMIT 1',(row['id'],)).fetchone() and not db.execute('SELECT 1 FROM settings WHERE key=?',('started:'+row['id'],)).fetchone() and not db.execute('SELECT 1 FROM application_channels WHERE app_id=? AND case_id<>app_id',(row['id'],)).fetchone() and not db.execute('SELECT 1 FROM giga_starts WHERE app_id=?',(row['id'],)).fetchone() and not db.execute('SELECT 1 FROM application_field_versions WHERE app_id=?',(row['id'],)).fetchone() and not db.execute('SELECT 1 FROM application_approvals WHERE app_id=?',(row['id'],)).fetchone()
                if untouched:
                    db.execute('UPDATE applications SET context=? WHERE id=?',(json.dumps(context,ensure_ascii=False),row['id']))
                    return {**dict(row),'context':context}
                if old['resume_hash']!=cv['content_hash'] or old['resume_id']!=selected:
                    raise ValueError('Отклик по этой вакансии уже создан с другим CV/версией. Проверьте существующий отклик.')
                if old.get('goal','')!=goal:raise ValueError('Отклик уже создан с другой карьерной целью. Проверьте его перед продолжением.')
                return self.get(row['id'])
            app_id=uuid.uuid4().hex[:20]
            db.execute('INSERT INTO applications VALUES(?,?,?,?,?)',(app_id,dedupe,json.dumps(context,ensure_ascii=False),'queued',time.time()))
            db.execute('INSERT INTO application_channels VALUES(?,?,?)',(app_id,app_id,time.time()))
        return self.get(app_id)
    def get(self,app_id):
        with self.connect() as db:row=db.execute('SELECT * FROM applications WHERE id=?',(app_id,)).fetchone()
        if not row:raise ValueError('Отклик не найден.')
        return {**dict(row),'context':json.loads(row['context'])}
    def list(self):
        with self.connect() as db:ids=[r[0] for r in db.execute('SELECT id FROM applications ORDER BY created DESC LIMIT 1000')]
        return [self.get(id) for id in ids]
    def activate(self,app_id):
        app=self.get(app_id)
        if app['context']['channel']!='telegram':raise ValueError('Это не Telegram-отклик.')
        if app['status']=='completed':raise ValueError('Отклик уже завершён.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            active=db.execute("SELECT id FROM applications WHERE status='active' AND id<>?",(app_id,)).fetchone()
            if active:raise ValueError('Сначала приостановите текущий диалог: /pause.')
            db.execute("UPDATE applications SET status='active' WHERE id=?",(app_id,))
        return self.get(app_id)
    def active(self):
        with self.connect() as db:row=db.execute("SELECT id FROM applications WHERE status='active' ORDER BY created DESC LIMIT 1").fetchone()
        return self.get(row[0]) if row else None
    def set_status(self,app_id,status):
        if status not in {'queued','paused','active','completed','submitted','uncertain','needs_input'}:raise ValueError('Неизвестный статус.')
        with self.connect() as db:db.execute('UPDATE applications SET status=? WHERE id=?',(status,app_id))
    @staticmethod
    def fingerprint(question,buttons,version=''):
        return hashlib.sha256(json.dumps([question,buttons,version],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    def receive(self,app_id,source_id,question,buttons,version=''):
        fp=self.fingerprint(question,buttons,version)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT id FROM turns WHERE app_id=? AND source_id=? AND fingerprint=?',(app_id,source_id,fp)).fetchone()
            if old:return self.turn(old[0]),False
            db.execute("UPDATE turns SET status='superseded' WHERE app_id=? AND status IN ('received','draft','needs_input')",(app_id,))
            tid=uuid.uuid4().hex[:20]
            db.execute('INSERT INTO turns(id,app_id,source_id,fingerprint,question,buttons,status,created) VALUES(?,?,?,?,?,?,?,?)',
                (tid,app_id,source_id,fp,question,json.dumps(buttons,ensure_ascii=False),'received',time.time()))
        return self.turn(tid),True
    def turn(self,turn_id):
        with self.connect() as db:row=db.execute('SELECT * FROM turns WHERE id=?',(turn_id,)).fetchone()
        if not row:raise ValueError('Вопрос не найден.')
        return {**dict(row),'buttons':json.loads(row['buttons'])}
    def draft(self,turn_id,text,model='manual',needs_user=False):
        if not isinstance(text,str) or (not text.strip() and not needs_user) or len(text.encode('utf-16-le'))//2>4000:raise ValueError('Сократите ответ до 4000 символов Telegram (эмодзи могут занимать два).')
        with self.connect() as db:
            count=db.execute("UPDATE turns SET draft=?,model=?,status=? WHERE id=? AND status IN ('received','draft','needs_input')",(text.strip(),model,'needs_input' if needs_user else 'draft',turn_id)).rowcount
            if not count:raise ValueError('Вопрос изменился или ответ уже отправлялся.')
        return self.turn(turn_id)
    def claim_send(self,turn_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count=db.execute("UPDATE turns SET status='sending' WHERE id=? AND status IN ('received','draft','needs_input')",(turn_id,)).rowcount
            if not count:raise ValueError('Этот ответ уже отправлен, отправляется или устарел. Повтор автоматически запрещён.')
        return self.turn(turn_id)
    def finish_send(self,turn_id,success):
        with self.connect() as db:db.execute('UPDATE turns SET status=? WHERE id=?',('sent' if success else 'uncertain',turn_id))
    def setting(self,key,value=None):
        with self.connect() as db:
            if value is not None:db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,str(value)))
            row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return row[0] if row else None
    def history(self,app_id):
        with self.connect() as db:rows=db.execute("SELECT question,draft FROM turns WHERE app_id=? AND status='sent' ORDER BY created DESC LIMIT 8",(app_id,)).fetchall()
        return [{'question':r['question'],'answer':r['draft']} for r in reversed(rows)]
