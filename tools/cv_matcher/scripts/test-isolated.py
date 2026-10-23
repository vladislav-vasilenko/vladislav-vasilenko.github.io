#!/usr/bin/env python3
"""Run all Python tests in a disposable source copy, never the working archive.

Use the project's interpreter: .venv/bin/python scripts/test-isolated.py
No .env, .cache, session, credential or production database is copied.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='career-isolated-tests-') as tmp:
    target=Path(tmp)
    for name in ('src','archive-web','hh-research-extension','docs'):
        shutil.copytree(source/name,target/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for path in source.glob('*.py'):shutil.copy2(path,target/path.name)
    (target/'scripts').mkdir()
    for path in (source/'scripts').glob('*.py'):shutil.copy2(path,target/'scripts'/path.name)
    shutil.copy2(source/'pyproject.toml',target/'pyproject.toml')
    env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ('OPENAI','TELEGRAM','API_KEY','TOKEN','SESSION','GOOGLE','PYTHONPATH'))}
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','src/tests','-t','.'],cwd=target,env=env)
    raise SystemExit(result.returncode)
