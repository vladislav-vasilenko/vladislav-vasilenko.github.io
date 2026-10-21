"""Explicit personal-calendar sync. OAuth secrets stay outside SQLite and backups."""
import base64,hashlib,json,os,secrets,threading,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,quote
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from .crm_planning import calendar_details

REDIRECT='http://127.0.0.1:8788/archive/calendar/callback'
API='https://www.googleapis.com/calendar/v3/calendars/primary/events'
_lock=threading.RLock()

class CalendarError(ValueError):
    def __init__(self,status):
        self.status=status
        super().__init__({401:'Google требует повторного подключения календаря.',403:'Google не разрешил доступ к календарю. Проверьте Calendar API и права OAuth.',404:'Связанное событие не найдено в этом календаре.',410:'Событие удалено в Google Calendar.',412:'Встреча изменилась в Google. Сначала получите изменения из календаря.'}.get(status,'Google Calendar не ответил. Изменения сохранены локально; синхронизацию можно повторить.'))

def http(method,url,body=None,headers=None,form=False):
    data=(urlencode(body).encode() if form else json.dumps(body).encode()) if body is not None else None
    request=Request(url,data=data,method=method,headers={**({'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'} if data else {}),**(headers or {})})
    try:
        with urlopen(request,timeout=20) as response:return json.loads(response.read() or '{}')
    except HTTPError as error:raise CalendarError(error.code) from None
    except (URLError,TimeoutError,OSError,ValueError):raise CalendarError(0) from None

def equivalent(remote,body):
    for key in ('summary','description','location','status'):
        if remote.get(key,'')!=body[key]:return False
    for key in ('start','end'):
        try:
            left=datetime.fromisoformat(remote[key]['dateTime'].replace('Z','+00:00'));right=datetime.fromisoformat(body[key]['dateTime'])
            if not left.tzinfo or left!=right:return False
        except (KeyError,ValueError,TypeError):return False
    return True

