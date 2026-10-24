"""Source-backed team / stream / person / vacancy graph; no inferred employment."""
import json
import re
import secrets
import time
from .archive_store import canonical,digest
from . import vacancy_team as teams

PRESETS={'kandinsky':{'name':'Kandinsky','pattern':r'kandinsky|кандинск'},'gigachat':{'name':'GigaChat','pattern':r'gigachat|гигачат'},'aliceart':{'name':'Yandex AliceART','pattern':r'alice\s*art|aliceart|алиса\s*арт'}}


def init(db):
    teams.init(db)
    db.execute('CREATE TABLE IF NOT EXISTS network_vacancy_streams(vacancy_id TEXT,team_id TEXT,name TEXT,payload TEXT,PRIMARY KEY(vacancy_id,team_id,name))')


def directory(db):
    result=[dict(row) for row in db.execute('SELECT * FROM network_teams ORDER BY name')]
    for key,preset in PRESETS.items():
        if not any(re.search(preset['pattern'],team['name'],re.I) for team in result):result.append({'id':'preset:'+key,'name':preset['name'],'company':'','virtual':True})
    return result


def resolve(db,ident,company=''):
    if isinstance(ident,str) and ident.startswith('preset:'):
        key=ident[7:]
        if key not in PRESETS:raise ValueError('Неизвестное направление.')
        name=PRESETS[key]['name'];ident=digest({'company':company.casefold(),'name':name.casefold()})[:24]
        db.execute('INSERT OR IGNORE INTO network_teams VALUES(?,?,?)',(ident,company,name))
    if not db.execute('SELECT 1 FROM network_teams WHERE id=?',(ident,)).fetchone():raise ValueError('Команда не найдена.')
    return ident


def view(archive,data):
    cluster=data.get('cluster','all');stream=data.get('stream','');query=teams.bounded(data.get('query',''),300).casefold()
    if cluster not in ('all',*PRESETS):raise ValueError('Выберите кластер.')
    with archive.connect() as db:
        init(db);directory_rows=directory(db);selected=[team for team in directory_rows if cluster=='all' or re.search(PRESETS[cluster]['pattern'],team['name'],re.I)]
        selected_ids={team['id'] for team in selected};people={};vacancies={};edges=[]
        all_jobs={row['id']:{'id':row['id'],'title':row['title'] or '', 'company':row['company'] or '', 'url':row['url'] or ''} for row in db.execute("SELECT id,json_extract(payload,'$.title') title,json_extract(payload,'$.company') company,json_extract(payload,'$.link') url FROM entities WHERE kind='vacancy'")}
        for row in db.execute('SELECT * FROM network_vacancy_teams'):
            if row['team_id'] not in selected_ids or row['vacancy_id'] not in all_jobs:continue
            job=all_jobs[row['vacancy_id']];vacancies[job['id']]=job;edges.append({'source':job['id'],'target':row['team_id'],'kind':'vacancy_team','status':'owner_link','label':'Сохранённая привязка вакансии'})
        for row in db.execute('SELECT * FROM network_members ORDER BY person_id'):
            if row['team_id'] not in selected_ids:continue
            person=json.loads(row['payload']);assignments=person.get('streams',[])
            if stream and not any(item['name']==stream for item in assignments):continue
            if query and query not in canonical(person).casefold():continue
            ident=row['person_id'];people[ident]={**person,'id':ident,'revision':row['revision']}
            edges.append({'source':ident,'target':row['team_id'],'kind':'person_team','status':person.get('membership_status','observed'),'label':{'organization_member':'Участник организации в источнике','job_poster':'Указан у вакансии','owner_link':'Привязка пользователя'}.get(person.get('relationship'),'Связь из источника'),'evidence_url':person.get('evidence_url',''),'evidence_quote':person.get('evidence_quote','')})
            for assignment in assignments:
                if stream and assignment['name']!=stream:continue
                edges.append({'source':ident,'target':row['team_id']+':stream:'+assignment['name'],'team_id':row['team_id'],'kind':'person_stream',**assignment})
        for row in db.execute('SELECT * FROM network_vacancy_streams'):
            if row['team_id'] in selected_ids and row['vacancy_id'] in vacancies and (not stream or row['name']==stream):edges.append({'source':row['vacancy_id'],'target':row['team_id']+':stream:'+row['name'],'team_id':row['team_id'],'kind':'vacancy_stream','name':row['name'],**json.loads(row['payload'])})
        # Explicit names in saved vacancy titles create suggestions, never membership facts.
        for team in selected:
            preset=next((p for p in PRESETS.values() if re.search(p['pattern'],team['name'],re.I)),None)
            if not preset:continue
            for job in all_jobs.values():
                if not re.search(preset['pattern'],job['title'],re.I) or any(e['source']==job['id'] and e['target']==team['id'] for e in edges):continue
                vacancies[job['id']]=job;edges.append({'source':job['id'],'target':team['id'],'kind':'vacancy_team','status':'hypothesis','label':'Предложено по названию вакансии','evidence_url':job['url'],'evidence_quote':job['title']})
        if stream:
            matching={edge['source'] for edge in edges if edge['kind']=='vacancy_stream' and edge['name']==stream}
            vacancies={key:value for key,value in vacancies.items() if key in matching}
            edges=[edge for edge in edges if not edge['kind'].startswith('vacancy_') or edge['source'] in matching]
        from .linkedin_workspace import settings
        account=settings(db).get('profile_url','');contact_count=db.execute("SELECT count(*) FROM linkedin_records WHERE account=? AND kind='contacts'",(account,)).fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='linkedin_records'").fetchone() else 0
    for team in selected:
        team['people']=[e['source'] for e in edges if e['kind']=='person_team' and e['target']==team['id']]
        team['vacancies']=[e['source'] for e in edges if e['kind']=='vacancy_team' and e['target']==team['id']]
    return {'teams':selected,'directory':directory_rows,'people':list(people.values()),'vacancies':list(vacancies.values()),'edges':edges,'streams':teams.STREAMS,'contact_count':contact_count,'presets':{key:value['name'] for key,value in PRESETS.items()},'coverage':'saved_and_observed_links'}


