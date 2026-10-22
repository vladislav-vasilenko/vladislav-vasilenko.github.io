"""Safe public navigation metadata from the repository's shared project manifest."""
import json
from pathlib import Path
from urllib.parse import urlsplit


def read(path=None):
    manifest = Path(path) if path else Path(__file__).resolve().parents[3] / 'workspace.projects.json'
    if not manifest.is_file():
        return {'portfolio': None, 'career': None}
    data = json.loads(manifest.read_text(encoding='utf-8'))
    projects = data.get('projects', {})
    result = {}
    for name in ('portfolio','career'):
        project = projects.get(name, {})
        url = project.get('public_url') if name == 'portfolio' else project.get('local_url')
        parsed = urlsplit(url or '')
        valid_origin = (
            parsed.scheme == 'https' and bool(parsed.hostname)
            if name == 'portfolio'
            else parsed.scheme == 'http' and parsed.netloc == '127.0.0.1:8788'
        )
        if not valid_origin or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Некорректная ссылка проекта.')
        result[name] = {'label': project.get('label', name), 'url': url}
    return result
