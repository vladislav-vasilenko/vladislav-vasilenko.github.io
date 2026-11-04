"""Block-by-block review between the published portfolio and the latest HH capture.

Nothing here calls a model or writes to HH. In block mode automatic publication
keeps the reviewed site text; HH changes wait until the owner decides on them.
"""
import difflib
import re
from .archive_store import digest, now_iso
from .portfolio_translations import FIELDS, MONTHS, current_translations, validate_translation
from .resume_files import redact_contacts
from . import portfolio_publication as publication

ACTIONS = ('hh', 'keep', 'rewrite')
LABELS = (('company', 'Компания'), ('role', 'Роль'), ('period', 'Период'), ('duration', 'Продолжительность'), ('description', 'Описание'))


def word_diff(old, new):
    a, b = re.findall(r'\s+|\S+', old or ''), re.findall(r'\s+|\S+', new or '')
    if len(a) * len(b) > 40000000:
        return [{'op': 'del', 'text': old}, {'op': 'add', 'text': new}]
    result = []
    def push(op, tokens):
        text = ''.join(tokens)
        if not text: return
        if result and result[-1]['op'] == op: result[-1]['text'] += text
        else: result.append({'op': op, 'text': text})
    for tag, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal': push('same', a[i:j])
        else: push('del', a[i:j]); push('add', b[k:l])
    return result


def period_start(value):
    for month, year in re.findall(r'([A-Za-zА-Яа-яЁё]+)\s+((?:19|20)\d{2})', (value or '').lower()):
        if month in MONTHS: return int(year), MONTHS[month]
    return 0, 0


def block_key(row):
    year, month = period_start(row.get('period'))
    company = re.sub(r'\W+', ' ', row.get('company', '').lower()).strip()
    return f'experience:{company}|{year:04d}-{month:02d}'


def content(row):
    return {name: row.get(name, '') for name, _ in LABELS}


def pair_rows(site_rows, hh_rows):
    """Exact company and start date first; then the closest unique text for renamed roles or edited dates."""
    pairs, free = [], list(site_rows)
    unmatched = []
    for row in hh_rows:
        found = next((item for item in free if block_key(item) == block_key(row)), None)
        if found: free.remove(found); pairs.append((found, row))
        else: unmatched.append(row)
    text = lambda row: ' '.join(row.get(name, '') for name in ('company', 'role', 'description'))
    scored = sorted(((difflib.SequenceMatcher(None, text(s)[:4000], text(h)[:4000], autojunk=False).ratio(), i, j)
                     for i, s in enumerate(free) for j, h in enumerate(unmatched)), reverse=True)
    used_site, used_hh = set(), set()
    for score, i, j in scored:
        if score < .5 or i in used_site or j in used_hh: continue
        used_site.add(i); used_hh.add(j); pairs.append((free[i], unmatched[j]))
    pairs += [(None, row) for j, row in enumerate(unmatched) if j not in used_hh]
    pairs += [(row, None) for i, row in enumerate(free) if i not in used_site]
    return pairs


def validate_site(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('experience'), list) or not isinstance(payload.get('title', ''), str):
        raise ValueError('Опубликованный файл портфолио имеет неверный формат.')
    for row in payload['experience']:
        if not isinstance(row, dict) or not all(isinstance(row.get(name), str) for name in FIELDS):
            raise ValueError('Опубликованный файл портфолио имеет неверный формат.')
    return payload


def site_blocks(payload):
    return {'title': payload.get('title', ''), 'about': payload.get('about') or {}, 'experience': payload['experience'],
            'language': (payload.get('source') or {}).get('language', ''), 'captured_at': now_iso()}


