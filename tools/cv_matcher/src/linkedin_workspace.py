"""Private LinkedIn workspace on the shared local database and browser command queue."""
from __future__ import annotations
import json
import re
import secrets
import time
import unicodedata
from urllib.parse import urlsplit, parse_qs, urlencode, unquote, quote
from .archive_store import canonical, digest, now_iso
from . import linkedin_pacing as pacing

KEY = 'linkedin-workspace-v1'
READS = {'profile.read', 'profile.form', 'profile.open', 'jobs.list', 'jobs.detail', 'messages.list', 'messages.thread', 'network.list', 'network.prepare', 'team.read'}
WRITES = {'profile.fill', 'profile.save', 'network.execute'}
KINDS = READS | WRITES
NETWORK_ACTIONS = {'connect', 'accept', 'ignore', 'withdraw', 'remove'}


def linkedin_url(value, kind='any'):
    if not isinstance(value, str) or len(value) > 1500: raise ValueError('Нужна ссылка LinkedIn.')
    u = urlsplit(value)
    if u.scheme != 'https' or u.netloc not in ('www.linkedin.com', 'linkedin.com') or u.username:
        raise ValueError('Разрешены только страницы https://www.linkedin.com/.')
    path = u.path;slug=None
    if path.startswith('/in/'):
        match=re.fullmatch(r'/in/([^/]+)(.*)',path)
        if not match:raise ValueError('Нужна ссылка на профиль LinkedIn /in/….')
        try:slug=unicodedata.normalize('NFC',unquote(match[1],errors='strict'))
        except UnicodeError:raise ValueError('Некорректный адрес профиля.') from None
        if not 1<=len(slug)<=150 or not all(char.isalnum() or char in '_-' for char in slug):raise ValueError('Некорректный адрес профиля.')
        path='/in/'+quote(slug,safe='_-')+match[2]
    if path.startswith('/messaging/thread/'):path=re.sub(r'%3[dD]','=',path)
    checked=re.sub(r'^/in/[^/]+','/in/profile',path) if path.startswith('/in/') else path
    if re.search(r'%|\.\.|[\\\x00-\x20]',checked):raise ValueError('Некорректный путь LinkedIn.')
    if kind == 'profile':
        if not re.fullmatch(r'/in/[^/]+(?:/(?:en|ru))?/?',path):raise ValueError('Нужна ссылка на профиль LinkedIn /in/….')
        path='/in/'+quote(slug,safe='_-')+'/'
    elif kind == 'job':
        m = re.fullmatch(r'/jobs/view/(?:[^/]+-)?(\d{1,25})/?', path)
        jid = m[1] if m else parse_qs(u.query).get('currentJobId', [''])[0]
        if not re.fullmatch(r'\d{1,25}', jid) or not path.startswith('/jobs/'):
            raise ValueError('Нужна ссылка на конкретную вакансию LinkedIn.')
        path = '/jobs/view/' + jid + '/'
    elif kind == 'thread' and not re.fullmatch(r'/messaging/thread/[A-Za-z0-9_-]{1,200}={0,2}/?', path):
        raise ValueError('Нужна ссылка на выбранный диалог LinkedIn.')
    elif kind == 'any' and not re.match(r'^/(?:in|jobs|messaging|mynetwork)(?:/|$)', path):
        raise ValueError('Эта страница не относится к рабочему разделу LinkedIn.')
    query={}
    if kind=='any' and path.startswith('/jobs/'):
        query={key:values[-1] for key,values in parse_qs(u.query).items() if key in ('keywords','geoId','location','origin','originToLandingJobPostings','start','currentJobId','f_TPR','f_WT','f_E','f_C')}
    if kind=='any' and path.startswith('/in/') and parse_qs(u.query).get('locale',[''])[0] in ('en_US','ru_RU'):query['locale']=parse_qs(u.query)['locale'][0]
    return 'https://www.linkedin.com' + path + ('?'+urlencode(query) if query else '')


def text(value, limit=20000):
    if not isinstance(value, str) or len(value) > limit: raise ValueError('Некорректный или слишком длинный текст.')
    return value.strip()


