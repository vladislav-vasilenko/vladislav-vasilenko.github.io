"""Reviewed translations of the primary resume; another HH revision is never substituted."""
import re
from .archive_store import digest
from .resume_files import redact_contacts

MONTHS = {
    **{name: i for i, name in enumerate(('january','february','march','april','may','june','july','august','september','october','november','december'), 1)},
    **{name: i for i, name in enumerate(('январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь'), 1)},
}
FIELDS = ('id', 'company', 'role', 'period', 'duration', 'description')

def period_key(value):
    points = []
    for month, year in re.findall(r'([A-Za-zА-Яа-яЁё]+)\s+((?:19|20)\d{2})', value.lower()):
        if month not in MONTHS:
            raise ValueError('Не удалось сверить месяц в датах перевода.')
        points.append((int(year), MONTHS[month]))
    current = bool(re.search(r'\b(?:now|present|сейчас|настоящее)\b', value.lower()))
    if len(points) != (1 if current else 2):
        raise ValueError('Нужны полные даты с месяцами из исходного резюме.')
    return tuple(points), current

def duration_key(value):
    if not value.strip():
        return (0, 0)
    years = re.search(r'(\d+)\s*(?:год(?:а|ов)?|лет|years?)\b', value.lower())
    months = re.search(r'(\d+)\s*(?:месяц(?:а|ев)?|months?)\b', value.lower())
    if not years and not months:
        raise ValueError('Не удалось сверить продолжительность работы.')
    return (int(years[1]) if years else 0, int(months[1]) if months else 0)

def validate_translation(items, source, language, source_language):
    if language not in ('ru', 'en') or language == source_language:
        raise ValueError('Выберите язык перевода, отличный от исходного.')
    if not isinstance(items, list) or len(items) != len(source):
        raise ValueError('Перевод должен включать все блоки текущего основного резюме.')
    originals = {item['id']: item for item in source}
    result = {}
    for row in items:
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise ValueError('Нужны компания, роль, период, продолжительность и описание каждого блока.')
        if any(not isinstance(row[k], str) or len(row[k]) > (100000 if k == 'description' else 2000) for k in FIELDS):
            raise ValueError('Некорректный текст перевода.')
        key = row['id']
        if key not in originals or key in result or not all(row[k].strip() for k in ('company','role','period')):
            raise ValueError('Блоки перевода не соответствуют текущему основному резюме.')
        if any(redact_contacts(row[k]) != row[k] for k in FIELDS):
            raise ValueError('Контактные данные не входят в публичный перевод опыта.')
        original = originals[key]
        if period_key(row['period']) != period_key(original['period']) or duration_key(row['duration']) != duration_key(original['duration']):
            raise ValueError('Перевод не должен изменять даты или продолжительность работы.')
        result[key] = {k: row[k].strip() for k in FIELDS}
    if sum(len(row['description']) for row in result.values()) > 250000:
        raise ValueError('Перевод слишком велик.')
    return [result[row['id']] for row in source]

def current_translations(state, primary, source, source_language):
    basis = digest(source)
    current, stale = {}, []
    for language, draft in state.get('experience_translations', {}).items():
        try:
            if draft.get('resume_id') != primary or draft.get('basis') != basis:
                raise ValueError('Источник изменился.')
            items = validate_translation(draft.get('items'), source, language, source_language)
            current[language] = {'basis': basis, 'items': items}
        except (ValueError, TypeError, KeyError, AttributeError):
            stale.append(language)
    return basis, current, stale
