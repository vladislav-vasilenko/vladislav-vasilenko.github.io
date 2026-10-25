"""Durable complete contact walks, made of bounded Chrome read commands."""
import json
import secrets
import time
from .archive_store import canonical


def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS linkedin_contact_collections(id TEXT PRIMARY KEY,account TEXT,scope TEXT,state TEXT,payload TEXT,updated REAL,command_id TEXT)')
    db.execute('CREATE INDEX IF NOT EXISTS linkedin_contact_collection_account ON linkedin_contact_collections(account,updated DESC)')


def active(db,account,scope):
    return db.execute("SELECT c.command_id FROM linkedin_contact_collections c JOIN browser_commands b ON b.id=c.command_id WHERE c.account=? AND c.scope=? AND c.state IN ('queued','running') AND b.state IN ('queued','running') ORDER BY c.updated DESC LIMIT 1",(account,scope)).fetchone()


def start(db,ident,params):
    db.execute('INSERT INTO linkedin_contact_collections VALUES(?,?,?,?,?,?,?)',(ident,params['account'],params['scope'],'queued',canonical({'links':[],'expected_total':None,'message':'Ожидается расширение.'}),time.time(),ident))


def view(db,account):
    row=db.execute("SELECT c.*,b.state command_state FROM linkedin_contact_collections c LEFT JOIN browser_commands b ON b.id=c.command_id WHERE c.account=? AND c.scope IN ('connections','received','sent') ORDER BY c.updated DESC LIMIT 1",(account,)).fetchone()
    if not row:return None
    payload=json.loads(row['payload']);state=row['state']
    if state in ('queued','running') and row['command_state'] not in ('queued','running'):state='needs_input'
    return {'id':row['id'],'scope':row['scope'],'state':state,'count':len(payload['links']),'expected_total':payload.get('expected_total'),'message':payload.get('message',''),'updated':row['updated']}


def observe(db,params,payload,links,outcome,*,partial=False,paused=False):
    ident=params.get('collection_id')
    if not ident:return None
    row=db.execute('SELECT * FROM linkedin_contact_collections WHERE id=? AND account=?',(ident,params['account'])).fetchone()
    if not row:raise ValueError('Не найден запуск полного сбора контактов.')
    data=json.loads(row['payload']);observed=sorted(set(data['links'])|set(links));data['links']=observed
    diagnostic=payload.get('diagnostics',{})
    expected=diagnostic.get('expected_total') if isinstance(diagnostic,dict) else None
    if type(expected) is int and 0<expected<=1000000:data['expected_total']=expected
    state='running';command=row['command_id'];expected=data.get('expected_total');count=len(observed)
    data['message']='Прочитано '+str(count)+((' из '+str(expected)) if expected else '')+' уникальных контактов.'
    if not partial:
        if outcome['state']!='completed' or params.get('stop') or paused:
            state='cancelled' if outcome['state']=='cancelled' or params.get('stop') else 'needs_input'
            data['message']=outcome.get('message') or 'Сбор остановлен; прочитанные контакты сохранены.'
        elif expected and count>=expected:
            state='completed';data['message']='Прочитаны все '+str(count)+' контактов, указанных в счётчике LinkedIn.'
        elif not links:
            at_end=payload.get('scroll',{}).get('at_end') is True
            state='completed' if at_end and not expected else 'partial'
            data['message']='После прокрутки новые профили не появились. '+('Число в счётчике LinkedIn ещё не достигнуто.' if expected and count<expected else 'Сохранена доступная часть списка.')
        else:
            next_params={**params,'only_new':True,'known_contacts':observed}
            command=secrets.token_hex(12);now=time.time()
            db.execute("INSERT INTO browser_commands VALUES(?,NULL,'linkedin.network.list',?,'queued',NULL,?,?,NULL)",(command,canonical(next_params),now,now))
            state='queued';data['message']+=' Следующая порция в очереди.'
    db.execute('UPDATE linkedin_contact_collections SET state=?,payload=?,updated=?,command_id=? WHERE id=?',(state,canonical(data),time.time(),command,ident))
    return {'id':ident,'state':state,'count':count,'expected_total':expected,'message':data['message']}
