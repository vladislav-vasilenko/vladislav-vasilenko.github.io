import json,os,sqlite3,tempfile,unittest,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.application_store import ApplicationStore
from src.archive_store import ArchiveStore
from src.crm_planning import date_time,icalendar
from src.google_calendar_sync import GoogleCalendar,CalendarError
from src.tests.test_archive import cv,job,record,CLIENT
from src.resume_source import content_hash
from src.workflow_bot import WorkflowBot
from src.tests.test_recruiter import Operator,update

class PlanningFixture:
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.path=self.root/'state.sqlite3';self.store=ApplicationStore(self.path);self.archive=ArchiveStore(self.path)
  at=datetime.now(timezone.utc).isoformat();self.cv=cv(text='Transformer PyTorch training. '*12,at=at);self.cv['content_hash']=content_hash(self.cv);self.jd=job(text='PyTorch Transformer research. '*15,at=at)
  self.archive.sync({'client_id':CLIENT,'records':[record('resume',self.cv),record('vacancy',self.jd)]});self.app=self.store.create({'resume_id':self.cv['id'],'bundle':{'resumes':[self.cv]},'vacancy':self.jd,'channel':'hh','goal':'DiT'});self.id=self.app['id']
 def meeting(self,**extra):return self.store.save_appointment(self.id,{'stage':'stage_1','title':'Техническое интервью','start_at':'2026-11-02T14:00','end_at':'2026-11-02T15:00','time_zone':'Europe/Moscow','location':'https://meet.google.com/test','notes':'Повторить DiT',**extra})

class PlanningTests(PlanningFixture,unittest.TestCase):
 def test_old_crm_migrates_without_losing_stage_and_reopens_idempotently(self):
  with self.store.connect() as db:
   db.execute('DROP TABLE application_crm');db.execute('CREATE TABLE application_crm(app_id TEXT PRIMARY KEY,stage TEXT,updated_at TEXT)');db.execute('INSERT INTO application_crm VALUES(?,?,?)',(self.id,'stage_2','old'))
  reopened=ApplicationStore(self.path);plan=reopened.workflow(self.id)['crm'];self.assertEqual(plan['stage'],'stage_2');self.assertEqual(plan['work_status'],'preparing');self.assertEqual(plan['updated_at'],'old');self.assertEqual(ApplicationStore(self.path).workflow(self.id)['crm'],plan)
 def test_ai_interview_defaults_to_waiting_then_independent_status_and_history(self):
  a=self.store.set_crm(self.id,'ai_screened');self.assertEqual(a['crm']['work_status'],'waiting_invitation');self.assertIn('командой',a['crm']['next_action'])
  a=self.store.set_crm(self.id,'ai_screened',work_status='preparing',next_action='Повторить flow matching',follow_up_at='2026-11-02T12:00+03:00',revision=a['crm']['revision'])
  self.assertEqual(a['crm']['follow_up_at'],'2026-11-02T09:00:00+00:00');self.assertEqual(a['crm']['stage'],'ai_screened')
  with self.assertRaisesRegex(ValueError,'уже изменён'):self.store.set_crm(self.id,'rejected',revision=1)
  self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':'hh_1','status':'viewed'}]});self.assertEqual(self.store.workflow(self.id)['crm']['work_status'],'preparing')
  a=self.store.set_crm(self.id,'offer');self.assertEqual(a['crm']['work_status'],'done');self.assertIsNone(a['crm']['follow_up_at'])
 def test_confirmed_hh_submission_advances_preparation_but_never_regresses_interview(self):
  self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':'hh_1','status':'submitted'}]});self.assertEqual(self.store.workflow(self.id)['crm']['stage'],'applied')
  self.store.set_crm(self.id,'stage_2');self.store.hh_sync({'source_url':'https://hh.ru/applicant/negotiations','records':[{'vacancy_id':'hh_1','status':'invited'}]});self.assertEqual(self.store.workflow(self.id)['crm']['stage'],'stage_2')
 def test_meeting_rescheduling_requires_revision_preserves_previous_text_and_ics_identity(self):
  first=self.meeting();self.assertEqual(first['start_at'],'2026-11-02T11:00:00+00:00');second=self.meeting(**{**first,'start_at':'2026-11-03T14:00','end_at':'2026-11-03T15:00'})
  self.assertEqual(first['id'],second['id']);self.assertEqual(second['revision'],2)
  with self.assertRaisesRegex(ValueError,'уже изменена'):self.meeting(**first)
  event=next(e for e in self.store.workflow(self.id)['events'] if e['type']=='appointment_saved');self.assertEqual(event['payload']['before']['start_at'],first['start_at'])
  text=icalendar(self.app,second);self.assertIn('UID:'+first['id'],text);self.assertIn('SEQUENCE:2',text);self.assertIn('DTSTART:20261103T110000Z',text);self.assertTrue(all(len(l.encode())<=75 for l in text.split('\r\n')))
  with self.assertRaises(ValueError):self.store.appointment('missing',second['id'])
 def test_dates_reject_dst_gaps_ambiguous_naive_values_and_negative_duration(self):
  for date in ['2026-03-29T02:30','2026-10-25T02:30']:
   with self.assertRaises(ValueError):date_time(date,'Europe/Berlin')
  self.assertEqual(date_time('2026-10-25T02:30+02:00','Europe/Berlin'),'2026-10-25T00:30:00+00:00')
  for change in [{'end_at':'2026-11-02T13:00'},{'time_zone':'Mars/Olympus'},{'status':'hired'}]:
   with self.assertRaises(ValueError):self.meeting(**change)
 def test_calendar_routes_require_session_origin_and_callbacks_reject_missing_state(self):
  from resume_import_server import create_app
  m=self.meeting()
  with TestClient(create_app('fixture',archive_path=self.path)) as c:
   self.assertEqual(c.get('/archive/calendar/status').status_code,401);self.assertEqual(c.get('/archive/calendar/callback?state=bad&code=bad').status_code,400)
   c.post('/archive/login',json={},headers={'X-Resume-Import-Token':'fixture'});self.assertEqual(c.get('/archive/calendar/status').status_code,200)
   body={'op':'link','app_id':self.id,'appointment_id':m['id']}
   self.assertEqual(c.post('/archive/calendar',json=body,headers={'Origin':'https://evil.test'}).status_code,401)
   result=c.post('/archive/calendar',json=body,headers={'Origin':'http://127.0.0.1:8788'});self.assertEqual(result.status_code,200);self.assertIn('calendar.google.com',result.json()['url'])
   response=c.get('/archive/calendar/ics',params={'app_id':self.id,'appointment_id':m['id']});self.assertIn('BEGIN:VCALENDAR',response.text)
   backup=c.get('/archive/export').text;self.assertIn('application_appointments',backup);self.assertNotIn('refresh_token',backup)

