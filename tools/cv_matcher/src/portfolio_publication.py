"""Publish only primary HH work history and owner-confirmed public project links."""
import asyncio
import base64
import json
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from .archive_store import canonical, digest, now_iso
from .career_trajectory import evidence_catalog
from .career_skills_catalog import SKILLS
from .github_collection_api import GitHubAPI, GitHubError, REPOSITORY
from .resume_files import redact_contacts

KEY = 'portfolio-publication'
TARGET = 'public/hh-experience.json'


def read(archive):
    with archive.connect() as db:
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {'enabled': False, 'phase': 'idle'}


def write(archive, **changes):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
        state = json.loads(row[0]) if row else {'enabled': False, 'phase': 'idle'}
        state.update(changes)
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (KEY, canonical(state)))
    return state


def github_url(value):
    if not isinstance(value, str): return None
    u = urlsplit(value)
    if u.scheme != 'https' or u.netloc != 'github.com' or u.query or u.fragment or not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./%-]+)?/?', u.path): return None
    return 'https://github.com' + u.path.rstrip('/')


def confirmed_skills(archive):
    """Owner-confirmed practice only; never exports private notes or CV text."""
    items = {}
    for item in evidence_catalog(archive, archive):
        url = github_url(item.get('url'))
        if item.get('state') not in ('confirmed', 'completed') or item.get('kind') not in ('project', 'research', 'professional') or not url: continue
        for key in item.get('skill_ids', []):
            if key in SKILLS:
                items.setdefault(key, {'id': key, 'label': SKILLS[key]['label'], 'links': []})
                if url not in [link['url'] for link in items[key]['links']]:
                    items[key]['links'].append({'url': url, 'label': urlsplit(url).path.split('/')[2]})
    return sorted(items.values(), key=lambda i: i['label'])


def parse_experience(text):
    node = shutil.which('node')
    if not node: raise ValueError('Для общего HH-парсера нужен Node.js в PATH сервиса.')
    helper = Path(__file__).resolve().parents[1] / 'hh-research-extension/portfolio-experience.mjs'
    result = subprocess.run([node, str(helper)], input=text, text=True, capture_output=True, timeout=20)
    if result.returncode: raise ValueError('Не удалось разобрать блок опыта HH. Предыдущая публикация сохранена.')
    parsed = json.loads(result.stdout)
    if not parsed.get('items') or len(parsed['items']) > 80:
        raise ValueError('Блок опыта не распознан полностью. Автопубликация остановлена.')
    # Only the standard section heading / aggregate duration may precede entries.
    preamble = parsed.get('unparsed', '')
    if re.sub(r'опыт работы|work experience|\d+|лет|год[а]?|месяц[аев]*|years?|months?|[\s:—–()-]', '', preamble, flags=re.I):
        raise ValueError('Перед блоками опыта остался неразобранный текст. Проверьте импорт HH.')
    if any(not item.get('company') or not item.get('role') or not item.get('dates') for item in parsed['items']):
        raise ValueError('Не все компании, роли и даты распознаны. Публикация остановлена.')
    return [{'id': 'hh-' + str(i), 'company': item['company'], 'role': item['role'],
             'period': item['dates'], 'duration': item.get('duration', ''),
             'description': item['description']} for i, item in enumerate(parsed['items'])]