def create_team(archive,data):
    name=teams.bounded(data.get('name',''),200);company=teams.bounded(data.get('company',''),500)
    if not name:raise ValueError('Укажите название команды.')
    ident=digest({'company':company.casefold(),'name':name.casefold()})[:24]
    with archive.connect() as db:init(db);db.execute('INSERT OR IGNORE INTO network_teams VALUES(?,?,?)',(ident,company,name))
    return {'team_id':ident}


def link_vacancy(archive,data):
    streams=data.get('streams',[])
    if not isinstance(streams,list) or any(name not in teams.STREAMS for name in streams):raise ValueError('Выберите известные стримы.')
    with archive.connect() as db:
        init(db);vacancy=teams.vacancy(db,data.get('vacancy_id'));ident=resolve(db,data.get('team_id'),vacancy.get('company',''))
        db.execute('INSERT OR IGNORE INTO network_vacancy_teams VALUES(?,?)',(data['vacancy_id'],ident))
        if streams:
            url=teams.safe_source(data.get('evidence_url',''));quote=teams.bounded(data.get('evidence_quote',''),6000);status=data.get('status','hypothesis')
            if not quote or status not in ('confirmed','hypothesis'):raise ValueError('Нужен источник связи со стримом.')
            for name in set(streams):db.execute('INSERT OR REPLACE INTO network_vacancy_streams VALUES(?,?,?,?)',(data['vacancy_id'],ident,name,canonical({'status':status,'evidence_url':url,'evidence_quote':quote})))
        db.execute('INSERT INTO network_events VALUES(?,?,?,?,?)',(secrets.token_hex(12),ident,'',canonical({'kind':'vacancy_link','vacancy_id':data['vacancy_id'],'streams':streams}),time.time()))
    return {'team_id':ident,'ok':True}


def link_contact(archive,data):
    from .linkedin_workspace import settings,linkedin_url
    url=linkedin_url(data.get('url'),'profile');quote=teams.bounded(data.get('evidence_quote',''),6000);evidence=teams.safe_source(data.get('evidence_url') or url);status=data.get('status','hypothesis');streams=data.get('streams',[])
    if status not in ('confirmed','hypothesis') or not quote:raise ValueError('Укажите основание и статус связи с командой.')
    if not isinstance(streams,list) or any(name not in teams.STREAMS for name in streams):raise ValueError('Выберите известные стримы.')
    with archive.connect() as db:
        init(db);account=settings(db).get('profile_url','');row=db.execute("SELECT payload FROM linkedin_records WHERE account=? AND kind='contacts' AND id=?",(account,url)).fetchone()
        if not row:raise ValueError('Сначала соберите этот контакт в LinkedIn.')
        person=json.loads(row[0]);ident=resolve(db,data.get('team_id'));person_id='linkedin:'+url;old=db.execute('SELECT * FROM network_members WHERE team_id=? AND person_id=?',(ident,person_id)).fetchone()
        if old and data.get('revision')!=old['revision']:raise ValueError('Связь уже сохранена. Уточните её в карточке команды, чтобы сохранить историю.')
        payload={'name':person['name'],'url':url,'source':'linkedin','relationship':'owner_link','membership_status':status,'role':teams.bounded(data.get('role',''),1000),'headline':person.get('headline',''),'evidence_url':evidence,'evidence_quote':quote,'observed_at':time.time(),'streams':[{'name':name,'status':status,'evidence_url':evidence,'evidence_quote':quote} for name in set(streams)]}
        db.execute('INSERT OR REPLACE INTO network_members VALUES(?,?,?,?)',(ident,person_id,canonical(payload),(old['revision'] if old else 0)+1))
        db.execute('INSERT INTO network_events VALUES(?,?,?,?,?)',(secrets.token_hex(12),ident,person_id,canonical({'kind':'contact_link','before':json.loads(old['payload']) if old else None,'after':payload}),time.time()))
    return {'ok':True,'team_id':ident}


def install(app):
    import asyncio
    from fastapi import HTTPException,Request
    @app.post('/archive/network')
    async def action(request:Request):
        try:
            raw=await request.body()
            if len(raw)>40000:raise ValueError('Слишком большой запрос.')
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError('Нужен объект запроса.')
            operations={'view':view,'team':create_team,'link_contact':link_contact,'link_vacancy':link_vacancy}
            if data.get('op') not in operations:raise ValueError('Неизвестное действие карты связей.')
            return await asyncio.to_thread(operations[data['op']],app.state.archive_store(),data)
        except (ValueError,KeyError,TypeError) as error:raise HTTPException(422,str(error)) from None
