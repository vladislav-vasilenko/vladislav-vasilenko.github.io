"""Local source archive. Search absence is evidence of absence in one scope, never closure."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
from .resume_files import redact_contacts
from .board_import import identity
from .analysis_store import AnalysisStore

FIELDS={
 'resume':('id','title','source_type','source_url','quality','sections','content_hash','file_hash','filename','captured_at','checked_at','reviewed_at','changed_at','extraction_method','warnings'),
 'vacancy':('id','title','company','link','source','source_page','search_page','origin_query','description','description_quality','locations','location','city','pub_date','collected_at','last_seen_at','first_seen','reviewed_at','review_method','recommended_for','archived','availability_checked_at','listing_verified_at','description_fetched_at','description_dirty','listing_changed_at','listing_snapshot','collector','board_id','adapter_id','adapter_version','extraction_method'),
 'scan':('id','scan_kind','scope_url','started_at','completed_at','ids','listing_complete','state','pages','start_page','error'),
 'profile':('primary_id','goal'),
 'ranking':('generated_at','model','resume_id','resume_title','resume_hash','input_count','ranked_count','excluded','goal','method','score_warning','usage_tokens','api_requests','company_filter','companies_filter','cache_reused','new_compared','cached','requested_count','processed_count','batches_completed','partial','all'),
}
def canonical(data):return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(data):return hashlib.sha256(canonical(data).encode()).hexdigest()
def now_iso():return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def source_time(data,kind,received):
    keys=('checked_at','captured_at','reviewed_at') if kind=='resume' else ('collected_at',)
    values=[]
    for key in keys:
        try:
            value=datetime.fromisoformat(str(data.get(key,'')).replace('Z','+00:00'))
            if value.tzinfo and value.timestamp()<=datetime.now(timezone.utc).timestamp()+300:values.append(value.astimezone(timezone.utc).isoformat(timespec='microseconds'))
        except ValueError:pass
    return max(values) if values else received
def text_of(kind,data):
    if kind=='resume':return data.get('title','')+'\n\n'+'\n\n'.join(str(s.get('heading',''))+'\n'+str(s.get('text','')) for s in data.get('sections',[]))
    return '\n\n'.join(str(data.get(k,'') or '') for k in ('title','company','description'))
def scope_url(value,kind):
    u=urlsplit(value)
    expected='/applicant/profile/me' if kind=='resume_catalog' else '/search/vacancy'
    if u.scheme!='https' or u.netloc!='hh.ru' or u.path.rstrip('/')!=expected:raise ValueError('Нужен подтверждённый источник HH.')
    pairs=sorted((k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if k not in {'page','from','hhtmFrom','hhtmFromLabel','search_session_id'})
    return urlunsplit(('https','hh.ru',expected,urlencode(pairs),''))

class ArchiveStore(AnalysisStore):
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);os.chmod(self.path.parent,0o700)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS entities(kind TEXT,id TEXT,title TEXT,company TEXT DEFAULT '',payload TEXT,version_id INTEGER,content_hash TEXT,source_at TEXT,first_seen TEXT,last_seen TEXT,availability TEXT DEFAULT 'unknown',PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,entity_id TEXT,content_hash TEXT,payload TEXT,received_at TEXT,source_at TEXT);
            CREATE INDEX IF NOT EXISTS versions_entity ON versions(kind,entity_id,id);
            CREATE TABLE IF NOT EXISTS receipts(client_id TEXT,kind TEXT,id TEXT,digest TEXT,PRIMARY KEY(client_id,kind,id));
            CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY,client_id TEXT,kind TEXT,scope TEXT,completed_at TEXT,complete INTEGER,payload TEXT);
            CREATE INDEX IF NOT EXISTS scans_scope ON scans(client_id,kind,scope,completed_at);
            CREATE TABLE IF NOT EXISTS membership(client_id TEXT,scope TEXT,kind TEXT,entity_id TEXT,present INTEGER,checked_at TEXT,scan_id TEXT,PRIMARY KEY(client_id,scope,kind,entity_id));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,entity_id TEXT,event TEXT,at TEXT,details TEXT);
            CREATE TABLE IF NOT EXISTS profiles(client_id TEXT PRIMARY KEY,payload TEXT,received_at TEXT);
            ''')
            self.init_analysis(db)
        os.chmod(self.path,0o600)
    def connect(self):
        db=sqlite3.connect(self.path,timeout=20);db.row_factory=sqlite3.Row;return db
    @staticmethod
    def client(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',value):raise ValueError('Некорректный идентификатор расширения.')
        return value
    def manifest(self,client):
        self.client(client)
        with self.connect() as db:rows=db.execute('SELECT kind,id,digest FROM receipts WHERE client_id=?',(client,)).fetchall()
        return {'records':{r['kind']+':'+r['id']:r['digest'] for r in rows}}
    def sync(self,payload):
        client=self.client(payload.get('client_id'));records=payload.get('records')
        if not isinstance(records,list) or len(records)>100:raise ValueError('Пакет должен содержать до 100 записей.')
        accepted=[];rejected=[];received=now_iso()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for record in records:
                try:
                    db.execute('SAVEPOINT record')
                    kind=record.get('kind');data=record.get('data');identifier=record.get('id')
                    if kind not in FIELDS or not isinstance(data,dict) or not isinstance(identifier,str) or not 1<=len(identifier)<=180:raise ValueError('Некорректная запись архива.')
                    if set(data)-set(FIELDS[kind]):raise ValueError('Запись содержит неизвестные служебные поля.')
                    checksum=digest(data)
                    if record.get('digest')!=checksum:raise ValueError('Контрольная сумма не совпадает.')
                    previous=db.execute('SELECT digest FROM receipts WHERE client_id=? AND kind=? AND id=?',(client,kind,identifier)).fetchone()
                    if not previous or previous[0]!=checksum:
                        if kind in ('resume','vacancy'):self._entity(db,kind,identifier,data,received)
                        elif kind=='scan':self._scan(db,client,identifier,data,received)
                        elif kind=='ranking':self._ranking(db,data)
                        else:
                            if identifier!='profile' or len(str(data.get('goal','')))>2000:raise ValueError('Некорректный профиль поиска.')
                            db.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?)',(client,canonical(data),received))
                            db.execute("INSERT OR IGNORE INTO archive_meta VALUES('initial_import_until',?)",(received,))
                        db.execute('INSERT OR REPLACE INTO receipts VALUES(?,?,?,?)',(client,kind,identifier,checksum))
                    db.execute('RELEASE record');accepted.append({'kind':kind,'id':identifier,'digest':checksum})
                except (ValueError,TypeError,KeyError,AttributeError) as error:
                    db.execute('ROLLBACK TO record');db.execute('RELEASE record')
                    rejected.append({'kind':str(record.get('kind',''))[:30] if isinstance(record,dict) else '', 'id':str(record.get('id',''))[:180] if isinstance(record,dict) else '', 'error':str(error)})
        return {'accepted':accepted,'rejected':rejected,'synced_at':received}
    @staticmethod
    def _event(db,kind,identifier,event,at,details):
        db.execute('INSERT INTO events(kind,entity_id,event,at,details) VALUES(?,?,?,?,?)',(kind,identifier,event,at,canonical(details)))
    def _entity(self,db,kind,identifier,data,received):
        if data.get('id')!=identifier or not isinstance(data.get('title'),str) or not data['title'].strip():raise ValueError('Нужны ID и название.')
        if len(canonical(data))>600000:raise ValueError('Запись слишком велика.')
        data=json.loads(canonical(data))
        if kind=='resume':
            if not re.fullmatch(r'(?:[a-fA-F0-9]{32,64}|file_[a-f0-9]{64}|gdoc_[A-Za-z0-9_-]+)',identifier):raise ValueError('Некорректный ID резюме.')
            if not isinstance(data.get('sections'),list) or not data['sections']:raise ValueError('Нет профессионального текста CV.')
            if data.get('quality') not in ('full','unavailable','needs_review'):raise ValueError('Неизвестное качество CV.')
            data['sections']=[{'key':str(s.get('key','document')),'heading':redact_contacts(str(s.get('heading',''))),'text':redact_contacts(str(s.get('text','')))} for s in data['sections'] if isinstance(s,dict) and s.get('key') not in ('contacts','contact','personal')]
        else:
            valid=identity(data.get('link',''))
            if not valid or valid['id']!=identifier:raise ValueError('ID вакансии не соответствует её ссылке.')
            if data.get('description_quality') not in ('full','snippet','missing','needs_review'):raise ValueError('Неизвестное качество вакансии.')
            if not isinstance(data.get('description',''),str):raise ValueError('Описание должно быть текстом.')
            data['description']=redact_contacts(data.get('description',''))
        old=db.execute('SELECT * FROM entities WHERE kind=? AND id=?',(kind,identifier)).fetchone()
        stamp=source_time(data,kind,received)
        if old and stamp<old['source_at']:
            # Delayed offline uploads can fill history but never replace a newer head.
            historic=digest(self._content(kind,data))
            if data.get('quality',data.get('description_quality'))=='full' and not db.execute('SELECT 1 FROM versions WHERE kind=? AND entity_id=? AND content_hash=?',(kind,identifier,historic)).fetchone():
                db.execute('INSERT INTO versions(kind,entity_id,content_hash,payload,received_at,source_at) VALUES(?,?,?,?,?,?)',(kind,identifier,historic,canonical(data),received,stamp))
            return
        availability=old['availability'] if old else 'unknown'
        if kind=='vacancy':
            explicit=source_url_is_detail(data.get('source_page',''),identifier)
            if explicit and type(data.get('archived')) is bool and (data['archived'] or data.get('description_quality')=='full'):
                availability='closed' if data['archived'] else 'active'
            if old:
                prior=json.loads(old['payload'])
                if prior.get('description_quality')=='full' and data.get('description_quality')!='full':
                    data={**prior,**data,'description':prior['description'],'description_quality':'full','title':prior['title'],'company':prior.get('company','')}
                data['recommended_for']=sorted(set(prior.get('recommended_for',[])+data.get('recommended_for',[])))
            # A search card cannot reopen a position confirmed archived on its detail page.
            if availability=='closed':data['archived']=True
            elif availability=='active':data['archived']=False
        elif old and data.get('quality')!='full':
            prior=json.loads(old['payload']);data={**data,'sections':prior['sections'],'title':prior['title']}
        content=digest(self._content(kind,data));version=old['version_id'] if old else None
        if not old or old['content_hash']!=content:
            cursor=db.execute('INSERT INTO versions(kind,entity_id,content_hash,payload,received_at,source_at) VALUES(?,?,?,?,?,?)',(kind,identifier,content,canonical(data),received,stamp));version=cursor.lastrowid
            self._event(db,kind,identifier,'added' if not old else 'changed',received,{'before_version':old['version_id'] if old else None,'after_version':version})
        if old and availability!=old['availability']:
            self._event(db,kind,identifier,'closed' if availability=='closed' else 'reopened',received,{'source_url':data.get('source_page'),'observed_at':data.get('collected_at')})
        elif not old and availability=='closed':self._event(db,kind,identifier,'closed',received,{'source_url':data.get('source_page'),'observed_at':data.get('collected_at')})
        db.execute('INSERT OR REPLACE INTO entities VALUES(?,?,?,?,?,?,?,?,?,?,?)',(kind,identifier,data['title'],str(data.get('company','')),canonical(data),version,content,stamp,old['first_seen'] if old else received,received,availability))
    @staticmethod
    def _content(kind,data):
        normalize=lambda value:' '.join(str(value or '').split())
        if kind=='resume':return {'title':normalize(data['title']),'sections':[{k:normalize(s.get(k)) for k in ('key','heading','text')} for s in data.get('sections',[])]}
        return {k:normalize(data.get(k)) if k!='locations' else data.get(k) for k in ('title','company','description','description_quality','locations','location','city')}
    def _scan(self,db,client,identifier,data,received):
        scan_kind=data.get('scan_kind');kind='resume' if scan_kind=='resume_catalog' else 'vacancy'
        if scan_kind not in ('resume_catalog','vacancy_search') or data.get('id')!=identifier:raise ValueError('Неизвестный тип наблюдения.')
        scope=scope_url(data.get('scope_url',''),scan_kind);ids=data.get('ids',[])
        if not isinstance(ids,list) or len(ids)>20000 or any(not isinstance(i,str) or len(i)>180 for i in ids):raise ValueError('Некорректные ID наблюдения.')
        end=data.get('completed_at') or received
        try:
            parsed=datetime.fromisoformat(end.replace('Z','+00:00'))
            if not parsed.tzinfo:raise ValueError()
            end=parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
        except (ValueError,AttributeError):raise ValueError('Некорректное время наблюдения.') from None
        complete=data.get('listing_complete') is True and data.get('start_page',0)==0 and data.get('state') not in ('failed','stopped','running')
        # Immutable run identity makes a retried upload idempotent.
        previous=db.execute('SELECT client_id,payload FROM scans WHERE id=?',(identifier,)).fetchone()
        if previous:
            if previous['client_id']!=client or json.loads(previous['payload'])!=data:raise ValueError('Нельзя изменить уже сохранённое наблюдение.')
            return
        db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?)',(identifier,client,kind,scope,end,int(complete),canonical(data)))
        existing={r['entity_id']:r for r in db.execute('SELECT * FROM membership WHERE client_id=? AND scope=? AND kind=?',(client,scope,kind))}
        observed=set(ids)
        for key in observed | (set(existing) if complete else set()):
            prior=existing.get(key)
            if prior and prior['checked_at']>end:continue
            present=key in observed
            if prior and bool(prior['present'])!=present:
                self._event(db,kind,key,'returned' if present else 'missing',end,{'scope':scope,'scan_id':identifier,'previous_scan':prior['scan_id'],'coverage':'complete' if complete else 'partial'})
            db.execute('INSERT OR REPLACE INTO membership VALUES(?,?,?,?,?,?,?)',(client,scope,kind,key,int(present),end,identifier))
    def summary(self):
        with self.connect() as db:
            counts={r['kind']:r['n'] for r in db.execute('SELECT kind,COUNT(*) n FROM entities GROUP BY kind')}
            full=db.execute("SELECT COUNT(*) FROM entities WHERE kind='vacancy' AND json_extract(payload,'$.description_quality')='full'").fetchone()[0]
            closed=db.execute("SELECT COUNT(*) FROM entities WHERE kind='vacancy' AND availability='closed'").fetchone()[0]
            missing=db.execute('SELECT COUNT(DISTINCT kind||entity_id) FROM membership WHERE present=0').fetchone()[0]
            versions=db.execute('SELECT COUNT(*) FROM versions').fetchone()[0];scans=db.execute('SELECT COUNT(*) FROM scans').fetchone()[0]
            last=db.execute('SELECT MAX(last_seen) FROM entities').fetchone()[0]
            profile=db.execute('SELECT payload FROM profiles ORDER BY received_at DESC LIMIT 1').fetchone()
        profile=json.loads(profile[0]) if profile else {}
        return {'resumes':counts.get('resume',0),'vacancies':counts.get('vacancy',0),'full_descriptions':full,'closed':closed,'missing_in_search':missing,'versions':versions,'scans':scans,'last_sync':last,'primary_id':profile.get('primary_id'),'goal':profile.get('goal','')}
    def entities(self,kind,*,q='',status='',offset=0,limit=50,resume_id='',goal=None,model='text-embedding-3-small',company='',companies=None,ranked_only=False,exclude_closed=False,all_items=False,include_payload=False,trajectory=''):
        if kind not in ('resume','vacancy'):raise ValueError('Неизвестный раздел.')
        where=['e.kind=?'];args=[kind]
        if q:
            body="json_extract(e.payload,'$.sections')" if kind=='resume' else "json_extract(e.payload,'$.description')"
            where.append('(e.title LIKE ? OR e.company LIKE ? OR '+body+' LIKE ?)');args.extend(['%'+q[:200]+'%']*3)
        if status in ('active','closed','unknown'):where.append('e.availability=?');args.append(status)
        if exclude_closed and kind=='vacancy':where.append("e.availability<>'closed'")
        if status=='missing':where.append('EXISTS(SELECT 1 FROM membership m WHERE m.kind=e.kind AND m.entity_id=e.id AND m.present=0)')
        if status=='full':where.append("json_extract(e.payload,'$.description_quality')='full'")
        if status=='needs_review':where.append("json_extract(e.payload,'$.description_quality')='needs_review'")
        clause=' AND '.join(where)
        with self.connect() as db:
            rows=db.execute('SELECT e.*,(SELECT COUNT(*) FROM versions v WHERE v.kind=e.kind AND v.entity_id=e.id) versions,(SELECT COUNT(*) FROM membership m WHERE m.kind=e.kind AND m.entity_id=e.id AND m.present=0) missing_scopes,json_extract(e.payload,\'$.description_quality\') quality FROM entities e WHERE '+clause+' ORDER BY e.last_seen DESC,e.id',args).fetchall()
            items=[dict(r) for r in rows]
            from .company_catalog import selection,raw_catalog
            selected=selection(companies,company)
            if selected is not None and kind=='vacancy':
                from .company_filter import company_key
                catalog=raw_catalog(self);allowed=set(selected)
                items=[r for r in items if company_key(r['company'],catalog) in allowed]
            self.analysis_states(db,items,resume_id,goal,model)
            if ranked_only:items=[r for r in items if r['ranking']]
            if status.startswith('embedding_'):items=[r for r in items if r['embedding']['status']==status.removeprefix('embedding_')]
            if kind=='vacancy' and resume_id:items.sort(key=lambda r:-(r['ranking']['score'] if r['ranking'] else -2))
            route_rows=[]
            if kind=='vacancy':
                from .career_trajectory_matching import paths,relations,accepts
                route_rows=paths(self)
                if trajectory and trajectory not in ('unassigned','intersection','needs_description') and trajectory not in {r['id'] for r in route_rows}:raise ValueError('Траектория не найдена.')
                if trajectory:
                    for item in items:item['trajectory']=relations(self,json.loads(item['payload']),route_rows)
                    items=[item for item in items if accepts(trajectory,item['trajectory'])]
            total=len(items)
            if not all_items:items=items[max(offset,0):max(offset,0)+min(max(limit,1),200)]
            for item in items:
                payload=item.pop('payload',None)
                if kind=='vacancy' and 'trajectory' not in item:item['trajectory']=relations(self,json.loads(payload),route_rows)
                if include_payload:item['payload']=json.loads(payload)
            if kind=='vacancy' and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='applications'").fetchone():
                queued={}
                for application in db.execute("SELECT id,status,context FROM applications ORDER BY created DESC"):
                    context=json.loads(application['context']);job_id=context.get('vacancy',{}).get('id')
                    if job_id not in queued:queued[job_id]={'id':application['id'],'status':application['status'],'channel':context.get('channel')}
                for item in items:item['application']=queued.get(item['id'])
        return {'total':total,'items':items,'trajectory_options':[{'id':r['id'],'label':r['label']} for r in route_rows]}
    def detail(self,kind,identifier,resume_id='',goal=None,model='text-embedding-3-small'):
        with self.connect() as db:
            row=db.execute('SELECT * FROM entities WHERE kind=? AND id=?',(kind,identifier)).fetchone()
            if not row:raise ValueError('Запись не найдена.')
            versions=db.execute('SELECT id,content_hash,received_at,source_at FROM versions WHERE kind=? AND entity_id=? ORDER BY source_at DESC,id DESC',(kind,identifier)).fetchall()
            membership=db.execute('SELECT * FROM membership WHERE kind=? AND entity_id=? ORDER BY checked_at DESC',(kind,identifier)).fetchall()
            state=self.analysis_states(db,[dict(row)],resume_id,goal,model)[0]
        result={**state,'payload':json.loads(row['payload']),'text':text_of(kind,json.loads(row['payload'])),'versions':[dict(r) for r in versions],'membership':[dict(r) for r in membership]}
        if kind=='vacancy':
            from .career_trajectory_matching import relations
            result['trajectory']=relations(self,result['payload'])
        return result
    def resume_snapshot(self,identifier,version_id):
        with self.connect() as db:
            row=db.execute("SELECT * FROM versions WHERE kind='resume' AND entity_id=? AND id=?",(identifier,version_id)).fetchone()
            if not row:raise ValueError('Снимок не принадлежит выбранному резюме.')
            current=db.execute("SELECT version_id FROM entities WHERE kind='resume' AND id=?",(identifier,)).fetchone()
        data=json.loads(row['payload'])
        return {'id':identifier,'title':data['title'],'payload':data,'text':text_of('resume',data),'version_id':row['id'],'content_hash':row['content_hash'],'source_at':row['source_at'],'received_at':row['received_at'],'current_version_id':current[0] if current else None,'api_requests':0}
    def diff(self,kind,identifier,before,after):
        with self.connect() as db:
            rows=db.execute('SELECT * FROM versions WHERE kind=? AND entity_id=? AND id IN (?,?)',(kind,identifier,before,after)).fetchall()
        versions={r['id']:r for r in rows}
        if before not in versions or after not in versions:raise ValueError('Выберите две версии этой записи.')
        left=text_of(kind,json.loads(versions[before]['payload']));right=text_of(kind,json.loads(versions[after]['payload']))
        # Word-level segments preserve complete source text while showing edits in long HH paragraphs.
        a=re.findall(r'\S+\s*|\s+',left);b=re.findall(r'\S+\s*|\s+',right)
        if len(a)+len(b)>50000:return {'before':before,'after':after,'segments':[{'type':'delete','text':left},{'type':'insert','text':right}],'large_document':True}
        segments=[]
        for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=len(a)+len(b)>10000).get_opcodes():
            if tag=='equal':segments.append({'type':'equal','text':''.join(b[k:l])})
            else:
                if i!=j:segments.append({'type':'delete','text':''.join(a[i:j])})
                if k!=l:segments.append({'type':'insert','text':''.join(b[k:l])})
        return {'before':before,'after':after,'segments':segments,'large_document':False}
    def timeline(self,offset=0,limit=100):
        with self.connect() as db:
            rows=db.execute("SELECT ev.*,e.title,e.company FROM events ev LEFT JOIN entities e ON e.kind=ev.kind AND e.id=ev.entity_id WHERE ev.event!='added' OR ev.at>COALESCE((SELECT value FROM archive_meta WHERE key='initial_import_until'),'') ORDER BY ev.at DESC,ev.id DESC LIMIT ? OFFSET ?",(min(max(limit,1),200),max(offset,0))).fetchall()
        return {'items':[{**dict(r),'details':json.loads(r['details'])} for r in rows]}
    def scans(self,offset=0):
        with self.connect() as db:rows=db.execute('SELECT * FROM scans ORDER BY completed_at DESC LIMIT 100 OFFSET ?',(max(offset,0),)).fetchall()
        return {'items':[{**dict(r),'payload':json.loads(r['payload'])} for r in rows]}
    def restore(self):
        with self.connect() as db:
            rows=db.execute('SELECT kind,payload FROM entities').fetchall();profile=db.execute('SELECT payload FROM profiles ORDER BY received_at DESC LIMIT 1').fetchone()
        profile=json.loads(profile[0]) if profile else {}
        rankings=self.ranking_history()['items']
        return {'resume_bundle':{'schema_version':2,'primary_id':profile.get('primary_id'),'resumes':[json.loads(r['payload']) for r in rows if r['kind']=='resume']},'vacancies':[json.loads(r['payload']) for r in rows if r['kind']=='vacancy'],'ranking_goal':profile.get('goal',''),'last_ranking':{**rankings[0],'top':rankings[0]['all'][:10]} if rankings else None}
    def compare(self,resume_id,vacancy_id):
        cv=self.detail('resume',resume_id);job=self.detail('vacancy',vacancy_id)
        if job['payload'].get('description_quality')!='full':raise ValueError('Сначала загрузите полное проверенное описание вакансии через расширение.')
        skills={'PyTorch':r'\bpytorch\b','Python':r'\bpython\b','Transformer':r'transformers?','Diffusion':r'diffusion|диффуз','Flow Matching':r'flow[ -]?matching','DiT':r'\bdit\b|diffusion transformer','LLM':r'\bllms?\b|языков\w* модел','SFT':r'\bsft\b|supervised fine.tun','RLHF':r'\brlhf\b','DPO':r'\bdpo\b','CUDA':r'\bcuda\b','Triton':r'\btriton\b','DDP':r'\bddp\b','FSDP':r'\bfsdp\b','DeepSpeed':r'deepspeed','NLP':r'\bnlp\b','Computer Vision':r'computer vision|компьютерн\w* зрени|\bcv[- ](?:engineer|инженер)','Docker':r'\bdocker\b','Kubernetes':r'kubernetes|\bk8s\b','C++':r'c\+\+','Математика':r'математ|линейн\w* алгебр|теори\w* вероятност|оптимизаци'}
        items=[]
        for name,pattern in skills.items():
            jd=re.search(pattern,job['text'],re.I)
            if not jd:continue
            match=re.search(pattern,cv['text'],re.I)
            items.append({'skill':name,'mentioned_in_cv':bool(match),'cv_excerpt':cv['text'][max(0,match.start()-130):match.end()+220] if match else '', 'vacancy_excerpt':job['text'][max(0,jd.start()-100):jd.end()+200]})
        return {'resume_id':resume_id,'vacancy_id':vacancy_id,'items':items,'note':'Локальные текстовые совпадения. Упоминание не доказывает владение навыком; отсутствие слова не доказывает отсутствие опыта. Генеративная модель и API не вызываются.'}
    def confirm_description(self,identifier,content_hash):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT payload,content_hash FROM entities WHERE kind='vacancy' AND id=?",(identifier,)).fetchone()
            if not row or row['content_hash']!=content_hash:raise ValueError('Текст изменился. Откройте текущую версию и проверьте её заново.')
            data=json.loads(row['payload'])
            if data.get('description_quality')!='needs_review' or len(data.get('description',''))<150:raise ValueError('Подтверждать можно только извлечённое описание, требующее проверки.')
            self._entity(db,'vacancy',identifier,{**data,'description_quality':'full','reviewed_at':now_iso(),'review_method':'user_confirmed_archive'},now_iso())
        return {'ok':True}

def source_url_is_detail(value,identifier):
    try:
        u=urlsplit(value)
        if u.scheme!='https' or u.username or u.password:return False
        if identifier.startswith('hh_'):return u.hostname=='hh.ru' and u.path.rstrip('/')=='/vacancy/'+identifier.removeprefix('hh_')
        from .career_questionnaires import HOSTS
        if u.netloc not in set().union(*HOSTS.values()):return False
        detail=identity(value);return bool(detail and detail['id']==identifier and not identifier.startswith('board_'))
    except (TypeError,ValueError):return False