def preview(archive):
    primary = archive.summary().get('primary_id')
    if not primary: raise ValueError('Выберите основное HH-резюме в локальном сервисе.')
    detail = archive.detail('resume', primary); cv = detail['payload']
    if cv.get('source_type', 'hh') != 'hh' or cv.get('quality') != 'full':
        raise ValueError('Основным должно быть полное HH-резюме.')
    sections = [s for s in cv.get('sections', []) if s.get('key') == 'experience']
    text = redact_contacts('\n\n'.join(s.get('text', '') for s in sections))
    if not 100 <= len(text) <= 250000: raise ValueError('Нет полного блока опыта HH.')
    items = parse_experience(text)
    skills = confirmed_skills(archive)
    about = redact_contacts('\n\n'.join(s.get('text', '') for s in cv.get('sections', []) if s.get('key') == 'about'))
    about = re.sub(r'^\s*(?:О себе|About me|About)\s*:?\s*', '', about, flags=re.I).strip()
    about_key = digest({'resume': primary, 'about': about})
    state = read(archive); draft = state.get('about_draft', {})
    reviewed = draft.get('resume_id') == primary and draft.get('basis') == about_key
    source_language = 'ru' if len(re.findall('[А-Яа-яЁё]', text)) > len(re.findall('[A-Za-z]', text)) / 3 else 'en'
    translations = dict(draft.get('translations', {})) if reviewed else {}
    if reviewed: translations[draft['language']] = draft['text']
    payload = {'schema_version': 1, 'enabled': True,
               'source': {'label': 'HH', 'captured_at': cv.get('checked_at') or cv.get('captured_at') or detail['source_at'],
                          'language': source_language,
                          'url': 'https://hh.ru/resume/' + primary if re.fullmatch('[a-fA-F0-9]{30,64}', primary) else ''},
               'about': {'text': translations.get(source_language, about),
                         'language': source_language, 'translations': translations,
                         'origin': 'reviewed' if reviewed else 'hh'},
               'experience': items, 'confirmed_skills': skills}
    return {'resume_title': cv['title'], 'resume_id': primary, 'version_id': detail['version_id'],
            'about_basis': about_key, 'about_source': about, 'about_needs_review': bool(draft) and not reviewed,
            'fingerprint': digest({'experience': items, 'skills': skills, 'language': payload['source']['language'], 'about': payload['about'], 'url': payload['source']['url']}), 'payload': payload,
            'skills_text': 'Подтверждённые навыки · проекты и лабораторные\n' + '\n'.join(
                s['label'] + ': ' + ', '.join(link['url'] for link in s['links']) for s in skills)}


def save_about(archive, data):
    proposal = preview(archive)
    if data.get('reset') is True:
        return write(archive, about_draft={})
    text = data.get('text'); language = data.get('language')
    if data.get('reviewed') is not True: raise ValueError('Проверьте текст перед сохранением для сайта.')
    if not isinstance(text, str) or not 30 <= len(text.strip()) <= 6000 or language not in ('ru', 'en'):
        raise ValueError('Нужен текст от 30 до 6000 символов и язык RU / EN.')
    if data.get('basis') != proposal['about_basis']: raise ValueError('Исходный текст HH изменился. Обновите предпросмотр.')
    if redact_contacts(text).strip() != text.strip(): raise ValueError('Уберите контактные данные из публичного введения.')
    old = read(archive).get('about_draft', {})
    translations = dict(old.get('translations', {})) if old.get('basis') == proposal['about_basis'] else {}
    translations[language] = text.strip()
    return write(archive, about_draft={'text': text.strip(), 'language': language, 'translations': translations,
                 'basis': proposal['about_basis'], 'resume_id': proposal['resume_id'], 'saved_at': now_iso()})


