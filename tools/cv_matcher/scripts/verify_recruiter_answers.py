"""Explicit paid OpenAI check from exports. Queues a local draft, sends nothing to Telegram."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import urllib.request
import urllib.error

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resumes',type=Path,required=True);parser.add_argument('--vacancies',type=Path,required=True)
    parser.add_argument('--vacancy-id',required=True);parser.add_argument('--goal',default='Generative Modelling / DiT / Transformer pre-training и post-training')
    parser.add_argument('--models',default='luna,terra,sol');args=parser.parse_args()
    models=args.models.split(',')
    if not set(models)<={'luna','terra','sol'}:parser.error('Допустимы luna,terra,sol')
    root=Path(__file__).resolve().parents[1];bundle=json.loads(args.resumes.read_text());selected=bundle['primary_id']
    cv=next(r for r in bundle['resumes'] if r['id']==selected);job=next(j for j in json.loads(args.vacancies.read_text()) if j['id']==args.vacancy_id)
    token=(root/'.cache/resume_import/token.txt').read_text().strip()
    def call(path,payload):
        request=urllib.request.Request('http://127.0.0.1:8788'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Resume-Import-Token':token})
        try:
            with urllib.request.urlopen(request,timeout=95) as response:return json.load(response)
        except urllib.error.HTTPError as error:return {'error':json.loads(error.read()).get('detail','Ошибка сервиса')}
    app=call('/applications',{'resume_id':selected,'bundle':{**bundle,'primary_id':selected,'resumes':[cv]},'vacancy':job,'goal':args.goal,'channel':'telegram'})
    if 'error' in app:print(app['error']);return 1
    def check(model):
        result=call('/answer-draft',{'application_id':app['id'],'question':'Почему вас заинтересовала эта вакансия и какой ваш опыт может пригодиться команде?','model':model})
        return model,result
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=dict(pool.map(check,models))
    directory=root/'.cache/live_checks';directory.mkdir(parents=True,exist_ok=True);os.chmod(directory,0o700)
    fd=os.open(directory/'recruiter_answers.json',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as handle:json.dump({'application_id':app['id'],'results':results},handle,ensure_ascii=False,indent=2)
    for model,result in results.items():print(json.dumps({'alias':model,**{k:result[k] for k in ['model','cached','api_requests','input_tokens','output_tokens','needs_user','error'] if k in result}},ensure_ascii=False))
    return int(any('error' in r for r in results.values()))

if __name__=='__main__':raise SystemExit(main())
