"""Allowlisted public projections. Never exports SQLite, entities or raw analyses."""
import re
from collections import Counter, defaultdict
from .career_skills_catalog import SKILLS
from .career_trajectory import overview
from .career_analytics import snapshot, number


def options(value, *, preview=False):
    if not isinstance(value, dict): raise ValueError('Выберите публичные визуализации.')
    result = {}
    if value.get('competencies') or value.get('crm'): raise ValueError('Внутренние разборы и история откликов не публикуются.')
    for key in ('enabled', 'trajectory', 'market'):
        if type(value.get(key, False)) is not bool: raise ValueError('Некорректный переключатель визуализации.')
        result[key] = value.get(key, False)
    identifier=value.get('trajectory_id', '')
    if not isinstance(identifier,str) or len(identifier)>100: raise ValueError('Выберите траекторию.')
    sample=value.get('sample','research')
    if sample not in ('research','all'): raise ValueError('Выберите исследовательскую или общую выборку.')
    result['sample']=sample
    result['trajectory_id']=identifier
    if result['enabled'] and value.get('reviewed') is not True and not preview: raise ValueError('Проверьте публичную выборку перед включением.')
    return result


def project(archive, settings):
    if not settings.get('enabled'): return None
    result = {'schema_version':1}
    if settings.get('trajectory'):
        value=overview(archive, archive, settings.get('trajectory_id') or None);path=value['path']
        if path:
            track=next(t for t in value['tracks'] if t['id']==path['track_id'])
            keys=sorted({k for s in path['stages'] for c in s['criteria'] for k in c['skill_ids'] if k in SKILLS})
            studying={k for e in value['evidence'] if e['kind']=='learning' and e['state']=='studying' for k in e['skill_ids']}
            # Publish the generic track name, never the private goal, target employer, criteria notes or evidence IDs.
            from .portfolio_publication import read
            from .resume_source import matching_text
            cv=archive.detail('resume',archive.summary()['primary_id'])['payload']
            allowed=set(re.findall(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',matching_text(cv)))
            labs=[{'url':r['url'],'label':r['url'].split('/')[-1]} for r in read(archive).get('github_activity',[]) if r.get('url') in allowed][:4]
            result['trajectory']={'label':track['label'], 'labs':labs, 'stages':[{'label':s['label']} for s in path['stages']],
                'focus_skills':[SKILLS[k]['label'] for k in keys[:5]], 'studying':[SKILLS[k]['label'] for k in keys if k in studying][:5]}
    if settings.get('market'):
        data=snapshot(archive); rows=[r for r in data['rows'] if settings.get('sample')=='all' or r['category'] in {'pretraining','post_training','diffusion','research','infrastructure','cuda'}];labels={t['id']:t['label'] for t in data['taxonomy']}
        groups=Counter(r['category'] for r in rows); top=[k for k,_ in groups.most_common(7)]
        group=lambda row:row['category'] if row['category'] in top else 'other_public'
        counts=defaultdict(Counter);buckets=Counter()
        for row in rows:
            category=group(row);counts[category]['total']+=1;counts[category]['full' if row['quality']=='full' else 'partial']+=1
            x=number(row['similarity'],-1,1);y=number(row['alignment'],-1,1)
            if x is not None and y is not None and not row.get('ranking_stale'):
                buckets[(round(x,2),round(y,2),category)]+=1
        if settings.get('market'):
            points=[{'x':x,'y':y,'category':category,'count':count} for (x,y,category),count in sorted(buckets.items())]
            result['market']={'sample':settings.get('sample','research'),'observed':len(rows), 'mapped':sum(p['count'] for p in points[:1200]), 'points':points[:1200],
                'categories':[{'id':key,'label':labels.get(key,'Другие направления'),'total':c['total'],'full':c['full'],'partial':c['partial']} for key,c in sorted(counts.items(),key=lambda i:-i[1]['total'])],
                'method':'Saved cosine similarities; rounded to 0.01 and grouped. Observed sample, not the entire market; not a skill or hiring probability score.'}
    return result