def compare(archive, publisher=None):
    publisher = publisher or publication.Publisher()
    site = validate_site(publisher.read_site())
    proposal = publication.preview(archive); state = publication.read(archive); hh = proposal['candidate']
    language = proposal['payload']['source']['language']; other = 'en' if language == 'ru' else 'ru'
    decisions = state.get('block_decisions', {})
    _, current, _ = current_translations(state, proposal['resume_id'], site['experience'], language)
    translated = {row['id']: row for row in (current.get(other) or {}).get('items', [])}
    def status(key, old, new, changed, label, kind, **extra):
        name = 'added' if old is None else 'removed' if new is None else 'changed' if changed else 'same'
        return {'key': key, 'kind': kind, 'label': label, 'status': name, 'site': old, 'hh': new,
                'acknowledged': name != 'same' and decisions.get(key, {}).get('hh_basis') == digest(new), **extra}
    title = site.get('title', ''); about = (site.get('about') or {}).get('text', ''); new_about = (hh['about'] or {}).get('text', '')
    blocks = [status('title', {'text': title}, {'text': hh['title']}, title != hh['title'], 'Заголовок резюме', 'title', diff={'text': word_diff(title, hh['title'])}, fields_changed=['text'] if title != hh['title'] else []),
              status('about', {'text': about}, {'text': new_about}, about != new_about, 'Введение', 'about', diff={'text': word_diff(about, new_about)}, fields_changed=['text'] if about != new_about else [],
                     site_translation={'text': ((site.get('about') or {}).get('translations') or {}).get(other, '')})]
    for old, new in pair_rows(site['experience'], hh['experience']):
        old_values, new_values = content(old) if old else None, content(new) if new else None
        changed = [name for name, _ in LABELS if old and new and old_values[name] != new_values[name]]
        row = new or old
        blocks.append(status(block_key(new or old), old_values, new_values, bool(changed), row['company'] + ' · ' + row['period'], 'experience', fields_changed=changed,
                             diff={name: word_diff(old_values[name] if old else '', new_values[name] if new else '') for name, _ in LABELS},
                             site_translation=content(translated[old['id']]) if old and old['id'] in translated else None, site_id=old['id'] if old else None))
    pending = [b for b in blocks if b['status'] != 'same' and not b['acknowledged']]
    return {'blocks': blocks, 'basis': digest({'site': [site.get('title'), site.get('about'), site['experience']], 'hh': hh}),
            'captured_at': proposal['payload']['source']['captured_at'], 'source_url': proposal['payload']['source']['url'],
            'resume_title': proposal['resume_title'], 'block_review': bool(state.get('block_review')), 'auto_publish': bool(state.get('enabled')),
            'translation_language': other if current.get(other) else None,
            'counts': {'pending': len(pending), 'same': sum(b['status'] == 'same' for b in blocks), 'acknowledged': sum(b['acknowledged'] for b in blocks)}}


def clean_text(value, minimum, maximum, message):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum: raise ValueError(message)
    if redact_contacts(value).strip() != value.strip(): raise ValueError('Уберите контактные данные из публичного блока.')
    return value.strip()


def clean_row(value):
    if not isinstance(value, dict): raise ValueError('Заполните поля переписанного блока.')
    row = {}
    for name, label in LABELS:
        minimum = 0 if name == 'duration' else 1
        row[name] = clean_text(value.get(name, ''), minimum, 100000 if name == 'description' else 2000, 'Заполните поле «' + label + '».')
    if period_start(row['period']) == (0, 0): raise ValueError('Период должен содержать месяц и год.')
    return row


