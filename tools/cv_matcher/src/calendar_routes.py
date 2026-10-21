"""Same-origin explicit calendar actions; OAuth callback uses a one-use state + PKCE."""
import asyncio,json
from fastapi import Request,HTTPException
from fastapi.responses import Response,HTMLResponse
from .google_calendar_sync import GoogleCalendar
from .crm_planning import icalendar,google_link

def install_calendar(app,root,store):
    calendar=GoogleCalendar(root);app.state.google_calendar=calendar
    @app.get('/archive/calendar/status')
    async def status():return calendar.status()
    @app.get('/archive/calendar/ics')
    async def ics(app_id:str,appointment_id:str):
        try:
            s=store();item=s.appointment(app_id,appointment_id)
            return Response(icalendar(s.get(app_id),item),media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="interview.ics"','Cache-Control':'no-store'})
        except ValueError as e:raise HTTPException(422,str(e)) from None
    @app.get('/archive/calendar/callback')
    async def callback(request:Request):
        query=getattr(request.state,'calendar_oauth_query',{})
        try:await asyncio.to_thread(calendar.callback,query.get('state',''),query.get('code',''))
        except ValueError: return HTMLResponse('<p>Вход не завершён. Вернитесь в CRM и подключите календарь заново.</p>',status_code=400,headers={'Referrer-Policy':'no-referrer','Cache-Control':'no-store'})
        return HTMLResponse('<meta name="referrer" content="no-referrer"><p>Google Calendar подключён. Вернитесь в CRM и обновите карточку встречи.</p><a href="/">Открыть CRM</a>',headers={'Referrer-Policy':'no-referrer','Cache-Control':'no-store'})
    @app.post('/archive/calendar')
    async def action(request:Request):
        body=await request.body()
        if len(body)>8192:raise HTTPException(413,'Запрос слишком большой.')
        try:
            data=json.loads(body);op=data['op']
            if op=='connect':return calendar.connect()
            s=store();app_id=data['app_id'];identifier=data['appointment_id']
            if op=='link':return {'url':google_link(s.get(app_id),s.appointment(app_id,identifier))}
            if op in ('push','pull'):return await asyncio.to_thread(calendar.sync,s,app_id,identifier,data['revision'],op,data.get('discard_local') is True)
            raise ValueError('Неизвестное действие календаря.')
        except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e) if isinstance(e,ValueError) else 'Некорректный запрос календаря.') from None
