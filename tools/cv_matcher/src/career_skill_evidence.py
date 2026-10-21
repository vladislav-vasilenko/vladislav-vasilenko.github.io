"""Independent evidence axes; missing proof is unknown, never an inferred gap."""
import re
from .career_skills_catalog import SKILLS
from .career_skill_requirements import hits
from .resume_source import matching_text,normalize
from .resume_files import redact_contacts
from .candidate_facts import read as facts
from .resume_supplements import read as supplements
from .candidate_profile import read as profile
from .career_skills_store import annotations

NEGATIVE=re.compile(r'нет (?:коммерческого )?опыта|не (?:работал|работала|использовал|использовала|умею)|без опыта|no experience|never used',re.I)
PLANNED=re.compile(r'планир|собираюсь|намерен|хочу изуч|буду изуч|пока только план|plan to|future work',re.I)
LEARNING=re.compile(r'изуча|учусь|курс|лекци|лабораторн|учебн|studying|course|lecture|6\.s184',re.I)
DONE=re.compile(r'реализовал|разработал|обучил|обучал|пров[её]л|воспроизв[её]л|построил|внедрил|оптимизировал|работаю|работал|освоил|владею|implemented|trained|built|conducted',re.I)
PROFESSIONAL=re.compile(r'коммерческ|на работе|production|продакш|в компании|для работодателя|в рабочем проекте',re.I)
RESEARCH=re.compile(r'эксперимент|абляци|benchmark|бенчмарк|исследовани|research experiment',re.I)
PROJECT=re.compile(r'самостоятельн|личн\w* проект|учебн|лабораторн|pet.project|собственн\w* проект',re.I)
GITHUB=re.compile(r'https://github\.com/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.\-/]+)?')

def automatic(text,source,version=None,employment=False):
 records=[];text=redact_contacts(text)
 for piece in re.split(r'\n+|(?<=[.!?;])\s+|,\s*(?:но|but)\s+',text):
  for key,m in hits(piece):
   quote=piece[max(0,m.start()-170):m.end()+220].strip()
   base={'skill_id':key,'quote':quote,'source':source,'source_version':version,'confidence':.7,'artifact_verified':False}
   if source=='cv':records.append({**base,'kind':'cv_mention','state':'mentioned'})
   if NEGATIVE.search(quote):records.append({**base,'kind':'explicit_gap','state':'confirmed'});continue
   if PLANNED.search(quote):records.append({**base,'kind':'learning','state':'planned'});continue
   learning=bool(LEARNING.search(quote))
   if learning:records.append({**base,'kind':'learning','state':'studying'})
   if DONE.search(quote):
    kind='research' if RESEARCH.search(quote) else 'project' if PROJECT.search(quote) else 'professional' if employment or PROFESSIONAL.search(quote) else 'practice'
    records.append({**base,'kind':kind,'state':'confirmed','educational':learning})
 return records

def collect(store,archive,resume_id,analyses):
 detail=archive.detail('resume',resume_id);cv=detail['payload'];cv_text=redact_contacts(matching_text(cv));records=automatic(cv_text,'cv',detail['version_id'])
 fact_rows=facts(store,resume_id);supp=supplements(archive,resume_id);owner=annotations(store,resume_id)
 for row in fact_rows:records.extend(automatic(row['text'],'candidate_fact',row['id']))
 for row in supp:records.extend(automatic(row['description'],'resume_supplement',row['version_id'],employment=True))
 for analysis in analyses:
  for row in analysis.get('requirements',[]):
   if row.get('status') not in ('confirmed','partial','studying','explicit_gap'):continue
   quotes=[q for q in row.get('resume_quotes',[]) if isinstance(q,str) and normalize(q) in normalize(cv_text)]
   if not quotes:continue
   for key,_ in hits(row.get('job_quote','')):
    for quote in quotes:
     if key not in {k for k,_ in hits(quote)} or PLANNED.search(quote):continue
     if row['status']=='confirmed' and (LEARNING.search(quote) or NEGATIVE.search(quote)):continue
     kind='explicit_gap' if row['status']=='explicit_gap' else 'learning' if row['status']=='studying' else 'analysis'
     records.append({'skill_id':key,'kind':kind,'state':row['status'],'quote':quote,'source':'luna_cached','source_version':analysis.get('key'),'confidence':.85,'artifact_verified':False})
 for row in owner:
  if row['state']!='retracted':records.append({**row,'source_version':row['revision'],'confidence':1.})
 grouped={}
 for key in SKILLS:
  rows=[r for r in records if r['skill_id']==key];confirmed=lambda k:any(r['kind']==k and r['state']=='confirmed' for r in rows)
  flags={k:confirmed(k) for k in ('professional','project','research','practice','explicit_gap')}
  flags.update(cv_mention=any(r['kind']=='cv_mention' for r in rows),learning=any(r['kind']=='learning' and r['state'] in ('studying','completed') for r in rows),learning_completed=any(r['kind']=='learning' and r['state']=='completed' for r in rows),analysis_confirmation=confirmed('analysis'),partial=any(r['state']=='partial' for r in rows),published=any(r.get('url') and (not r['url'].startswith('https://github.com/') or len(r['url'].rstrip('/').split('/'))>=5) and r['state']=='confirmed' and r['kind'] in ('project','research') for r in rows))
  practical=any(flags[k] for k in ('professional','project','research','practice','analysis_confirmation'))
  conflict=flags['explicit_gap'] and practical or any(r['state']=='not_confirmed' and confirmed(r['kind']) for r in rows)
  state='conflict' if conflict else 'confirmed' if practical else 'explicit_gap' if flags['explicit_gap'] else 'studying' if flags['learning'] else 'partial' if flags['partial'] else 'unknown'
  grouped[key]={'skill_id':key,'state':state,'flags':flags,'evidence':rows[:30],'owner_revisions':{r['kind']:r['revision'] for r in owner if r['skill_id']==key}}
 links=set(GITHUB.findall(cv_text));p=profile(store)['values'].get('portfolio_url','')
 if GITHUB.fullmatch(p):links.add(p)
 for row in records:
  url=row.get('url','')
  if GITHUB.fullmatch(url):links.add(url)
 return {'skills':grouped,'github':[{'url':url.rstrip('.,)/'),'verified':False,'note':'Ссылка из CV/профиля/уточнения. Содержимое и качество репозитория автоматически не проверены.'} for url in sorted(links)],'versions':{'cv':detail['version_id'],'facts':[r['id'] for r in fact_rows],'supplements':[r['version_id'] for r in supp],'owner':[(r['skill_id'],r['kind'],r['revision']) for r in owner]},'resume':detail}