def apply_blocks(archive, data, publisher=None):
    publisher = publisher or publication.Publisher()
    if data.get('reviewed') is not True: raise ValueError('Подтвердите проверку блоков перед публикацией.')
    decisions = data.get('decisions')
    if not isinstance(decisions, dict) or not decisions: raise ValueError('Выберите решение хотя бы для одного блока.')
    result = compare(archive, publisher)
    if data.get('basis') != result['basis']: raise ValueError('Сайт или снимок HH изменились. Обновите сравнение.')
    blocks = {b['key']: b for b in result['blocks']}
    unknown = [key for key in decisions if key not in blocks]
    if unknown or any(not isinstance(v, dict) or v.get('action') not in ACTIONS for v in decisions.values()):
        raise ValueError('Решения не соответствуют текущему сравнению.')
    site = validate_site(publisher.read_site()); proposal = publication.preview(archive); state = publication.read(archive); hh = proposal['candidate']
    language = proposal['payload']['source']['language']; other = 'en' if language == 'ru' else 'ru'
    if (site.get('source') or {}).get('language', language) != language: raise ValueError('Язык основного резюме изменился. Сначала отключите режим блоков и проверьте публикацию целиком.')
    title, about = site.get('title', ''), dict(site.get('about') or {})
    remembered = dict(state.get('block_decisions', {}))
    for key in ('title', 'about'):
        choice = decisions.get(key)
        if not choice: continue
        block = blocks[key]
        if choice['action'] == 'hh' and block['status'] == 'same': raise ValueError('Этот блок уже совпадает с HH.')
        if key == 'title' and choice['action'] != 'keep':
            title = hh['title'] if choice['action'] == 'hh' else clean_text((choice.get('value') or {}).get('text'), 1, 1000, 'Заголовок должен содержать от 1 до 1000 символов.')
        if key == 'about' and choice['action'] != 'keep':
            had = ((site.get('about') or {}).get('translations') or {}).get(other)
            about = dict(hh['about']) if choice['action'] == 'hh' else {'text': clean_text((choice.get('value') or {}).get('text'), 30, 6000, 'Введение должно содержать от 30 до 6000 символов.'), 'language': language, 'origin': 'reviewed', 'translations': {}}
            translations = dict(about.get('translations') or {})
            translation = (choice.get('translation') or {}).get('text')
            if translation or had:
                translations[other] = clean_text(translation, 30, 6000, 'Нужен проверенный перевод введения от 30 до 6000 символов.')
                about['origin'] = 'reviewed'
            translations[language] = about['text']; about['translations'] = translations
        remembered[key] = {'action': choice['action'], 'hh_basis': digest(block['hh']), 'saved_at': now_iso()}
    drafts = dict(state.get('experience_translations', {}))
    _, current, _ = current_translations(state, proposal['resume_id'], site['experience'], language)
    old_rows = {row['id']: row for row in (current.get(other) or {}).get('items', [])}
    rows, translations_new = [], []
    for block in result['blocks']:
        if block['kind'] != 'experience': continue
        choice = decisions.get(block['key']); action = choice['action'] if choice else 'keep'
        if action == 'hh' and block['status'] == 'same': raise ValueError('Этот блок уже совпадает с HH.')
        if choice: remembered[block['key']] = {'action': action, 'hh_basis': digest(block['hh']), 'saved_at': now_iso()}
        value = block['site'] if action == 'keep' else block['hh'] if action == 'hh' else clean_row(choice.get('value'))
        if value is None: continue
        row = dict(value); rows.append(row)
        if old_rows:
            if value == block['site']: translations_new.append((row, old_rows.get(block['site_id'])))
            else:
                translated = choice.get('translation')
                if not isinstance(translated, dict): raise ValueError('Нужен проверенный перевод для блока: ' + block['label'])
                translations_new.append((row, {name: translated.get(name, '') for name, _ in LABELS}))
    order = sorted(range(len(rows)), key=lambda i: (tuple(-v for v in period_start(rows[i]['period'])), i))
    experience = []
    for position, index in enumerate(order):
        rows[index]['id'] = 'hh-' + str(position); experience.append({name: rows[index][name] for name in FIELDS})
    if len(experience) > 80 or not experience: raise ValueError('На сайте должен оставаться хотя бы один блок опыта, не более 80.')
    basis = digest(experience)
    if old_rows:
        translated_rows = [{**(translation or {}), 'id': row['id']} for row, translation in translations_new]
        drafts[other] = {'resume_id': proposal['resume_id'], 'basis': basis, 'language': other, 'saved_at': now_iso(),
                         'items': validate_translation(translated_rows, experience, other, language)}
    snapshot = {'block_review': state.get('block_review', False), 'site_blocks': state.get('site_blocks'),
                'block_decisions': state.get('block_decisions', {}), 'experience_translations': state.get('experience_translations', {})}
    publication.write(archive, block_review=True, block_decisions=remembered, experience_translations=drafts,
                      site_blocks={'title': title, 'about': about, 'experience': experience, 'language': language, 'captured_at': now_iso()})
    outcome = publication.publish(archive, publisher)
    if outcome.get('phase') not in ('published', 'up_to_date'):
        publication.write(archive, **snapshot)
        raise ValueError(outcome.get('error') or 'Публикация уже выполняется. Сайт не изменён; повторите позже.')
    return {'phase': outcome['phase'], 'commit': outcome.get('commit') if outcome['phase'] == 'published' else None, 'comparison': compare(archive, publisher)}


def set_mode(archive, enabled, publisher=None):
    if type(enabled) is not bool: raise ValueError('Укажите режим проверки по блокам.')
    if not enabled: return publication.write(archive, block_review=False)
    site = validate_site((publisher or publication.Publisher()).read_site())
    return publication.write(archive, block_review=True, site_blocks=site_blocks(site))
