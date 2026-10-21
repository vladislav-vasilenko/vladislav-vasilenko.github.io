"""Owner-pasted professional vacancy text; no server-side URL fetching."""
from datetime import datetime,timezone
from urllib.parse import urlsplit
from .board_import import identity
from .discovery import source_url
from .archive_store import digest

def import_text(archive,data):
    url=source_url(data.get('url'),detail=True);job=identity(url)
    title=data.get('title','').strip();text=data.get('text','').strip();company=data.get('company','').strip()
    if not 3<=len(title)<=500 or not 150<=len(text)<=100000 or len(company)>300:raise ValueError('Укажите название и полный текст вакансии (от 150 символов).')
    if data.get('confirmed_full') is not True:raise ValueError('Подтвердите, что вставили полное описание, включая требования и обязанности.')
    # Pasted text does not prove a job is currently accepting applications.
    row={**job,'title':title,'company':company or urlsplit(url).hostname,'description':text,'description_quality':'full','extraction_method':'owner_pasted_full','source_page':url,'collected_at':datetime.now(timezone.utc).isoformat()}
    result=archive.sync({'client_id':'owner-text-import','records':[{'kind':'vacancy','id':job['id'],'data':row,'digest':digest(row)}]})
    if result['rejected']:raise ValueError('Текст не сохранён. Проверьте ссылку вакансии.')
    return {'vacancy_id':job['id'],'api_requests':0}

def collect_one(store,url):
    url=source_url(url,detail=True)
    return {'command_id':store.queue_command('collect',payload={'source_url':url,'vacancy_id':identity(url)['id']}),'vacancy_id':identity(url)['id']}

def status(store,command_id):
    import json
    from .hybrid_collection import leaf,merged_result
    row=leaf(store,command_id)
    if row['kind']!='collect':raise ValueError('Задача чтения вакансии не найдена.')
    return {'state':row['state'],'result':merged_result(row),'vacancy_id':row['payload']['vacancy_id'],'command_id':row['id'],'transport':row['payload'].get('collection_transport','chrome')}
