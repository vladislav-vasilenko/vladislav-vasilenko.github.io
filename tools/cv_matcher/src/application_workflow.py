"""Durable HH observations, draft discussion and single-use, exact-content approval."""
import json,hashlib,secrets,time,re
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit
from .resume_source import normalize

def packed(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def hashed(value):return hashlib.sha256(packed(value).encode()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def hh_url(value):
    try:
        u=urlsplit(value)
        return u.scheme=='https' and u.netloc in ('hh.ru','chat.hh.ru') and not u.username
    except (ValueError,TypeError):return False
HH_STATES={'submitted','viewed','invited','rejected','withdrawn','unknown'}
from .application_form_answers import FormAnswersMixin
from .career_application_fields import CareerFieldsMixin
from .giga_handoff import GigaMixin
from .delivery_store import DeliveryMixin
from .application_channels import ChannelMixin
from .crm_planning import PlanningMixin,CRM_STAGES,WORK_STATUSES,STAGE_DEFAULTS,crm_value

class WorkflowMixin(PlanningMixin,DeliveryMixin,ChannelMixin,GigaMixin,FormAnswersMixin,CareerFieldsMixin):
    def init_workflow(self,db):
        db.executescript('''
        CREATE TABLE IF NOT EXISTS application_workflow(app_id TEXT PRIMARY KEY,revision INTEGER DEFAULT 0,draft TEXT DEFAULT '',state TEXT DEFAULT 'draft',form TEXT,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS application_discussion(id INTEGER PRIMARY KEY AUTOINCREMENT,app_id TEXT,role TEXT,text TEXT,at TEXT,request_id TEXT);
        CREATE TABLE IF NOT EXISTS application_drafts(id INTEGER PRIMARY KEY AUTOINCREMENT,app_id TEXT,revision INTEGER,text TEXT,text_hash TEXT,actor TEXT,at TEXT,UNIQUE(app_id,revision));
        CREATE TABLE IF NOT EXISTS application_chat_requests(app_id TEXT,request_id TEXT,input_hash TEXT,state TEXT,result TEXT,PRIMARY KEY(app_id,request_id));
        CREATE TABLE IF NOT EXISTS application_approvals(id TEXT PRIMARY KEY,app_id TEXT,intent_hash TEXT,payload TEXT,status TEXT,expires REAL,created_at TEXT);
        CREATE TABLE IF NOT EXISTS browser_commands(id TEXT PRIMARY KEY,app_id TEXT,kind TEXT,payload TEXT,state TEXT,worker_id TEXT,created REAL,updated REAL,result TEXT);
        CREATE TABLE IF NOT EXISTS application_events(id INTEGER PRIMARY KEY AUTOINCREMENT,app_id TEXT,type TEXT,payload TEXT,at TEXT);
        CREATE TABLE IF NOT EXISTS hh_observations(key TEXT PRIMARY KEY,vacancy_id TEXT,negotiation_id TEXT,status TEXT,observed_at TEXT,source_url TEXT,payload TEXT);
        CREATE INDEX IF NOT EXISTS hh_observations_vacancy ON hh_observations(vacancy_id,observed_at DESC);
        CREATE TABLE IF NOT EXISTS hh_threads(id TEXT PRIMARY KEY,vacancy_id TEXT,source_url TEXT,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS hh_messages(key TEXT PRIMARY KEY,thread_id TEXT,external_id TEXT,text TEXT,direction TEXT,message_at TEXT,observed_at TEXT,payload TEXT);
        CREATE INDEX IF NOT EXISTS hh_messages_thread ON hh_messages(thread_id,observed_at);
        CREATE TABLE IF NOT EXISTS workflow_delivery(key TEXT PRIMARY KEY,state TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS application_crm(app_id TEXT PRIMARY KEY,stage TEXT,updated_at TEXT);
        ''')
        self.init_planning(db)
        self.init_delivery(db)
        self.init_channels(db)
        self.init_giga(db)
        from .discovery import init as init_discovery
        init_discovery(db)
        from .agent_tasks import init as init_agent
        init_agent(db)
        from .agent_progress import init as init_progress
        init_progress(db)
        from .application_preparation import init as init_preparations
        init_preparations(db)
        from .luna_batch import init as init_batches
        init_batches(db)
        self.init_form_answers(db)
        from .candidate_profile import init as init_profile
        init_profile(db)
    def _wf(self,db,app_id):
        if not db.execute('SELECT 1 FROM applications WHERE id=?',(app_id,)).fetchone():raise ValueError('Отклик не найден.')
        db.execute('INSERT OR IGNORE INTO application_workflow(app_id,updated_at) VALUES(?,?)',(app_id,utc()))
        return dict(db.execute('SELECT * FROM application_workflow WHERE app_id=?',(app_id,)).fetchone())
    def _event(self,db,app_id,kind,data):db.execute('INSERT INTO application_events(app_id,type,payload,at) VALUES(?,?,?,?)',(app_id,kind,packed(data),utc()))
    def _invalidate(self,db,app_id):
        db.execute("UPDATE application_approvals SET status='revoked' WHERE app_id=? AND status='approved'",(app_id,))
        db.execute("UPDATE browser_commands SET state='cancelled',updated=? WHERE app_id=? AND kind IN ('execute','career_fill') AND state='queued'",(time.time(),app_id))
    def _blocked_edit(self,wf):
        if wf['state'] in ('sending','filling','uncertain','submitted','superseded'):raise ValueError('Сначала проверьте результат предыдущего действия в браузере; повтор автоматически не выполняется.')
    def workflow(self,app_id):
        app=self.get(app_id);case_id=self.case_id(app_id)
        with self.connect() as db:
            wf=self._wf(db,app_id)
            running=db.execute("SELECT * FROM browser_commands WHERE app_id=? AND state='running' AND kind='execute' AND updated<?",(app_id,time.time()-300)).fetchone()
            if running:
                db.execute("UPDATE browser_commands SET state='uncertain',updated=? WHERE id=?",(time.time(),running['id']))
                db.execute("UPDATE application_workflow SET state='uncertain',updated_at=? WHERE app_id=?",(utc(),app_id));wf['state']='uncertain'
            discussions=[dict(r) for r in db.execute('SELECT * FROM application_discussion WHERE app_id=? ORDER BY id',(app_id,))]
            versions=[dict(r) for r in db.execute('SELECT * FROM application_drafts WHERE app_id=? ORDER BY revision DESC',(app_id,))]
            observations=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM hh_observations WHERE vacancy_id=? ORDER BY observed_at DESC LIMIT 100',(app['context']['vacancy']['id'],))]
            threads=[dict(r) for r in db.execute('SELECT * FROM hh_threads WHERE vacancy_id=?',(app['context']['vacancy']['id'],))]
            messages=[]
            for thread in threads:messages.extend(dict(r) for r in db.execute('SELECT * FROM hh_messages WHERE thread_id=? ORDER BY COALESCE(message_at,observed_at),rowid LIMIT 500',(thread['id'],)))
            approvals=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM application_approvals WHERE app_id=? ORDER BY created_at DESC LIMIT 10',(app_id,))]
            events=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM application_events WHERE app_id IN (SELECT app_id FROM application_channels WHERE case_id=?) ORDER BY id DESC LIMIT 100',(case_id,))]
            commands=[dict(r) for r in db.execute('SELECT id,kind,state,updated,result FROM browser_commands WHERE app_id=? ORDER BY created DESC LIMIT 10',(app_id,))]
            crm=db.execute('SELECT * FROM application_crm WHERE app_id=?',(case_id,)).fetchone()
        from .candidate_facts import read as read_facts
        return {**app,'user_facts':read_facts(self,app['context']['resume_id']),'case_id':case_id,'giga_invitation':self.giga_invitation(app_id),'form_answers':self.form_answers(app_id),'field_history':self.field_history(app_id),'field_suggestions':self.field_suggestions(app_id),'channels':self.linked_channels(app_id),'crm':crm_value(crm),'appointments':self.appointments(app_id),'crm_stages':CRM_STAGES,'work_statuses':WORK_STATUSES,'stage_defaults':STAGE_DEFAULTS,'workflow':{**wf,'form':json.loads(wf['form']) if wf['form'] else None},'discussion':discussions,'draft_versions':versions,'hh_observations':observations,'hh_threads':threads,'hh_messages':messages,'approvals':approvals,'events':events,'commands':commands}

    def renew_context(self,app_id,cv,job,goal):
        old=self.workflow(app_id);self._blocked_edit(old['workflow'])
        if old['status']!='queued' or old['crm']['stage']!='preparing':raise ValueError('Обновление контекста доступно до отправки и начала собеседований.')
        ctx=old['context']
        if job['id']!=ctx['vacancy']['id']:raise ValueError('Нельзя заменить вакансию.')
        payload={'resume_id':cv['id'],'bundle':{'resumes':[cv]},'vacancy':job,'goal':goal,'channel':ctx['channel']}
        # Validate everything before retiring the previous context. Its letters and chat stay intact.
        from .resume_source import _load_resume_bundle
        _load_resume_bundle({'primary_id':cv['id'],'resumes':[cv]},now=datetime.now(timezone.utc))
        if job.get('archived') or job.get('description_quality')!='full':raise ValueError('Нужна полная открытая вакансия.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._blocked_edit(self._wf(db,app_id))
            if db.execute("SELECT 1 FROM hh_observations WHERE vacancy_id=? AND status<>'unknown'",(job['id'],)).fetchone():raise ValueError('На HH уже есть отклик.')
            self._invalidate(db,app_id);db.execute("UPDATE browser_commands SET state='cancelled' WHERE app_id=? AND state IN ('queued','running')",(app_id,))
            db.execute("UPDATE applications SET dedupe=dedupe||':history:'||id,status='superseded' WHERE id=?",(app_id,));db.execute("UPDATE application_workflow SET state='superseded' WHERE app_id=?",(app_id,));self._event(db,app_id,'context_retired',{})
        try:new=self.create(payload)
        except Exception:
            with self.connect() as db:db.execute("UPDATE applications SET dedupe=?,status='queued' WHERE id=?",(ctx['channel']+':'+job['id'],app_id));db.execute("UPDATE application_workflow SET state='draft' WHERE app_id=?",(app_id,))
            raise
        with self.connect() as db:self._event(db,new['id'],'context_renewed',{'previous_application_id':app_id})
        return self.workflow(new['id'])
    def save_letter(self,app_id,text,revision,actor='user'):
        if not isinstance(text,str) or len(text)>16000:raise ValueError('Сопроводительный текст должен быть не длиннее 16000 символов.')
        text=text.strip()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');wf=self._wf(db,app_id);self._blocked_edit(wf)
            if wf['revision']!=revision:raise ValueError('Письмо уже изменилось. Обновите карточку.')
            if wf['draft']!=text:
                revision+=1;self._invalidate(db,app_id)
                context=json.loads(db.execute('SELECT context FROM applications WHERE id=?',(app_id,)).fetchone()[0])
                keep_form=packed({**json.loads(wf['form']),'draft_revision':revision}) if context['channel']=='career' and wf['form'] else None
                db.execute('UPDATE application_workflow SET revision=?,draft=?,state=?,form=?,updated_at=? WHERE app_id=?',(revision,text,'needs_input' if keep_form else 'draft',keep_form,utc(),app_id))
                db.execute('INSERT INTO application_drafts(app_id,revision,text,text_hash,actor,at) VALUES(?,?,?,?,?,?)',(app_id,revision,text,hashed(text),actor,utc()))
                self._event(db,app_id,'draft_saved',{'revision':revision,'actor':actor})
            if actor=='user':self.setting_in(db,'needs_clarification:'+app_id,'no')
        return self.workflow(app_id)
    def hh_sync(self,data):
        source=data.get('source_url','');observed=data.get('observed_at',utc());records=data.get('records',[])
        if not hh_url(source) or not isinstance(records,list) or len(records)>200:raise ValueError('Нужен снимок страницы HH с максимум 200 записями.')
        try:
            stamp=datetime.fromisoformat(observed.replace('Z','+00:00'))
            if not stamp.tzinfo or stamp>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError()
            observed=stamp.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError,AttributeError):raise ValueError('Некорректное время наблюдения HH.') from None
        added=messages_added=0;warnings=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for record in records:
                vid=record.get('vacancy_id');thread=record.get('thread_id');state=record.get('status','unknown')
                if vid is not None and not re.fullmatch(r'hh_\d{1,20}',str(vid)):raise ValueError('Некорректная вакансия HH.')
                if state not in HH_STATES:raise ValueError('Неизвестный статус HH.')
                if record.get('source_url') and not hh_url(record['source_url']):raise ValueError('Некорректный источник HH.')
                url=record.get('source_url') or source
                if thread:
                    if not isinstance(thread,str) or len(thread)>250:raise ValueError('Некорректный идентификатор чата.')
                    old=db.execute('SELECT vacancy_id FROM hh_threads WHERE id=?',(thread,)).fetchone()
                    if old and old[0] and vid and old[0]!=vid:raise ValueError('Чат уже связан с другой вакансией.')
                    vid=vid or (old[0] if old else None)
                    db.execute('INSERT INTO hh_threads VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET vacancy_id=COALESCE(hh_threads.vacancy_id,excluded.vacancy_id),source_url=excluded.source_url,updated_at=MAX(hh_threads.updated_at,excluded.updated_at)',(thread,vid,url,observed))
                texts=record.get('messages',[])
                if not isinstance(texts,list) or len(texts)>500:raise ValueError('В снимке слишком много сообщений.')
                baseline=bool(thread and db.execute('SELECT 1 FROM hh_messages WHERE thread_id=? LIMIT 1',(thread,)).fetchone())
                new_messages=[]
                for message in texts:
                    if not thread:raise ValueError('Сообщения требуют идентификатора чата.')
                    text=message.get('text','');external=str(message.get('id',''));direction=message.get('direction','unknown');at=str(message.get('at') or '')
                    if not isinstance(text,str) or not text.strip() or len(text)>20000 or len(external)>200 or direction not in ('incoming','outgoing','unknown'):raise ValueError('Некорректное сообщение HH.')
                    # HH's message ID is identity; relative time labels and direction can change.
                    if external and db.execute('SELECT 1 FROM hh_messages WHERE thread_id=? AND external_id=? LIMIT 1',(thread,external)).fetchone():continue
                    key=hashed([thread,external] if external else [thread,at,text])
                    fresh_message=db.execute('INSERT OR IGNORE INTO hh_messages VALUES(?,?,?,?,?,?,?,?)',(key,thread,external,text,direction,at,observed,packed(message))).rowcount
                    messages_added+=fresh_message
                    if baseline and fresh_message and direction!='outgoing':new_messages.append((key,text,direction))
                if not vid:continue
                clean={k:record.get(k) for k in ('vacancy_id','thread_id','status','status_text','resume_id','title','negotiation_id')}
                previous_status=db.execute("SELECT status,observed_at FROM hh_observations WHERE vacancy_id=? AND status<>'unknown' ORDER BY observed_at DESC,rowid DESC LIMIT 1",(vid,)).fetchone()
                key=hashed([vid,clean,url,observed])
                fresh=db.execute('INSERT OR IGNORE INTO hh_observations VALUES(?,?,?,?,?,?,?)',(key,vid,record.get('negotiation_id'),state,observed,url,packed(clean))).rowcount;added+=fresh
                app=db.execute("SELECT id,status,context FROM applications WHERE dedupe=?",('hh:'+vid,)).fetchone()
                if app and record.get('resume_id') and record['resume_id']!=json.loads(app['context'])['resume_id']:app=None
                if app:
                    for message_key,text,direction in new_messages:self._event(db,app['id'],'hh_message',{'message_key':message_key,'text':text[:700],'direction':direction,'thread_id':thread,'source_url':url})
                if app and thread:
                    from .giga_handoff import invitation_url
                    for message in texts:
                        candidates=list(message.get('links',[])) if isinstance(message.get('links',[]),list) else []
                        candidates+=re.findall(r'https://(?:t\.me|telegram\.me)/Giga_recruiter_bot\?[^\s<>]+',message['text'],re.I)
                        for candidate in candidates:
                            try:invite=invitation_url(candidate)
                            except ValueError:continue
                            from .giga_handoff import GigaBindingConflict
                            try:self.save_giga_invite(app['id'],invite['url'],url,thread,message.get('id',''),db=db)
                            except GigaBindingConflict:
                                conflict=hashed([app['id'],invite['url'],thread])
                                detail='Приглашение Giga связано с другой вакансией. Автоматическая перепривязка запрещена; остальные наблюдения сохранены.'
                                if db.execute('INSERT OR IGNORE INTO integration_conflicts VALUES(?,?,?,?,?,?)',(conflict,app['id'],'giga_binding',url,detail,time.time())).rowcount:self._event(db,app['id'],'integration_conflict',{'conflict_id':conflict,'note':detail})
                                warnings.append(detail)
                if app and state!='unknown':
                    latest=db.execute("SELECT status FROM hh_observations WHERE vacancy_id=? AND status<>'unknown' ORDER BY observed_at DESC LIMIT 1",(vid,)).fetchone()[0]
                    if state==latest and state!=app['status'] and not (state=='submitted' and app['status'] in ('viewed','invited','rejected','withdrawn')):
                        db.execute('UPDATE applications SET status=? WHERE id=?',(state,app['id']))
                        self._wf(db,app['id']);self._invalidate(db,app['id'])
                        # A concurrent read must not alter a claimed browser action.
                        db.execute("UPDATE application_workflow SET state='submitted',updated_at=? WHERE app_id=? AND state NOT IN ('sending','filling')",(utc(),app['id']))
                        if state in ('submitted','viewed','invited'):self.mark_applied(db,app['id'])
                    if fresh and (not previous_status or observed>=previous_status['observed_at'] and previous_status['status']!=state) and not (state=='submitted' and app['status'] in ('viewed','invited','rejected','withdrawn')):self._event(db,app['id'],'hh_status',{'status':state,'source_url':url,'thread_id':thread})
            self.setting_in(db,'hh_last_sync',observed)
        return {'observations_added':added,'messages_added':messages_added,'warnings':list(dict.fromkeys(warnings)),'partial':True,'note':'Сохранены наблюдения загруженных страниц. Отсутствие отклика не меняет его статус.'}
    @staticmethod
    def setting_in(db,key,value):db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,str(value)))
    def hh_inbox(self):
        with self.connect() as db:
            records=[{**dict(r),'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM hh_observations o WHERE rowid=(SELECT rowid FROM hh_observations x WHERE x.vacancy_id=o.vacancy_id ORDER BY (status="unknown"),observed_at DESC,rowid DESC LIMIT 1) ORDER BY observed_at DESC LIMIT 200')]
            unbound=[dict(r) for r in db.execute('SELECT * FROM hh_threads WHERE vacancy_id IS NULL')]
        return {'items':records,'unbound_threads':unbound,'last_sync':self.setting('hh_last_sync')}
    def bind_thread(self,thread,app_id,confirmed):
        if confirmed is not True:raise ValueError('Подтвердите, что это чат выбранной вакансии.')
        app=self.get(app_id)
        with self.connect() as db:
            row=db.execute('SELECT * FROM hh_threads WHERE id=?',(thread,)).fetchone()
            if not row or row['vacancy_id']:raise ValueError('Чат уже связан или не найден.')
            db.execute('UPDATE hh_threads SET vacancy_id=? WHERE id=?',(app['context']['vacancy']['id'],thread));self._event(db,app_id,'thread_bound',{'thread_id':thread,'source_url':row['source_url']})
        return self.workflow(app_id)
    def queue_command(self,kind,app_id=None,payload=None):
        if kind not in ('prepare','execute','refresh','sync','discover','collect','resume_import','career_open'):raise ValueError('Неизвестная задача Chrome.')
        if kind=='career_open':
            from .board_import import identity
            from .career_questionnaires import HOSTS
            target=urlsplit(str((payload or {}).get('url','')));job=identity((payload or {}).get('url',''))
            if not app_id or not job or job['id']!=self.get(app_id)['context']['vacancy']['id'] or target.scheme!='https' or target.netloc not in set().union(*HOSTS.values()):raise ValueError('Нужна ссылка на выбранную вакансию компании.')
        if kind=='resume_import' and not re.fullmatch(r'(?:[a-f0-9]{38}|gdoc_[A-Za-z0-9_-]{10,200})',str((payload or {}).get('resume_id',''))):raise ValueError('Нужен идентификатор HH-резюме или Google Docs.')
        if app_id:
            app=self.get(app_id)
            if kind in ('prepare','execute') and app['context']['channel']!='hh':raise ValueError('Автоматическая отправка доступна для HH. На сайте компании перенесите письмо в форму вручную.')
        if kind=='sync' and (payload or {}).get('source_url'):
            target=urlsplit(payload['source_url'])
            if target.scheme!='https' or target.netloc!='hh.ru' or not re.fullmatch(r'/chat/\d{1,25}/?',target.path) or target.query or target.fragment:raise ValueError('Нужна ссылка на открытый чат https://hh.ru/chat/…')
        if kind in ('discover','collect'):
            from .discovery import source_url
            source_url((payload or {}).get('source_url',''),detail=kind=='collect')
        if kind=='collect' and 'collection_transport' not in (payload or {}):
            from .hybrid_collection import prepare
            from .discovery import config
            payload=prepare(payload,config(self).get('transport','chrome_only'))
        identifier=secrets.token_hex(12)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute("SELECT id FROM browser_commands WHERE app_id IS ? AND kind=? AND payload=? AND state IN ('queued','running')",(app_id,kind,packed(payload or {}))).fetchone()
            if prior:return prior[0]
            db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,?,?,?,?)',(identifier,app_id,kind,packed(payload or {}),'queued',None,time.time(),time.time(),None))
            if app_id:self._event(db,app_id,'browser_queued',{'kind':kind,'command_id':identifier})
        return identifier
    def next_command(self,worker,kinds=None,app_ids=None,*,auto_sync=False,resume_bump_version=None,resume_import_version=None,collection_version=None):
        if not isinstance(worker,str) or not 5<=len(worker)<=100:raise ValueError('Некорректный браузерный исполнитель.')
        kinds=['prepare','execute','refresh','sync'] if kinds is None else kinds
        if not isinstance(kinds,list) or not kinds or any(k not in ('prepare','execute','refresh','sync','discover','collect','career_fill','career_open','resume_import','resume_bump') for k in kinds):raise ValueError('Неподдерживаемые возможности исполнителя.')
        if 'career_fill' in kinds and (kinds!=['career_fill'] or not isinstance(app_ids,list) or not 1<=len(app_ids)<=100 or any(not isinstance(a,str) for a in app_ids)):raise ValueError('Перенос компании требует привязанных вкладок.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if kinds==['discover','collect']:self.setting_in(db,'collection_worker_protocol',str(collection_version if type(collection_version) is int else 0))
            worker_name='career' if kinds in (['career_fill'],['career_open']) else 'collection' if kinds==['discover','collect'] else 'resume' if kinds==['resume_import'] else 'hh'
            self.setting_in(db,worker_name+'_worker_last_seen',str(time.time()))
            if worker_name=='hh':
                self.setting_in(db,'hh_auto_sync_worker',packed({'enabled':auto_sync is True,'at':time.time(),'worker_id':worker}))
                if 'resume_bump' in kinds and type(resume_bump_version) is int and resume_bump_version==1:self.setting_in(db,'hh_resume_bump_worker',packed({'at':time.time(),'worker_id':worker,'version':1}))
            db.execute("UPDATE browser_commands SET state='queued',worker_id=NULL WHERE state='running' AND kind NOT IN ('execute','career_fill','discover','collect','resume_bump') AND NOT (kind='sync' AND json_extract(payload,'$.automatic')=1) AND updated<?",(time.time()-300,))
            # Never repeat a claimed disclosure after an MV3 suspension/crash.
            stale=db.execute("SELECT app_id FROM browser_commands WHERE state='running' AND kind='career_fill' AND updated<?",(time.time()-300,)).fetchall()
            for old in stale:db.execute("UPDATE application_workflow SET state='needs_input',form=NULL WHERE app_id=? AND state IN ('filling','fill_approved')",(old['app_id'],))
            db.execute("UPDATE browser_commands SET state='uncertain' WHERE state='running' AND kind='career_fill' AND updated<?",(time.time()-300,))
            query="SELECT * FROM browser_commands WHERE state='queued' AND kind IN ("+','.join('?' for _ in kinds)+')';params=list(kinds)
            if type(collection_version) is not int or collection_version<2:query+=" AND json_extract(payload,'$.backfill_run') IS NULL"
            query+=" AND NOT EXISTS (SELECT 1 FROM collection_backfill_runs b WHERE b.id=json_extract(browser_commands.payload,'$.backfill_run') AND b.state<>'running')"
            query+=" AND NOT (kind IN ('collect','discover') AND COALESCE(json_extract(payload,'$.collection_transport'),'chrome')='python')"
            if type(resume_import_version) is not int or resume_import_version<2:query+=" AND NOT (kind='resume_import' AND json_extract(payload,'$.resume_id') LIKE 'gdoc_%')"
            if type(resume_bump_version) is not int or resume_bump_version!=1:query+=" AND kind<>'resume_bump'"
            query+=" AND NOT EXISTS (SELECT 1 FROM agent_task_controls c WHERE c.command_id=browser_commands.id AND c.requested<>'') AND NOT (kind='discover' AND EXISTS (SELECT 1 FROM discovery_runs d WHERE d.id=json_extract(browser_commands.payload,'$.run_id') AND d.state NOT IN ('collecting','waiting_chrome')))"
            # Old extensions cannot consume a background-sync job in their form tab.
            from .hh_auto_sync import _config
            if auto_sync is not True or not _config(db)['enabled']:query+=" AND NOT (kind='sync' AND COALESCE(json_extract(payload,'$.automatic'),0)=1)"
            else:
                query+=" AND NOT (kind='sync' AND COALESCE(json_extract(payload,'$.automatic'),0)=1 AND EXISTS (SELECT 1 FROM browser_commands busy WHERE busy.state='running' AND busy.kind IN ('prepare','execute','refresh','sync','discover','collect') AND busy.updated>?))";params.append(time.time()-300)
            query+=" AND NOT (kind='sync' AND json_extract(payload,'$.automatic')=1 AND EXISTS (SELECT 1 FROM browser_commands reads WHERE reads.state='queued' AND reads.kind IN ('discover','collect') AND coalesce(json_extract(reads.payload,'$.collection_transport'),'chrome')='chrome'))"
            if kinds==['career_fill']:query+=' AND app_id IN ('+','.join('?' for _ in app_ids)+')';params.extend(app_ids)
            row=db.execute(query+" ORDER BY CASE WHEN kind='execute' THEN 0 WHEN kind='prepare' THEN 1 WHEN kind='sync' AND json_extract(payload,'$.automatic')=1 THEN 3 ELSE 2 END,created LIMIT 1",params).fetchone()
            if not row:return {'command':None}
            db.execute("UPDATE browser_commands SET state='running',worker_id=?,updated=? WHERE id=? AND state='queued'",(worker,time.time(),row['id']))
            if row['kind']=='discover':db.execute("UPDATE discovery_runs SET state='collecting',updated=? WHERE id=json_extract(?,'$.run_id') AND state='waiting_chrome'",(time.time(),row['payload']))
        command={**dict(row),'payload':json.loads(row['payload']),'worker_id':worker}
        if row['app_id']:command['application']=self.workflow(row['app_id'])
        return {'command':command}

    def browser_status(self):
        workers={}
        with self.connect() as db:
            for name,kinds in [('hh',('prepare','execute','refresh','sync','resume_bump')),('career',('career_fill','career_open')),('collection',('discover','collect')),('python_collection',('discover','collect')),('resume',('resume_import',))]:
                try:seen=float(self.setting(name+'_worker_last_seen') or 0)
                except ValueError:seen=0
                marks=','.join('?' for _ in kinds)
                transport_filter=" AND coalesce(json_extract(payload,'$.collection_transport'),'chrome')"+("='python'" if name=='python_collection' else "<>'python'") if name in ('collection','python_collection') else ''
                queued=db.execute("SELECT COUNT(*) FROM browser_commands WHERE state='queued' AND kind IN ("+marks+")"+transport_filter,kinds).fetchone()[0]
                running=db.execute("SELECT COUNT(*) FROM browser_commands WHERE state='running' AND updated>? AND kind IN ("+marks+")"+transport_filter,(time.time()-600,*kinds)).fetchone()[0]
                workers[name]={'connected':bool(seen and 0<=time.time()-seen<180),'last_seen':seen or None,'queued':queued,'running':running}
        from .runtime_health import read_health
        workers['giga']=read_health(self,'giga')
        from .hh_auto_sync import status
        from .resume_bump import status as bump_status
        return {**workers['hh'],'workers':workers,'auto_sync':status(self),'resume_bump':bump_status(self)}
    def prepared(self,app_id,snapshot,*,command_id=None):
        app=self.get(app_id)
        if app['context']['channel']!='hh' or not isinstance(snapshot,dict):raise ValueError('Нужна форма HH.')
        fields=snapshot.get('fields',[])
        if snapshot.get('state')!='form' or snapshot.get('selected_resume_id')!=app['context']['resume_id'] or not isinstance(fields,list) or len(fields)>80:raise ValueError('В форме не подтверждено выбранное CV.')
        if not isinstance(snapshot.get('fingerprint'),str) or len(snapshot['fingerprint'])>200000:raise ValueError('Нет версии формы.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');wf=self._wf(db,app_id)
            if wf['state']=='sending':
                cmd=db.execute("SELECT * FROM browser_commands WHERE id=? AND app_id=? AND kind='execute' AND state='running'",(command_id,app_id)).fetchone()
                if not cmd:raise ValueError('Следующий шаг принимается только от выполняемой команды.')
                approval=db.execute("SELECT status FROM application_approvals WHERE id=?",(json.loads(cmd['payload'])['approval_id'],)).fetchone()
                if not approval or approval[0]!='claimed':raise ValueError('Нет выполненного разрешения для следующего шага.')
            else:self._blocked_edit(wf)
            self._invalidate(db,app_id)
            db.execute('INSERT OR IGNORE INTO application_form_versions VALUES(?,?,?,?)',(app_id,snapshot['fingerprint'],packed(snapshot),time.time()))
            form={**snapshot,'draft_revision':wf['revision']};db.execute("UPDATE application_workflow SET form=?,state='needs_approval',updated_at=? WHERE app_id=?",(packed(form),utc(),app_id));self._event(db,app_id,'form_prepared',{'revision':wf['revision']})
        return self.workflow(app_id)
    def intent(self,app_id,answers=None):
        item=self.workflow(app_id);wf=item['workflow'];form=wf['form'];ctx=item['context']
        if ctx['channel']!='hh':raise ValueError('Разрешение отправки через HH доступно только для вакансии HH.')
        self._blocked_edit(wf)
        if self.setting('needs_clarification:'+app_id)=='yes':raise ValueError('Редактору нужны уточнения. Ответьте ему или сохраните проверенный текст вручную.')
        if item['status'] in ('submitted','viewed','invited','rejected','withdrawn','completed'):raise ValueError('По этой вакансии уже есть отклик HH.')
        if item['crm']['stage']!='preparing':raise ValueError('Отклик уже переведён в этап подбора. Возврат к подготовке требует ручного изменения CRM.')
        if not form or wf['revision']!=form.get('draft_revision') or not wf['draft']:raise ValueError('Сохраните письмо и подготовьте актуальную форму HH.')
        if form.get('selected_resume_id')!=ctx['resume_id']:raise ValueError('В форме выбрано другое CV.')
        values=answers if answers is not None else self.form_answers(app_id)['values']
        if not isinstance(values,dict) or set(values)!={f['id'] for f in form['fields']}:raise ValueError('Ответы не соответствуют полям формы.')
        covers=[f for f in form['fields'] if f.get('purpose')=='cover']
        if len(covers)>1 or (covers and values.get(covers[0]['id'])!=wf['draft']):raise ValueError('Письмо в форме должно точно совпадать с согласуемым текстом.')
        if not covers and wf['state']!='needs_approval':raise ValueError('Следующий шаг анкеты ещё не прочитан.')
        for field in form['fields']:
            value=values[field['id']];typ=field.get('type')
            if typ in ('checkbox','radio'):
                if type(value) is not bool:raise ValueError('Некорректный выбор поля.')
            elif not isinstance(value,str) or len(value)>16000:raise ValueError('Некорректный текст поля.')
            if typ=='select' and value not in [o['value'] for o in field.get('options',[])]:raise ValueError('Выбран недоступный вариант.')
            if field.get('required') and (not value if typ!='radio' else not any(values[f['id']] for f in form['fields'] if f.get('group')==field.get('group'))):raise ValueError('Заполните обязательные поля анкеты.')
        if not re.match(r'^(отправить|откликнуться|далее|продолжить)',form.get('submit_label',''),re.I):raise ValueError('Действие HH не распознано.')
        intent={'app_id':app_id,'resume_id':ctx['resume_id'],'resume_hash':ctx['resume_hash'],'vacancy_id':ctx['vacancy']['id'],'vacancy_hash':hashed([ctx['vacancy']['title'],normalize(ctx['vacancy']['description'])]),'revision':wf['revision'],'draft':wf['draft'],'answers':values,'form_fingerprint':form['fingerprint'],'submit_label':form['submit_label'],'form_snapshot':form,'field_revisions':self.form_answers(app_id)['revisions']}
        return {**intent,'intent_hash':hashed(intent)}
    def approve(self,app_id,intent_hash,answers=None,confirmed=False):
        if confirmed is not True:raise ValueError('Нужно явное разрешение на показанный отклик.')
        self.validate_current(app_id,active=True)
        intent=self.intent(app_id,answers)
        if intent['intent_hash']!=intent_hash:raise ValueError('Состав отклика изменился. Просмотрите новую версию.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');wf=self._wf(db,app_id);self._blocked_edit(wf)
            if wf['revision']!=intent['revision'] or wf['draft']!=intent['draft'] or not wf['form'] or json.loads(wf['form'])['fingerprint']!=intent['form_fingerprint']:raise ValueError('Письмо или форма изменились.')
            current_revisions={r['field_id']:r['revision'] for r in db.execute('SELECT field_id,revision FROM application_field_drafts WHERE app_id=? AND form_fingerprint=?',(app_id,intent['form_fingerprint']))}
            if any(current_revisions.get(field,0)!=revision for field,revision in intent['field_revisions'].items()):raise ValueError('Ответы изменились. Просмотрите новую версию.')
            self._invalidate(db,app_id);identifier=secrets.token_hex(12)
            db.execute('INSERT INTO application_approvals VALUES(?,?,?,?,?,?,?)',(identifier,app_id,intent_hash,packed(intent),'approved',time.time()+900,utc()))
            # Explicit columns keep the approval and execution command in one transaction.
            command=secrets.token_hex(12);db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,?,?,?,?)',(command,app_id,'execute',packed({'approval_id':identifier}),'queued',None,time.time(),time.time(),None))
            db.execute("UPDATE application_workflow SET state='approved',updated_at=? WHERE app_id=?",(utc(),app_id));self._event(db,app_id,'approved',{'approval_id':identifier,'intent_hash':intent_hash})
        return {'approval_id':identifier,'command_id':command}
    def claim_approval(self,command_id,worker,fingerprint):
        with self.connect() as db:app=db.execute('SELECT app_id FROM browser_commands WHERE id=?',(command_id,)).fetchone()
        if not app:raise ValueError('Команда не найдена.')
        self.validate_current(app[0],active=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');command=db.execute('SELECT * FROM browser_commands WHERE id=?',(command_id,)).fetchone()
            if not command or command['state']!='running' or command['worker_id']!=worker or command['kind']!='execute':raise ValueError('Команда не принадлежит этому исполнителю.')
            approval=db.execute('SELECT * FROM application_approvals WHERE id=?',(json.loads(command['payload'])['approval_id'],)).fetchone()
            if not approval or approval['status']!='approved' or approval['expires']<time.time():raise ValueError('Разрешение уже использовано, отозвано или истекло.')
            intent=json.loads(approval['payload']);wf=self._wf(db,command['app_id'])
            if wf['state']!='approved' or wf['revision']!=intent['revision'] or wf['draft']!=intent['draft'] or not wf['form'] or json.loads(wf['form'])['fingerprint']!=intent['form_fingerprint'] or fingerprint!=intent['form_fingerprint']:raise ValueError('Письмо или форма изменились; нужно новое разрешение.')
            db.execute("UPDATE application_approvals SET status='claimed' WHERE id=?",(approval['id'],));db.execute("UPDATE application_workflow SET state='sending',updated_at=? WHERE app_id=?",(utc(),command['app_id']));self._event(db,command['app_id'],'send_claimed',{'command_id':command_id})
        return intent
    def finish_command(self,command_id,worker,result):
        with self.connect() as db:bump=db.execute("SELECT 1 FROM browser_commands WHERE id=? AND kind='resume_bump'",(command_id,)).fetchone()
        if bump:
            from .resume_bump import finish
            return finish(self,command_id,worker,result)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');cmd=db.execute('SELECT * FROM browser_commands WHERE id=?',(command_id,)).fetchone()
            if not cmd or not cmd['worker_id'] or cmd['worker_id']!=worker:raise ValueError('Команда принадлежит другому исполнителю.')
            if cmd['state']=='cancelled' and cmd['kind'] in ('discover','collect') and result.get('state') in ('complete','failed','needs_input'):
                if cmd['result'] is None:db.execute('UPDATE browser_commands SET result=? WHERE id=?',(packed(result),command_id))
                return {'ok':True,'ignored':True,'note':'Чтение заменено новой командой; старый результат не завершает новую задачу.'}
            if cmd['result'] is not None:
                if json.loads(cmd['result'])==result:return {'ok':True,'replayed':True}
                raise ValueError('Для команды уже сохранён другой результат.')
            if cmd['state'] not in ('running','uncertain') and not (cmd['state']=='cancelled' and result.get('state')=='submitted'):raise ValueError('Команда уже завершена.')
            state=result.get('state')
            if state=='submitted':
                ctx=json.loads(db.execute('SELECT context FROM applications WHERE id=?',(cmd['app_id'],)).fetchone()[0]) if cmd['app_id'] else None
                u=urlsplit(result.get('source_url',''));vid=ctx['vacancy']['id'][3:] if ctx else ''
                from urllib.parse import parse_qs
                target=(u.path.rstrip('/')=='/vacancy/'+vid or u.path.rstrip('/')=='/applicant/vacancy_response' and any(parse_qs(u.query).get(k)==[vid] for k in ('vacancyId','vacancy_id')))
                if not hh_url(result.get('source_url','')) or not target or not re.search(r'вы откликнулись|отклик отправлен|успешно отправлен',str(result.get('evidence','')),re.I):raise ValueError('Нет подтверждения отправки для этой вакансии на странице HH.')
            allowed={'complete','needs_input','submitted','uncertain','failed'}
            if state not in allowed:raise ValueError('Некорректный результат браузера.')
            db.execute('UPDATE browser_commands SET state=?,result=?,updated=? WHERE id=?',(state,packed(result),time.time(),command_id))
            if cmd['app_id']:
                wf=self._wf(db,cmd['app_id']);target='uncertain' if cmd['kind']=='execute' and state in ('failed','uncertain') and wf['state']=='sending' else 'submitted' if state=='submitted' else 'needs_input' if state in ('failed','needs_input') and wf['state']!='needs_approval' else wf['state']
                db.execute('UPDATE application_workflow SET state=?,updated_at=? WHERE app_id=?',(target,utc(),cmd['app_id']))
                if state=='submitted':
                    db.execute("UPDATE applications SET status='submitted' WHERE id=? AND status NOT IN ('viewed','invited','rejected','withdrawn')",(cmd['app_id'],));self.mark_applied(db,cmd['app_id'])
                    stamp=utc();proof={'status':'submitted','status_text':result['evidence'],'vacancy_id':ctx['vacancy']['id'],'resume_id':ctx['resume_id']}
                    db.execute('INSERT OR IGNORE INTO hh_observations VALUES(?,?,?,?,?,?,?)',(hashed([command_id,proof]),ctx['vacancy']['id'],None,'submitted',stamp,result['source_url'],packed(proof)))
                self._event(db,cmd['app_id'],'browser_result',result)
        return {'ok':True}

    def recover_unsent(self,app_id,confirmed):
        if confirmed is not True:raise ValueError('Подтвердите личную проверку откликов HH.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');wf=self._wf(db,app_id)
            if wf['state']!='uncertain':raise ValueError('Ручная сверка нужна только при неизвестном результате.')
            ctx=json.loads(db.execute('SELECT context FROM applications WHERE id=?',(app_id,)).fetchone()[0])
            known=db.execute("SELECT 1 FROM hh_observations WHERE vacancy_id=? AND status<>'unknown'",(ctx['vacancy']['id'],)).fetchone()
            if known:raise ValueError('В базе есть подтверждённый отклик HH. Повтор запрещён.')
            self._invalidate(db,app_id);db.execute("UPDATE browser_commands SET state='cancelled' WHERE app_id=? AND state='running'",(app_id,))
            db.execute("UPDATE application_workflow SET state='draft',form=NULL,updated_at=? WHERE app_id=?",(utc(),app_id))
            self._event(db,app_id,'user_verified_unsent',{})
        return self.workflow(app_id)

    def validate_current(self,app_id,active=False):
        from .manual_applications import all_marks
        if active:
            with self.connect() as db:manual=all_marks(db)
            if manual.get(self.get(app_id)['context']['vacancy']['id'],{}).get('marked'):raise ValueError('Отклик уже отмечен вами как сделанный. Повторная отправка заблокирована для этой записи.')
        from .resume_source import _load_resume_bundle
        app=self.get(app_id);ctx=app['context']
        with self.connect() as db:
            try:
                cv=db.execute("SELECT payload FROM entities WHERE kind='resume' AND id=?",(ctx['resume_id'],)).fetchone()
                job=db.execute("SELECT payload,availability FROM entities WHERE kind='vacancy' AND id=?",(ctx['vacancy']['id'],)).fetchone()
                sent=db.execute("SELECT 1 FROM hh_observations WHERE vacancy_id=? AND status<>'unknown' LIMIT 1",(ctx['vacancy']['id'],)).fetchone()
            except Exception:raise ValueError('Сначала синхронизируйте CV и вакансию в локальный архив.') from None
        if not cv or not job:raise ValueError('В архиве нет актуальных CV/вакансии.')
        if sent:raise ValueError('На HH уже есть отклик по этой вакансии.')
        cv=json.loads(cv[0]);jd=json.loads(job[0])
        if cv.get('content_hash')!=ctx['resume_hash']:raise ValueError('CV изменилось после подготовки отклика. Нужно заново согласовать контекст.')
        _load_resume_bundle({'schema_version':2,'primary_id':ctx['resume_id'],'resumes':[cv]},now=datetime.now(timezone.utc))
        from .resume_files import redact_contacts
        if normalize(redact_contacts(jd.get('description','')))!=normalize(ctx['vacancy']['description']) or jd.get('title')!=ctx['vacancy']['title']:raise ValueError('Текст вакансии изменился. Нужен новый просмотр отклика.')
        if jd.get('archived') or job['availability']=='closed':raise ValueError('Вакансия закрыта; отправка запрещена.')
        if active:
            from .archive_store import source_url_is_detail
            try:checked=datetime.fromisoformat(str(jd.get('availability_checked_at') or (jd.get('collected_at','') if source_url_is_detail(jd.get('source_page',''),ctx['vacancy']['id']) else '')).replace('Z','+00:00'))
            except ValueError:checked=None
            if job['availability']!='active' or not checked or not checked.tzinfo or not -timedelta(minutes=5)<=datetime.now(timezone.utc)-checked<=timedelta(minutes=30):raise ValueError('Нужна свежая проверка активности вакансии. Откройте полное описание и сохраните его заново.')
        return app
