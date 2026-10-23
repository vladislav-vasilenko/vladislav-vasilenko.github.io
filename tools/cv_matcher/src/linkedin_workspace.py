"""Private LinkedIn workspace on the shared local database and browser command queue."""
from __future__ import annotations
import json
import re
import secrets
import time
from urllib.parse import urlsplit, parse_qs, urlencode
from .archive_store import canonical, digest, now_iso

KEY = 'linkedin-workspace-v1'
READS = {'profile.read', 'profile.form', 'jobs.list', 'jobs.detail', 'messages.list', 'messages.thread', 'network.list', 'network.prepare'}
WRITES = {'profile.fill', 'profile.save', 'network.execute'}
KINDS = READS | WRITES
NETWORK_ACTIONS = {'connect', 'accept', 'ignore', 'withdraw', 'remove'}


def linkedin_url(value, kind='any'):
    if not isinstance(value, str) or len(value) > 1500: raise ValueError('Нужна ссылка LinkedIn.')
    u = urlsplit(value)
    if u.scheme != 'https' or u.netloc not in ('www.linkedin.com', 'linkedin.com') or u.username:
        raise ValueError('Разрешены только страницы https://www.linkedin.com/.')
    path = u.path
    if re.search(r'%|\.\.|[\\\x00-\x20]', path): raise ValueError('Некорректный путь LinkedIn.')
    if kind == 'profile':
        m = re.fullmatch(r'/in/([A-Za-z0-9_-]{1,150})(?:/(?:en|ru))?/?', path)
        if not m: raise ValueError('Нужна ссылка на собственный профиль /in/….')
        path = '/in/' + m[1] + '/'
    elif kind == 'job':
        m = re.fullmatch(r'/jobs/view/(?:[^/]+-)?(\d{1,25})/?', path)
        jid = m[1] if m else parse_qs(u.query).get('currentJobId', [''])[0]
        if not re.fullmatch(r'\d{1,25}', jid) or not path.startswith('/jobs/'):
            raise ValueError('Нужна ссылка на конкретную вакансию LinkedIn.')
        path = '/jobs/view/' + jid + '/'
    elif kind == 'thread' and not re.fullmatch(r'/messaging/thread/[A-Za-z0-9_-]{1,200}/?', path):
        raise ValueError('Нужна ссылка на выбранный диалог LinkedIn.')
    elif kind == 'any' and not re.match(r'^/(?:in|jobs|messaging|mynetwork)(?:/|$)', path):
        raise ValueError('Эта страница не относится к рабочему разделу LinkedIn.')
    return 'https://www.linkedin.com' + path


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
            state['profile_url'] = url
        if 'paused' in data:
            if type(data['paused']) is not bool: raise ValueError('Некорректное состояние паузы.')
            state['paused'] = data['paused']
        save_settings(db, state)
    return state