class GoogleCalendar:
    def __init__(self,root,transport=http):self.root=Path(root);self.path=self.root/'.cache/calendar/oauth.json';self.pending={};self.transport=transport
    def tokens(self):
        try:return json.loads(self.path.read_text())
        except (FileNotFoundError,ValueError):return {}
    def persist(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True);os.chmod(self.path.parent,0o700)
        temp=self.path.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as file:json.dump(data,file)
        os.chmod(temp,0o600);os.replace(temp,self.path)
    def status(self):
        return {'configured':bool(os.getenv('GOOGLE_CALENDAR_CLIENT_ID') and os.getenv('GOOGLE_CALENDAR_CLIENT_SECRET')),'connected':bool(self.tokens().get('refresh_token')),'setup_hint':'Для синхронизации включите Google Calendar API и создайте OAuth-клиент типа Web application. Добавьте redirect URI '+REDIRECT+'; GOOGLE_CALENDAR_CLIENT_ID и GOOGLE_CALENDAR_CLIENT_SECRET задайте в локальном .env, затем перезапустите сервис. Без подключения доступны .ics и ручное добавление в Google.'}
    def connect(self):
        if not self.status()['configured']:raise ValueError(self.status()['setup_hint'])
        state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);self.pending={k:v for k,v in self.pending.items() if v[0]>time.time()};self.pending[state]=(time.time()+600,verifier)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':os.environ['GOOGLE_CALENDAR_CLIENT_ID'],'redirect_uri':REDIRECT,'response_type':'code','scope':'https://www.googleapis.com/auth/calendar.events.owned','access_type':'offline','prompt':'consent','state':state,'code_challenge':challenge,'code_challenge_method':'S256'})}
    def callback(self,state,code):
        expires,verifier=self.pending.pop(state,(0,''))
        if expires<time.time() or not code:raise ValueError('Вход в Google истёк или отменён. Подключите календарь заново.')
        with _lock:
            data=self.transport('POST','https://oauth2.googleapis.com/token',{'client_id':os.environ['GOOGLE_CALENDAR_CLIENT_ID'],'client_secret':os.environ['GOOGLE_CALENDAR_CLIENT_SECRET'],'redirect_uri':REDIRECT,'code':code,'code_verifier':verifier,'grant_type':'authorization_code'},form=True)
            if not data.get('refresh_token'):raise ValueError('Google не выдал долгосрочный доступ. Повторите подключение с разрешением календаря.')
            data['expires_at']=time.time()+data.get('expires_in',3600);self.persist(data)
    def request(self,method,url,body=None,headers=None):
        with _lock:
            data=self.tokens()
            if not data.get('refresh_token'):raise ValueError('Сначала подключите Google Calendar в разделе встреч.')
            if data.get('expires_at',0)<time.time()+60:
                refreshed=self.transport('POST','https://oauth2.googleapis.com/token',{'client_id':os.getenv('GOOGLE_CALENDAR_CLIENT_ID',''),'client_secret':os.getenv('GOOGLE_CALENDAR_CLIENT_SECRET',''),'refresh_token':data['refresh_token'],'grant_type':'refresh_token'},form=True)
                data.update(refreshed);data['expires_at']=time.time()+refreshed.get('expires_in',3600);self.persist(data)
            return self.transport(method,url,body,headers={'Authorization':'Bearer '+data['access_token'],**(headers or {})})

    def sync(self,store,app_id,appointment_id,revision,direction,discard_local=False):
        if direction not in ('push','pull'):raise ValueError('Неизвестное направление синхронизации.')
        with _lock:
            item=store.appointment(app_id,appointment_id);app=store.get(app_id)
            if item['revision']!=revision:raise ValueError('Встреча уже изменена. Обновите карточку.')
            event_id=item['event_id'] or 'cv'+hashlib.sha256(appointment_id.encode()).hexdigest()[:40];url=API+'/'+quote(event_id,safe='')
            try:remote=self.request('GET',url)
            except CalendarError as e:
                if e.status!=404 or item['event_id'] or direction=='pull':raise
                remote=None
            if remote and not (remote.get('status')=='cancelled' and item['event_id']) and remote.get('extendedProperties',{}).get('private',{}).get('cv_matcher_appointment')!=appointment_id:raise ValueError('Событие не связано с этой встречей CRM.')
            if direction=='pull':
                if item['calendar_revision']!=revision and discard_local is not True:raise ValueError('Есть несинхронизированные изменения в CRM. Сначала согласуйте их с календарём.')
                if remote.get('status')=='cancelled':change={**item,'status':'cancelled'}
                else:
                    start=remote.get('start',{});end=remote.get('end',{})
                    if not start.get('dateTime') or not end.get('dateTime'):raise ValueError('В Google встреча стала событием на весь день. Укажите время в CRM вручную.')
                    change={**item,'start_at':start['dateTime'],'end_at':end['dateTime'],'time_zone':start.get('timeZone',item['time_zone']),'location':remote.get('location','')}
                updated=store.save_appointment(app_id,change,actor='google_calendar');revision=updated['revision']
            else:
                title,details=calendar_details(app,item)
                body={'summary':title,'description':details,'location':item['location'],'start':{'dateTime':item['start_at'],'timeZone':item['time_zone']},'end':{'dateTime':item['end_at'],'timeZone':item['time_zone']},'status':'cancelled' if item['status']=='cancelled' else 'confirmed','extendedProperties':{'private':{'cv_matcher_appointment':appointment_id}}}
                if remote:
                    if item['etag'] and item['etag']!=remote.get('etag'):raise CalendarError(412)
                    if not item['etag'] and not equivalent(remote,body):raise ValueError('В Google уже есть эта встреча с другими данными. Обновление не выполнено; проверьте событие в календаре.')
                    remote=self.request('PATCH',url+'?sendUpdates=none',body,headers={'If-Match':remote['etag']})
                else:
                    if item['status']=='cancelled':raise ValueError('Отменённая встреча не создаётся в календаре.')
                    try:remote=self.request('POST',API+'?sendUpdates=none',{'id':event_id,**body})
                    except CalendarError as e:
                        if e.status==409:raise ValueError('Событие уже создано. Повторите синхронизацию для проверки его состояния.') from None
                        raise
            # Preserve the synced revision even if another client edited the appointment meanwhile.
            with store.connect() as db:
                db.execute('INSERT OR REPLACE INTO calendar_links VALUES(?,?,?,?,?,?)',(appointment_id,event_id,remote.get('etag'),revision,remote.get('htmlLink',''),datetime.now(timezone.utc).isoformat()))
                store._event(db,app_id,'calendar_synced',{'id':appointment_id,'revision':revision,'direction':direction})
            return store.appointment(app_id,appointment_id)
