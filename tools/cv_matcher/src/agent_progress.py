"""Validated browser counters and read-only progress presentation; no model access."""
import json,time
from .application_workflow import packed

COUNTERS=('discovered','planned','loaded','reused','failed','skipped_closed','archived','review','pages')
def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS browser_command_progress(command_id TEXT PRIMARY KEY,worker_id TEXT,sequence INTEGER,payload TEXT,updated REAL)')

def report(store,command_id,worker,sequence,progress):
    if type(sequence) is not int or not 1<=sequence<=1000000 or not isinstance(progress,dict):raise ValueError('Некорректный прогресс.')
    if any(k not in (*COUNTERS,'phase') for k in progress):raise ValueError('Лишние поля прогресса.')
    for key in COUNTERS:
        value=progress.get(key)
        if value is not None and (type(value) is not int or not 0<=value<=100000):raise ValueError('Некорректный счётчик прогресса.')
    if progress.get('phase') not in ('starting','listing','descriptions','returning','saving','complete','failed','stopped'):raise ValueError('Неизвестный этап чтения.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');command=db.execute('SELECT * FROM browser_commands WHERE id=? AND worker_id=?',(command_id,worker)).fetchone()
        if not command or command['kind'] not in ('discover','collect') or command['state']!='running':raise ValueError('Задача чтения завершена или принадлежит другому исполнителю.')
        old=db.execute('SELECT sequence FROM browser_command_progress WHERE command_id=?',(command_id,)).fetchone()
        if old and old[0]>=sequence:return {'ok':True,'ignored':True}
        db.execute('INSERT OR REPLACE INTO browser_command_progress VALUES(?,?,?,?,?)',(command_id,worker,sequence,packed(progress),time.time()))
    return {'ok':True}

def snapshot(store,kind,row):
    with store.connect() as db:
        if kind=='search':
            rows=db.execute("SELECT c.payload,c.result,p.payload progress FROM browser_commands c LEFT JOIN browser_command_progress p ON p.command_id=c.id WHERE c.kind='discover' AND json_extract(c.payload,'$.run_id')=? ORDER BY c.created DESC",(row['id'],)).fetchall()
            count=len(json.loads(row['payload'])['sources'])
        else:
            rows=db.execute('SELECT c.payload,c.result,p.payload progress FROM browser_commands c LEFT JOIN browser_command_progress p ON p.command_id=c.id WHERE c.id=?',(row['id'],)).fetchall();count=1
    from urllib.parse import urlsplit,parse_qsl
    sources={};seen=set()
    for item in rows:
        payload=json.loads(item['payload']);url=payload.get('source_url','')
        # Retries share the same payload. Continuations have a distinct cursor or
        # attempted-ID checkpoint, so their completed reads accumulate.
        identity=packed(payload)
        if identity in seen:continue
        seen.add(identity)
        parsed=urlsplit(url);source=(parsed.netloc,parsed.path,tuple(sorted((k,v) for k,v in parse_qsl(parsed.query) if k not in ('page','from','hhtmFrom','search_session_id'))))
        result=json.loads(item['result'] or '{}')
        progress=json.loads(item['progress'] or '{}') or result.get('progress',{})
        group=sources.setdefault(source,{'progress':[],'ids':set(),'reused_ids':set(),'pages':{}})
        group['progress'].append(progress);group['ids'].update(result.get('listing_ids',[]));group['reused_ids'].update(result.get('reused_ids',[]))
        group['pages'][url]=max(group['pages'].get(url,0),progress.get('pages') or 0)
    metrics={k:0 for k in COUNTERS}
    for group in sources.values():
        values=group['progress']
        for k in ('planned','loaded','failed','skipped_closed','archived','review'):metrics[k]+=sum(p.get(k) or 0 for p in values)
        metrics['discovered']+=max([len(group['ids'])]+[p.get('discovered') or 0 for p in values])
        # Repeated listing reads reuse the same fresh IDs: never sum those twice.
        metrics['reused']+=max([len(group['reused_ids'])]+[p.get('reused') or 0 for p in values])
        metrics['pages']+=sum(group['pages'].values())
    metrics['planned_complete']=len(sources)==count and all(p.get('planned') is not None for g in sources.values() for p in g['progress'])
    metrics['reported']=any(bool(p) for g in sources.values() for p in g['progress'])
    return metrics

def text(task):
    p=task['progress'];known=p.get('planned_complete',False);planned=str(p.get('planned',0)) if known else ('не менее '+str(p['planned'])+'; итог уточняется' if p.get('planned') else 'уточняется после чтения выдачи')
    def value(key):return str(p.get(key,0)) if p.get('reported') else 'ожидаем данные'
    lines=['🔎 Поиск вакансий · '+task['label'],f"Источники: {p.get('sources_done',0)} из {p.get('sources_total',1)}",'Найдено в прочитанной выдаче: '+value('discovered'),'Запланировано полных описаний: '+planned,'Прочитано полных описаний: '+value('loaded'),'Взято из свежего кэша: '+value('reused'),'Не удалось прочитать: '+value('failed'),'Пропущено закрытых: '+(str(p.get('skipped_closed',0)+p.get('archived',0)) if p.get('reported') else 'ожидаем данные')]
    if p.get('review'):lines.append('Требуют проверки текста: '+str(p['review']))
    if p.get('ranked'):lines.append('Обновлён рейтинг: '+str(p['ranked']))
    if task.get('next_action'):lines.append(task['next_action'])
    lines.append('📌 Счётчики всего запуска. Охват ограничен настройками источников; это не все вакансии сайта. /tasks — управление.')
    return '\n'.join(lines)

class EditRetry(Exception):
    def __init__(self,after=30):self.after=max(5,min(3600,int(after)))