def init(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS browser_commands(id TEXT PRIMARY KEY,app_id TEXT,kind TEXT,payload TEXT,state TEXT,worker_id TEXT,created REAL,updated REAL,result TEXT);
      CREATE TABLE IF NOT EXISTS linkedin_snapshots(id TEXT PRIMARY KEY,account TEXT,kind TEXT,payload TEXT,fingerprint TEXT,created REAL);
      CREATE INDEX IF NOT EXISTS linkedin_snapshot_kind ON linkedin_snapshots(account,kind,created DESC);
      CREATE TABLE IF NOT EXISTS linkedin_records(account TEXT,kind TEXT,id TEXT,payload TEXT,updated REAL,PRIMARY KEY(account,kind,id));
      CREATE TABLE IF NOT EXISTS linkedin_receipts(command_id TEXT PRIMARY KEY,payload_hash TEXT,result TEXT);
      CREATE TABLE IF NOT EXISTS linkedin_notes(account TEXT,kind TEXT,id TEXT,payload TEXT,revision INTEGER,PRIMARY KEY(account,kind,id));
    ''')
    from .linkedin_contacts import init as init_contacts
    init_contacts(db)


def settings(db):
    row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {'profile_url': '', 'paused': False}


def save_settings(db, state):
    db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (KEY, canonical(state)))


def configure(archive, data):
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE'); state = settings(db)
        if 'profile_url' in data:
            if data.get('own_profile') is not True: raise ValueError('Подтвердите, что это ваш профиль LinkedIn.')
            url = linkedin_url(data['profile_url'], 'profile')
            if url != state.get('profile_url'):
                if db.execute("SELECT 1 FROM browser_commands WHERE kind LIKE 'linkedin.%' AND state='running'").fetchone():
                    raise ValueError('Дождитесь завершения текущей операции перед сменой аккаунта.')
                db.execute("UPDATE browser_commands SET state='cancelled' WHERE kind LIKE 'linkedin.%' AND state='queued'")
            if url!=state.get('profile_url'):state.pop('read_pacing',None)
            state['profile_url'] = url
        if 'paused' in data:
            if type(data['paused']) is not bool: raise ValueError('Некорректное состояние паузы.')
            state['paused'] = data['paused']
            if not data['paused']:state.pop('pause_reason',None)
        save_settings(db, state)
    return state


def source(archive, resume_id=None):
    """Same reviewed intro as the public portfolio; all raw education sources stay local."""
    rid = resume_id or archive.summary().get('primary_id')
    if not rid: raise ValueError('Выберите основное HH-резюме в разделе «Резюме».')
    cv = archive.detail('resume', rid)
    payload = cv['payload']
    if payload.get('source_type', 'hh') != 'hh' or payload.get('quality') != 'full':
        raise ValueError('Нужно полное основное HH-резюме.')
    sections = payload.get('sections', [])
    about = '\n\n'.join(s.get('text', '') for s in sections if s.get('key') == 'about')
    about = re.sub(r'^\s*(?:О себе|About me|About)\s*:?\s*', '', about, flags=re.I).strip()
    from .portfolio_publication import read, parse_experience
    draft = read(archive).get('about_draft', {})
    reviewed = draft.get('resume_id') == rid and draft.get('basis') == digest({'resume': rid, 'about': about})
    work = '\n\n'.join(s.get('text', '') for s in sections if s.get('key') == 'experience')
    warnings = []
    try: experience = parse_experience(work) if work else []
    except ValueError:
        experience = []; warnings.append('Опыт требует ручного сопоставления; исходный текст сохранён.')
    result = {'resume_id': rid, 'version_id': cv['version_id'], 'source_at':cv.get('source_at') or next((v['source_at'] for v in cv.get('versions',[]) if v['id']==cv['version_id']),None) or payload.get('captured_at'), 'headline': payload['title'],
              'source_url': payload.get('source_url') or 'https://hh.ru/resume/' + rid,
              'about': draft['text'] if reviewed else about, 'hh_about':about, 'sections':sections, 'about_origin': 'reviewed' if reviewed else 'hh',
              'translations': draft.get('translations', {}) if reviewed else {},
              'experience': experience, 'experience_text': work,
              'education': [s for s in sections if re.search('education|course|certificate|training', s.get('key', ''), re.I)
                            or re.search('образован|курс|сертификат', s.get('heading', ''), re.I)],
              'warnings': warnings}
    result['fingerprint'] = digest(result)
    return result


def snapshot(db, identifier, account, kind=None):
    row = db.execute('SELECT * FROM linkedin_snapshots WHERE id=? AND account=?', (identifier, account)).fetchone()
    if not row or (kind and row['kind'] != kind): raise ValueError('Сначала прочитайте актуальную страницу через расширение.')
    return {**dict(row), 'payload': json.loads(row['payload'])}


def _put_snapshot(db, account, kind, payload):
    ident = secrets.token_hex(12)
    db.execute('INSERT INTO linkedin_snapshots VALUES(?,?,?,?,?,?)', (ident, account, kind, canonical(payload), digest(payload), time.time()))
    return ident


def _expire(db):
    # Reads are also stopped rather than retried forever on a changed page/account.
    if not db.execute("SELECT 1 FROM browser_commands WHERE kind LIKE 'linkedin.%' AND state='running' AND updated<? LIMIT 1",(time.time()-180,)).fetchone():return
    db.execute("UPDATE browser_commands SET state=CASE WHEN kind IN ('linkedin.profile.fill','linkedin.profile.save','linkedin.network.execute') THEN 'uncertain' ELSE 'needs_input' END, result=? WHERE kind LIKE 'linkedin.%' AND state='running' AND updated<?",
               (canonical({'message': 'Связь с расширением прервалась. Проверьте страницу перед повтором.'}), time.time()-180))


def overview(archive):
    with archive.connect() as db:
        init(db); _expire(db); config = settings(db); account = config.get('profile_url', '')
        rows = db.execute("SELECT * FROM browser_commands WHERE kind LIKE 'linkedin.%' AND json_extract(payload,'$.account')=? ORDER BY created DESC LIMIT 100", (account,)).fetchall()
        commands = [{**dict(r), 'payload': json.loads(r['payload']), 'result': json.loads(r['result']) if r['result'] else None} for r in rows]
        for command in commands:
            if 'snapshot' in command['payload']:command['payload'].pop('snapshot')
            if 'values' in command['payload']:command['payload']['changed_fields_count']=len(command['payload'].pop('values'))
            known=command['payload'].pop('known_contacts',None)
            if known is not None:command['payload']['known_contacts_count']=len(known)
        records = {}
        for kind in ('jobs', 'threads', 'contacts'):
            records[kind] = []
            for r in db.execute('SELECT r.*, n.payload notes, n.revision FROM linkedin_records r LEFT JOIN linkedin_notes n ON n.account=r.account AND n.kind=r.kind AND n.id=r.id WHERE r.account=? AND r.kind=? ORDER BY r.updated DESC LIMIT 1000', (account, kind)):
                records[kind].append({**(_card_metadata(json.loads(r['payload'])) if kind=='jobs' else json.loads(r['payload'])), 'notes': json.loads(r['notes']) if r['notes'] else {}, 'revision': r['revision'] or 0})
        queue_counts={}
        for r in db.execute("SELECT kind,state,count(*) amount FROM browser_commands WHERE kind LIKE 'linkedin.%' AND json_extract(payload,'$.account')=? GROUP BY kind,state",(account,)):
            queue_counts.setdefault(r['kind'][9:],{})[r['state']]=r['amount']
        for thread in records['threads']:
            thread['message_count']=len(thread.pop('messages',[]));thread['text']=thread.get('preview') or thread.get('text','')[:1200]
        from .linkedin_contacts import view as contact_collection_view
        contact_collection=contact_collection_view(db,account)
        contact_count=db.execute("SELECT count(*) FROM linkedin_records WHERE account=? AND kind='contacts'",(account,)).fetchone()[0]
        recent = {}
        for kind in ('profile.read', 'profile.form', 'profile.fill', 'network.prepare'):
            r = db.execute('SELECT id FROM linkedin_snapshots WHERE account=? AND kind=? ORDER BY created DESC LIMIT 1', (account, kind)).fetchone()
            if r: recent[kind] = snapshot(db, r[0], account)
    with archive.connect() as db:
        imported={r[0] for r in db.execute("SELECT id FROM entities WHERE kind='vacancy' AND id LIKE 'linkedin_%'")}
    for job in records['jobs']: job['in_archive']=job['id'] in imported
    return {'settings': config, 'connected': time.time()-config.get('last_seen', 0) < 100,
            'contact_collection':contact_collection,'contact_count':contact_count,'commands': commands, 'queue_counts':queue_counts, 'records': records, 'snapshots': recent, 'limit': 1000}


def enqueue(archive, data):
    action = data.get('action')
    if action not in KINDS: raise ValueError('Неизвестная операция LinkedIn.')
    with archive.connect() as db:
        init(db); config = settings(db)
    account = config.get('profile_url')
    if not account: raise ValueError('Укажите и подтвердите собственный профиль LinkedIn.')
    p = {'account': account}
    if action == 'jobs.list':
        p['url'] = linkedin_url(data.get('url') or 'https://www.linkedin.com/jobs/')
        if not urlsplit(p['url']).path.startswith('/jobs/'): raise ValueError('Нужна страница вакансий.')
        if type(data.get('load_details',False)) is not bool:raise ValueError('Выберите режим загрузки описаний.')
        p['load_details']=data.get('load_details',False)
        interval=data.get('interval_seconds',3)
        if type(interval) not in (int,float) or not 2<=interval<=60:raise ValueError('Пауза между переходами от 2 до 60 секунд.')
        p['interval_ms']=int(interval*1000)
        p['pacing_options']=pacing.options(data,config.get('read_pacing',{}))
        p['listing_mode']=data.get('listing_mode','auto')
        if p['listing_mode'] not in ('auto','infinite','pagination'):raise ValueError('Выберите способ обхода выдачи.')
        p['diagnostics']=data.get('diagnostics') is True
        p['collection']=data.get('collection','all')
        if p['collection'] not in ('all','preferences','profile','more'):raise ValueError('Выберите раздел рекомендаций LinkedIn.')
        p['import_on_capture']=False
    elif action == 'jobs.detail':
        p.update(url=linkedin_url(data.get('url'), 'job'),import_on_capture=False)
        with archive.connect() as db:
            prior=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='jobs' AND id=?",(account,'linkedin_'+p['url'].rstrip('/').split('/')[-1])).fetchone()
        if prior:p['job_title']=json.loads(prior[0]).get('title','')
    elif action == 'team.read':
        from .vacancy_team import init as init_team, assert_link
        with archive.connect() as db:init_team(db);assert_link(db,data)
        p.update(url=linkedin_url(data.get('url'),'job'),vacancy_id=data['vacancy_id'],team_id=data['team_id'])
    elif action == 'messages.thread':
        p['url'] = linkedin_url(data.get('url'), 'thread');p['message_limit']=data.get('message_limit',200)
        if type(p['message_limit']) is not int or not 1<=p['message_limit']<=500:raise ValueError('От 1 до 500 сообщений за проход.')
    elif action == 'messages.list':
        p['url'] = 'https://www.linkedin.com/messaging/';p['diagnostics']=data.get('diagnostics') is True
        p['collect_all']=data.get('collect_all') is True;p['scope']=data.get('scope','all');p['load_threads']=data.get('load_threads') is True;p['message_limit']=data.get('message_limit',200)
        if p['scope'] not in ('all','jobs','unread','inmail'):raise ValueError('Выберите папку сообщений.')
        if type(p['message_limit']) is not int or not 1<=p['message_limit']<=500:raise ValueError('От 1 до 500 сообщений за проход.')
    elif action == 'network.list':
        scope = data.get('scope', 'connections')
        paths = {'connections': '/mynetwork/invite-connect/connections/', 'received': '/mynetwork/invitation-manager/', 'sent': '/mynetwork/invitation-manager/sent/'}
        if scope not in paths: raise ValueError('Неизвестный список контактов.')
        p.update(url='https://www.linkedin.com'+paths[scope], scope=scope)
        if type(data.get('only_new',False)) is not bool:raise ValueError('Выберите режим дозагрузки контактов.')
        p['only_new']=data.get('only_new',False)
        if type(data.get('collect_all',False)) is not bool:raise ValueError('Выберите режим полного сбора контактов.')
        p['collect_all']=data.get('collect_all',False)
        if p['only_new']:
            with archive.connect() as db:
                rows=db.execute("SELECT id FROM linkedin_records WHERE account=? AND kind='contacts' AND (json_extract(payload,'$.scope')=? OR EXISTS(SELECT 1 FROM json_each(json_extract(payload,'$.scopes')) WHERE value=?))",(account,scope,scope)).fetchall()
            p['known_contacts']=[row[0] for row in rows]
    elif action == 'profile.read':
        p['url'] = account;p['profile_language']=data.get('profile_language','current')
        if p['profile_language'] not in ('current','en','ru'):raise ValueError('Выберите язык профиля LinkedIn.')
    elif action == 'profile.form': p['url'] = account  # Reads the editor already opened by the owner.
    elif action == 'profile.open':
        url=linkedin_url(data.get('url') or account);section=data.get('section')
        if section not in ('headline','about','experience','education','certifications','courses'):raise ValueError('Выберите раздел профиля.')
        with archive.connect() as db:
            snap=snapshot(db,data.get('snapshot_id'),account,'profile.read');profile=snap['payload']
        allowed=[profile.get('intro_edit_url')] if section=='headline' else [profile.get('about_edit_url')] if section=='about' else []
        block=profile.get('sections',{}).get(section,{})
        allowed.extend(item.get('url') for item in [*block.get('links',[]),*block.get('detail',{}).get('links',[])])
        edit_label=data.get('edit_label')
        if edit_label:
            if section not in ('headline','about') or edit_label not in profile.get('edit_controls',{}).get(section,[]):raise ValueError('Кнопка редактора должна быть обнаружена в выбранной секции.')
            p.update(url=account,section=section,edit_label=edit_label)
        else:
            if url not in allowed or not url.startswith(account) or '/edit/' not in url:raise ValueError('Сначала перечитайте профиль: ссылка редактора должна быть обнаружена в выбранной секции.')
            p.update(url=url,section=section)
        p['profile_language']=profile.get('profile_language') or 'current'

    elif action == 'network.prepare':
        p['url'] = linkedin_url(data.get('url'), 'profile')
        p['network_action'] = data.get('network_action')
        if p['network_action'] not in NETWORK_ACTIONS or p['url'] == account: raise ValueError('Выберите контакт и действие.')
    if action in ('jobs.list', 'network.list', 'messages.list'):
        limit = 300 if action=='network.list' and p.get('collect_all') else 10000 if action=='messages.list' and p.get('collect_all') else data.get('limit', 100)
        maximum=500 if action=='jobs.list' else 10000 if action=='messages.list' and p.get('collect_all') else 300
        if type(limit) is not int or not 1 <= limit <= maximum: raise ValueError('Лимит от 1 до '+str(maximum)+' записей.')
        p['limit'] = limit
    if action in WRITES:
        if data.get('confirmed') is not True: raise ValueError('Подтвердите конкретное изменение в предпросмотре.')
        with archive.connect() as db:
            snap = snapshot(db, data.get('snapshot_id'), account)
        if time.time()-snap['created'] > 900: raise ValueError('Предпросмотр старше 15 минут. Прочитайте страницу снова.')
        if data.get('fingerprint') != snap['fingerprint']: raise ValueError('Предпросмотр изменился.')
        if action == 'network.execute':
            if snap['kind'] != 'network.prepare': raise ValueError('Сначала подготовьте действие с контактом.')
            p.update(snapshot=snap['payload'], url=linkedin_url(snap['payload']['url']), network_action=snap['payload']['action'])
        else:
            expected = 'profile.form' if action == 'profile.fill' else 'profile.fill'
            if snap['kind'] != expected: raise ValueError('Сначала прочитайте форму или перенесите проверенные поля.')
            current = source(archive,data.get('resume_id') or snap['payload'].get('source_resume_id'))
            if data.get('source_fingerprint') != current['fingerprint']: raise ValueError('Основное резюме или введение изменилось. Обновите сравнение.')
            if action == 'profile.save' and snap['payload'].get('source_fingerprint') != current['fingerprint']:
                raise ValueError('Источник изменился после переноса. Прочитайте форму и согласуйте поля заново.')
            p.update(snapshot=snap['payload'], source_fingerprint=current['fingerprint'],source_resume_id=current['resume_id'])
            if action == 'profile.fill':
                fields = {f['id']: f for f in snap['payload'].get('fields', [])}
                values = data.get('values')
                if not isinstance(values, dict) or not values or not set(values) <= set(fields): raise ValueError('Выберите поля текущей формы.')
                for key, val in values.items():
                    f = fields[key]
                    if f['type'] == 'checkbox':
                        if type(val) is not bool: raise ValueError('Для флажка нужно true / false.')
                    else:
                        text(val, min(f.get('max_length') or 20000, 20000))
                        if f['type'] == 'select' and val not in [o['value'] for o in f.get('options', [])]: raise ValueError('Выберите существующий вариант списка.')
                p['values'] = values
        p.update(snapshot_id=snap['id'], expires=snap['created']+900)
    now = time.time()
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current=settings(db)
        if current.get('profile_url') != account: raise ValueError('Аккаунт изменился.')
        if action=='network.list' and p.get('collect_all'):
            from .linkedin_contacts import active
            existing=active(db,account,p['scope'])
            if existing:return {'id':existing[0],'duplicate':True}
            previous_collection=db.execute('SELECT * FROM linkedin_contact_collections WHERE account=? AND scope=? ORDER BY updated DESC LIMIT 1',(account,p['scope'])).fetchone()
        else:previous_collection=None
        if action=='jobs.list':
            pacing.state(current).update(p['pacing_options']);pacing.state(current);save_settings(db,current)
        if action in WRITES:
            old = db.execute("SELECT id FROM browser_commands WHERE kind=? AND json_extract(payload,'$.snapshot_id')=?", ('linkedin.'+action, p['snapshot_id'])).fetchone()
        else:
            old = db.execute("SELECT id FROM browser_commands WHERE kind=? AND payload=? AND state IN ('queued','running')", ('linkedin.'+action, canonical(p))).fetchone()
        if old: return {'id': old[0], 'duplicate': True}
        ident = secrets.token_hex(12)
        if action=='network.list' and p.get('collect_all'):
            from .linkedin_contacts import start
            if previous_collection and previous_collection['state']!='completed' and not data.get('restart'):
                previous_payload=json.loads(previous_collection['payload']);p.update(collection_id=previous_collection['id'],only_new=True,known_contacts=previous_payload['links'])
                db.execute("UPDATE linkedin_contact_collections SET state='queued',command_id=?,updated=? WHERE id=?",(ident,now,previous_collection['id']))
            else:
                p['collection_id']=ident;p['only_new']=False;p.pop('known_contacts',None);start(db,ident,p)
        db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,?,?,?,?)', (ident, None, 'linkedin.'+action, canonical(p), 'queued', None, now, now, None))
    return {'id': ident}


def source_guard(db,resume_id=None):
    row=db.execute('SELECT payload FROM profiles ORDER BY received_at DESC LIMIT 1').fetchone();profile=json.loads(row[0]) if row else {}
    resume_id=resume_id or profile.get('primary_id');resume=db.execute("SELECT content_hash,version_id FROM entities WHERE kind='resume' AND id=?",(resume_id,)).fetchone()
    row=db.execute("SELECT value FROM archive_meta WHERE key='portfolio-publication'").fetchone();draft=json.loads(row[0]).get('about_draft') if row else None
    return digest({'primary_id':profile.get('primary_id'),'resume_id':resume_id,'resume':list(resume) if resume else None,'about_draft':draft})


def claim(archive, data):
    worker = text(data.get('worker_id'), 100)
    if not re.fullmatch(r'linkedin-[\w-]{8,80}', worker): raise ValueError('Неизвестный исполнитель.')
    current_source=None;guard=None
    with archive.connect() as db:
        init(db);pending=db.execute("SELECT payload FROM browser_commands WHERE kind IN ('linkedin.profile.fill','linkedin.profile.save') AND state='queued' ORDER BY created,id LIMIT 1").fetchone();source_resume_id=json.loads(pending[0]).get('source_resume_id') if pending else None;before=source_guard(db,source_resume_id) if pending else None
    if pending:
        try:current_source=source(archive,source_resume_id)['fingerprint']
        except ValueError:current_source=''
        with archive.connect() as db:
            guard=source_guard(db,source_resume_id)
        if before!=guard:current_source=''
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE'); _expire(db); config = settings(db)
        config.update(last_seen=time.time(), extension_version=text(data.get('version', ''), 30)); save_settings(db, config)
        if config.get('paused') or not config.get('profile_url'): return {'command': None}
        if db.execute("SELECT 1 FROM browser_commands WHERE kind LIKE 'linkedin.%' AND state='running'").fetchone(): return {'command': None}
        read_state=pacing.status(config);save_settings(db,config)
        candidates=db.execute("SELECT * FROM browser_commands WHERE kind LIKE 'linkedin.%' AND state='queued' AND json_extract(payload,'$.account')=? ORDER BY created,id",(config['profile_url'],)).fetchall()
        r=next((item for item in candidates if item['kind'] not in ('linkedin.jobs.detail','linkedin.jobs.list','linkedin.messages.thread','linkedin.messages.list') or not read_state['wait_ms']),None)
        if not r:return {'command':None,'retry_after_ms':read_state['wait_ms'] if candidates else 0}

        params=json.loads(r['payload'])
        version=config.get('extension_version','')
        version=tuple(map(int,version.split('.'))) if re.fullmatch(r'\d+\.\d+\.\d+',version) else (0,0,0)
        if r['kind']=='linkedin.profile.open' and version<(0,13,0):
            db.execute("UPDATE browser_commands SET state='needs_input',result=? WHERE id=?",(canonical({'message':'Перезагрузите расширение 0.13.0 для открытия и сохранения блоков профиля из сервиса.'}),r['id']))
            return {'command':None}
        if (params.get('only_new') or params.get('collect_all')) and version<(0,12,4):
            db.execute("UPDATE browser_commands SET state='needs_input',result=? WHERE id=?",(canonical({'message':'Для дозагрузки новых контактов перезагрузите расширение версии 0.12.4 или новее, затем повторите сбор.'}),r['id']))
            return {'command':None}
        if r['kind'][9:] in WRITES:
            if params.get('expires',0)<time.time() or (r['kind'].startswith('linkedin.profile.') and (current_source!=params.get('source_fingerprint') or guard!=source_guard(db,params.get('source_resume_id')))):
                db.execute("UPDATE browser_commands SET state='needs_input',result=? WHERE id=?",(canonical({'message':'Предпросмотр или источник изменились. Подготовьте операцию заново.'}),r['id']))
                return {'command':None}
        db.execute("UPDATE browser_commands SET state='running',worker_id=?,updated=? WHERE id=?", (worker,time.time(),r['id']))
        return {'command': {**dict(r), 'state': 'running', 'worker_id': worker, 'payload': json.loads(r['payload'])}}


def _owned(db, data):
    r = db.execute("SELECT * FROM browser_commands WHERE id=? AND worker_id=? AND kind LIKE 'linkedin.%'", (data.get('id'),data.get('worker_id'))).fetchone()
    if not r: raise ValueError('Команда принадлежит другому исполнителю.')
    return r


def control(archive, data):
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE')
        r = db.execute("SELECT * FROM browser_commands WHERE id=? AND kind LIKE 'linkedin.%'", (data.get('id'),)).fetchone()
        if not r: raise ValueError('Задача не найдена.')
        if r['state'] == 'queued': db.execute("UPDATE browser_commands SET state='cancelled' WHERE id=?", (r['id'],))
        elif r['state'] == 'running' and r['kind'][9:] in READS:
            p = json.loads(r['payload']); p['stop'] = True
            db.execute('UPDATE browser_commands SET payload=? WHERE id=?', (canonical(p),r['id']))
        else: raise ValueError('Запись уже началась или задача завершена. Сверьте результат на LinkedIn.')
    return {'ok': True}


def progress(archive, data):
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE'); r = _owned(db, data)
        if r['state'] != 'running': return {'continue': False}
        p = json.loads(r['payload'])
        count = data.get('count', 0)
        if type(count) is not int or not 0 <= count <= 10000: raise ValueError('Некорректный прогресс.')
        config=settings(db)
        config['last_seen']=time.time();save_settings(db,config)
        if data.get('unit_id') is not None:
            if r['kind'] not in ('linkedin.jobs.list','linkedin.messages.list'):raise ValueError('Эта операция не поддерживает поштучное чтение.')
            unit=linkedin_url(data['unit_id'],'job' if r['kind']=='linkedin.jobs.list' else 'thread');pacing.complete(config,r['id']+':'+unit);save_settings(db,config)
        reading=pacing.status(config) if r['kind'] in ('linkedin.jobs.list','linkedin.messages.list') else {}
        if r['kind'] in ('linkedin.jobs.list','linkedin.messages.list'):save_settings(db,config)
        message=text(data.get('message',''),500)
        if reading.get('wait_ms'):message=('Перерыв между порциями' if reading['break_until']>time.time() else 'Пауза перед следующим чтением')+' · до '+str(round(reading['wait_ms']/1000))+' сек · '+str(count)+' записей'
        db.execute('UPDATE browser_commands SET updated=?,result=? WHERE id=?', (time.time(),canonical({'count':count,'message':message,**reading}),r['id']))
        return {'continue':not p.get('stop') and not config.get('paused'),**reading}


def _card_metadata(job):
    """Recover explicit company/location lines from older saved short cards."""
    if job.get('description_quality')!='full':
        lines=[line.strip() for line in job.get('description','').splitlines() if line.strip()]
        if '•' in lines:
            index=lines.index('•')
            if index>0 and index+1<len(lines):
                job={**job,'company':job.get('company') or lines[index-1],'location':job.get('location') or lines[index+1],
                     'locations':job.get('locations') or [lines[index+1]]}
    return job

def _logo(value):
    if not isinstance(value,str) or len(value)>2500:return ''
    u=urlsplit(value)
    return value if u.scheme=='https' and not u.username and u.hostname in ('media.licdn.com','static.licdn.com') else ''


def _record(db, account, kind, ident, payload):
    if not ident or len(ident)>1600: raise ValueError('Некорректный идентификатор записи.')
    db.execute('INSERT OR REPLACE INTO linkedin_records VALUES(?,?,?,?,?)', (account,kind,ident,canonical(payload),time.time()))


def result(archive, data, *, partial=False):
    outcome = data.get('outcome')
    if not isinstance(outcome, dict) or len(canonical(outcome))>2_000_000: raise ValueError('Слишком большой результат.')
    if outcome.get('state') not in ('completed','needs_input','uncertain','failed','cancelled'): raise ValueError('Некорректный статус.')
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE'); r = _owned(db, data)
        receipt=db.execute('SELECT * FROM linkedin_receipts WHERE command_id=?',(r['id'],)).fetchone()
        if receipt:
            if receipt['payload_hash']!=digest(outcome): raise ValueError('Результат уже зафиксирован другой редакцией.')
            return {'ok':True, 'duplicate':True, **json.loads(receipt['result'])}
        if r['state'] in ('completed','failed','needs_input','cancelled'): return {'ok':True, 'duplicate':True}
        if r['state'] not in ('running','uncertain'): raise ValueError('Команда уже завершена.')
        p = json.loads(r['payload']); account = p['account']; action = r['kind'][9:]
        if partial and action not in ('jobs.list','messages.list','messages.thread','network.list'): raise ValueError('Эта операция не поддерживает порционный сбор.')
        summary = {'state':outcome['state'], 'message':text(outcome.get('message',''),2000)}
        payload = outcome.get('data', {})
        if not isinstance(payload,dict): raise ValueError('Нужен объект результата.')
        if action.startswith('profile.') or action == 'network.prepare':
            if outcome['state'] == 'completed' or action=='profile.read' and outcome['state']=='needs_input' and payload.get('sections'):
                if action=='profile.read' and linkedin_url(payload.get('url'),'profile')!=account:raise ValueError('Прочитан другой профиль.')
                if action in ('profile.form','profile.fill','profile.open'):
                    fields = payload.get('fields', [])
                    if not isinstance(fields,list) or not 1<=len(fields)<=80 or not payload.get('form_fingerprint'): raise ValueError('Нет распознанной формы.')
                    if not linkedin_url(payload.get('url')).startswith(account): raise ValueError('Форма другого профиля.')
                if action == 'network.prepare':
                    if linkedin_url(payload.get('url')) != p['url'] or payload.get('action') != p['network_action'] or not payload.get('target_fingerprint'): raise ValueError('Контакт или действие не совпадает.')
                if action=='profile.open':payload={**payload,'section':p['section']}
                if action=='profile.fill':
                    old_fields={field['id']:field for field in p['snapshot']['fields']}
                    payload={**payload,'source_fingerprint':p['source_fingerprint'],'source_resume_id':p.get('source_resume_id'),'section':p['snapshot'].get('section'),'changes':[{'label':old_fields[key]['label'],'before':old_fields[key].get('value'),'after':value} for key,value in p['values'].items()]}
                if action=='profile.read' and p.get('verify_snapshot_id'):
                    previous=snapshot(db,p['verify_snapshot_id'],account,'profile.fill')['payload'];haystack=' '.join([payload.get('headline',''),*[str(block.get('text',''))+' '+str(block.get('detail',{}).get('text','')) for block in payload.get('sections',{}).values()]])
                    normalized=lambda value:re.sub(r'\s+',' ',str(value or '')).strip().casefold()
                    checked=[{'label':change['label'],'matched':isinstance(change['after'],str) and len(change['after'].strip())>=4 and normalized(change['after']) in normalized(haystack)} for change in previous.get('changes',[])]
                    payload={**payload,'verification':{'snapshot_id':p['verify_snapshot_id'],'state':'verified' if checked and all(item['matched'] for item in checked) else 'needs_review','fields':checked}}
                    summary['verification']=payload['verification']
                summary['snapshot_id'] = _put_snapshot(db,account,'profile.form' if action=='profile.open' else action,payload)
                if action=='profile.save' and not payload.get('dialog_open'):
                    now=time.time();db.execute("INSERT INTO browser_commands VALUES(?,NULL,'linkedin.profile.read',?,'queued',NULL,?,?,NULL)",(secrets.token_hex(12),canonical({'account':account,'url':account,'profile_language':p['snapshot'].get('profile_language') or 'current','verify_snapshot_id':p['snapshot_id']}),now,now))
        elif action == 'team.read':
            from .vacancy_team import capture
            if outcome['state']=='completed':summary.update(capture(db,p,payload.get('items',[]),'linkedin'))
        elif action in ('jobs.list','jobs.detail'):
            rows = payload.get('items', [])
            if not isinstance(rows,list) or len(rows)>300: raise ValueError('Слишком много вакансий.')
            if payload.get('diagnostics'):_put_snapshot(db,account,'jobs.diagnostics',{'links':payload['diagnostics'],'scroll':payload.get('scroll',{})})
            accepted = 0;detail_queue=[]
            for job in rows:
                link = linkedin_url(job.get('link'), 'job'); jid = 'linkedin_'+link.rstrip('/').split('/')[-1]
                if action == 'jobs.detail' and link != p['url']: raise ValueError('Открыта другая вакансия.')
                description = text(job.get('description',''),200000)
                full = action == 'jobs.detail' and job.get('description_quality') == 'full' and len(description)>=150
                vacancy = {'id':jid, 'title':text(job.get('title'),500), 'company':text(job.get('company',''),500), 'link':link,
                           'description':description, 'description_quality':'full' if full else 'snippet', 'location':text(job.get('location',''),500),
                           'locations':job.get('locations',[]), 'company_logo_url':_logo(job.get('company_logo_url','')), 'linkedin_signals':job.get('linkedin_signals',{}), 'source':'linkedin', 'source_page':link if action=='jobs.detail' else p['url'], 'collected_at':now_iso(),
                           'adapter_id':'linkedin-session', 'adapter_version':'2', 'extraction_method':'visible_dom'}
                if not vacancy['title']: continue
                from .vacancy_locations import normalize_locations
                from .linkedin_job_signals import validate as validate_signals
                vacancy=normalize_locations(vacancy);vacancy['linkedin_signals']=validate_signals(vacancy['linkedin_signals'])
                prior=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='jobs' AND id=?",(account,jid)).fetchone()
                archived=db.execute("SELECT payload FROM entities WHERE kind='vacancy' AND id=?",(jid,)).fetchone()
                previous=json.loads(prior[0]) if prior else json.loads(archived[0]) if archived else {}
                head={**previous,**vacancy}
                head['linkedin_signals']={**previous.get('linkedin_signals',{}),**vacancy['linkedin_signals']}
                if previous.get('description_quality')=='full' and not full:
                    for key in ('title','company','description','description_quality','description_fetched_at','archived'):
                        if key in previous:head[key]=previous[key]
                for key in ('company','location','locations','work_formats','company_logo_url','linkedin_signals'):
                    if not head.get(key) and previous.get(key):head[key]=previous[key]
                if full:head['description_fetched_at']=now_iso()
                # Commands queued before this release retain their original archive behavior.
                if p.get('import_on_capture',True):
                    archive._entity(db,'vacancy',jid,head,now_iso())
                    head=json.loads(db.execute("SELECT payload FROM entities WHERE kind='vacancy' AND id=?",(jid,)).fetchone()[0])
                apply = json.loads(prior[0]).get('apply',{}) if prior else {}
                if action=='jobs.detail':
                    apply={'kind':job.get('apply',{}).get('kind','unknown'),'url':link}
                    candidate=job.get('apply',{}).get('url','')
                    u=urlsplit(candidate)
                    if apply['kind']=='external' and u.scheme=='https' and u.hostname and not u.username:
                        allowed={k:v[-1] for k,v in parse_qs(u.query).items() if k.lower() in ('id','jobid','job_id','gh_jid','rid','reqid')}
                        apply['url']=u._replace(query=urlencode(allowed),fragment='').geturl()
                    elif apply['kind'] not in ('easy_apply','external'): apply['kind']='unknown'
                sections=job.get('recommendation_sections',[])
                if not isinstance(sections,list) or any(k not in ('preferences','profile','more','search') for k in sections):raise ValueError('Неизвестный раздел рекомендаций.')
                _record(db,account,'jobs',jid,{**head,'apply':apply,'apply_url':apply.get('url',''),'apply_kind':apply.get('kind','unknown'),'recommendation_sections':sorted(set(previous.get('recommendation_sections',[])+sections))}); accepted+=1
                if head.get('description_quality')!='full':detail_queue.append(link)
            if action=='jobs.list' and 'collected_links' in payload:
                links=payload['collected_links']
                if partial or rows or not isinstance(links,list) or len(links)>p.get('limit',500) or len(links)>500:raise ValueError('Некорректное завершение порционного сбора.')
                links=list(dict.fromkeys(linkedin_url(u,'job') for u in links));accepted=len(links);detail_queue=[]
                for link in links:
                    record=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='jobs' AND id=?",(account,'linkedin_'+link.rstrip('/').split('/')[-1])).fetchone()
                    if not record:raise ValueError('Порция вакансий ещё не сохранена. Повторите подтверждение.')
                    if json.loads(record[0]).get('description_quality')!='full':detail_queue.append(link)
            queued=0
            if action=='jobs.list' and not partial and p.get('load_details') and outcome['state']=='completed':
                for link in detail_queue:
                    if db.execute("SELECT 1 FROM browser_commands WHERE kind='linkedin.jobs.detail' AND state IN ('queued','running') AND json_extract(payload,'$.account')=? AND json_extract(payload,'$.url')=?",(account,link)).fetchone():continue
                    now=time.time();ident=secrets.token_hex(12)
                    db.execute("INSERT INTO browser_commands VALUES(?,NULL,'linkedin.jobs.detail',?,'queued',NULL,?,?,NULL)",(ident,canonical({'account':account,'url':link,'import_on_capture':False,'job_title':next((j.get('title','') for j in rows if linkedin_url(j.get('link'),'job')==link),'')}),now,now));queued+=1
            summary.update(count=accepted,details_queued=queued,coverage='partial',reason=text(payload.get('reason','Доступная часть выдачи'),500))
        elif action in ('messages.list','messages.thread','network.list'):
            kind='contacts' if action=='network.list' else 'threads'
            if payload.get('diagnostics'):_put_snapshot(db,account,'messages.diagnostics',payload['diagnostics'])
            rows=payload.get('items',[])
            if not isinstance(rows,list) or len(rows)>300: raise ValueError('Слишком много записей.')
            for item in rows:
                url=linkedin_url(item.get('url'), 'profile' if kind=='contacts' else 'thread')
                record={'id':url,'url':url,'name':text(item.get('name',''),500), 'text':text(item.get('text',''),200000),
                        'observed_at':now_iso(),'scope':p.get('scope',''), 'coverage':'visible_only'}
                badges=item.get('badges',[])
                if not isinstance(badges,list) or len(badges)>30 or any(not isinstance(b,str) or len(b)>200 for b in badges):raise ValueError('Некорректные бейджи LinkedIn.')
                record['badges']=list(dict.fromkeys(badges))
                for key in ('unread_label','time_label','time','mutual_label'):
                    if key in item:record[key]=text(item[key],300)
                record['avatar_url']=_logo(item.get('avatar_url',''))
                if kind=='threads' and item.get('headline'):record['headline']=text(item['headline'],1000)
                if action=='messages.list' and type(item.get('list_position')) is int and 0<=item['list_position']<100000:
                    record.update(list_position=item['list_position'],listing_id=r['id'])
                if kind=='contacts':
                    for field,maximum in [('headline',1000),('company',500),('location',500),('degree',100),('relationship',100)]:record[field]=text(item.get(field,''),maximum)
                previous=db.execute('SELECT payload FROM linkedin_records WHERE account=? AND kind=? AND id=?',(account,kind,url)).fetchone()
                old=json.loads(previous[0]) if previous else {}
                record={**old,**record}
                if not record['name']:record['name']=old.get('name','')
                if not record['avatar_url']:record['avatar_url']=old.get('avatar_url','')
                if kind=='contacts':
                    # A short invitation card must not erase a richer connection.
                    for field in ('headline','company','location','degree','mutual_label'):
                        if not record.get(field):record[field]=old.get(field,'')
                    record['first_seen_at']=old.get('first_seen_at',record['observed_at'])
                    record['scopes']=sorted(set(old.get('scopes',[])+[p['scope']]))
                    if 'company_source' in item:
                        record['company_source']='profile_link' if item['company_source']=='profile_link' else old.get('company_source','')
                        if not record['company_source'] and old.get('company_source')!='profile_link':record['company']=''
                if action=='messages.list':
                    record['preview']=text(item.get('preview',item.get('text','')),2000);record['text']=old.get('text',record['text'])
                if action=='messages.thread':
                    from .linkedin_messages import messages, merge
                    record['messages']=merge(old.get('messages',[]),messages(item.get('messages',[])))
                    record['message_count']=len(record['messages']);record['read_quality']='loaded'
                    if old.get('name'):record['name']=old['name']
                    record['time_label']=old.get('time_label') or (record['messages'][-1].get('sent_label','') if record['messages'] else '')
                    record['history_coverage']=text(payload.get('history_coverage','loaded_only'),100)
                    if url != p['url']: raise ValueError('Открыт другой диалог.')
                    record['vacancy_links']=sorted(set(linkedin_url(v,'job') for v in item.get('vacancy_links',[])[:100]))
                _record(db,account,kind,url,record)
            count=len(rows);queued=0
            if action=='network.list' and 'collected_contacts' in payload:
                links=payload['collected_contacts']
                if partial or rows or not isinstance(links,list) or len(links)>p['limit']:raise ValueError('Некорректное завершение списка контактов.')
                links=list(dict.fromkeys(linkedin_url(u,'profile') for u in links));count=len(links)
                for link in links:
                    if not db.execute("SELECT 1 FROM linkedin_records WHERE account=? AND kind='contacts' AND id=?",(account,link)).fetchone():raise ValueError('Контакт ещё не сохранён.')
            if action=='messages.list' and 'collected_threads' in payload:
                links=payload['collected_threads']
                if partial or rows or not isinstance(links,list) or len(links)>p['limit']:raise ValueError('Некорректное завершение списка чатов.')
                links=list(dict.fromkeys(linkedin_url(u,'thread') for u in links));count=len(links)
                for link in links:
                    if not db.execute("SELECT 1 FROM linkedin_records WHERE account=? AND kind='threads' AND id=?",(account,link)).fetchone():raise ValueError('Диалог ещё не сохранён.')
                    if not p.get('load_threads') or outcome['state']!='completed':continue
                    if db.execute("SELECT 1 FROM browser_commands WHERE kind='linkedin.messages.thread' AND state IN ('queued','running') AND json_extract(payload,'$.account')=? AND json_extract(payload,'$.url')=?",(account,link)).fetchone():continue
                    now=time.time();db.execute("INSERT INTO browser_commands VALUES(?,NULL,'linkedin.messages.thread',?,'queued',NULL,?,?,NULL)",(secrets.token_hex(12),canonical({'account':account,'url':link,'message_limit':p['message_limit']}),now,now));queued+=1
            summary.update(count=count,threads_queued=queued,coverage='partial',reason=text(payload.get('reason','Доступная часть выдачи'),500))
            if action=='messages.list' and payload.get('listing_coverage') in ('available_boundary','selected_limit','pass_limit','stopped','read_error'):
                summary['listing_coverage']=payload['listing_coverage']
            if action=='network.list' and p.get('collection_id'):
                from .linkedin_contacts import observe
                collection=observe(db,p,payload,[linkedin_url(item['url'],'profile') for item in rows] if partial else payload.get('collected_contacts',[linkedin_url(item['url'],'profile') for item in rows]),outcome,partial=partial,paused=settings(db).get('paused',False))
                summary['collection']=collection
        if partial:
            db.execute('UPDATE browser_commands SET updated=?,result=? WHERE id=?',(time.time(),canonical(summary),r['id']))
            return {'ok':True,'continue':not p.get('stop') and not settings(db).get('paused')}
        if action in ('jobs.detail','messages.thread'):
            config=settings(db);pacing.complete(config,r['id']);save_settings(db,config)
        if re.search(r'LinkedIn требует вход|ручную проверку|ограничил доступ',summary['message'],re.I):
            config=settings(db);config.update(paused=True,pause_reason=summary['message']);save_settings(db,config)
        db.execute('INSERT INTO linkedin_receipts VALUES(?,?,?)',(r['id'],digest(outcome),canonical(summary)))
        db.execute('UPDATE browser_commands SET state=?,updated=?,result=? WHERE id=?',(outcome['state'],time.time(),canonical(summary),r['id']))
    return {'ok':True, **summary}


def import_jobs(archive,data):
    identifiers=data.get('ids')
    if not isinstance(identifiers,list) or not 1<=len(identifiers)<=300 or any(not isinstance(i,str) or not re.fullmatch(r'linkedin_\d{1,25}',i) for i in identifiers):
        raise ValueError('Выберите от 1 до 300 вакансий LinkedIn.')
    counts={'added':0,'updated':0,'unchanged':0,'protected':0}
    from .archive_store import FIELDS
    with archive.connect() as db:
        init(db);db.execute('BEGIN IMMEDIATE');account=settings(db).get('profile_url','')
        for jid in dict.fromkeys(identifiers):
            row=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='jobs' AND id=?",(account,jid)).fetchone()
            if not row:raise ValueError('Вакансия отсутствует в текущей подборке LinkedIn: '+jid)
            payload={k:v for k,v in _card_metadata(json.loads(row[0])).items() if k in FIELDS['vacancy']}
            old=db.execute("SELECT content_hash,payload,source_at FROM entities WHERE kind='vacancy' AND id=?",(jid,)).fetchone()
            archive._entity(db,'vacancy',jid,payload,now_iso())
            head=db.execute("SELECT content_hash FROM entities WHERE kind='vacancy' AND id=?",(jid,)).fetchone()
            if not old:counts['added']+=1
            elif head['content_hash']!=old['content_hash']:counts['updated']+=1
            elif json.loads(old['payload']).get('description_quality')=='full' and payload.get('description_quality')!='full':counts['protected']+=1
            else:counts['unchanged']+=1
    return {'ok':True,**counts,'count':sum(counts.values())}


def save_note(archive, data):
    kind=data.get('kind'); ident=data.get('id')
    if kind not in ('contacts','threads'): raise ValueError('Выберите контакт или диалог.')
    note={'text':text(data.get('text',''),10000), 'tags':text(data.get('tags',''),1000),
          'vacancy_id':text(data.get('vacancy_id',''),180), 'follow_up':text(data.get('follow_up',''),30)}
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE'); account=settings(db).get('profile_url','')
        if not db.execute('SELECT 1 FROM linkedin_records WHERE account=? AND kind=? AND id=?',(account,kind,ident)).fetchone(): raise ValueError('Запись не найдена.')
        if note['vacancy_id'] and not db.execute("SELECT 1 FROM entities WHERE kind='vacancy' AND id=?",(note['vacancy_id'],)).fetchone(): raise ValueError('Вакансия не найдена в архиве.')
        old=db.execute('SELECT revision FROM linkedin_notes WHERE account=? AND kind=? AND id=?',(account,kind,ident)).fetchone()
        revision=old[0] if old else 0
        if data.get('revision',0)!=revision: raise ValueError('Заметка обновлена в другой вкладке. Перечитайте её.')
        db.execute('INSERT OR REPLACE INTO linkedin_notes VALUES(?,?,?,?,?)',(account,kind,ident,canonical(note),revision+1))
    return {'ok':True,'revision':revision+1}


def checkpoint(archive, data):
    return result(archive, data, partial=True)


def contacts(archive,data):
    """Search the complete private contact collection, independently of overview limits."""
    query=text(data.get('query',''),300).casefold();scope=data.get('scope','all')
    from . import contact_relevance as relevance
    category=data.get('category','all');plan=data.get('plan','all')
    if category not in ('all',*relevance.CATEGORIES) or plan not in ('all',*relevance.PLANS):raise ValueError('Неизвестный фильтр контактов.')
    offset=data.get('offset',0);limit=data.get('limit',50)
    if scope not in ('all','connections','received','sent'):raise ValueError('Неизвестный список контактов.')
    if type(offset) is not int or not 0<=offset<=1000000 or type(limit) is not int or not 1<=limit<=500:raise ValueError('Некорректная страница контактов.')
    with archive.connect() as db:
        init(db);account=settings(db).get('profile_url','')
        db.create_function('casefold',1,lambda value:str(value or '').casefold())
        where="r.account=? AND r.kind='contacts'";args=[account]
        if scope!='all':
            where+=" AND (json_extract(r.payload,'$.scope')=? OR EXISTS(SELECT 1 FROM json_each(json_extract(r.payload,'$.scopes')) WHERE value=?))";args.extend([scope,scope])
        if query:
            where+=" AND instr(casefold(r.payload||coalesce(n.payload,'')),?)>0";args.append(query)
        join=" FROM linkedin_records r LEFT JOIN linkedin_notes n ON n.account=r.account AND n.kind=r.kind AND n.id=r.id WHERE "+where
        rows=db.execute('SELECT r.payload,n.payload notes,n.revision'+join+' ORDER BY r.updated DESC,r.id',args).fetchall()
        items=[{**json.loads(row['payload']),'notes':json.loads(row['notes']) if row['notes'] else {},'revision':row['revision'] or 0} for row in rows]
        relevance.init(db);context=relevance.basis(archive,db,account)
        reviews={row['id']:{**json.loads(row['payload']),'revision':row['revision']} for row in db.execute('SELECT * FROM linkedin_contact_reviews WHERE account=?',(account,))}
        for item in items:
            item['team_links']=context['team_links'].get(item['url'],[]);item['relevance']=relevance.classify(item,context);item['review']=reviews.get(item['id'],{'plan':'none','revision':0,'note':''})
        if plan!='all':items=[item for item in items if item['review']['plan']==plan]
        counts={name:sum(item['relevance']['is_recruiter'] if name=='recruiter' else item['relevance']['category']==name for item in items) for name in relevance.CATEGORIES}
        if category=='recruiter':items=[item for item in items if item['relevance']['is_recruiter']]
        elif category!='all':items=[item for item in items if item['relevance']['category']==category]
        total=len(items);items=items[offset:offset+limit]
        from .linkedin_contacts import view
        collection=view(db,account)
    return {'items':items,'total':total,'offset':offset,'next_offset':offset+limit if offset+limit<total else None,'collection':collection,'categories':relevance.CATEGORIES,'plans':relevance.PLANS,'classification_counts':counts,'basis':{key:context[key] for key in ('resume_title','goal','trajectory','current','adjacent','hash')}}


def profile_history(archive,data):
    with archive.connect() as db:
        init(db);account=settings(db).get('profile_url','')
        if data.get('id'):
            result=snapshot(db,data['id'],account)
            if not result['kind'].startswith('profile.'):raise ValueError('Это не версия профиля.')
            return result
        rows=db.execute("SELECT id,kind,created,json_extract(payload,'$.title') title FROM linkedin_snapshots WHERE account=? AND kind LIKE 'profile.%' ORDER BY created DESC LIMIT 80",(account,)).fetchall()
    return {'items':[dict(row) for row in rows]}


def contacts_context(archive,data):
    """Exact selected CV and active trajectory, prepared locally for clipboard export."""
    from .career_skills_store import get
    flags={key:data.get(key,True) for key in ('include_resume','include_trajectory','include_goal')}
    if any(type(value) is not bool for value in flags.values()) or type(data.get('metadata_only',False)) is not bool:raise ValueError('Выберите состав контекста флажками.')
    summary=archive.summary();result={};rid=data.get('resume_id') or summary.get('primary_id')
    if flags['include_resume']:
        if not rid:raise ValueError('Выберите резюме в сервисе или снимите флажок добавления резюме.')
        cv=archive.detail('resume',rid);payload=cv['payload']
        if payload.get('quality')!='full':raise ValueError('Для анализа нужно полное резюме.')
        result['resume']={'id':rid,'title':payload['title'],'version_id':cv['version_id'],'source_url':payload.get('source_url','')}
        if not data.get('metadata_only'):result['resume']['sections']=payload.get('sections',[])
    with archive.connect() as db:
        if flags['include_trajectory']:
            active=data.get('trajectory_id') or get(db,'trajectory-active');result['trajectory']=get(db,'trajectory:'+active) if active else None
        if flags['include_goal']:result['goal']=summary.get('goal','')
    if not data.get('metadata_only') and data.get('include_team_coverage',True):
        from .network_map import view
        network=view(archive,{'cluster':'all'})
        result['team_coverage']=[{'team':team['name'],'observed_people':len(team['people']),'linked_or_suggested_vacancies':len(team['vacancies']),'coverage':'saved_observations_only'} for team in network['teams']]
    return result


def thread_detail(archive,data):
    url=linkedin_url(data.get('url'),'thread');offset=data.get('offset',0);limit=data.get('limit',50)
    if type(offset) is not int or not 0<=offset<=1000000 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Некорректная страница сообщений.')
    with archive.connect() as db:
        init(db);account=settings(db).get('profile_url');row=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='threads' AND id=?",(account,url)).fetchone()
        if not row:raise ValueError('Диалог не сохранён для этого аккаунта.')
        thread=json.loads(row[0]);note=db.execute("SELECT payload,revision FROM linkedin_notes WHERE account=? AND kind='threads' AND id=?",(account,url)).fetchone();thread.update(notes=json.loads(note[0]) if note else {},revision=note[1] if note else 0);items=thread.pop('messages',[]);end=max(0,len(items)-offset);start=max(0,end-limit)
    return {**thread,'messages':items[start:end],'message_count':len(items),'next_offset':offset+limit if start else None}