def source(archive):
    """Same reviewed intro as the public portfolio; all raw education sources stay local."""
    rid = archive.summary().get('primary_id')
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
    result = {'resume_id': rid, 'version_id': cv['version_id'], 'headline': payload['title'],
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
    db.execute("UPDATE browser_commands SET state=CASE WHEN kind IN ('linkedin.profile.fill','linkedin.profile.save','linkedin.network.execute') THEN 'uncertain' ELSE 'needs_input' END, result=? WHERE kind LIKE 'linkedin.%' AND state='running' AND updated<?",
               (canonical({'message': 'Связь с расширением прервалась. Проверьте страницу перед повтором.'}), time.time()-180))


def overview(archive):
    with archive.connect() as db:
        init(db); _expire(db); config = settings(db); account = config.get('profile_url', '')
        rows = db.execute("SELECT * FROM browser_commands WHERE kind LIKE 'linkedin.%' AND json_extract(payload,'$.account')=? ORDER BY created DESC LIMIT 100", (account,)).fetchall()
        commands = [{**dict(r), 'payload': json.loads(r['payload']), 'result': json.loads(r['result']) if r['result'] else None} for r in rows]
        records = {}
        for kind in ('jobs', 'threads', 'contacts'):
            records[kind] = []
            for r in db.execute('SELECT r.*, n.payload notes, n.revision FROM linkedin_records r LEFT JOIN linkedin_notes n ON n.account=r.account AND n.kind=r.kind AND n.id=r.id WHERE r.account=? AND r.kind=? ORDER BY r.updated DESC LIMIT 1000', (account, kind)):
                records[kind].append({**json.loads(r['payload']), 'notes': json.loads(r['notes']) if r['notes'] else {}, 'revision': r['revision'] or 0})
        recent = {}
        for kind in ('profile.read', 'profile.form', 'profile.fill', 'network.prepare'):
            r = db.execute('SELECT id FROM linkedin_snapshots WHERE account=? AND kind=? ORDER BY created DESC LIMIT 1', (account, kind)).fetchone()
            if r: recent[kind] = snapshot(db, r[0], account)
    return {'settings': config, 'connected': time.time()-config.get('last_seen', 0) < 100,
            'commands': commands, 'records': records, 'snapshots': recent, 'limit': 1000}


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
    elif action == 'jobs.detail': p['url'] = linkedin_url(data.get('url'), 'job')
    elif action == 'messages.thread': p['url'] = linkedin_url(data.get('url'), 'thread')
    elif action == 'messages.list': p['url'] = 'https://www.linkedin.com/messaging/'
    elif action == 'network.list':
        scope = data.get('scope', 'connections')
        paths = {'connections': '/mynetwork/invite-connect/connections/', 'received': '/mynetwork/invitation-manager/', 'sent': '/mynetwork/invitation-manager/sent/'}
        if scope not in paths: raise ValueError('Неизвестный список контактов.')
        p.update(url='https://www.linkedin.com'+paths[scope], scope=scope)
    elif action == 'profile.read': p['url'] = account
    elif action == 'profile.form': p['url'] = account  # Reads the editor already opened by the owner.
    elif action == 'network.prepare':
        p['url'] = linkedin_url(data.get('url'), 'profile')
        p['network_action'] = data.get('network_action')
        if p['network_action'] not in NETWORK_ACTIONS or p['url'] == account: raise ValueError('Выберите контакт и действие.')
    if action in ('jobs.list', 'network.list', 'messages.list'):
        limit = data.get('limit', 100)
        if type(limit) is not int or not 1 <= limit <= 300: raise ValueError('Лимит от 1 до 300 записей.')
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
            current = source(archive)
            if data.get('source_fingerprint') != current['fingerprint']: raise ValueError('Основное резюме или введение изменилось. Обновите сравнение.')
            if action == 'profile.save' and snap['payload'].get('source_fingerprint') != current['fingerprint']:
                raise ValueError('Источник изменился после переноса. Прочитайте форму и согласуйте поля заново.')
            p.update(snapshot=snap['payload'], source_fingerprint=current['fingerprint'])
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
        if settings(db).get('profile_url') != account: raise ValueError('Аккаунт изменился.')
        if action in WRITES:
            old = db.execute("SELECT id FROM browser_commands WHERE kind=? AND json_extract(payload,'$.snapshot_id')=?", ('linkedin.'+action, p['snapshot_id'])).fetchone()
        else:
            old = db.execute("SELECT id FROM browser_commands WHERE kind=? AND payload=? AND state IN ('queued','running')", ('linkedin.'+action, canonical(p))).fetchone()
        if old: return {'id': old[0], 'duplicate': True}
        ident = secrets.token_hex(12)
        db.execute('INSERT INTO browser_commands VALUES(?,?,?,?,?,?,?,?,?)', (ident, None, 'linkedin.'+action, canonical(p), 'queued', None, now, now, None))
    return {'id': ident}


def claim(archive, data):
    worker = text(data.get('worker_id'), 100)
    if not re.fullmatch(r'linkedin-[\w-]{8,80}', worker): raise ValueError('Неизвестный исполнитель.')
    with archive.connect() as db:
        init(db); db.execute('BEGIN IMMEDIATE'); _expire(db); config = settings(db)
        config.update(last_seen=time.time(), extension_version=text(data.get('version', ''), 30)); save_settings(db, config)
        if config.get('paused') or not config.get('profile_url'): return {'command': None}
        if db.execute("SELECT 1 FROM browser_commands WHERE kind LIKE 'linkedin.%' AND state='running'").fetchone(): return {'command': None}
        r = db.execute("SELECT * FROM browser_commands WHERE kind LIKE 'linkedin.%' AND state='queued' AND json_extract(payload,'$.account')=? ORDER BY created,id LIMIT 1", (config['profile_url'],)).fetchone()
        if not r: return {'command': None}
        params=json.loads(r['payload'])
        if r['kind'][9:] in WRITES:
            if params.get('expires',0)<time.time() or (r['kind'].startswith('linkedin.profile.') and source(archive)['fingerprint']!=params.get('source_fingerprint')):
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
        db.execute('UPDATE browser_commands SET updated=?,result=? WHERE id=?', (time.time(), canonical({'count':count, 'message':text(data.get('message',''),500)}),r['id']))
        return {'continue': not p.get('stop') and not settings(db).get('paused')}


def _record(db, account, kind, ident, payload):
    if not ident or len(ident)>250: raise ValueError('Некорректный идентификатор записи.')
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
        if partial and action not in ('jobs.list','messages.list','network.list'): raise ValueError('Эта операция не поддерживает порционный сбор.')
        summary = {'state':outcome['state'], 'message':text(outcome.get('message',''),2000)}
        payload = outcome.get('data', {})
        if not isinstance(payload,dict): raise ValueError('Нужен объект результата.')
        if action.startswith('profile.') or action == 'network.prepare':
            if outcome['state'] == 'completed' or action=='profile.read' and outcome['state']=='needs_input' and payload.get('sections'):
                if action=='profile.read' and linkedin_url(payload.get('url'),'profile')!=account:raise ValueError('Прочитан другой профиль.')
                if action in ('profile.form','profile.fill'):
                    fields = payload.get('fields', [])
                    if not isinstance(fields,list) or not 1<=len(fields)<=80 or not payload.get('form_fingerprint'): raise ValueError('Нет распознанной формы.')
                    if not linkedin_url(payload.get('url')).startswith(account): raise ValueError('Форма другого профиля.')
                if action == 'network.prepare':
                    if linkedin_url(payload.get('url')) != p['url'] or payload.get('action') != p['network_action'] or not payload.get('target_fingerprint'): raise ValueError('Контакт или действие не совпадает.')
                if action=='profile.fill': payload={**payload,'source_fingerprint':p['source_fingerprint']}
                summary['snapshot_id'] = _put_snapshot(db,account,action,payload)
        elif action in ('jobs.list','jobs.detail'):
            rows = payload.get('items', [])
            if not isinstance(rows,list) or len(rows)>300: raise ValueError('Слишком много вакансий.')
            accepted = 0
            for job in rows:
                link = linkedin_url(job.get('link'), 'job'); jid = 'linkedin_'+link.rstrip('/').split('/')[-1]
                if action == 'jobs.detail' and link != p['url']: raise ValueError('Открыта другая вакансия.')
                description = text(job.get('description',''),200000)
                full = action == 'jobs.detail' and job.get('description_quality') == 'full' and len(description)>=150
                vacancy = {'id':jid, 'title':text(job.get('title'),500), 'company':text(job.get('company',''),500), 'link':link,
                           'description':description, 'description_quality':'full' if full else 'snippet', 'location':text(job.get('location',''),500),
                           'locations':job.get('locations',[]), 'source':'linkedin', 'source_page':link if action=='jobs.detail' else p['url'], 'collected_at':now_iso(),
                           'adapter_id':'linkedin-session', 'adapter_version':'1', 'extraction_method':'visible_dom'}
                if not vacancy['title']: continue
                archive._entity(db,'vacancy',jid,vacancy,now_iso())
                # Re-read the protected archive head so a new listing cannot downgrade a complete JD.
                head=json.loads(db.execute("SELECT payload FROM entities WHERE kind='vacancy' AND id=?",(jid,)).fetchone()[0])
                prior=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='jobs' AND id=?",(account,jid)).fetchone()
                apply = json.loads(prior[0]).get('apply',{}) if prior else {}
                if action=='jobs.detail':
                    apply={'kind':job.get('apply',{}).get('kind','unknown'),'url':link}
                    candidate=job.get('apply',{}).get('url','')
                    u=urlsplit(candidate)
                    if apply['kind']=='external' and u.scheme=='https' and u.hostname and not u.username:
                        allowed={k:v[-1] for k,v in parse_qs(u.query).items() if k.lower() in ('id','jobid','job_id','gh_jid','rid','reqid')}
                        apply['url']=u._replace(query=urlencode(allowed),fragment='').geturl()
                    elif apply['kind'] not in ('easy_apply','external'): apply['kind']='unknown'
                _record(db,account,'jobs',jid,{**head,'apply':apply}); accepted+=1
            summary.update(count=accepted, coverage='partial', reason=text(payload.get('reason','Доступная часть выдачи'),500))
        elif action in ('messages.list','messages.thread','network.list'):
            kind='contacts' if action=='network.list' else 'threads'
            rows=payload.get('items',[])
            if not isinstance(rows,list) or len(rows)>300: raise ValueError('Слишком много записей.')
            for item in rows:
                url=linkedin_url(item.get('url'), 'profile' if kind=='contacts' else 'thread')
                record={'id':url,'url':url,'name':text(item.get('name',''),500), 'text':text(item.get('text',''),200000),
                        'observed_at':now_iso(),'scope':p.get('scope',''), 'coverage':'visible_only'}
                previous=db.execute('SELECT payload FROM linkedin_records WHERE account=? AND kind=? AND id=?',(account,kind,url)).fetchone()
                if previous and action=='messages.list': record['text']=json.loads(previous[0]).get('text',record['text'])
                if action=='messages.thread':
                    if url != p['url']: raise ValueError('Открыт другой диалог.')
                    record['vacancy_links']=sorted(set(linkedin_url(v,'job') for v in item.get('vacancy_links',[])[:100]))
                _record(db,account,kind,url,record)
            summary.update(count=len(rows),coverage='partial',reason=text(payload.get('reason','Доступная часть выдачи'),500))
        if partial:
            db.execute('UPDATE browser_commands SET updated=?,result=? WHERE id=?',(time.time(),canonical(summary),r['id']))
            return {'ok':True,'continue':not p.get('stop') and not settings(db).get('paused')}
        db.execute('INSERT INTO linkedin_receipts VALUES(?,?,?)',(r['id'],digest(outcome),canonical(summary)))
        db.execute('UPDATE browser_commands SET state=?,updated=?,result=? WHERE id=?',(outcome['state'],time.time(),canonical(summary),r['id']))
    return {'ok':True, **summary}


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
