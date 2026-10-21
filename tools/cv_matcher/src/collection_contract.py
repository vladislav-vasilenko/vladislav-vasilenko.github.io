"""The same vacancy envelope for Chrome exports and Python collectors."""
from datetime import datetime,timezone
from pathlib import Path
from .board_import import identity

ADAPTERS={'career.avito.com':'avito','ozon.tech':'ozon','career.ozon.ru':'ozon','www.tbank.ru':'tbank','tbank.ru':'tbank','yandex.ru':'yandex','yandex.com':'yandex','rabota.sber.ru':'sber'}

def normalize_browser_rows(rows):
    from urllib.parse import urlsplit
    result=[]
    for row in rows:
        adapter=ADAPTERS.get(urlsplit(row.get('link','')).hostname)
        if not adapter:result.append(row);continue
        valid=identity(row['link'])
        if not valid or not row.get('title'):continue
        quality=row.get('description_quality','needs_review')
        if quality=='full' and len(row.get('description',''))<150:quality='snippet'
        result.append({**row,**valid,'collector':row.get('collector','playwright'),'adapter_id':adapter,'adapter_version':row.get('adapter_version','python-v1'),'description_quality':quality,'source_page':row.get('source_page') or row['link'],'collected_at':row.get('collected_at') or datetime.now(timezone.utc).isoformat()})
    return result

def archive_browser_rows(rows,path):
    """Persist supported source snapshots to the shared local archive, without HTTP/model calls."""
    from .archive_store import ArchiveStore,now_iso
    supported=[r for r in rows if r.get('adapter_id') in set(ADAPTERS.values())]
    if not supported:return
    store=ArchiveStore(path)
    with store.connect() as db:
        for row in supported:store._entity(db,'vacancy',row['id'],row,now_iso())

def read_browser_board(page):
    """Reuse the exact Chrome adapter on a caller-owned Playwright page."""
    root=Path(__file__).resolve().parents[1]/'hh-research-extension'
    prelude='\n'.join((root/name).read_text() for name in ('board-core.js','board-adapters.js'))
    collector=(root/'board-content.js').read_text().strip().removesuffix(';')
    return page.evaluate('() => {\n'+prelude+'\nreturn (\n'+collector+'\n);\n}')
