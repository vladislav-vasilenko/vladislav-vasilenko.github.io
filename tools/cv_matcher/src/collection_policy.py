"""Shared read-collection policy. No model calls or browser state."""
from urllib.parse import urlsplit

MODES = ('chrome_only', 'python_only', 'python_first', 'chrome_first')
CHROME_HOSTS = {'hh.ru', 'career.avito.com', 'ozon.tech', 'career.ozon.ru', 'yandex.ru', 'yandex.com', 'rabota.sber.ru', 'tbank.ru', 'www.tbank.ru'}
SOURCES = {'yandex.ru':'yandex','yandex.com':'yandex','rabota.sber.ru':'sber','career.avito.com':'avito','ozon.tech':'ozon','career.ozon.ru':'ozon','tbank.ru':'tinkoff','www.tbank.ru':'tinkoff','www.google.com':'google','careers.google.com':'google','metacareers.com':'meta','www.metacareers.com':'meta'}
PYTHON_HOSTS = set(SOURCES)
MANUAL_REASONS = {'access_required','login_required','captcha','unsupported_python_source','filters_not_supported_in_python','native_filter_requires_chrome','unsupported_layout','incomplete_descriptions','unverified_empty','archive_rejected'}
TRANSIENT_REASONS = {'public_http_failed','http_timeout','http_rate_limited','http_unavailable','python_timeout','python_process_failed','python_interrupted','chrome_interrupted','navigation_timeout','python_error','python_parser_error'}


def prepare(payload, mode):
    if mode not in MODES:
        raise ValueError('Неизвестный порядок способов сбора.')
    from .discovery import source_url
    source_url(payload.get('source_url',''),detail=bool(payload.get('vacancy_id')) or urlsplit(payload.get('source_url','')).path.startswith('/vacancy/'))
    host = urlsplit(payload['source_url']).hostname
    order = {'chrome_only':['chrome'], 'python_only':['python'], 'python_first':['python','chrome'], 'chrome_first':['chrome','python']}[mode]
    order = [item for item in order if host in (PYTHON_HOSTS if item == 'python' else CHROME_HOSTS)]
    if not order:
        raise ValueError('Выбранный способ не поддерживает этот источник. Google/Meta требуют Python; HH — подключённый Chrome.')
    return {**payload, 'collection_transport':order[0], 'transport_order':order, 'transport_history':[]}


def reason_for(error):
    """Stable diagnostics without retaining arbitrary page or exception contents."""
    message = str(error).lower()
    if '429' in message: return 'http_rate_limited'
    if any(word in message for word in ('captcha','капч','access denied','403','доступ ограничен')): return 'access_required'
    if any(word in message for word in ('login','авторизац','требует вход')): return 'login_required'
    if any(word in message for word in ('timeout','timed out','таймаут','не загрузилась','не готова')): return 'navigation_timeout'
    return 'python_error'


def retry_delay(reason, attempt):
    if reason not in TRANSIENT_REASONS or attempt >= 3:
        return None
    return min(1800, 60 * 3 ** max(0, attempt - 1))