class FakeGoogle:
 def __init__(self):self.event=None;self.calls=[];self.version=0
 def __call__(self,method,url,body=None,headers=None,form=False):
  self.calls.append((method,url,body,headers));self.version+=1
  if method=='GET':
   if not self.event:raise CalendarError(404)
   return dict(self.event)
  if method=='PATCH':
   if headers.get('If-Match')!=self.event['etag']:raise CalendarError(412)
   self.event.update(body)
  elif method=='POST':self.event={**body,'htmlLink':'https://calendar.google.com/calendar/event?eid=test'}
  self.event['etag']='v'+str(self.version);return dict(self.event)

class CalendarTests(PlanningFixture,unittest.TestCase):
 def calendar(self):
  fake=FakeGoogle();calendar=GoogleCalendar(self.root,transport=fake);calendar.persist({'refresh_token':'private-refresh','access_token':'private-access','expires_at':time.time()+3600});return calendar,fake
 def test_push_creates_once_and_rescheduling_updates_same_event_with_etag(self):
  calendar,fake=self.calendar();first=self.meeting();linked=calendar.sync(self.store,self.id,first['id'],1,'push');self.assertEqual(linked['calendar_state'],'synced')
  second=self.meeting(**{**first,'start_at':'2026-11-03T14:00','end_at':'2026-11-03T15:00'});self.assertEqual(second['calendar_state'],'pending');linked2=calendar.sync(self.store,self.id,first['id'],2,'push')
  self.assertEqual(linked['event_id'],linked2['event_id']);self.assertEqual(sum(c[0]=='POST' for c in fake.calls),1);self.assertEqual(sum(c[0]=='PATCH' for c in fake.calls),1);self.assertEqual(calendar.path.stat().st_mode&0o777,0o600)
  self.assertNotIn('attendees',fake.event)
 def test_remote_change_never_silently_overwritten_and_pull_updates_local_date(self):
  calendar,fake=self.calendar();m=self.meeting();calendar.sync(self.store,self.id,m['id'],1,'push');fake.event['etag']='remote-change';fake.event['start']={'dateTime':'2026-11-04T14:00+03:00','timeZone':'Europe/Moscow'};fake.event['end']={'dateTime':'2026-11-04T15:00+03:00'}
  with self.assertRaises(CalendarError):calendar.sync(self.store,self.id,m['id'],1,'push')
  pulled=calendar.sync(self.store,self.id,m['id'],1,'pull');self.assertEqual(pulled['start_at'],'2026-11-04T11:00:00+00:00');self.assertEqual(pulled['calendar_state'],'synced')
 def test_explicit_pull_conflict_requires_discard_and_cancelled_event_is_imported(self):
  calendar,fake=self.calendar();m=self.meeting();calendar.sync(self.store,self.id,m['id'],1,'push');changed=self.meeting(**{**m,'notes':'Локальные правки'})
  fake.event={'id':fake.event['id'],'etag':'cancelled','status':'cancelled'}
  with self.assertRaises(ValueError):calendar.sync(self.store,self.id,m['id'],2,'pull')
  pulled=calendar.sync(self.store,self.id,m['id'],2,'pull',True);self.assertEqual(pulled['status'],'cancelled');self.assertEqual(pulled['notes'],'Локальные правки')
 def test_timeout_after_create_retries_same_id_even_when_google_normalizes_timezone(self):
  calendar,fake=self.calendar();m=self.meeting();normal=fake.__call__;failed=False
  def request(method,url,body=None,headers=None,form=False):
   nonlocal failed
   result=normal(method,url,body,headers,form)
   if method=='POST' and not failed:
    failed=True;fake.event['start']['dateTime']='2026-11-02T14:00:00+03:00';fake.event['end']['dateTime']='2026-11-02T15:00:00+03:00';raise CalendarError(0)
   return result
  calendar.transport=request
  with self.assertRaises(CalendarError):calendar.sync(self.store,self.id,m['id'],1,'push')
  linked=calendar.sync(self.store,self.id,m['id'],1,'push');self.assertEqual(linked['calendar_state'],'synced');self.assertEqual(sum(c[0]=='POST' for c in fake.calls),1)
 def test_oauth_state_is_one_use_and_pkce_secrets_never_returned(self):
  from urllib.parse import urlsplit,parse_qs
  with patch.dict(os.environ,{'GOOGLE_CALENDAR_CLIENT_ID':'client','GOOGLE_CALENDAR_CLIENT_SECRET':'private-secret'}):
   calendar=GoogleCalendar(self.root,transport=lambda *a,**k:{'access_token':'a','refresh_token':'r','expires_in':3600});result=calendar.connect();query=parse_qs(urlsplit(result['url']).query)
   self.assertIn('code_challenge',query);self.assertNotIn('private-secret',result['url']);calendar.callback(query['state'][0],'code')
   with self.assertRaises(ValueError):calendar.callback(query['state'][0],'code')
   self.assertTrue(calendar.status()['connected']);self.assertNotIn('refresh_token',json.dumps(calendar.status()))

