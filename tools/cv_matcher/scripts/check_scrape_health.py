#!/usr/bin/env python3
"""Fail the run after publishing if a source failed. Standard library only.

Saved vacancies are published either way; this makes a broken source visible
instead of leaving it as "0 new, 0 errors" in a green run.
"""
import json
from pathlib import Path
import sys

DEFAULT = Path(__file__).resolve().parents[3] / 'public' / 'online_scraped.json'


def check(path=DEFAULT, out=sys.stdout):
    stats = json.loads(Path(path).read_text(encoding='utf-8')).get('stats_last_run') or {}
    failed = 0
    for name, source in sorted(stats.items()):
        listed, errors = source.get('listed', 0), source.get('errors', 0)
        if source.get('failed'):
            failed += 1
            print(f'::error::{name}: source failed ({listed} listed, {errors} errors). See the job log.', file=out)
        elif errors:
            print(f'::warning::{name}: partial collection ({listed} listed, {errors} errors).', file=out)
    print(f'{len(stats) - failed} of {len(stats)} sources healthy.', file=out)
    return 1 if failed or not stats else 0


if __name__ == '__main__':
    sys.exit(check())
