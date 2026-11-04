"""Allowlisted public projections. Never exports SQLite, entities or raw analyses."""
import json
import re
from collections import Counter, defaultdict
from .career_skills_catalog import SKILLS
from .career_trajectory import overview
from .career_analytics import snapshot, number
from .market_regions import MARKETS, market_of

RESEARCH_SAMPLE = {'pretraining','post_training','diffusion','research','infrastructure','cuda'}
# Directions backed by the owner's work history, not only the target research roles.
EXPERIENCE_SAMPLE = RESEARCH_SAMPLE | {'rag','ai_automation','vision','nlp'}
SAMPLES = {'research':RESEARCH_SAMPLE,'experience':EXPERIENCE_SAMPLE}


def in_sample(category,sample):
    return sample=='all' or category in SAMPLES[sample]


EXAMPLES_PER_CATEGORY=25
EXAMPLES_MAX_CHARS=300000
EMPLOYERS_PER_MARKET=40
SECTION=re.compile(r'(?:^|\n)\s*(?:обязанности|задачи|чем (?:предстоит|вы будете|ты будешь)[^\n]*|что (?:предстоит|нужно|делать)[^\n]*|responsibilities|what you(?:.ll| will)[^\n]*|you will[^\n]*|the role|about the role)\s*:?\s*\n',re.I)


# Keeps sales, finance and similar roles at AI companies out of the examples. Their text mentions ML, so the classifier counts them.
NON_TECHNICAL=re.compile(r'\b(?:account executive|accountant|accounting|recruit\w*|sales|legal|counsel|payroll|tax|revenue|marketing|communications|executive assistant|office manager|talent|business development|finance)\b|бухгалтер|продаж|рекрутер|юрист|маркетолог',re.I)


def public_text(value):
    """Vacancy text without contacts or links."""
    from .resume_files import redact_contacts
    return re.sub(r'https?://\S+|www\.\S+|\S+@\S+','',redact_contacts(value or ''))


def employer_name(row):
    return re.sub(r'\s+',' ',public_text(row.get('company'))).strip()[:80]


def summary(description,limit=140):
    text=public_text(description);found=SECTION.search(text)
    lines=[re.sub(r'^[\s•·*\-–—]+','',line).strip() for line in (text[found.end():] if found else text).split('\n')]
    picked=' '.join(line for line in lines if len(line)>=25)[:limit*2]
    picked=re.sub(r'\s+',' ',picked).strip()
    return picked if len(picked)<=limit else picked[:limit].rsplit(' ',1)[0].rstrip(' ,;:—-')+'…'


def examples_for(archive,rows,group,labels):
    # The page loader refuses a snapshot over 500000 characters, so shrink rather than lose the site's data.
    for limit in (EXAMPLES_PER_CATEGORY,15,10,5):
        result=examples_with_limit(archive,rows,group,labels,limit)
        if len(json.dumps(result,ensure_ascii=False))<=EXAMPLES_MAX_CHARS:return result
    return {}


def examples_with_limit(archive,rows,group,labels,limit):
    """The newest open vacancies per category. Fit scores and any vacancy the owner applied to or marked stay out."""
    chosen={};taken=[]
    for row in sorted(rows,key=lambda r:(str(r.get('first_seen') or ''),r['id']),reverse=True):
        if row.get('quality')!='full' or row.get('availability')=='closed' or row.get('application_id') or row.get('stage','none')!='none' or (row.get('manual_application') or {}).get('marked') or NON_TECHNICAL.search(row.get('title') or ''):continue
        # Per market, so filtering still fills each list. The newest first order lets the page take 25 for "all".
        items=chosen.setdefault((group(row),market_of(row)),[])
        if len(items)<limit:items.append(row);taken.append(row)
    ids=[row['id'] for row in taken];payloads={}
    with archive.connect() as db:
        for start in range(0,len(ids),400):
            part=ids[start:start+400]
            for found in db.execute(f"SELECT id,payload FROM entities WHERE kind='vacancy' AND id IN ({','.join('?'*len(part))})",part):payloads[found['id']]=json.loads(found['payload'])
    result={}
    for row in taken:
        cards=result.setdefault(group(row),[])
        if row['id'] not in payloads:continue
        title=re.sub(r'\s+',' ',re.sub(r'^[\s,;:|·—–-]+|[\s,;:|·—–-]+$','',public_text(row.get('title')))).strip()[:160]
        brief=summary(payloads[row['id']].get('description'))
        if not title or not brief:continue
        cards.append({'title':title,'company':employer_name(row),'summary':brief,'market':market_of(row),'keywords':[labels[t][:50] for t in row.get('tags',[]) if t!=row['category'] and t in labels][:4]})
    return {category:cards for category,cards in result.items() if cards}


