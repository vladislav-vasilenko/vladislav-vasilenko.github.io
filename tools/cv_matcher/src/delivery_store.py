"""Durable owner notifications. Ambiguous network outcomes require human reconciliation."""
import json,secrets,time
from contextlib import nullcontext

class DeliveryRejected(ValueError):
    """Telegram explicitly rejected the request: no message was accepted."""

class DeliveryMixin:
    def init_delivery(self,db):
        columns={r[1] for r in db.execute('PRAGMA table_info(workflow_delivery)')}
        for name,definition in {'payload':'TEXT','lease_token':'TEXT','lease_until':'REAL','attempts':'INTEGER DEFAULT 0','message_ids':'TEXT','last_error':'TEXT','revision':'INTEGER DEFAULT 0','updated_at':'REAL','next_attempt':'REAL DEFAULT 0'}.items():
            if name not in columns:db.execute('ALTER TABLE workflow_delivery ADD COLUMN '+name+' '+definition)
        db.execute("UPDATE workflow_delivery SET state='uncertain',last_error='Старый claimed: проверьте личный чат перед повтором.',updated_at=?,revision=revision+1 WHERE state='claimed'",(time.time(),))

    def enqueue_delivery(self,key,text,keyboard=None,*,db=None):
        from .application_workflow import packed,utc
        payload=packed({'text':text,'keyboard':keyboard})
        with (self.connect() if db is None else nullcontext(db)) as connection:
            if db is None:connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT OR IGNORE INTO workflow_delivery(key,state,created_at,payload,updated_at) VALUES(?,'pending',?,?,?)",(key,utc(),payload,time.time()))
            # A legacy record can acquire its original payload when the source event is revisited.
            connection.execute('UPDATE workflow_delivery SET payload=? WHERE key=? AND payload IS NULL',(payload,key))
        return key

    def deliveries(self,limit=100):
        with self.connect() as db:
            db.execute("UPDATE workflow_delivery SET state='uncertain',last_error='Отправка прервана: результат Telegram неизвестен. Проверьте чат.',revision=revision+1,updated_at=? WHERE state='sending' AND lease_until<?",(time.time(),time.time()))
            rows=db.execute("SELECT * FROM workflow_delivery WHERE state<>'sent' ORDER BY created_at LIMIT ?",(limit,)).fetchall()
        return [{**dict(r),'payload':json.loads(r['payload']) if r['payload'] else None,'message_ids':json.loads(r['message_ids'] or '[]')} for r in rows]

    def claim_delivery_send(self,key):
        self.deliveries()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            token=secrets.token_hex(16)
            changed=db.execute("UPDATE workflow_delivery SET state='sending',lease_token=?,lease_until=?,attempts=attempts+1,revision=revision+1,updated_at=? WHERE key=? AND state='pending' AND payload IS NOT NULL AND COALESCE(next_attempt,0)<=?",(token,time.time()+120,time.time(),key,time.time())).rowcount
            if not changed:return None
            row=dict(db.execute('SELECT * FROM workflow_delivery WHERE key=?',(key,)).fetchone())
        return {**row,'payload':json.loads(row['payload'])}

    def finish_delivery(self,key,lease_token,*,message_ids=None,rejected=False,error=False):
        from .application_workflow import packed
        state='pending' if rejected else 'uncertain' if error else 'sent'
        with self.connect() as db:
            # Late transport success may settle an expired lease, but never a newer attempt.
            changed=db.execute("UPDATE workflow_delivery SET state=?,message_ids=?,last_error=?,next_attempt=?,revision=revision+1,updated_at=? WHERE key=? AND lease_token=? AND state IN ('sending','uncertain')",(state,packed(message_ids or []),'Telegram отклонил доставку; повтор после восстановления доступа.' if rejected else 'Нет подтверждения Telegram. Проверьте личный чат.' if error else None,time.time()+60 if rejected else 0,time.time(),key,lease_token)).rowcount
            if not changed:raise ValueError('Попытка доставки уже обработана или изменена.')

    def resolve_delivery(self,key,revision,resolution,confirmed=False):
        if confirmed is not True or resolution not in ('sent','retry'):raise ValueError('Подтвердите проверку личного чата Telegram и выберите результат.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM workflow_delivery WHERE key=?',(key,)).fetchone()
            if not row or row['state']!='uncertain' or row['revision']!=revision:raise ValueError('Состояние доставки изменилось. Обновите список.')
            if resolution=='retry' and not row['payload']:raise ValueError('Текст старого уведомления ещё не восстановлен из события. Повтор без текста невозможен.')
            db.execute("UPDATE workflow_delivery SET state=?,lease_token=NULL,lease_until=NULL,next_attempt=0,last_error=?,revision=revision+1,updated_at=? WHERE key=?",('pending' if resolution=='retry' else 'sent','Пользователь подтвердил отсутствие сообщения и разрешил повтор.' if resolution=='retry' else 'Получение подтверждено пользователем.',time.time(),key))
        return {'ok':True}
