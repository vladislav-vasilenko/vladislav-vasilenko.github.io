"""Content-addressed local vectors and version-bound ranking history; no network calls."""
import hashlib
import json
import math
import struct
from pathlib import Path
from datetime import datetime, timezone
from .resume_source import normalize, matching_text

def stamp():return datetime.now(timezone.utc).isoformat()
def text_hash(text):return hashlib.sha256(normalize(text).encode()).hexdigest()
def document_text(kind,data):
    return matching_text(data) if kind=='resume' else data['title']+'\n'+data.get('description','')

class AnalysisStore:
    def init_analysis(self,db):
        db.executescript('''
        CREATE TABLE IF NOT EXISTS embedding_vectors(key TEXT PRIMARY KEY,namespace TEXT,model TEXT,dimensions INTEGER,text_hash TEXT,vector BLOB,created_at TEXT);
        CREATE TABLE IF NOT EXISTS document_embeddings(kind TEXT,entity_id TEXT,document_hash TEXT,model TEXT,namespace TEXT,chunk_index INTEGER,embedding_key TEXT,PRIMARY KEY(kind,entity_id,document_hash,namespace,chunk_index));
        CREATE INDEX IF NOT EXISTS document_embedding_lookup ON document_embeddings(kind,entity_id,document_hash,model);
        CREATE TABLE IF NOT EXISTS ranking_runs(id TEXT PRIMARY KEY,resume_id TEXT,model TEXT,generated_at TEXT,payload TEXT);
        CREATE INDEX IF NOT EXISTS rankings_resume ON ranking_runs(resume_id,generated_at DESC);
        CREATE TABLE IF NOT EXISTS archive_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS skill_analysis_failures(key TEXT PRIMARY KEY,payload TEXT,error TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS external_analysis_requests(id TEXT PRIMARY KEY,context TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS skill_analyses(key TEXT PRIMARY KEY,resume_id TEXT,vacancy_id TEXT,resume_hash TEXT,vacancy_hash TEXT,goal TEXT,model TEXT,created_at TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS skill_analysis_sources(key TEXT PRIMARY KEY,resume_version_id INTEGER,vacancy_version_id INTEGER,resume_text TEXT,vacancy_text TEXT);
        CREATE INDEX IF NOT EXISTS skill_analyses_pair ON skill_analyses(resume_id,vacancy_id,created_at DESC);
        ''')
        first=db.execute('SELECT MIN(received_at) FROM profiles').fetchone()[0]
        if first:db.execute("INSERT OR IGNORE INTO archive_meta VALUES('initial_import_until',?)",(first,))

    def vector(self,key):
        with self.connect() as db:row=db.execute('SELECT dimensions,vector FROM embedding_vectors WHERE key=?',(key,)).fetchone()
        if not row:return None
        try:return list(struct.unpack('<'+'f'*row['dimensions'],row['vector']))
        except struct.error:return None

    def save_vector(self,key,namespace,text,vector):
        info=json.loads(namespace);dimensions=info.get('dimensions')
        if not isinstance(vector,list) or not vector or len(vector)>10000 or (dimensions and len(vector)!=dimensions) or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in vector) or not any(vector):
            raise ValueError('Некорректный embedding в локальном кэше.')
        packed=struct.pack('<'+'f'*len(vector),*vector)
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO embedding_vectors VALUES(?,?,?,?,?,?,?)',(key,namespace,info.get('model'),len(vector),text_hash(text),packed,stamp()))

    def bind_document(self,kind,identifier,text,cache,texts):
        with self.connect() as db:
            for index,key in enumerate(cache.keys(texts)):
                if db.execute('SELECT 1 FROM embedding_vectors WHERE key=?',(key,)).fetchone():
                    db.execute('INSERT OR IGNORE INTO document_embeddings VALUES(?,?,?,?,?,?,?)',(kind,identifier,text_hash(text),json.loads(cache.namespace)['model'],cache.namespace,index,key))

    def index_legacy_embeddings(self,cache_dir):
        """Adopt existing paid vectors, including older document versions. Never call an API."""
        from .extension_ranking import chunks,MODELS
        from .resume_source import CachedEmbeddings
        with self.connect() as db:rows=db.execute('SELECT kind,entity_id,payload FROM versions').fetchall()
        with self.connect() as db:existing={r[0] for r in db.execute('SELECT key FROM embedding_vectors')}
        for row in rows:
            data=json.loads(row['payload'])
            if row['kind']=='vacancy' and data.get('description_quality')!='full':continue
            text=document_text(row['kind'],data);parts=chunks(text)
            for model,dimensions in MODELS.items():
                cache=CachedEmbeddings.__new__(CachedEmbeddings)
                cache.namespace=json.dumps({'class':'src.extension_ranking.OpenAIBackend','model':model,'endpoint':'https://api.openai.com/v1','dimensions':dimensions,'version':'extension-ranking-v1'},sort_keys=True)
                for key,part in zip(cache.keys(parts),parts):
                    if key in existing:continue
                    try:
                        self.save_vector(key,cache.namespace,part,json.loads((Path(cache_dir)/(key+'.json')).read_text()))
                        existing.add(key)
                    except (OSError,ValueError,TypeError,OverflowError):continue
                self.bind_document(row['kind'],row['entity_id'],text,cache,parts)

    def _ranking(self,db,data):
        from .archive_store import canonical,digest
        from .extension_ranking import MODELS
        if data.get('model') not in MODELS or not isinstance(data.get('resume_id'),str) or not isinstance(data.get('resume_hash'),str) or len(str(data.get('goal','')))>2000:
            raise ValueError('Некорректный контекст рейтинга.')
        try:
            parsed=datetime.fromisoformat(data['generated_at'].replace('Z','+00:00'))
            if not parsed.tzinfo:raise ValueError()
        except (ValueError,KeyError,AttributeError):raise ValueError('Некорректная дата рейтинга.') from None
        if not isinstance(data.get('all'),list) or len(data['all'])>2000:raise ValueError('Рейтинг должен содержать до 2000 вакансий.')
        allowed=('id','title','company','link','score','cv_similarity','goal_similarity','evidence','collected_at','vacancy_hash','ranked_at')
        rows=[]
        for item in data['all']:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str):raise ValueError('Некорректная строка рейтинга.')
            if any(type(item.get(k)) not in (int,float) or not math.isfinite(item[k]) or not -1.001<=item[k]<=1.001 for k in ('score','cv_similarity')):raise ValueError('Некорректная оценка рейтинга.')
            if item.get('goal_similarity') is not None and (type(item['goal_similarity']) not in (int,float) or not math.isfinite(item['goal_similarity']) or not -1.001<=item['goal_similarity']<=1.001):raise ValueError('Некорректная оценка цели.')
            rows.append({k:item[k] for k in allowed if k in item})
        data={**data,'all':rows};identifier=digest({k:data.get(k) for k in ('resume_id','resume_hash','model','goal','generated_at')})
        if len(canonical(data).encode())>8*1024*1024:raise ValueError('Рейтинг слишком велик.')
        previous=db.execute('SELECT payload FROM ranking_runs WHERE id=?',(identifier,)).fetchone()
        if previous and previous[0]!=canonical(data):raise ValueError('Сохранённый рейтинг неизменяем.')
        db.execute('INSERT OR IGNORE INTO ranking_runs VALUES(?,?,?,?,?)',(identifier,data['resume_id'],data['model'],parsed.astimezone(timezone.utc).isoformat(),canonical(data)))
        return identifier

    def save_ranking(self,data):
        from .archive_store import FIELDS
        clean={k:data[k] for k in FIELDS['ranking'] if k in data}
        with self.connect() as db:return self._ranking(db,clean)

    def cached_ranking_items(self,resume_id,resume_hash,goal,model,jobs):
        expected={job['id']:job for job in jobs};saved={}
        with self.connect() as db:runs=db.execute('SELECT payload FROM ranking_runs WHERE resume_id=? AND model=? ORDER BY generated_at DESC',(resume_id,model)).fetchall()
        for run in runs:
            data=json.loads(run[0])
            if data.get('resume_hash')!=resume_hash or data.get('goal','')!=goal:continue
            for item in data['all']:
                job=expected.get(item['id'])
                if not job or item['id'] in saved:continue
                current=text_hash(document_text('vacancy',job))
                if item.get('vacancy_hash')!=current and not (not item.get('vacancy_hash') and item.get('collected_at') and item['collected_at']==job.get('collected_at')):continue
                saved[item['id']]={**item,'title':job['title'],'company':job.get('company',''),'link':job['link'],'collected_at':job.get('collected_at'),'ranked_at':item.get('ranked_at') or data['generated_at']}
        return saved

    def ranking_history(self,resume_id=''):
        with self.connect() as db:
            rows=db.execute('SELECT id,payload FROM ranking_runs '+('WHERE resume_id=? ' if resume_id else '')+'ORDER BY generated_at DESC LIMIT 100',([resume_id] if resume_id else [])).fetchall()
        return {'items':[{**json.loads(r['payload']),'id':r['id']} for r in rows]}

    def analysis_states(self,db,entities,resume_id='',goal=None,model='text-embedding-3-small'):
        """Scores belong to a specific CV + JD + goal + model; vectors belong to documents."""
        from .extension_ranking import chunks
        from .manual_applications import all_marks
        manual=all_marks(db)
        bindings={}
        for r in db.execute('SELECT kind,entity_id,document_hash,namespace,COUNT(*) n FROM document_embeddings WHERE model=? GROUP BY kind,entity_id,document_hash,namespace',(model,)):
            key=(r['kind'],r['entity_id']);bindings.setdefault(key,[]).append(r)
        cv=db.execute("SELECT payload FROM entities WHERE kind='resume' AND id=?",(resume_id,)).fetchone()
        cv=json.loads(cv[0]) if cv else None
        runs=db.execute('SELECT payload FROM ranking_runs WHERE resume_id=? AND model=? ORDER BY generated_at DESC',(resume_id,model)).fetchall() if cv else []
        scores={}
        for run in runs:
            data=json.loads(run[0])
            if data['resume_hash']!=cv.get('content_hash') or (goal is not None and data.get('goal','')!=goal):continue
            for item in data['all']:
                scores.setdefault(item['id'],[]).append({**item,'generated_at':data['generated_at'],'model':model,'goal':data.get('goal','')})
        for entity in entities:
            if entity['kind']=='vacancy':entity['manual_application']=manual.get(entity['id'],{'marked':False,'revision':0})
            data=json.loads(entity['payload']);text=document_text(entity['kind'],data);current=text_hash(text);parts=len(chunks(text));known=bindings.get((entity['kind'],entity['id']),[])
            current_counts=[r['n'] for r in known if r['document_hash']==current];count=max(current_counts,default=0)
            status='generated' if parts and count==parts else 'partial' if count else 'stale' if known else 'not_generated'
            if entity['kind']=='vacancy' and data.get('description_quality')!='full':status='needs_description'
            entity['embedding']={'status':status,'model':model,'chunks_ready':count,'chunks_total':parts}
            candidates=scores.get(entity['id'],[]) if entity['kind']=='vacancy' else []
            valid=next((item for item in candidates if item.get('vacancy_hash')==current or (not item.get('vacancy_hash') and item.get('collected_at') and item['collected_at']==data.get('collected_at'))),None)
            entity['ranking']=valid;entity['ranking_stale']=bool(candidates) and valid is None
        return entities