def employer_counts(cells):
    """Vacancy counts for each market's largest employers. No scores: the map stays anonymous by employer."""
    totals=defaultdict(Counter)
    for (name,market,_),count in cells.items():
        if name:totals[market][name]+=count['full']+count['partial']
    keep={(market,name) for market,names in totals.items() for name,_ in sorted(names.items(),key=lambda i:(-i[1],i[0]))[:EMPLOYERS_PER_MARKET]}
    rows=defaultdict(list)
    for (name,market,category),count in sorted(cells.items()):
        if (market,name) in keep:rows[name].append([market,category,count['full'],count['partial']])
    return [{'name':name,'counts':values} for name,values in sorted(rows.items())]


def options(value, *, preview=False):
    if not isinstance(value, dict): raise ValueError('Выберите публичные визуализации.')
    result = {}
    if value.get('competencies') or value.get('crm'): raise ValueError('Внутренние разборы и история откликов не публикуются.')
    for key in ('enabled', 'trajectory', 'market', 'examples'):
        if type(value.get(key, False)) is not bool: raise ValueError('Некорректный переключатель визуализации.')
        result[key] = value.get(key, False)
    identifier=value.get('trajectory_id', '')
    if not isinstance(identifier,str) or len(identifier)>100: raise ValueError('Выберите траекторию.')
    sample=value.get('sample','research')
    if sample not in ('research','experience','all'): raise ValueError('Выберите исследовательскую или общую выборку.')
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
        data=snapshot(archive); rows=[r for r in data['rows'] if in_sample(r['category'],settings.get('sample','research'))];labels={t['id']:t['label'] for t in data['taxonomy']}
        groups=Counter(r['category'] for r in rows); top=[k for k,_ in groups.most_common(7)]
        group=lambda row:row['category'] if row['category'] in top else 'other_public'
        counts=defaultdict(Counter);buckets=Counter();by_market=defaultdict(lambda:defaultdict(Counter));by_employer=defaultdict(Counter)
        for row in rows:
            category=group(row);counts[category]['total']+=1;counts[category]['full' if row['quality']=='full' else 'partial']+=1
            market=market_of(row);by_employer[(employer_name(row),market,category)]['full' if row['quality']=='full' else 'partial']+=1;by_market[market][category]['total']+=1;by_market[market][category]['full' if row['quality']=='full' else 'partial']+=1
            x=number(row['similarity'],-1,1);y=number(row['alignment'],-1,1)
            if x is not None and y is not None and not row.get('ranking_stale'):
                buckets[(round(x,2),round(y,2),category,market)]+=1
        if settings.get('market'):
            points=[{'x':x,'y':y,'category':category,'market':market,'count':count} for (x,y,category,market),count in sorted(buckets.items())]
            markets=[{'id':key,'categories':[{'id':category,'total':c['total'],'full':c['full'],'partial':c['partial']} for category,c in sorted(by_market[key].items())]} for key in MARKETS if key in by_market]
            # Date only, and only moves with new vacancies, so it never causes a commit by itself.
            newest=max((str(r['first_seen']) for r in rows if r.get('first_seen')),default='')
            examples=examples_for(archive,rows,group,labels) if settings.get('examples') else None
            result['market']={'markets':markets,**({'employers':employer_counts(by_employer)} if settings.get('examples') else {}),**({'examples':examples} if examples else {}),**({'data_as_of':newest[:10]} if newest else {}),'sample':settings.get('sample','research'),'observed':len(rows), 'mapped':sum(p['count'] for p in points[:1200]), 'points':points[:1200],
                'categories':[{'id':key,'label':labels.get(key,'Другие направления'),'total':c['total'],'full':c['full'],'partial':c['partial']} for key,c in sorted(counts.items(),key=lambda i:-i[1]['total'])],
                'method':'Saved cosine similarities; rounded to 0.01 and grouped. Observed sample, not the entire market; not a skill or hiring probability score.'}
    return result
