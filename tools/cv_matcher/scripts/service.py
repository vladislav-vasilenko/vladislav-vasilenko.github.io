#!/usr/bin/env python3
"""Start, open, restart or stop the one local service used by the Dock application.

Usage: service.py [open|url|status|restart|stop]. Standard library only.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = Path(__file__).resolve().parent.parent
SERVER = PROJECT / 'resume_import_server.py'
PYTHON = PROJECT / '.venv/bin/python'
STATE = PROJECT / '.cache/resume_import'
TOKEN = STATE / 'token.txt'
URL = 'http://127.0.0.1:8788'
START_TIMEOUT = 120
# Dock apps get a minimal PATH, but the GitHub import needs gh.
EXTRA_PATH = ('/opt/homebrew/bin', '/usr/local/bin', str(Path.home() / '.local/bin'))


def request(path, body=None):
    """Call the service with the pairing token from disk. The token never leaves this process."""
    headers = {'X-Resume-Import-Token': TOKEN.read_text().strip()}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    call = urllib.request.Request(URL + path, data=data, headers=headers)
    with urllib.request.urlopen(call, timeout=5) as response:
        return json.load(response)


def healthy():
    try:
        return request('/health').get('service') == 'cv-matcher-local'
    except (OSError, ValueError):
        return False


def owned_pid():
    """The PID we started, only if that process is still this project's service."""
    pid_file = STATE / 'server.pid'
    try:
        pid = int(pid_file.read_text())
    except (OSError, ValueError):
        return None
    command = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True).stdout
    return pid if str(SERVER) in command else None


def start():
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'launcher.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if healthy():
            return
        if not PYTHON.exists():
            raise RuntimeError('Не найдено окружение .venv. Выполните uv sync в ' + str(PROJECT))
        log_path = STATE / 'server.log'
        env = {**os.environ, 'PATH': os.pathsep.join([*EXTRA_PATH, os.environ.get('PATH', '/usr/bin:/bin')])}
        with log_path.open('ab') as log:
            process = subprocess.Popen([str(PYTHON), str(SERVER)], cwd=PROJECT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        (STATE / 'server.pid').write_text(str(process.pid))
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if healthy():
                return
            if process.poll() is not None:
                raise RuntimeError('Сервис не запустился. Возможно, порт 8788 занят. Подробности: ' + str(log_path))
            time.sleep(0.25)
        raise RuntimeError('Сервис не ответил за ' + str(START_TIMEOUT) + ' секунд. Подробности: ' + str(log_path))


def stop():
    pid = owned_pid()
    if pid is None:
        if healthy():
            raise RuntimeError('Сервис запущен не из Dock (например, через npm run career:dev). Остановите его там.')
        print('Сервис не запущен.')
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if owned_pid() is None:
            print('Сервис остановлен.')
            return
        time.sleep(0.25)
    raise RuntimeError('Сервис не остановился за 15 секунд. PID: ' + str(pid))


def login_url():
    """A one-time login link, valid for 60 seconds, so opening from the Dock needs no token prompt."""
    return request('/archive/open', {})['url']


def main(command):
    if command == 'status':
        print('running' if healthy() else 'stopped')
    elif command == 'stop':
        stop()
    elif command in ('open', 'url', 'restart'):
        if command == 'restart':
            stop()
        start()
        link = login_url()
        if command == 'url':
            print(link)
        else:
            subprocess.run(['/usr/bin/open', link], check=True)
    else:
        raise RuntimeError('Команды: open, url, status, restart, stop.')


if __name__ == '__main__':
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else 'open')
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
