"""Offline evaluation on a labeled set, no models or archive mutation."""
from .career_skill_requirements import extract

def evaluate(items):
 tp=fp=fn=exact=0;errors=[];citations=0;broken=0
 for item in items:
  rows=extract({'id':item['id'],'description_quality':'full','description':item['text']})['requirements']
  actual={(r['skill_id'],r['type']) for r in rows};expected=set(item['expected'].items())
  tp+=len(actual&expected);fp+=len(actual-expected);fn+=len(expected-actual);exact+=actual==expected
  if actual!=expected:errors.append({'id':item['id'],'extra':sorted(actual-expected),'missing':sorted(expected-actual)})
  for r in rows:
   citations+=1;broken+=item['text'][r['quote_start']:r['quote_start']+len(r['quote'])]!=r['quote']
 return {'cases':len(items),'true_positive':tp,'false_positive':fp,'false_negative':fn,'precision':round(tp/max(1,tp+fp),4),'recall':round(tp/max(1,tp+fn),4),'exact_cases':exact,'citations':citations,'broken_citations':broken,'errors':errors,'note':'Development regression set; not held-out production accuracy.'}
