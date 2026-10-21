"""Reviewed document imports reuse extraction, browser queue and ArchiveStore snapshots."""
import base64
import binascii
import json
import re
import secrets
import time
from urllib.parse import urlsplit
from .resume_files import extract_resume, redact_contacts, MAX_FILE, MAX_TEXT
from .resume_source import content_hash
from .archive_store import now_iso, canonical

PREFIX='resume-document-preview:'
TTL=3600

def google_target(value):
    try:
        u=urlsplit(str(value).strip());m=re.fullmatch(r'/document/d/([A-Za-z0-9_-]{10,200})(?:/(?:edit|view|preview))?/?',u.path)
        if u.scheme!='https' or u.hostname!='docs.google.com' or u.username or u.password or u.port not in (None,443) or not m:raise ValueError()
        return {'resume_id':'gdoc_'+m[1],'url':'https://docs.google.com/document/d/'+m[1]+'/edit'}
    except (ValueError,TypeError):raise ValueError('Нужна прямая ссылка https://docs.google.com/document/d/…/edit.') from None

def preview(archive,candidate,key=None):
    text=candidate.get('text','')
    if not isinstance(text,str) or not 100<=len(text)<=MAX_TEXT:raise ValueError('Проверьте полный текст документа: от 100 до 250 000 символов.')
    candidate={**candidate,'text':redact_contacts(text)};key=key or secrets.token_hex(20)
    with archive.connect() as db:
        db.execute('DELETE FROM archive_meta WHERE key LIKE ? AND CAST(json_extract(value,\'$.expires\') AS REAL)<?',(PREFIX+'%',time.time()))
        old=db.execute('SELECT value FROM archive_meta WHERE key=?',(PREFIX+key,)).fetchone()
        if old:return json.loads(old[0])
        count=db.execute('SELECT COUNT(*) FROM archive_meta WHERE key LIKE ? AND json_extract(value,\'$.saved\') IS NULL',(PREFIX+'%',)).fetchone()[0]
        if count>=20:raise ValueError('Слишком много непроверенных документов. Сохраните текущий текст или дождитесь истечения часа.')
        result={'preview_id':key,'candidate':candidate,'expires':time.time()+TTL,'api_requests':0}
        db.execute('INSERT INTO archive_meta VALUES(?,?)',(PREFIX+key,canonical(result)))
    return result

def extract(archive,data):
    encoded=data.get('content_base64');filename=data.get('filename')
    if not isinstance(encoded,str) or len(encoded)>MAX_FILE*4//3+4 or not isinstance(filename,str) or len(filename)>300:raise ValueError('Нужен файл до 12 МБ и его имя.')
    try:content=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise ValueError('Файл повреждён при передаче.') from None
    return preview(archive,extract_resume(content,filename))

def google_start(store,url):
    target=google_target(url)
    return {**target,'command_id':store.queue_command('resume_import',payload={'resume_id':target['resume_id']}),'api_requests':0}

def google_status(store,archive,command_id):
    with store.connect() as db:row=db.execute("SELECT state,result,payload FROM browser_commands WHERE id=? AND kind='resume_import'",(command_id,)).fetchone()
    if not row:raise ValueError('Чтение Google Docs не найдено.')
    rid=json.loads(row['payload']).get('resume_id','')
    if not rid.startswith('gdoc_'):raise ValueError('Это задача другого источника.')
    result=json.loads(row['result'] or '{}');out={'state':row['state'],'note':result.get('note',''),'api_requests':0}
    if row['state']=='complete':
        candidate=result.get('candidate')
        if not isinstance(candidate,dict):raise ValueError('Расширение не передало текст документа. Обновите расширение и повторите чтение.')
        source=google_target(candidate.get('source_url',''))
        if source['resume_id']!=rid or candidate.get('id')!=rid:raise ValueError('Прочитан другой документ; сохранение остановлено.')
        allowed={'id','source_url','title','text','captured_at','extraction_method','warnings'}
        candidate={k:v for k,v in candidate.items() if k in allowed};candidate['source_type']='google_docs'
        out.update(preview(archive,candidate,'google-'+command_id))
    return out

def save(archive,data):
    key=data.get('preview_id','')
    if not isinstance(key,str) or not re.fullmatch(r'(?:[a-f0-9]{40}|google-[a-f0-9]{24})',key):raise ValueError('Предпросмотр не найден.')
    if data.get('confirmed') is not True:raise ValueError('Проверьте текст и подтвердите полноту документа.')
    title=data.get('title');text=data.get('text')
    if not isinstance(title,str) or not 1<=len(title.strip())<=300 or not isinstance(text,str) or not 100<=len(text.strip())<=MAX_TEXT:raise ValueError('Нужны название и полный проверенный текст резюме.')
    title=redact_contacts(title.strip());text=redact_contacts(text.strip());now=now_iso()
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT value FROM archive_meta WHERE key=?',(PREFIX+key,)).fetchone()
        if not row:raise ValueError('Предпросмотр истёк. Прочитайте документ заново.')
        draft=json.loads(row[0]);candidate=draft['candidate']
        requested=content_hash({'title':title,'sections':[{'key':'document','heading':'Резюме','text':text}]})
        if draft.get('saved'):
            if draft['saved']['content_hash']!=requested:raise ValueError('Этот предпросмотр уже сохранён. Для новой редакции прочитайте источник заново.')
            return draft['saved']
        if draft['expires']<time.time():raise ValueError('Предпросмотр истёк. Прочитайте документ заново.')
        allowed={'id','source_type','source_url','file_hash','filename','captured_at','extraction_method','warnings'}
        cv={k:v for k,v in candidate.items() if k in allowed}
        cv.update(title=title,sections=[{'key':'document','heading':'Резюме','text':text}],quality='full',checked_at=candidate.get('captured_at') or now,captured_at=candidate.get('captured_at') or now,reviewed_at=now,content_hash=requested)
        archive._entity(db,'resume',cv['id'],cv,now)
        saved={'resume_id':cv['id'],'content_hash':requested,'api_requests':0,'note':'Проверенное резюме сохранено. Основное CV не изменено.'}
        draft['saved']=saved;db.execute('UPDATE archive_meta SET value=? WHERE key=?',(canonical(draft),PREFIX+key))
    return saved
