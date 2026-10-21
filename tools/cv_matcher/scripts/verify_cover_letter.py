"""Explicit paid live check using extension exports; never submits an application."""
import argparse
import json
import os
from pathlib import Path
import urllib.request
import urllib.error

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resumes',type=Path,required=True)
    parser.add_argument('--vacancies',type=Path,required=True)
    parser.add_argument('--vacancy-id',required=True)
    parser.add_argument('--resume-id')
    parser.add_argument('--sentences',type=int,choices=range(1,51),default=2)
    parser.add_argument('--comments',default='')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    bundle=json.loads(args.resumes.read_text())
    selected=args.resume_id or bundle['primary_id']
    cv=next(r for r in bundle['resumes'] if r['id']==selected)
    job=next(j for j in json.loads(args.vacancies.read_text()) if j['id']==args.vacancy_id)
    payload={'resume_id':selected,'bundle':{**bundle,'primary_id':selected,'resumes':[cv]},'vacancy':job,'sentence_count':args.sentences,'comments':args.comments}
    token=(root/'.cache/resume_import/token.txt').read_text().strip()
    request=urllib.request.Request('http://127.0.0.1:8788/cover-letter',data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-Resume-Import-Token':token},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=390) as response:result=json.load(response)
    except urllib.error.HTTPError as error:
        print(json.loads(error.read()).get('detail','Сервис отклонил черновик.'));return 1
    assert result['resume_id']==selected and result['resume_hash']==cv['content_hash'] and result['vacancy_id']==job['id']
    assert result['sentence_count']==args.sentences and len(result['evidence'])==args.sentences
    directory=root/'.cache/live_checks';directory.mkdir(parents=True,exist_ok=True);os.chmod(directory,0o700)
    path=directory/'cover_letter.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as handle:json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ['vacancy_title','model','sentence_count','word_count','char_count','cached','api_requests','input_tokens','output_tokens']},ensure_ascii=False))
    print(result['text'])
    return 0

if __name__=='__main__':raise SystemExit(main())
