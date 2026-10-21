"""One recruitment case with frozen per-channel contexts and explicit screening completion."""
import json,secrets,time

class ChannelMixin:
    def init_channels(self,db):
        db.execute('CREATE TABLE IF NOT EXISTS application_channels(app_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,linked_at REAL NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS application_channels_case ON application_channels(case_id)')
        # Legacy cards remain separate until their context is explicitly checked and linked.
        db.execute('INSERT OR IGNORE INTO application_channels SELECT id,id,created FROM applications')

    def case_id(self,app_id):
        with self.connect() as db:
            row=db.execute('SELECT case_id FROM application_channels WHERE app_id=?',(app_id,)).fetchone()
        return row[0] if row else app_id

    def linked_channels(self,app_id):
        case_id=self.case_id(app_id)
        with self.connect() as db:
            rows=db.execute('SELECT a.id,a.status,a.context FROM applications a JOIN application_channels c ON c.app_id=a.id WHERE c.case_id=? ORDER BY a.created',(case_id,)).fetchall()
        return [{'id':r['id'],'channel':json.loads(r['context'])['channel'],'status':r['status']} for r in rows]

    def start_screening(self,app_id,confirmed=False):
        from .application_workflow import packed
        if confirmed is not True:raise ValueError('Подтвердите связь Giga с этой вакансией и выбранным CV.')
        case_id=self.case_id(app_id);source=self.get(case_id);ctx=source['context']
        if ctx['channel']!='hh':raise ValueError('Переход в Giga доступен из карточки HH.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._wf(db,case_id)
            stage=db.execute('SELECT stage FROM application_crm WHERE app_id=?',(case_id,)).fetchone()
            if stage and stage[0] in ('rejected','offer'):raise ValueError('Отбор уже завершён. Проверьте этап CRM.')
            if db.execute("SELECT 1 FROM browser_commands WHERE app_id=? AND kind='execute' AND state IN ('queued','running','uncertain')",(case_id,)).fetchone():raise ValueError('Сначала сверьте результат отправки HH.')
            if source['status'] not in ('submitted','viewed','invited'):
                raise ValueError('Сначала синхронизируйте подтверждённый отклик или приглашение HH.')
            old=db.execute('SELECT * FROM applications WHERE dedupe=?',('telegram:'+ctx['vacancy']['id'],)).fetchone()
            if old:
                other=json.loads(old['context'])
                if {k:v for k,v in other.items() if k!='channel'}!={k:v for k,v in ctx.items() if k!='channel'}:raise ValueError('Существующий Giga-диалог использует другой CV, цель или версию вакансии. Автоматическое объединение запрещено.')
                child=old['id'];root=db.execute('SELECT case_id FROM application_channels WHERE app_id=?',(child,)).fetchone()
                if root and root[0] not in (child,case_id):raise ValueError('Диалог уже связан с другим откликом.')
                if (not root or root[0]==child) and db.execute('SELECT 1 FROM application_crm WHERE app_id=?',(child,)).fetchone():raise ValueError('У отдельной карточки Giga уже есть план CRM. Сначала сверяйте его вручную; история не объединяется автоматически.')
            else:
                child=secrets.token_hex(10)
                db.execute('INSERT INTO applications VALUES(?,?,?,?,?)',(child,'telegram:'+ctx['vacancy']['id'],packed({**ctx,'channel':'telegram'}),'queued',time.time()))
            db.execute('INSERT OR IGNORE INTO application_channels VALUES(?,?,?)',(case_id,case_id,time.time()))
            previous=db.execute('SELECT case_id FROM application_channels WHERE app_id=?',(child,)).fetchone()
            if not previous or previous[0]!=case_id:
                db.execute('INSERT OR REPLACE INTO application_channels VALUES(?,?,?)',(child,case_id,time.time()))
                self._event(db,case_id,'channel_linked',{'channel':'telegram','application_id':child,'actor':'user','resume_hash':ctx['resume_hash']})
        return self.workflow(child)

    def screening_preview(self,app_id):
        from .application_workflow import hashed
        a=self.get(app_id)
        if a['context']['channel']!='telegram':raise ValueError('Выберите диалог Giga.')
        case_id=self.case_id(app_id)
        with self.connect() as db:
            turns=[dict(r) for r in db.execute('SELECT id,source_id,fingerprint,question,status FROM turns WHERE app_id=? ORDER BY created,id',(app_id,))]
            crm=db.execute('SELECT * FROM application_crm WHERE app_id=?',(case_id,)).fetchone()
        if not turns:raise ValueError('Сначала прочитайте текущий диалог Giga: /question.')
        if any(t['status'] in ('sending','uncertain') for t in turns):raise ValueError('Сначала сверьте результат отправки ответа Giga.')
        if a['status'] not in ('active','paused','completed'):raise ValueError('Сначала выберите этот диалог Giga.')
        return {'app_id':app_id,'case_id':case_id,'title':a['context']['vacancy']['title'],'resume_title':a['context']['resume_title'],'last_message':turns[-1]['question'],'token':hashed([app_id,a['status'],a['context'],turns,dict(crm) if crm else None])[:24]}

    def complete_screening(self,app_id,token,confirmed=False):
        from .application_workflow import packed,utc
        from .crm_planning import crm_value,STAGE_DEFAULTS
        if confirmed is not True:raise ValueError('Подтвердите фактическое завершение AI-интервью.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            preview=self.screening_preview(app_id)
            if preview['token']!=token:raise ValueError('Диалог или план изменился. Проверьте завершение ещё раз.')
            root=preview['case_id'];old=crm_value(db.execute('SELECT * FROM application_crm WHERE app_id=?',(root,)).fetchone())
            if old['stage'] in ('rejected','offer'):raise ValueError('Отбор уже завершён. Проверьте этап CRM.')
            if self.get(app_id)['status']=='completed':return {'ok':True,'case_id':root}
            db.execute("UPDATE applications SET status='completed' WHERE id=?",(app_id,))
            # A later manually recorded stage must never be moved backwards.
            if old['stage'] in ('preparing','applied'):
                state,action=STAGE_DEFAULTS['ai_screened']
                db.execute('INSERT INTO application_crm(app_id,stage,work_status,next_action,follow_up_at,revision,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET stage=excluded.stage,work_status=excluded.work_status,next_action=excluded.next_action,follow_up_at=NULL,revision=excluded.revision,updated_at=excluded.updated_at',(root,'ai_screened',state,action,None,old['revision']+1,utc()))
                self._invalidate(db,root)
                self._event(db,root,'crm_stage',{'before':old['stage'],'stage':'ai_screened','work_status':state,'next_action':action,'actor':'user_confirmed_giga'})
            self._event(db,root,'ai_screening_completed',{'channel_application_id':app_id,'actor':'user','last_message':preview['last_message'],'confirmation_token':token})
            self.setting_in(db,'awaiting_answer','');self.setting_in(db,'awaiting_answer_preferences','')
        return {'ok':True,'case_id':root}
