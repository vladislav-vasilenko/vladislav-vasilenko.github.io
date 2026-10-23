"""Resumable GitHub vacancy import; no CV uploads, model calls or inferred closures."""
import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from bs4 import BeautifulSoup
from .archive_store import canonical, digest, now_iso
from .board_import import identity
from .github_collection_api import GitHubAPI, GitHubError, REPOSITORY

KEY = 'github-collection-import'
BATCH_SIZE = 100
LEASE_SECONDS = 600
COUNTERS = ('added', 'updated', 'unchanged', 'protected', 'rejected', 'duplicates')


def read(db):
    row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {'enabled': False, 'phase': 'idle', 'history': []}


def write(db, state):
    db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (KEY, canonical(state)))


def status(archive):
    with archive.connect() as db:
        state = read(db)
    state['running'] = state.get('phase') in ('checking', 'downloading', 'importing') and state.get('lease_until', 0) > time.time()
    if state.get('phase') in ('checking', 'downloading', 'importing') and not state['running']:
        state['phase'] = 'interrupted'
    return {k: v for k, v in state.items() if k not in ('lease', 'lease_until')} | {
        'repository': REPOSITORY, 'interval_seconds': 3600, 'api_requests_models': 0,
    }


def configure(archive, enabled):
    if type(enabled) is not bool:
        raise ValueError('Нужно включить или выключить автопроверку.')
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE'); state = read(db); state['enabled'] = enabled; write(db, state)
    return status(archive)


def acquire(archive):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE'); state = read(db)
        if state.get('lease_until', 0) > time.time():
            return None
        lease = uuid.uuid4().hex
        state.update(lease=lease, lease_until=time.time() + LEASE_SECONDS, phase='checking', error='', last_checked_at=now_iso())
        write(db, state)
    return lease


def update(archive, lease, **fields):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE'); state = read(db)
        if state.get('lease') != lease:
            raise GitHubError('Импорт уже продолжен другим процессом.')
        state.update(fields); state['lease_until'] = time.time() + LEASE_SECONDS; write(db, state)
    return state


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not parsed.tzinfo or parsed.timestamp() > time.time() + 300:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ValueError('Нет корректного времени получения описания.') from None


def normalize(row, exported_at):
    if not isinstance(row, dict):
        raise ValueError('Запись не является объектом.')
    link = row.get('link', '')
    if not isinstance(link, str) or len(link) > 3000:
        raise ValueError('Некорректная ссылка.')
    u = urlsplit(link)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError('Нужна HTTPS-ссылка без учётных данных.')
    if u.hostname in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Локальный адрес не является вакансией.')
    params = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
              if not re.match(r'^(utm_|hhtm|__rr|abt_)|^(from|ref|source|trackingId)$', k, re.I)]
    url = urlunsplit(('https', u.hostname.lower(), re.sub('/+', '/', u.path).rstrip('/') or '/', urlencode(sorted(params)), ''))
    valid = identity(url)
    if not valid:
        raise ValueError('Ссылка не соответствует вакансии.')
    title = row.get('title'); text = row.get('description', '')
    if not isinstance(title, str) or not title.strip() or len(title) > 1000 or not isinstance(text, str) or len(text) > 100000:
        raise ValueError('Нет названия или недопустимый размер текста.')
    company = row.get('company', '')
    if not isinstance(company, str) or len(company) > 1000:
        raise ValueError('Некорректное название компании.')
    if re.search(r'<(?:p|div|ul|li|h[1-6])(?:\s|>)', text, re.I):
        soup = BeautifulSoup(text, 'html.parser')
        for el in soup.select('script,style,form,nav'): el.decompose()
        text = soup.get_text('\n', strip=True)
    quality = row.get('description_quality')
    if quality not in (None, 'full', 'snippet', 'missing', 'needs_review'):
        raise ValueError('Неизвестный признак полноты описания.')
    quality = quality or ('needs_review' if len(text.strip()) >= 150 else 'snippet')
    if len(text.strip()) < 150:
        quality = 'snippet'
    elif re.search(r'access denied|verify you are human|captcha|доступ ограничен|подтвердите.{0,20}не робот', text, re.I):
        quality = 'needs_review'
    # Listing last_seen is never the age of a full description. first_seen is
    # conservative for legacy cumulative exports; it cannot refresh old text.
    captured = row.get('description_fetched_at') or row.get('collected_at') or row.get('first_seen')
    if not captured:
        quality = 'needs_review' if quality == 'full' else quality
        captured = exported_at
    stamp = timestamp(captured)
    if stamp > exported_at:
        raise ValueError('Время описания позже времени выгрузки.')
    locations = row.get('locations', [])
    if not isinstance(locations, list) or len(locations) > 100 or any(not isinstance(x, str) or len(x) > 500 for x in locations):
        raise ValueError('Некорректные места работы.')
    data = {**valid, 'title': title.strip(), 'company': company.strip(), 'description': text,
            'description_quality': quality, 'locations': locations, 'collected_at': stamp,
            'source': 'github_actions', 'source_page': valid['link'], 'collector': 'github_actions',
            'adapter_id': 'github-json', 'adapter_version': '1', 'extraction_method': 'imported_export'}
    from .vacancy_locations import normalize_locations
    data=normalize_locations({**data,**{k:row[k] for k in ('location','city','work_formats','work_format','locations_status','locations_complete') if k in row}})
    for key in ('pub_date', 'origin_query'):
        if isinstance(row.get(key), str) and len(row[key]) <= 3000: data[key] = row[key]
    return data


