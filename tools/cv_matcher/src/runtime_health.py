"""Fresh runtime evidence, separate from configured credentials or an open session file."""
import json,time,asyncio

def write_health(store,name,state,*,verified=False):
    store.setting('runtime:'+name,json.dumps({'state':state,'checked_at':time.time(),'verified':verified}))

def read_health(store,name):
    try:value=json.loads(store.setting('runtime:'+name) or '{}')
    except (ValueError,TypeError):value={}
    fresh=0<=time.time()-value.get('checked_at',0)<120
    return {**value,'state':value.get('state','unknown') if fresh else 'stale','connected':bool(fresh and value.get('verified') and value.get('state')=='connected')}

class GigaHealth:
    def __init__(self,store,client,owner):
        self.store,self.client,self.owner=store,client,str(owner);self.last_probe=0
    async def check(self,force=False):
        if not self.client:
            write_health(self.store,'giga','not_configured');return False
        if not self.client.is_connected():
            write_health(self.store,'giga','reconnecting')
            if not force and time.monotonic()-self.last_probe<45:return False
            self.last_probe=time.monotonic()
            try:await asyncio.wait_for(self.client.connect(),timeout=8)
            except Exception:return False
            if not self.client.is_connected():return False
            force=True
        if not force and time.monotonic()-self.last_probe<45:return read_health(self.store,'giga')['connected']
        self.last_probe=time.monotonic()
        try:
            me=await asyncio.wait_for(self.client.get_me(),timeout=8)
            valid=bool(me and not me.bot and str(me.id)==self.owner)
            write_health(self.store,'giga','connected' if valid else 'unauthorized',verified=valid)
            return valid
        except (TimeoutError,OSError,ValueError,ConnectionError):
            write_health(self.store,'giga','reconnecting');return False
        except Exception:
            write_health(self.store,'giga','error');return False
