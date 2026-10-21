"""Recruitment stage, next action and versioned appointments, independent of HH state."""
import json,secrets
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from urllib.parse import urlencode

CRM_STAGES={'preparing':'Подготовка','applied':'Отклик отправлен','ai_screened':'Пройдено интервью с AI-рекрутером','recruiter':'Общение с рекрутером','stage_1':'Первый этап','stage_2':'Второй этап','stage_3':'Третий этап','rejected':'Отказ','offer':'Оффер'}
WORK_STATUSES={'preparing':'Готовлюсь','waiting_reply':'Ждём ответа','waiting_invitation':'Ждём приглашения на интервью','scheduled':'Интервью назначено','done':'Завершено'}
STAGE_DEFAULTS={'preparing':('preparing','Подготовить отклик'),'applied':('waiting_reply','Дождаться ответа на отклик'),'ai_screened':('waiting_invitation','Дождаться приглашения на интервью с командой'),'recruiter':('waiting_invitation','Согласовать интервью'),'stage_1':('preparing','Подготовиться к первому этапу'),'stage_2':('preparing','Подготовиться ко второму этапу'),'stage_3':('preparing','Подготовиться к третьему этапу'),'rejected':('done',''),'offer':('done','')}

def stamp():return datetime.now(timezone.utc).isoformat()
def date_time(value,zone='Europe/Moscow'):
    """Accept browser local time with an explicit IANA zone, persist UTC; reject DST gaps."""
    try:
        tz=ZoneInfo(zone);d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if not d.tzinfo:
            candidate=d.replace(tzinfo=tz)
            if candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=d:raise ValueError()
            if candidate.utcoffset()!=d.replace(tzinfo=tz,fold=1).utcoffset():raise ValueError()
            d=candidate
        return d.astimezone(timezone.utc).isoformat()
    except (ValueError,TypeError,AttributeError,ZoneInfoNotFoundError):raise ValueError('Укажите корректные дату, время и часовой пояс. Для неоднозначного времени нужен UTC-сдвиг.') from None

def crm_value(row=None):
    data=dict(row) if row else {};stage=data.get('stage','preparing');state,action=STAGE_DEFAULTS.get(stage,STAGE_DEFAULTS['preparing'])
    return {'stage':stage,'work_status':state,'next_action':action,'follow_up_at':None,'revision':0,'updated_at':None,**data}