def validate_export(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('vacancies'), list) or len(payload['vacancies']) > 20000:
        raise ValueError('Выгрузка должна содержать до 20000 вакансий.')
    exported_at = timestamp(payload.get('last_updated'))
    if type(payload.get('total')) is not int or payload['total'] != len(payload['vacancies']):
        raise ValueError('Количество вакансий не соответствует выгрузке.')
    stats = payload.get('stats_last_run', {})
    if not isinstance(stats, dict) or len(stats) > 50:
        raise ValueError('Некорректный отчёт источников.')
    sources = []
    for name, values in stats.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', name) or not isinstance(values, dict):
            raise ValueError('Некорректный источник отчёта.')
        errors = values.get('errors', 0)
        if type(errors) is not int or errors < 0:
            raise ValueError('Некорректный счётчик ошибок источника.')
        sources.append({'source': name, 'errors': errors})
    return exported_at, sources


def apply_batch(archive, lease, rows, offset):
    """Records and checkpoint commit together; crash/retry never doubles counts."""
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE'); state = read(db)
        if state.get('lease') != lease or state['offset'] != offset:
            raise GitHubError('Пакет уже обработан другим импортом.')
        for data in rows:
            old = db.execute("SELECT * FROM entities WHERE kind='vacancy' AND id=?", (data['id'],)).fetchone()
            prior = json.loads(old['payload']) if old else None
            if prior and (data['collected_at'] < old['source_at'] or prior['description_quality'] == 'full' and data['description_quality'] != 'full'):
                state['counts']['protected'] += 1
                continue
            db.execute('SAVEPOINT vacancy')
            try:
                archive._entity(db, 'vacancy', data['id'], data, now_iso())
                head = db.execute("SELECT content_hash FROM entities WHERE kind='vacancy' AND id=?", (data['id'],)).fetchone()[0]
                outcome = 'added' if not old else 'updated' if head != old['content_hash'] else 'unchanged'
                state['counts'][outcome] += 1
                db.execute('INSERT OR REPLACE INTO receipts VALUES(?,?,?,?)', ('github-actions-import', 'vacancy', data['id'], digest(data)))
                db.execute('RELEASE vacancy')
            except (ValueError, TypeError, KeyError):
                db.execute('ROLLBACK TO vacancy'); db.execute('RELEASE vacancy')
                state['counts']['rejected'] += 1
        state.update(offset=offset + len(rows), lease_until=time.time() + LEASE_SECONDS)
        write(db, state)


