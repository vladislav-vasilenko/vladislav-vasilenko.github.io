"""Import any accessible HH resume by URL; ownership/catalog membership is irrelevant."""
import json
import re
from urllib.parse import urlsplit


def target(url):
    try:
        u = urlsplit(str(url).strip())
        match = re.fullmatch(r'/resume/([a-f0-9]{38})/?', u.path, re.I)
        if u.scheme != 'https' or not (u.hostname == 'hh.ru' or (u.hostname or '').endswith('.hh.ru')) or u.username or u.password or u.port not in (None, 443) or not match:
            raise ValueError()
        identifier = match[1].lower()
        return {'resume_id': identifier, 'url': 'https://hh.ru/resume/'+identifier}
    except (ValueError, TypeError):
        raise ValueError('Вставьте прямую ссылку https://hh.ru/resume/… на резюме. Оно должно быть доступно в вашем Chrome.') from None


def start(store, url):
    value = target(url)
    return {**value, 'command_id': store.queue_command('resume_import', payload={'resume_id': value['resume_id']}), 'api_requests': 0}


def read(store, command_id):
    with store.connect() as db:
        row = db.execute("SELECT state,result,payload FROM browser_commands WHERE id=? AND kind='resume_import'", (command_id,)).fetchone()
    if not row:
        raise ValueError('Задача импорта резюме не найдена.')
    return {'state': row['state'], 'result': json.loads(row['result'] or '{}'), 'resume_id': json.loads(row['payload'])['resume_id'], 'api_requests': 0}
