"""Scheduled notification policy, independent of Telegram transport and collection."""
import json
import time
from datetime import datetime, timezone
from .application_workflow import packed
from .application_attention import items

MODES = {'tasks': 'Незавершённые отклики и проверки', 'both': 'Проверки и новые вакансии',
         'discovery': 'Только новые вакансии', 'off': 'Без уведомлений по расписанию'}

def config(store, values=None):
    if values is not None:
        if not isinstance(values, dict) or set(values) != {'mode'} or not isinstance(values.get('mode'),str) or values['mode'] not in MODES:
            raise ValueError('Выберите режим уведомлений Telegram.')
        store.setting('telegram_notifications', packed(values))
    saved = json.loads(store.setting('telegram_notifications') or '{}')
    return {'mode': saved.get('mode', 'tasks'), 'modes': MODES}

def status(service):
    return {**config(service.store), 'times': [v.strip() for v in service.times], 'timezone': str(service.zone)}

def review_payload(store, identifiers=None, now=None):
    queue = [item for item in items(store, now) if item['reminder_due'] and (identifiers is None or item['id'] in identifiers)]
    if not queue: return None
    shown = queue[:8]
    text = 'Пора продолжить отклики · ' + str(len(queue)) + '\nТа же очередь действий, что в разделе «Сегодня».\n'
    for index, item in enumerate(shown, 1):
        text += '\n' + str(index) + '. ' + item['title'][:100] + ' · ' + item['company'][:70] + '\n' + item['next'][:140] + '\n'
    if len(queue) > len(shown): text += '\nЕщё ' + str(len(queue) - len(shown)) + ' — в списке откликов.\n'
    text += '\nОткройте карточку и проверьте следующий шаг. Отправка требует вашего подтверждения.'
    keyboard = [[(str(index) + '. ' + item['title'][:45], 'w:open:' + item['id'])] for index, item in enumerate(shown, 1)]
    keyboard.append([('Все отклики', 'w:menu:apps')])
    return {'text': text, 'keyboard': keyboard, 'ids': [item['id'] for item in queue]}

def plan_reviews(service, slot, now=None):
    key = 'review-digest:' + slot.isoformat()
    payload = review_payload(service.store, now=now or slot)
    if payload is None: return
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM workflow_delivery WHERE key=?', (key,)).fetchone(): return
        service.store.setting_in(db, 'notification:' + key, packed({'kind': 'reviews', 'ids': payload['ids'], 'expires': slot.timestamp() + 4 * 3600}))
        service.enqueue(key, payload['text'], payload['keyboard'], db=db)

def prepare_delivery(service, key, now=None):
    """Revalidate queued reminders after sleep; never resend uncertain attempts."""
    now = now or datetime.now(timezone.utc)
    raw = service.store.setting('notification:' + key)
    reason = None; payload = None
    mode = config(service.store)['mode']
    if raw:
        meta = json.loads(raw)
        if now.timestamp() >= meta['expires']: reason = 'Истёк интервал уведомления.'
        elif meta['kind'] == 'reviews':
            if mode not in ('tasks', 'both'): reason = 'Напоминания о проверках выключены.'
            else:
                payload = review_payload(service.store, meta['ids'], now)
                if payload is None: reason = 'Действия уже завершены или отложены.'
        elif meta['kind'] == 'recommendation':
            if mode not in ('both', 'discovery'): reason = 'Подборки по расписанию выключены.'
            else:
                eligible = service.candidates(fresh=True, now=now)
                if not any(c['job']['id'] == meta['vacancy_id'] for c in eligible): reason = 'Актуальность рекомендации больше не подтверждена.'
    # Old scheduled search/progress headers also obey the newly selected policy.
    if key.startswith('digest:'):
        if mode not in ('both', 'discovery'): reason = 'Подборки по расписанию выключены.'
        else:
            try:
                stamp = datetime.fromisoformat(key[len('digest:'):].removesuffix(':progress'))
                if now.timestamp() - stamp.timestamp() >= 4 * 3600: reason = 'Истёк интервал подборки.'
            except ValueError: pass
    if reason:
        with service.store.connect() as db:
            db.execute("UPDATE workflow_delivery SET state='cancelled',last_error=?,revision=revision+1,updated_at=? WHERE key=? AND state='pending'", (reason, time.time(), key))
        return False
    if payload:
        with service.store.connect() as db:
            db.execute("UPDATE workflow_delivery SET payload=? WHERE key=? AND state='pending'", (packed({'text': payload['text'], 'keyboard': payload['keyboard']}), key))
    return True
