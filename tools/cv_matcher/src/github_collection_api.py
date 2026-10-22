"""Read-only GitHub API access using the owner's existing gh authentication."""
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile

REPOSITORY = 'vladislav-vasilenko/vladislav-vasilenko.github.io'
WORKFLOW = 'daily-scrape.yml'
MAX_BYTES = 32 * 1024 * 1024


class GitHubError(ValueError):
    pass


class GitHubAPI:
    def __init__(self, executable=None):
        self.executable = executable or shutil.which('gh')

    def request(self, endpoint, *, raw=False):
        if not self.executable:
            raise GitHubError('Нужен GitHub CLI (gh) с выполненным входом в ваш GitHub-аккаунт.')
        if not endpoint.startswith('repos/' + REPOSITORY + '/'):
            raise GitHubError('Разрешён только источник вакансий этого репозитория.')
        args = [self.executable, 'api', '--method', 'GET', endpoint, '-H',
                'Accept: ' + ('application/vnd.github.raw+json' if raw else 'application/vnd.github+json')]
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            with subprocess.Popen(args, stdout=output, stderr=errors, stdin=subprocess.DEVNULL) as process:
                try:
                    process.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
                    raise GitHubError('GitHub не ответил вовремя. Повторите импорт позже.') from None
                if process.returncode:
                    errors.seek(0); message = errors.read(8192).decode(errors='replace')
                    if '403' in message or 'rate limit' in message.lower():
                        raise GitHubError('GitHub ограничил запросы или не разрешил чтение Actions/Contents. Проверьте доступ gh.')
                    if '404' in message:
                        raise GitHubError('Источник GitHub не найден или недоступен текущему аккаунту gh.')
                    raise GitHubError('Не удалось прочитать GitHub API. Проверьте вход через gh auth login и доступ к репозиторию.')
            if output.tell() > MAX_BYTES:
                raise GitHubError('Выгрузка GitHub превышает лимит 32 МБ.')
            output.seek(0); data = output.read(MAX_BYTES + 1)
        if raw:
            return data
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise GitHubError('GitHub вернул некорректный JSON.') from None

    def latest(self):
        data = self.request(f'repos/{REPOSITORY}/actions/workflows/{WORKFLOW}/runs?branch=main&per_page=30')
        runs = [r for r in data.get('workflow_runs', []) if r.get('head_branch') == 'main'
                and r.get('event') in ('schedule', 'workflow_dispatch')
                and r.get('head_repository', {}).get('full_name') == REPOSITORY]
        complete = [r for r in runs if r.get('status') == 'completed']
        if not complete:
            raise GitHubError('Завершённых запусков сбора на main пока нет.')
        run = max(complete, key=lambda r: (r['run_number'], r.get('run_attempt', 1)))
        if type(run.get('id')) is not int or not re.fullmatch('[a-f0-9]{40}', run.get('head_sha', '')):
            raise GitHubError('Некорректное описание запуска GitHub.')
        return {k: run.get(k) for k in ('id', 'run_number', 'run_attempt', 'head_sha', 'conclusion', 'created_at', 'updated_at')}

    def export(self, run):
        artifacts = self.request(f'repos/{REPOSITORY}/actions/runs/{run["id"]}/artifacts?per_page=100')
        attempt = run.get('run_attempt') or 1
        names = {f'vacancies-export-{attempt}'} | ({'vacancies-export'} if attempt == 1 else set())
        candidates = [a for a in artifacts.get('artifacts', []) if a.get('name') in names and not a.get('expired')]
        if candidates:
            artifact = max(candidates, key=lambda a: a['id'])
            if type(artifact.get('id')) is not int or artifact.get('size_in_bytes', MAX_BYTES + 1) > MAX_BYTES:
                raise GitHubError('Некорректный размер артефакта GitHub.')
            data = self.request(f'repos/{REPOSITORY}/actions/artifacts/{artifact["id"]}/zip', raw=True)
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                    entries = [i for i in bundle.infolist() if i.filename == 'online_scraped.json']
                    if len(entries) != 1 or entries[0].file_size > MAX_BYTES:
                        raise GitHubError('Артефакт не содержит допустимую выгрузку вакансий.')
                    payload = json.loads(bundle.read(entries[0]))
            except (zipfile.BadZipFile, ValueError, UnicodeError, RuntimeError):
                raise GitHubError('Артефакт вакансий повреждён или имеет неверный формат.') from None
            origin = payload.get('collection_run', {}) if isinstance(payload, dict) else {}
            if str(origin.get('id')) != str(run['id']) or str(origin.get('attempt')) != str(attempt):
                raise GitHubError('Выгрузка не соответствует запуску и попытке GitHub Actions.')
            return payload, 'artifact', []
        # Compatibility only: the commit snapshot can predate this run. Never
        # advertise it as fresh extraction, even when the workflow succeeded.
        data = self.request(f'repos/{REPOSITORY}/contents/public/online_scraped.json?ref={run["head_sha"]}', raw=True)
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeError):
            raise GitHubError('Снимок JSON в репозитории повреждён.') from None
        return payload, 'legacy_snapshot', ['У запуска нет артефакта. Импортируется исторический JSON из его коммита; дата выгрузки показана отдельно.']
