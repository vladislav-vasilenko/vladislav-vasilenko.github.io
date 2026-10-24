"""Persistent read scheduling. Pacing does not guarantee avoidance of platform restrictions."""
import math
import secrets
import time

DEFAULTS={'batch_min':8,'batch_max':12,'delay_min_seconds':3,'delay_max_seconds':8,'batch_pause_seconds':60}


def options(data, previous=None):
    result={**DEFAULTS,**{k:v for k,v in (previous or {}).items() if k in DEFAULTS}}
    for key in DEFAULTS:
        if key in data:result[key]=data[key]
    for key in ('batch_min','batch_max'):
        if type(result[key]) is not int or not 1<=result[key]<=50:raise ValueError('Размер порции от 1 до 50 вакансий.')
    for key in ('delay_min_seconds','delay_max_seconds'):
        if type(result[key]) not in (int,float) or not math.isfinite(result[key]) or not 2<=result[key]<=120:raise ValueError('Интервал между вакансиями от 2 до 120 секунд.')
    pause=result['batch_pause_seconds']
    if type(pause) not in (int,float) or not math.isfinite(pause) or not 10<=pause<=3600:raise ValueError('Перерыв между порциями от 10 до 3600 секунд.')
    if result['batch_min']>result['batch_max'] or result['delay_min_seconds']>result['delay_max_seconds']:raise ValueError('Минимум не может превышать максимум.')
    return result


def choose(low,high):
    return low+secrets.randbelow(high-low+1)


def state(config):
    result=config.setdefault('read_pacing',{})
    result.update(options(result))
    if type(result.get('target')) is not int or not result['batch_min']<=result['target']<=result['batch_max']:
        result['target']=choose(result['batch_min'],result['batch_max'])
    result.setdefault('done',0);result.setdefault('next_at',0);result.setdefault('break_until',0)
    return result


def complete(config,unit_id,now=None):
    now=time.time() if now is None else now;p=state(config)
    # A lost acknowledgement can repeat progress/result without consuming a slot twice.
    if p.get('last_unit')==unit_id:return status(config,now)
    p['last_unit']=unit_id;p['done']+=1
    p['last_delay_ms']=choose(round(p['delay_min_seconds']*1000),round(p['delay_max_seconds']*1000))
    p['next_at']=now+p['last_delay_ms']/1000
    if p['done']>=p['target']:
        p['last_batch_size']=p['target'];p['done']=0
        p['target']=choose(p['batch_min'],p['batch_max'])
        p['break_until']=now+p['batch_pause_seconds'];p['next_at']=max(p['next_at'],p['break_until'])
    return status(config,now)


def status(config,now=None):
    now=time.time() if now is None else now;p=state(config)
    return {'wait_ms':max(0,math.ceil((p['next_at']-now)*1000)),
            'break_until':p['break_until'],'next_at':p['next_at'],'batch_done':p['done'],'batch_target':p['target']}