def discussion_context(archive):
    """Private, on-demand context; no model calls and no automatic public goals."""
    proposal = preview(archive)
    from .career_trajectory import overview
    current = overview(archive, archive).get('path')
    trajectory = {'label': current['label'], 'goal': current['goal'],
                  'stages': [{'label': s['label'], 'criteria': [c['label'] for c in s['criteria']]} for s in current['stages']]} if current else None
    repositories = sorted(set(re.findall(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', '\n'.join(i['description'] for i in proposal['payload']['experience']))))[:6]
    return {'about': proposal['payload']['about'], 'hh_about': proposal['about_source'], 'trajectory': trajectory,
            'work': proposal['payload']['experience'][:4], 'repositories': repositories,
            'github_activity': read(archive).get('github_activity', []),
            'instruction': 'Перепиши введение под шапкой резюме без заголовка «Обо мне»: 80–130 слов. Сначала текущая исследовательская специализация, затем подтверждённая инженерная и коммерческая база, затем желаемая роль. Отделяй карьерные цели от уже достигнутого. Ссылайся только на переданные работы. Не добавляй навыки, результаты, публикации или авторство по названию репозитория. Обновления GitHub — активность проекта, а не доказательство личного вклада. Предложи RU и EN, отметь неоднозначности. Ничего не публикуй автоматически.'}


def refresh_github_activity(archive, client=None):
    context = discussion_context(archive); client = client or Publisher(); items = []
    for url in context['repositories']:
        owner, repo = urlsplit(url).path.split('/')[1:3]
        if not client.public_repository(owner, repo): continue
        data = client.research_request(owner, repo)
        commits = client.research_request(owner, repo, commits=True)
        items.append({'url': url, 'description': str(data.get('description') or '')[:600], 'pushed_at': data.get('pushed_at'),
                      'commits': [{'url': c.get('html_url'), 'message': str(c.get('commit', {}).get('message', '')).split('\n')[0][:240],
                                   'date': c.get('commit', {}).get('committer', {}).get('date')} for c in commits[:3]]})
    write(archive, github_activity=items, github_checked_at=now_iso())
    return {'items': items, 'checked_at': now_iso(), 'api_requests_models': 0}


class Publisher(GitHubAPI):
    def research_request(self, owner, repo, commits=False):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo):
            raise ValueError('Некорректная ссылка репозитория.')
        endpoint = f'repos/{owner}/{repo}' + ('/commits?per_page=3' if commits else '')
        result = subprocess.run([self.executable, 'api', '--method', 'GET', endpoint],
                                capture_output=True, text=True, timeout=15)
        if result.returncode or len(result.stdout) > 1000000:
            raise GitHubError('Не удалось прочитать публичную активность GitHub. Предыдущий снимок сохранён.')
        return json.loads(result.stdout)

    def public_repository(self, owner, repo):
        # Only metadata is read, never repository files or lab contents.
        result = subprocess.run([self.executable, 'api', f'repos/{owner}/{repo}', '--jq', '.private'],
                                capture_output=True, text=True, timeout=30)
        if result.returncode or result.stdout.strip() not in ('true','false'):
            raise GitHubError('Не удалось проверить публичность GitHub-подтверждения. Предыдущая публикация сохранена.')
        return result.stdout.strip() == 'false'

    def publish(self, payload):
        endpoint = f'repos/{REPOSITORY}/contents/{TARGET}'
        existing = self.request(endpoint)
        sha = existing.get('sha')
        if not isinstance(sha, str): raise GitHubError('Не найден управляемый файл портфолио в репозитории.')
        body = {'message': 'chore(portfolio): sync primary HH experience and project evidence', 'sha': sha,
                'branch': 'main', 'content': base64.b64encode((canonical(payload) + '\n').encode()).decode()}
        with tempfile.TemporaryFile(mode='w+') as request:
            json.dump(body, request); request.seek(0)
            result = subprocess.run([self.executable, 'api', '--method', 'PUT', endpoint, '--input', '-'],
                                    stdin=request, capture_output=True, text=True, timeout=90)
        if result.returncode: raise GitHubError('GitHub не принял публикацию. Проверьте права Contents:write и повторите; прежняя версия сайта сохранена.')
        return json.loads(result.stdout)['commit']['sha']


def publish(archive, publisher=None):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
        state = json.loads(row[0]) if row else {'enabled': False}
        if state.get('phase') == 'publishing' and state.get('started', 0) > time.time() - 600: return state
        state.update(phase='publishing', started=time.time(), error='')
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (KEY, canonical(state)))
    try:
        proposal = preview(archive); state = read(archive)
        if proposal['fingerprint'] == state.get('published_fingerprint'):
            return write(archive, phase='up_to_date', last_checked_at=now_iso())
        publisher = publisher or Publisher()
        payload = proposal['payload']; public = {}
        for skill in payload['confirmed_skills']:
            for link in skill['links']:
                owner, repo = urlsplit(link['url']).path.split('/')[1:3]
                key = (owner, repo)
                if key not in public: public[key] = publisher.public_repository(owner, repo)
            skill['links'] = [link for link in skill['links'] if public[tuple(urlsplit(link['url']).path.split('/')[1:3])]]
        payload['confirmed_skills'] = [s for s in payload['confirmed_skills'] if s['links']]
        commit = publisher.publish(payload)
        return write(archive, phase='published', published_fingerprint=proposal['fingerprint'],
                     last_checked_at=now_iso(), published_at=now_iso(), commit=commit,
                     resume_id=proposal['resume_id'], version_id=proposal['version_id'],
                     experience_count=len(payload['experience']), skill_count=len(payload['confirmed_skills']), error='')
    except Exception as error:
        return write(archive, phase='error', error=str(error)[:400] if isinstance(error, (ValueError, GitHubError)) else 'Публикация прервана. Проверьте подключение GitHub и повторите.')


async def scheduler(archive_factory, period=60):
    while True:
        await asyncio.sleep(period)
        archive = archive_factory(); state = read(archive)
        if not state.get('enabled'): continue
        try: checked = datetime.fromisoformat(state.get('last_checked_at', '')).timestamp()
        except ValueError: checked = 0
        if time.time() - max(checked, state.get('started', 0)) < 300: continue
        await asyncio.to_thread(publish, archive)

