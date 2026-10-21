"""Usage: .venv/bin/python scripts/evaluate-career-skills.py [labeled.json]."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from src.skills_quality import evaluate
path=Path(sys.argv[1]) if len(sys.argv)>1 else root/'src/tests/fixtures/skill_requirements_labeled.json'
print(json.dumps(evaluate(json.loads(path.read_text())['items']),ensure_ascii=False,indent=2))