class PlanningMixin:
    def mark_applied(self,db,app_id):
        old=crm_value(db.execute('SELECT * FROM application_crm WHERE app_id=?',(app_id,)).fetchone())
        if old['stage']!='preparing':return
        state,action=STAGE_DEFAULTS['applied']
        db.execute('INSERT INTO application_crm(app_id,stage,work_status,next_action,follow_up_at,revision,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET stage=excluded.stage,work_status=excluded.work_status,next_action=excluded.next_action,revision=excluded.revision,updated_at=excluded.updated_at',(app_id,'applied',state,action,old['follow_up_at'],old['revision']+1,stamp()))
        self._event(db,app_id,'crm_stage',{'before':old['stage'],'stage':'applied','work_status':state,'next_action':action,'previous':old,'actor':'hh_confirmation'})

    def init_planning(self,db):
        db.execute('BEGIN IMMEDIATE')
        columns={r[1] for r in db.execute('PRAGMA table_info(application_crm)')}
        for name,definition in {'work_status':"TEXT DEFAULT 'preparing'",'next_action':"TEXT DEFAULT ''",'follow_up_at':'TEXT','revision':'INTEGER DEFAULT 0'}.items():
            if name not in columns:db.execute('ALTER TABLE application_crm ADD COLUMN '+name+' '+definition)
        if 'work_status' not in columns:
            for stage,(state,action) in STAGE_DEFAULTS.items():db.execute('UPDATE application_crm SET work_status=?,next_action=? WHERE stage=?',(state,action,stage))
        db.executescript('''CREATE TABLE IF NOT EXISTS application_appointments(
          id TEXT PRIMARY KEY,app_id TEXT NOT NULL,stage TEXT NOT NULL,title TEXT NOT NULL,
          start_at TEXT NOT NULL,end_at TEXT NOT NULL,time_zone TEXT NOT NULL,location TEXT DEFAULT '',
          notes TEXT DEFAULT '',status TEXT DEFAULT 'scheduled',revision INTEGER DEFAULT 1,updated_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS appointments_app ON application_appointments(app_id,start_at);
          CREATE TABLE IF NOT EXISTS calendar_links(appointment_id TEXT PRIMARY KEY,event_id TEXT,etag TEXT,revision INTEGER,html_link TEXT,synced_at TEXT);''')

    def set_crm(self,app_id,stage,note='',actor='user',*,work_status=None,next_action=None,follow_up_at=None,revision=None,clear_follow_up=False):
        app_id=self.case_id(app_id)
        if stage not in CRM_STAGES:raise ValueError('Неизвестный этап CRM.')
        if not isinstance(note,str) or len(note)>2000:raise ValueError('Комментарий — до 2000 символов.')
        if next_action is not None and (not isinstance(next_action,str) or len(next_action)>2000):raise ValueError('Следующий шаг — до 2000 символов.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._wf(db,app_id)
            old=crm_value(db.execute('SELECT * FROM application_crm WHERE app_id=?',(app_id,)).fetchone())
            if revision is not None and revision!=old['revision']:raise ValueError('План уже изменён. Обновите карточку.')
            state=work_status or (STAGE_DEFAULTS[stage][0] if stage!=old['stage'] else old['work_status'])
            if state not in WORK_STATUSES:raise ValueError('Неизвестное состояние работы.')
            action=next_action if next_action is not None else STAGE_DEFAULTS[stage][1] if stage!=old['stage'] else old['next_action']
            due=date_time(follow_up_at) if follow_up_at else None if clear_follow_up or state=='done' else old['follow_up_at']
            new={'stage':stage,'work_status':state,'next_action':action.strip(),'follow_up_at':due}
            if any(new[k]!=old[k] for k in new) or note.strip():
                db.execute('INSERT INTO application_crm(app_id,stage,work_status,next_action,follow_up_at,revision,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET stage=excluded.stage,work_status=excluded.work_status,next_action=excluded.next_action,follow_up_at=excluded.follow_up_at,revision=excluded.revision,updated_at=excluded.updated_at',(app_id,stage,state,action.strip(),due,old['revision']+1,stamp()))
                self._event(db,app_id,'crm_stage',{'before':old['stage'],**new,'previous':old,'note':note.strip(),'actor':actor})
                if stage!=old['stage']:self._invalidate(db,app_id)
        return self.workflow(app_id)

    def appointments(self,app_id):
        app_id=self.case_id(app_id)
        with self.connect() as db:
            rows=db.execute('SELECT a.*,c.event_id,c.etag,c.revision calendar_revision,c.html_link,c.synced_at FROM application_appointments a LEFT JOIN calendar_links c ON c.appointment_id=a.id WHERE app_id=? ORDER BY start_at DESC',(app_id,)).fetchall()
        return [{**dict(r),'calendar_state':'not_linked' if not r['event_id'] else 'synced' if r['revision']==r['calendar_revision'] else 'pending'} for r in rows]

    def appointment(self,app_id,identifier):
        self.get(app_id)
        item=next((a for a in self.appointments(app_id) if a['id']==identifier),None)
        if not item:raise ValueError('Встреча не найдена в этом отклике.')
        return item

    def save_appointment(self,app_id,data,actor='user'):
        app_id=self.case_id(app_id)
        if not isinstance(data,dict):raise ValueError('Некорректный план встречи.')
        stage=data.get('stage','stage_1');status=data.get('status','scheduled');zone=data.get('time_zone','Europe/Moscow')
        if stage not in CRM_STAGES or status not in ('scheduled','completed','cancelled'):raise ValueError('Неизвестный этап или статус встречи.')
        start=date_time(data.get('start_at'),zone);end=date_time(data.get('end_at'),zone)
        minutes=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()/60
        if not 5<=minutes<=1440:raise ValueError('Продолжительность встречи — от 5 минут до 24 часов.')
        clean={'stage':stage,'status':status,'start_at':start,'end_at':end,'time_zone':zone}
        for key,limit in [('title',300),('location',2000),('notes',4000)]:
            value=data.get(key,'')
            if not isinstance(value,str) or len(value)>limit:raise ValueError('Слишком длинное или некорректное поле встречи: '+key)
            clean[key]=value.strip()
        if not clean['title']:raise ValueError('Укажите название встречи.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');self._wf(db,app_id)
            old=db.execute('SELECT * FROM application_appointments WHERE id=? AND app_id=?',(data.get('id',''),app_id)).fetchone()
            if data.get('id') and not old:raise ValueError('Встреча не найдена.')
            if old and data.get('revision')!=old['revision']:raise ValueError('Встреча уже изменена. Обновите карточку.')
            identifier=old['id'] if old else secrets.token_hex(12)
            if not old or any(old[k]!=v for k,v in clean.items()):
                rev=old['revision']+1 if old else 1;cols=['id','app_id',*clean,'revision','updated_at']
                db.execute('INSERT OR REPLACE INTO application_appointments('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[identifier,app_id,*clean.values(),rev,stamp()])
                self._event(db,app_id,'appointment_saved',{'id':identifier,'revision':rev,'before':dict(old) if old else None,**clean,'actor':actor})
        return self.appointment(app_id,identifier)

def calendar_details(app,item):
    c=app['context'];return item['title']+' · '+c['vacancy']['company'], 'Вакансия: '+c['vacancy']['title']+'\n'+c['vacancy']['link']+'\nЭтап: '+CRM_STAGES[item['stage']]+'\n'+item['notes']

def google_link(app,item):
    title,details=calendar_details(app,item)
    fmt=lambda s:datetime.fromisoformat(s).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return 'https://calendar.google.com/calendar/render?'+urlencode({'action':'TEMPLATE','text':title,'dates':fmt(item['start_at'])+'/'+fmt(item['end_at']),'details':details,'location':item['location'],'ctz':item['time_zone']})

def icalendar(app,item):
    def esc(s):return s.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    fmt=lambda s:datetime.fromisoformat(s).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    title,details=calendar_details(app,item)
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//CV Matcher//Interviews//RU','BEGIN:VEVENT','UID:'+item['id']+'@cv-matcher.local','SEQUENCE:'+str(item['revision']),'DTSTAMP:'+fmt(item['updated_at']),'DTSTART:'+fmt(item['start_at']),'DTEND:'+fmt(item['end_at']),'SUMMARY:'+esc(title),'DESCRIPTION:'+esc(details),'LOCATION:'+esc(item['location']),'STATUS:'+('CANCELLED' if item['status']=='cancelled' else 'CONFIRMED'),'END:VEVENT','END:VCALENDAR']
    folded=[]
    for line in lines:
        part=''
        for ch in line:
            if len((part+ch).encode('utf-8'))>73:folded.append(part);part=' '+ch
            else:part+=ch
        folded.append(part)
    return '\r\n'.join(folded)+'\r\n'
