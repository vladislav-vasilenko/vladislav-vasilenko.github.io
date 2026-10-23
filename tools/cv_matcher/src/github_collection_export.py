"""Export only a checkpoint produced by this Actions run, never checkout data.

Standard library only: validation still works if uv or a scraper fails.
The importer checks this identity again before writing to the local archive.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil

MAX_BYTES = 32 * 1024 * 1024


def prepare(source, target, *, run_id, attempt, sha):
    source, target = Path(source), Path(target)
    if not run_id or not attempt or not sha:
        raise ValueError('Missing GitHub run identity; refusing to export historical data.')
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError('Missing or oversized vacancy checkpoint.')
    try:
        payload = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError()
        origin = payload.get('collection_run')
        if not isinstance(origin, dict) or any(str(origin.get(k)) != str(v) for k, v in
                (('id', run_id), ('attempt', attempt), ('sha', sha))):
            raise ValueError()
        rows = payload.get('vacancies')
        stats = payload.get('stats_last_run')
        if not isinstance(rows, list) or len(rows) > 20000 or payload.get('total') != len(rows):
            raise ValueError()
        if any(not isinstance(row, dict) for row in rows) or not isinstance(stats, dict) or not stats:
            raise ValueError()
        if any(not isinstance(s, dict) or type(s.get('errors')) is not int or s['errors'] < 0 for s in stats.values()):
            raise ValueError()
        exported = datetime.fromisoformat(payload['last_updated'].replace('Z', '+00:00'))
        if exported.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        raise ValueError('Invalid checkpoint or run identity; refusing to export historical data.') from None
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target / 'online_scraped.json')
    # Source names are fixed by the CLI; do not include vacancy text or raw errors.
    lines = ['## Vacancy collection', '', f'Exported {len(rows)} saved vacancies.', '',
             'Saved total includes earlier observations; it is not a count of live vacancies.', '',
             '| Source | New | Errors |', '| --- | ---: | ---: |']
    for name in ('yandex', 'google', 'meta', 'sber'):
        if name in stats:
            item = stats[name]
            added = item.get('new', 0)
            lines.append(f'| {name} | {added if type(added) is int else 0} | {item["errors"]} |')
    if any(s['errors'] for s in stats.values()):
        lines += ['', 'Partial source failures occurred. The checkpoint is available for local import.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[3] / 'public' / 'online_scraped.json'
    summary = prepare(source, args.target, run_id=os.getenv('GITHUB_RUN_ID'),
                      attempt=os.getenv('GITHUB_RUN_ATTEMPT'), sha=os.getenv('GITHUB_SHA'))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
            output.write(summary)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('ready=true\n')
    print(summary)


if __name__ == '__main__':
    main()
