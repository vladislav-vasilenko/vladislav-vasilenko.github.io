"""One editable employer catalog shared by the dashboard and browser extension."""
import hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
from .china_sources import CHINA_SOURCES
ROOT=Path(__file__).resolve().parents[1]
REGIONS={'rus':'RUS','us_uk_eu':'US / UK / EU','china':'China','jp':'JP','au_nz':'Australia / New Zealand','other':'Другие'}
TIERS={'top':'Top Tier','second':'2nd Tier','others':'Other Tier'}
ADAPTERS={'career.avito.com':'avito','ozon.tech':'ozon-tech','career.ozon.ru':'ozon-career','yandex.ru':'yandex','yandex.com':'yandex','tbank.ru':'tbank','www.tbank.ru':'tbank','rabota.sber.ru':'sber','hh.ru':'hh'}
SELECTORS=('link_selector','card_selector','title_selector','description_selector')

def defaults():
    profile=json.loads((ROOT/'hh-research-extension/search-profile.json').read_text())
    extras={g['id']:g for g in json.loads((ROOT/'hh-research-extension/company-groups.json').read_text())}
    rows=[]
    for c in profile['companies']:
        aliases=list(dict.fromkeys(c['aliases']+extras.get(c['id'],{}).get('aliases',[])+(['МТС AI'] if c['id']=='mws' else [])))
        urls=[c['career_url']] if c.get('career_url') else []
        if c['id']=='ozon':urls=['https://ozon.tech/vacancies/','https://career.ozon.ru/vacancy/']
        rows.append({'id':c['id'],'label':c['label'],'tier':c['tier'],'region':c.get('region','other'),'aliases':aliases,'career_url':urls[0] if urls else '', 'boards':[{'url':u,**dict.fromkeys(SELECTORS,'')} for u in urls]})
    return rows

def raw_catalog(store):
    with store.connect() as db:row=db.execute("SELECT value FROM archive_meta WHERE key='company_catalog'").fetchone()
    rows=json.loads(row[0]) if row else defaults()
    return required_companies(rows)

def required_companies(rows):
    base={r['id']:r for r in defaults()}
    rows=[{**r,'region':r.get('region') or base.get(r['id'],{}).get('region','other')} for r in rows]
    return rows+[r for r in base.values() if r['id'] in ('google','meta',*CHINA_SOURCES) and r['id'] not in {c['id'] for c in rows}]

def revision(rows):return hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def read(store):
    rows=raw_catalog(store)
    for c in rows:
        for board in c['boards']:
            adapter=ADAPTERS.get(urlsplit(board['url']).hostname)
            board['adapter_id']=adapter
            board['status']='custom' if any(board.get(k) for k in SELECTORS) else 'builtin' if adapter else 'missing'
    # Status decorations are not part of the optimistic write version.
    return {'companies':rows,'revision':revision(raw_catalog(store)),'tiers':TIERS,'regions':REGIONS,'adapters':ADAPTERS}

def validate(rows):
    if not isinstance(rows,list) or not 1<=len(rows)<=500:raise ValueError('Нужен список от 1 до 500 компаний.')
    clean=[];seen=set();hosts={}
    for c in rows:
        if not isinstance(c,dict):raise ValueError('Неверный формат компании.')
        key=c.get('id');label=c.get('label');tier=c.get('tier');aliases=c.get('aliases')
        if not isinstance(key,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}',key) or key in seen:raise ValueError('ID компании должен быть уникальным: латиница, цифры, _ или -.')
        seen.add(key)
        if not isinstance(label,str) or not 1<=len(label.strip())<=200 or tier not in TIERS:raise ValueError('Укажите название компании и её tier.')
        if not isinstance(aliases,list) or not aliases or len(aliases)>40 or any(not isinstance(a,str) or not 1<=len(a.strip())<=160 for a in aliases):raise ValueError('Нужны варианты названия компании, по одному на строку.')
        boards=c.get('boards',[])
        if not isinstance(boards,list) or len(boards)>10:raise ValueError('До 10 job boards для компании.')
        result=[]
        for b in boards:
            if not isinstance(b,dict):raise ValueError('Неверные настройки job board.')
            u=b.get('url','');parsed=urlsplit(u) if isinstance(u,str) else None
            if not parsed or parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or len(u)>2000:raise ValueError('Адрес job board должен быть HTTPS-ссылкой без логина, пароля и фрагмента.')
            # One host can serve several research teams of the same employer; choose a specific path for custom boards.
            path=parsed.hostname+parsed.path.rstrip('/')
            if path in hosts and hosts[path]!=key:raise ValueError('Один job board уже указан у другой компании. Укажите отдельный раздел сайта.')
            hosts[path]=key
            selectors={}
            for name in SELECTORS:
                value=b.get(name,'')
                if not isinstance(value,str) or len(value)>700:raise ValueError('CSS-селектор должен быть строкой до 700 символов.')
                selectors[name]=value.strip()
            result.append({'url':u,**selectors})
        region=c.get('region') or next((r.get('region','other') for r in defaults() if r['id']==key),'other')
        if region not in REGIONS:raise ValueError('Выберите регион компании.')
        clean.append({'id':key,'label':label.strip(),'tier':tier,'region':region,'aliases':list(dict.fromkeys(a.strip() for a in aliases)),'boards':result,'career_url':result[0]['url'] if result else ''})
    return clean

def save(store,data):
    rows=validate(data.get('companies'));stamp=revision(rows)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute("SELECT value FROM archive_meta WHERE key='company_catalog'").fetchone();current=required_companies(json.loads(old[0]) if old else defaults())
        if data.get('revision')!=revision(current):raise ValueError('Настройки изменились в другом окне. Обновите страницу настроек перед сохранением.')
        db.execute('CREATE TABLE IF NOT EXISTS company_catalog_history(revision TEXT PRIMARY KEY,payload TEXT,saved_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        for items in (current,rows):db.execute('INSERT OR IGNORE INTO company_catalog_history(revision,payload) VALUES(?,?)',(revision(items),json.dumps(items,ensure_ascii=False)))
        db.execute("INSERT OR REPLACE INTO archive_meta VALUES('company_catalog',?)",(json.dumps(rows,ensure_ascii=False),))
    return read(store)

def selection(value=None,legacy=''):
    if value is None:return [legacy] if legacy else None
    if not isinstance(value,list) or len(value)>500 or any(not isinstance(k,str) or not 1<=len(k)<=300 for k in value):raise ValueError('Некорректный список выбранных компаний.')
    return list(dict.fromkeys(value))
