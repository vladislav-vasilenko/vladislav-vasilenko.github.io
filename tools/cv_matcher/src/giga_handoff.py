"""Bound HH -> Giga invitations and once-only, reviewed deep-link starts."""
import json,re,secrets,time
from urllib.parse import urlsplit,parse_qs,urlencode

def invitation_url(value):
    try:
        u=urlsplit(value)
        if u.scheme!='https' or u.netloc.lower() not in ('t.me','telegram.me') or u.path.lower().rstrip('/')!='/giga_recruiter_bot' or u.fragment:raise ValueError()
        q=parse_qs(u.query,keep_blank_values=True)
        if set(q)!= {'start'} or len(q['start'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',q['start'][0]):raise ValueError()
        return {'url':'https://t.me/Giga_recruiter_bot?'+urlencode({'start':q['start'][0]}),'start_param':q['start'][0]}
    except (ValueError,TypeError,AttributeError):raise ValueError('Нужна HTTPS-ссылка @Giga_recruiter_bot с единственным start-параметром.') from None

class GigaBindingConflict(ValueError):
    pass

class GigaMixin:
    def init_giga(self,db):
        db.executescript('''CREATE TABLE IF NOT EXISTS giga_invites(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,url TEXT NOT NULL,start_param TEXT NOT NULL,source_url TEXT,source_thread TEXT,source_message TEXT,created REAL,UNIQUE(case_id,start_param));
        CREATE TABLE IF NOT EXISTS integration_conflicts(id TEXT PRIMARY KEY,app_id TEXT,kind TEXT,source_url TEXT,detail TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS giga_starts(invite_id TEXT PRIMARY KEY,app_id TEXT NOT NULL,nonce INTEGER NOT NULL,state TEXT NOT NULL,baseline TEXT,started REAL NOT NULL,receipt TEXT);''')

    def save_giga_invite(self,app_id,url,source_url='',thread_id='',message_id='',*,db=None):
        from contextlib import nullcontext
        from .application_workflow import hashed
        self.get(app_id)
        value=invitation_url(url);case_id=self.case_id(app_id)
        with (self.connect() if db is None else nullcontext(db)) as c:
            # A token seen under another vacancy is ambiguous; never silently rebind it.
            other=c.execute('SELECT case_id FROM giga_invites WHERE start_param=? AND case_id<>?',(value['start_param'],case_id)).fetchone()
            if other:raise GigaBindingConflict('Это приглашение Giga уже связано с другой вакансией.')
            key=hashed([case_id,value['start_param']])[:20]
            if c.execute('INSERT OR IGNORE INTO giga_invites VALUES(?,?,?,?,?,?,?,?)',(key,case_id,value['url'],value['start_param'],source_url,thread_id,str(message_id),time.time())).rowcount:
                self._event(c,case_id,'giga_invite',{'invite_id':key,'source_url':source_url,'thread_id':thread_id})
        return self.giga_invitation(app_id) if db is None else key

    def giga_invitation(self,app_id):
        case_id=self.case_id(app_id)
        with self.connect() as db:row=db.execute('SELECT i.*,s.state start_state,s.app_id channel_application_id FROM giga_invites i LEFT JOIN giga_starts s ON s.invite_id=i.id WHERE i.case_id=? ORDER BY i.created DESC LIMIT 1',(case_id,)).fetchone()
        return dict(row) if row else None

    def giga_start_preview(self,app_id):
        from .application_workflow import hashed
        app=self.get(app_id);invite=self.giga_invitation(app_id)
        if app['context']['channel']!='telegram' or not invite:raise ValueError('Сначала сохраните приглашение Giga из чата этой вакансии на HH.')
        return {'app_id':app_id,'invite':invite,'title':app['context']['vacancy']['title'],'resume_title':app['context']['resume_title'],'token':hashed([app_id,app['context'],invite['id']])[:24]}

    def claim_giga_start(self,app_id,token,baseline):
        from .application_workflow import packed
        preview=self.giga_start_preview(app_id)
        if preview['token']!=token:raise ValueError('Приглашение или CV изменились. Просмотрите запуск ещё раз.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            active=db.execute("SELECT id FROM applications WHERE status='active'").fetchone()
            if not active or active[0]!=app_id:raise ValueError('Сначала выберите этот Giga-диалог.')
            if not db.execute("INSERT OR IGNORE INTO giga_starts VALUES(?,?,?,'sending',?,?,NULL)",(preview['invite']['id'],app_id,secrets.randbits(63),packed(baseline),time.time())).rowcount:raise ValueError('Приглашение уже запускалось. Повтор запрещён; используйте /question и проверьте результат.')
            self.setting_in(db,'giga_current_invite',preview['invite']['id'])
            self._event(db,self.case_id(app_id),'giga_start_claimed',{'invite_id':preview['invite']['id'],'channel_application_id':app_id})
            row=dict(db.execute('SELECT * FROM giga_starts WHERE invite_id=?',(preview['invite']['id'],)).fetchone())
        return {**row,'start_param':preview['invite']['start_param']}

    def finish_giga_start(self,invite_id,success):
        with self.connect() as db:db.execute('UPDATE giga_starts SET state=? WHERE invite_id=? AND state=\'sending\'',('sent' if success else 'uncertain',invite_id))

    def giga_question_current(self,app_id,source_id,fingerprint):
        invite=self.giga_invitation(app_id)
        current=self.setting('giga_current_invite')
        if not invite:return not current or current=='legacy:'+app_id
        if current!=invite['id']:return False
        with self.connect() as db:run=db.execute('SELECT * FROM giga_starts WHERE invite_id=? AND app_id=?',(invite['id'],app_id)).fetchone()
        if not run or run['state'] not in ('sending','sent','uncertain'):return False
        baseline=json.loads(run['baseline'] or 'null')
        if not isinstance(source_id,int):return False
        return not baseline or source_id>baseline['id'] or source_id==baseline['id'] and fingerprint!=baseline['fingerprint']
