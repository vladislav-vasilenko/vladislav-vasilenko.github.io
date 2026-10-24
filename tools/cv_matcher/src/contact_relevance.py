"""Explainable professional relevance and a reversible local connection-review plan."""
import json
import re
import secrets
import time
from .archive_store import canonical,digest
from .career_skills_store import get

CATEGORIES={'team':'Целевая команда','recruiter':'Рекрутер / Talent Acquisition','focus':'Связь с текущим фокусом','adjacent':'Смежный опыт','review':'Проверить связь с фокусом','unknown':'Недостаточно данных'}
PLANS={'none':'Без решения','keep':'Оставить','unfollow':'Отписаться от ленты','disconnect':'Рассмотреть Disconnect','later':'Вернуться позже'}
RECRUITER=re.compile(r'\brecruit(?:er|ing|ment|ers)\b|\bsourc(?:er|ing)\b|\btalent\s+(?:acquisition|partner|recruit|scout)|\bheadhunt|\bHR\s+(?:partner|manager|director)|рекрутер|рекрутинг|подбор\w* персонал',re.I)
DOMAINS={
 'ML / AI':r'\b(?:AI|ML|LLM|GenAI|PyTorch|TensorFlow|diffusion|transformers?|RLHF)\b|machine learning|deep learning|generative|генератив|нейросет|машинн\w* обучен|искусственн\w* интеллект|flow matching',
 'Исследования':r'\bresearch(?:er)?\b|scientist|исследован|математик|statistics|probability',
 'Разработка':r'\b(?:software|python|backend|full.?stack|frontend|swift|iOS|MLOps|DevOps|SRE|CUDA|GPU)\b|разработчик|программир|software engineer',
 'Продукты':r'product (?:manager|lead|owner)|technical product|руководител\w* продукт|менеджер продукт|продуктов\w* менеджер',
}


def init(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS linkedin_contact_reviews(account TEXT,id TEXT,payload TEXT,revision INTEGER,PRIMARY KEY(account,id));
      CREATE TABLE IF NOT EXISTS linkedin_contact_review_events(id TEXT PRIMARY KEY,account TEXT,person_id TEXT,payload TEXT,created REAL);''')


def basis(archive,db,account):
    summary=archive.summary();resume=None
    if summary.get('primary_id'):
        row=db.execute("SELECT payload FROM entities WHERE kind='resume' AND id=?",(summary['primary_id'],)).fetchone()
        if row:resume=json.loads(row[0])
    active=get(db,'trajectory-active');path=get(db,'trajectory:'+active) if active else None
    focus=' '.join([summary.get('goal',''),(resume or {}).get('title',''),canonical(path) if path else ''])
    from .resume_source import matching_text
    experience=matching_text(resume) if resume else ''
    current=[name for name,pattern in DOMAINS.items() if re.search(pattern,focus,re.I)]
    adjacent=[name for name,pattern in DOMAINS.items() if name not in current and re.search(pattern,experience,re.I)]
    members=set();team_links={}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='network_members'").fetchone():
        for row in db.execute('SELECT m.payload,t.id,t.name FROM network_members m JOIN network_teams t ON t.id=m.team_id'):
            person=json.loads(row['payload']);url=person.get('url');members.add(url);team_links.setdefault(url,[]).append({'team_id':row['id'],'team':row['name'],'streams':person.get('streams',[]),'status':person.get('membership_status','observed'),'evidence_url':person.get('evidence_url',''),'evidence_quote':person.get('evidence_quote','')})
    return {'resume_id':summary.get('primary_id'),'resume_title':(resume or {}).get('title',''),'goal':summary.get('goal',''),'trajectory':(path or {}).get('label',''),'current':current,'adjacent':adjacent,'members':members,'team_links':team_links,'hash':digest({'focus':focus,'experience':experience})}


def classify(person,context):
    headline=person.get('headline','').strip();recruiter=bool(RECRUITER.search(headline))
    result={'category':'unknown','is_recruiter':recruiter,'evidence':headline,'basis_hash':context['hash'],'matches':[],'method':'visible_professional_headline'}
    if person['url'] in context['members']:
        result.update(category='team',reason='Есть сохранённая связь с командой. Роль и стрим проверяются по отдельным источникам.')
    elif recruiter:
        result.update(category='recruiter',reason='В видимой должности явно указана работа с наймом.')
    elif not headline or len(headline)<12:
        result['reason']='В карточке мало профессиональных сведений. Отсутствие текста не означает отсутствия связи.'
    elif not context['current']:
        result['reason']='Сначала выберите резюме, цель или карьерную траекторию для сравнения.'
    else:
        matches=[name for name in context['current'] if re.search(DOMAINS[name],headline,re.I)]
        adjacent=[name for name in context['adjacent'] if re.search(DOMAINS[name],headline,re.I)]
        if matches:result.update(category='focus',matches=matches,reason='Наблюдается пересечение с текущим направлением: '+', '.join(matches)+'.')
        elif adjacent:result.update(category='adjacent',matches=adjacent,reason='Есть пересечение с опытом из резюме: '+', '.join(adjacent)+'.')
        else:result.update(category='review',reason='В этом headline не найдены признаки найма или связи с выбранным направлением. Проверьте профиль и историю знакомства перед решением.')
    result['label']=CATEGORIES[result['category']]
    return result


def review(archive,data):
    from .linkedin_workspace import init as init_workspace,settings,linkedin_url,text
    url=linkedin_url(data.get('id'),'profile');plan=data.get('plan');note=text(data.get('note',''),5000)
    if plan not in PLANS or type(data.get('revision',0)) is not int:raise ValueError('Выберите решение для локального плана.')
    with archive.connect() as db:
        init_workspace(db);init(db);db.execute('BEGIN IMMEDIATE');account=settings(db).get('profile_url','')
        if not db.execute("SELECT 1 FROM linkedin_records WHERE account=? AND kind='contacts' AND id=?",(account,url)).fetchone():raise ValueError('Контакт не сохранён в этом аккаунте.')
        old=db.execute('SELECT * FROM linkedin_contact_reviews WHERE account=? AND id=?',(account,url)).fetchone();revision=old['revision'] if old else 0
        if revision!=data.get('revision',0):raise ValueError('План изменён в другой вкладке. Обновите контакт.')
        payload={'plan':plan,'note':note,'updated':time.time(),'execution':'local_plan_only'}
        db.execute('INSERT OR REPLACE INTO linkedin_contact_reviews VALUES(?,?,?,?)',(account,url,canonical(payload),revision+1))
        db.execute('INSERT INTO linkedin_contact_review_events VALUES(?,?,?,?,?)',(secrets.token_hex(12),account,url,canonical({'before':json.loads(old['payload']) if old else None,'after':payload}),time.time()))
    return {'ok':True,'revision':revision+1,'review':payload}