class PlanningBotTests(PlanningFixture,unittest.IsolatedAsyncioTestCase):
 async def test_status_offline_prompt_and_scheduling_never_invoke_drafter(self):
  op=Operator();bot=WorkflowBot(self.store,op,42,drafter=lambda *a: (_ for _ in ()).throw(AssertionError('Paid model called')))
  await bot.update(update(callback=f'w:stage:{self.id}@ai_screened'));self.assertEqual(self.store.workflow(self.id)['crm']['work_status'],'waiting_invitation')
  await bot.update(update(callback=f'w:offline:{self.id}'));await bot.update(update(text='Составь письмо на 3 предложения. Мотивация: DiT.'));self.assertTrue(any('Мотивация: DiT.' in m[0] and 'КОНТЕКСТ' in m[0] for m in op.messages))
  await bot.update(update(callback=f'w:meeting:{self.id}'));await bot.update(update(text='2026-11-02 14:00 | 60 | Техинтервью | Москва'))
  self.assertEqual(len(self.store.workflow(self.id)['appointments']),1)
 async def test_reminders_are_durable_and_reschedule_gets_new_reminder(self):
  op=Operator();bot=WorkflowBot(self.store,op,42);m=self.meeting();now=datetime(2026,11,2,10,30,tzinfo=timezone.utc)
  await bot.plan_reminders(now);count=len(op.messages);self.assertEqual(count,1);await WorkflowBot(self.store,op,42).plan_reminders(now);self.assertEqual(len(op.messages),count)
  self.store.set_crm(self.id,'ai_screened',follow_up_at='2026-11-02T10:00Z');await bot.plan_reminders(now);self.assertEqual(len(op.messages),count+1)
  await bot.plan_reminders(now);self.assertEqual(len(op.messages),count+1)
