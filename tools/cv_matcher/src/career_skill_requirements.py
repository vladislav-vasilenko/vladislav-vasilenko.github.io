"""Conservative, cited local extraction, enriched by existing validated Luna rows."""
import re
from .career_skills_catalog import SKILLS,VERSION
from .career_analytics import apple_match
from .resume_source import normalize
from .archive_store import digest

EXTRACTOR=VERSION+'-requirements-1'
HEADINGS=re.compile(r'(?:(?:Обязательные|Ключевые|Hard)\s+(?:требования|requirements)|Требования|Мы жд[её]м(?:,? что вы)?|Мы ожидаем|Что мы жд[её]м|What we expect|Requirements|Qualifications|Must have|Будет плюсом|Будет преимуществом|Желательно|Nice to have|Preferred(?: qualifications)?|Основные задачи|Что нужно делать|Чем предстоит заниматься|Обязанности|Твои задачи|Задачи|Responsibilities|What you.ll do|Условия|Мы предлагаем|Что предлагаем|Benefits)(?:[ \t]*[:：]|[ \t]*(?=\n|$))',re.I)
PREFERRED=re.compile(r'плюсом|преимуществ|желател|nice to have|preferred|было бы здорово',re.I)
REQUIRED=re.compile(r'требован|мы жд|мы ожида|requirements|qualifications|must have|необходим|требуется|обязател|уверенн|опыт|знани|понимани|владени|умеете|должны|must|required|proficien|experience|familiarity',re.I)
NEGATED=re.compile(r'(?:не\s+(?:нужен|нужно|требуется|требуем|обязател\w*)|(?:опыт|знание)\s+[^.;\n]{0,50}не\s+(?:нужен|требуется|обязател\w*)|no\s+[^.;\n]{0,40}(?:required|necessary))',re.I)
BENEFITS=re.compile(r'условия|мы предлагаем|что предлагаем|benefits',re.I)
HARD_BLOCKER=re.compile(r'обязательн|must have|критичн|жестк|строго|строгие требования|не менее \d+|mandatory|non-negotiable|essential',re.I)

def hits(text):
 for key,s in SKILLS.items():
  match=apple_match(text,s['pattern']) if key=='metal' else re.search(s['pattern'],text,re.I)
  if not match:continue
  if key=='triton' and re.search(r'triton.{0,15}(?:inference server|сервер)',text,re.I) and not re.search(r'kernel|ядр|jit',text,re.I):continue
  yield key,match

def passages(text):
 """Retain original spans; headings apply only until the next heading."""
 headings=list(HEADINGS.finditer(text));regions=[]
 start=0;mode='mentioned';section=''
 for h in headings:
  if h.start()>start:regions.append((start,h.start(),mode,section))
  section=h.group();mode='skip' if BENEFITS.search(section) else 'preferred' if PREFERRED.search(section) else 'required' if REQUIRED.search(section) else 'mentioned';start=h.end()
 regions.append((start,len(text),mode,section))
 for start,end,mode,section in regions:
  if mode=='skip':continue
  for m in re.finditer(r'[^\n;]+',text[start:end]):
   raw=m.group();offset=start+m.start()
   # Split prose sentences without breaking decimals or C++/identifiers.
   for part in re.finditer(r'.+?(?:[.!?](?=\s+[A-ZА-ЯЁ—-])|$)',raw):
    quote=part.group().strip()
    if quote:yield quote,mode,section,offset+part.start()+len(part.group())-len(part.group().lstrip())

def requirement_type(quote,mode,section=''):
 if NEGATED.search(quote):return 'mentioned',True,'none'
 if PREFERRED.search(quote):return 'preferred',False,'nice'
 if mode=='preferred':return mode,False,'nice'
 if mode=='required' or REQUIRED.search(quote):
  is_hard=bool(HARD_BLOCKER.search(section) or HARD_BLOCKER.search(quote))
  return 'required',False,'hard' if is_hard else 'standard'
 return 'mentioned',False,'none'

def extract(job,analysis=None):
 if job.get('description_quality')!='full':return {'requirements':[],'unmapped':[],'state':'missing_full_description','extractor':EXTRACTOR}
 text=job.get('description','');items=[];seen=set();unmapped=[]
 for quote,mode,section,offset in passages(text):
  kind,negated,strictness=requirement_type(quote,mode,section);found=list(hits(quote))
  if not found and mode in ('required','preferred') and len(quote)>15:unmapped.append(quote[:400])
  for key,m in found:
   # Keep an exact continuous source fragment even for a huge flattened DOM line.
   left=max(0,m.start()-160);right=min(len(quote),max(m.end()+160,left+400));evidence=quote[left:right]
   identity=(key,kind,offset+left,evidence)
   if identity in seen:continue
   seen.add(identity);items.append({'id':digest([job['id'],*identity]),'vacancy_id':job['id'],'skill_id':key,'normalized_skill':SKILLS[key]['label'],'quote':evidence,'quote_start':offset+left,'type':kind,'strictness':strictness,'confidence':.9 if section else .75 if kind!='mentioned' else .55,'negated':negated,'source':'local_rules','section':section,'extractor':EXTRACTOR,'analysis_key':None})
 if analysis:
  for row in analysis.get('requirements',[]):
   quote=row.get('job_quote','')
   if not isinstance(quote,str) or len(quote)<15 or normalize(quote) not in normalize(text):continue
   # Anchor Luna to the original region; never upgrade a casual mention solely
   # because the old model marked importance=must.
   anchor=re.search(r'\s+'.join(re.escape(t) for t in quote.split()),text)
   if not anchor:continue
   quote=anchor.group()
   base=[i for i in items if normalize(quote) in normalize(i['quote']) or normalize(i['quote']) in normalize(quote)]
   kind='preferred' if row.get('importance')=='nice' else 'required' if row.get('importance')=='must' and any(i['type']=='required' for i in base) else 'mentioned'
   strictness='hard' if row.get('importance')=='must' else 'nice' if row.get('importance')=='nice' else 'standard' if kind=='required' else 'none'
   for key,_ in hits(quote):
    items.append({'id':digest([job['id'],analysis.get('key'),key,quote]),'vacancy_id':job['id'],'skill_id':key,'normalized_skill':SKILLS[key]['label'],'quote':quote,'quote_start':anchor.start(),'type':kind,'strictness':strictness,'confidence':.95 if kind!='mentioned' else .7,'negated':bool(NEGATED.search(quote)),'source':'luna_cached','section':next((i['section'] for i in base if i['skill_id']==key),''),'extractor':EXTRACTOR,'analysis_key':analysis.get('key')})
 return {'requirements':items,'unmapped':list(dict.fromkeys(unmapped))[:30],'state':'ready','extractor':EXTRACTOR}