def pull(archive, lease=None, api=None):
    lease = lease or acquire(archive)
    if not lease: return status(archive)
    api = api or GitHubAPI()
    try:
        run = api.latest(); key = f'{run["id"]}:{run.get("run_attempt") or 1}'
        with archive.connect() as db: state = read(db)
        if state.get('cursor') == key:
            update(archive, lease, phase='up_to_date', latest_run=run, error='')
            return status(archive)
        update(archive, lease, phase='downloading', latest_run=run)
        payload, transport, warnings = api.export(run)
        exported_at, sources = validate_export(payload)
        records = {}; invalid = 0; duplicates = 0; examples = []
        for row in payload['vacancies']:
            try:
                data = normalize(row, exported_at)
                previous = records.get(data['id'])
                if previous:
                    duplicates += 1
                    rank = lambda x: (x['description_quality'] == 'full', x['collected_at'], len(x['description']))
                    if rank(previous) >= rank(data): continue
                records[data['id']] = data
            except (ValueError, TypeError):
                invalid += 1
                if len(examples) < 5: examples.append('Запись ' + str(len(records) + invalid + duplicates) + ': неверная структура, ссылка или время.')
        rows = sorted(records.values(), key=lambda r: r['id']); fingerprint = digest(rows)
        if datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(exported_at).timestamp() > 3 * 86400:
            warnings.append('Выгрузка старше трёх дней. Импорт не подтверждает текущую активность вакансий.')
        if run.get('conclusion') != 'success': warnings.append('Workflow завершился с ошибкой; состояние источников и дата данных показаны отдельно.')
        if state.get('pending_key') == key and state.get('fingerprint') == fingerprint:
            offset = state.get('offset', 0)
        else:
            offset = 0
            state = update(archive, lease, pending_key=key, fingerprint=fingerprint, offset=0,
                           counts={**dict.fromkeys(COUNTERS, 0), 'rejected': invalid, 'duplicates': duplicates})
        update(archive, lease, phase='importing', total=len(rows), input_total=len(payload['vacancies']),
               exported_at=exported_at, sources=sources, warnings=warnings, invalid_examples=examples, transport=transport)
        while offset < len(rows):
            batch = rows[offset:offset + BATCH_SIZE]
            apply_batch(archive, lease, batch, offset); offset += len(batch)
        with archive.connect() as db:
            db.execute('BEGIN IMMEDIATE'); state = read(db)
            if state.get('lease') != lease: raise GitHubError('Импорт продолжен другим процессом.')
            receipt = {'run': run, 'imported_at': now_iso(), 'exported_at': exported_at, 'counts': state['counts'],
                       'sources': sources, 'transport': transport, 'warnings': warnings}
            state.update(cursor=key, phase='complete', last_import=receipt, error='',
                         history=([receipt] + [h for h in state.get('history', []) if h['run']['id'] != run['id']])[:10])
            write(db, state)
    except Exception as error:
        # Raw CLI errors and source text never enter the dashboard/logs.
        message = str(error) if isinstance(error, (GitHubError, ValueError)) else 'Импорт прерван. Сохранённые пакеты останутся; повторная проверка продолжит обработку.'
        update(archive, lease, phase='error', error=message[:500])
    finally:
        with archive.connect() as db:
            db.execute('BEGIN IMMEDIATE'); state = read(db)
            if state.get('lease') == lease:
                state['lease_until'] = 0; write(db, state)
    return status(archive)


async def scheduler(archive_factory, period=30):
    while True:
        await asyncio.sleep(period)
        archive = archive_factory(); state = status(archive)
        if not state.get('enabled') or state['running']: continue
        try: checked = datetime.fromisoformat(state.get('last_checked_at', '')).timestamp()
        except ValueError: checked = 0
        if time.time() - checked < 3600: continue
        await asyncio.to_thread(pull, archive)
