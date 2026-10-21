"""One explicit live/cached skill review; no application or recruiter messaging."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from src.archive_store import ArchiveStore
from src.skill_analysis import analyze
load_dotenv(ROOT/'.env')
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('vacancy_id');parser.add_argument('--resume-id');args=parser.parse_args()
store=ArchiveStore(ROOT/'.cache/applications/state.sqlite3');resume=args.resume_id or store.summary()['primary_id']
try:
 result=analyze(store,resume,args.vacancy_id,store.summary()['goal'])
 print(json.dumps({'ok':True,'vacancy_id':result['vacancy_id'],'model':result['model'],'requirements':len(result['requirements']),'coverage':result['metrics']['overall']['percent'],'cached':result['cached'],'api_requests':result['api_requests'],'key':result['key']},ensure_ascii=False))
except ValueError as error:print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False));sys.exit(1)
