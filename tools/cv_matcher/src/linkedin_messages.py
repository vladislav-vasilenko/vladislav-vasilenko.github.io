"""Validate locally stored conversation messages; never render remote HTML."""
from urllib.parse import urlsplit


def string(value,maximum):
    if not isinstance(value,str) or len(value)>maximum:raise ValueError('Некорректное поле сообщения LinkedIn.')
    return value.strip()


def messages(rows):
    if not isinstance(rows,list) or len(rows)>500:raise ValueError('Слишком много сообщений в порции.')
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('Неверный формат сообщения.')
        item={key:string(row.get(key,''),limit) for key,limit in [('id',1000),('sender',500),('text',20000),('sent_label',200),('sent_at',100)]}
        if not item['id'] or item['id'] in seen:continue
        seen.add(item['id']);item['id_kind']='source' if row.get('id_kind')=='source' else 'content'
        badges=row.get('badges',[])
        if not isinstance(badges,list) or len(badges)>30:raise ValueError('Слишком много бейджей сообщения.')
        item['badges']=[string(b,200) for b in badges]
        attachments=row.get('attachments',[])
        if not isinstance(attachments,list) or len(attachments)>10:raise ValueError('Слишком много ссылок сообщения.')
        item['attachments']=[]
        for a in attachments:
            url=string(a.get('url',''),2500);u=urlsplit(url)
            if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('Небезопасная ссылка в сообщении.')
            item['attachments'].append({'url':url,'label':string(a.get('label',''),200)})
        result.append(item)
    return result


def merge(previous,incoming):
    """Insert previously unseen messages around known anchors, preserving source order."""
    rows={m['id']:m for m in previous};order=list(rows);anchor=None
    for item in reversed(incoming):
        key=item['id']
        if key not in rows:
            index=order.index(anchor) if anchor in rows else len(order)
            order.insert(index,key)
        rows[key]=item;anchor=key
    return [rows[key] for key in order]
