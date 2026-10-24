"""Private, source-independent teams, contacts and evidence-backed stream assignments."""
import json
import re
import secrets
import time
from urllib.parse import urlsplit
from .archive_store import canonical, digest

STREAMS = ['Pre-training', 'Post-training', 'Optimization', 'Distillation',
           'Super-resolution', 'VAE / KVAE', 'Captioning Pipeline', 'Pre-training Data',
           'Post-training Data', 'Metrics & Evaluation (Benchmarking)', 'Harness']


def init(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS network_teams(id TEXT PRIMARY KEY,company TEXT,name TEXT);
      CREATE TABLE IF NOT EXISTS network_vacancy_teams(vacancy_id TEXT,team_id TEXT,PRIMARY KEY(vacancy_id,team_id));
      CREATE TABLE IF NOT EXISTS network_members(team_id TEXT,person_id TEXT,payload TEXT,revision INTEGER,PRIMARY KEY(team_id,person_id));
      CREATE TABLE IF NOT EXISTS network_events(id TEXT PRIMARY KEY,team_id TEXT,person_id TEXT,payload TEXT,created REAL);
    ''')


def bounded(value, size=1000):
    if not isinstance(value,str) or len(value)>size: raise ValueError('Некорректное поле команды.')
    return value.strip()


def safe_source(value):
    value=bounded(value,2000); u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password: raise ValueError('Нужна HTTPS-ссылка на источник.')
    return value


def vacancy(db, identifier):
    row=db.execute("SELECT payload FROM entities WHERE kind='vacancy' AND id=?",(identifier,)).fetchone()
    if not row: raise ValueError('Вакансия не найдена в основной подборке.')
    return json.loads(row[0])


def view(archive, data):
    with archive.connect() as db:
        init(db); vacancy(db,data.get('vacancy_id'))
        teams=[]
        for row in db.execute('SELECT t.* FROM network_teams t JOIN network_vacancy_teams v ON t.id=v.team_id WHERE v.vacancy_id=? ORDER BY t.name',(data['vacancy_id'],)):
            members=[{**json.loads(m['payload']),'id':m['person_id'],'revision':m['revision']} for m in db.execute('SELECT * FROM network_members WHERE team_id=? ORDER BY person_id',(row['id'],))]
            teams.append({**dict(row),'members':members})
        commands=[]
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='browser_commands'").fetchone():
            commands=[{**dict(r),'result':json.loads(r['result']) if r['result'] else None} for r in db.execute("SELECT id,state,result FROM browser_commands WHERE kind='linkedin.team.read' AND json_extract(payload,'$.vacancy_id')=? ORDER BY created DESC LIMIT 5",(data['vacancy_id'],))]
    return {'teams':teams,'streams':STREAMS,'commands':commands,'coverage':'public_visible_only'}


def bind(archive,data):
    name=bounded(data.get('name',''),200)
    if not name: raise ValueError('Укажите команду или лабораторию.')
    with archive.connect() as db:
        init(db); v=vacancy(db,data.get('vacancy_id')); company=bounded(v.get('company',''),500)
        ident=digest({'company':company.casefold(),'name':name.casefold()})[:24]
        db.execute('INSERT OR IGNORE INTO network_teams VALUES(?,?,?)',(ident,company,name))
        db.execute('INSERT OR IGNORE INTO network_vacancy_teams VALUES(?,?)',(data['vacancy_id'],ident))
    return {'team_id':ident}


def assert_link(db, data):
    vacancy(db,data.get('vacancy_id'))
    if not db.execute('SELECT 1 FROM network_vacancy_teams WHERE vacancy_id=? AND team_id=?',(data['vacancy_id'],data.get('team_id'))).fetchone():raise ValueError('Команда не связана с этой вакансией.')


def capture(db, data, rows, source):
    assert_link(db,data)
    if not isinstance(rows,list) or len(rows)>1000: raise ValueError('Слишком много участников.')
    for row in rows:
        url=safe_source(row.get('url','')); u=urlsplit(url)
        if source=='linkedin':
            from .linkedin_workspace import linkedin_url
            url=linkedin_url(url,'profile')
        elif source=='huggingface':
            if u.netloc!='huggingface.co' or not re.fullmatch(r'/[\w-]+',u.path):raise ValueError('Некорректный профиль Hugging Face.')
        else:raise ValueError('Неизвестный адаптер участников.')
        ident=source+':'+url; old=db.execute('SELECT payload,revision FROM network_members WHERE team_id=? AND person_id=?',(data['team_id'],ident)).fetchone()
        previous=json.loads(old[0]) if old else {}
        payload={**previous,'name':bounded(row.get('name',''),500),'url':url,'source':source,
                 'observed_role':bounded(row.get('role',''),1000),'relationship':bounded(row.get('relationship','organization_member'),100),
                 'evidence_url':safe_source(data['url']),
                 'evidence_quote':bounded(row.get('evidence_quote',''),6000),'observed_at':time.time(),
                 'streams':previous.get('streams',[]),'coverage':'public_visible_only'}
        badges=row.get('badges',[])
        if not isinstance(badges,list) or len(badges)>30:raise ValueError('Некорректные бейджи участника.')
        payload['badges']=[bounded(b,200) for b in badges]
        db.execute('INSERT OR REPLACE INTO network_members VALUES(?,?,?,?)',(data['team_id'],ident,canonical(payload),(old[1] if old else 0)+1))
    db.execute('INSERT INTO network_events VALUES(?,?,?,?,?)',(secrets.token_hex(12),data['team_id'],'',canonical({'source':source,'url':data['url'],'count':len(rows),'coverage':'public_visible_only'}),time.time()))
    return {'count':len(rows),'coverage':'public_visible_only'}


def collect_huggingface(archive,data):
    org=bounded(data.get('organization',''),100)
    if not re.fullmatch(r'[\w-]+',org):raise ValueError('Укажите имя организации Hugging Face.')
    with archive.connect() as db:init(db);assert_link(db,data)
    import requests
    url='https://huggingface.co/'+org
    # Fixed public host and escaped slug; never forward local credentials or follow redirects.
    response=requests.get('https://huggingface.co/api/organizations/'+org+'/members',timeout=20,allow_redirects=False)
    if response.status_code!=200:raise ValueError('Hugging Face не вернул публичный список участников.')
    rows=response.json()
    if not isinstance(rows,list) or len(rows)>1000:raise ValueError('Неизвестный формат списка Hugging Face.')
    members=[]
    for r in rows:
        username=r.get('user')
        if not isinstance(username,str) or not re.fullmatch(r'[\w-]+',username):raise ValueError('Неизвестный формат участника Hugging Face.')
        members.append({'url':'https://huggingface.co/'+username,'name':r.get('fullname') or username,'role':'',
                        'relationship':'organization_member','evidence_url':url,'evidence_quote':'Public organization member: '+org,
                        'badges':['PRO'] if r.get('isPro') is True else []})
    with archive.connect() as db:init(db);return capture(db,{**data,'url':url},members,'huggingface')


def annotate(archive,data):
    assignments=data.get('streams',[])
    if not isinstance(assignments,list) or len(assignments)>len(STREAMS) or any(s not in STREAMS for s in assignments):raise ValueError('Выберите известные стримы.')
    status=data.get('status','hypothesis')
    if status not in ('confirmed','hypothesis'):raise ValueError('Укажите статус связи со стримом.')
    quote=bounded(data.get('evidence_quote',''),6000);url=safe_source(data.get('evidence_url',''))
    if assignments and not quote:raise ValueError('Укажите основание назначения стримов.')
    with archive.connect() as db:
        init(db);assert_link(db,data)
        old=db.execute('SELECT payload,revision FROM network_members WHERE team_id=? AND person_id=?',(data['team_id'],data.get('person_id'))).fetchone()
        if not old or old[1]!=data.get('revision'):raise ValueError('Запись изменилась. Обновите список.')
        p=json.loads(old[0]);before=canonical(p)
        p.update(role=bounded(data.get('role',''),1000),streams=[{'name':name,'status':status,'evidence_url':url,'evidence_quote':quote,'reviewed_at':time.time()} for name in dict.fromkeys(assignments)])
        db.execute('UPDATE network_members SET payload=?,revision=revision+1 WHERE team_id=? AND person_id=?',(canonical(p),data['team_id'],data['person_id']))
        db.execute('INSERT INTO network_events VALUES(?,?,?,?,?)',(secrets.token_hex(12),data['team_id'],data['person_id'],canonical({'before':json.loads(before),'after':p}),time.time()))
    return {'ok':True}


def install(app):
    import asyncio
    from fastapi import HTTPException,Request
    @app.post('/archive/vacancy-team')
    async def action(request:Request):
        try:
            raw=await request.body()
            if len(raw)>40000:raise ValueError('Слишком большой запрос.')
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError('Нужен объект запроса.')
            op=data.get('op');archive=app.state.archive_store()
            operations={'view':view,'bind':bind,'huggingface':collect_huggingface,'annotate':annotate}
            if op=='linkedin':
                from .linkedin_workspace import enqueue
                with archive.connect() as db:init(db);assert_link(db,data)
                return await asyncio.to_thread(enqueue,archive,{**data,'action':'team.read'})
            if op not in operations:raise ValueError('Неизвестная операция команды.')
            return await asyncio.to_thread(operations[op],archive,data)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e)) from None
