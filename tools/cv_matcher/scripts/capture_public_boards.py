"""Fetch only explicitly supplied public URLs. No bypass, login or auto-response."""
import argparse
import json
import sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.board_import import extract_html

p = argparse.ArgumentParser()
p.add_argument("--urls", required=True, help="JSON array of observed listing/detail URLs")
p.add_argument("--output", required=True)
args = p.parse_args()
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
results, failures = [], []
session = requests.Session()
session.headers["User-Agent"] = "CVMatcher/0.3 (public vacancy analysis)"
for index, url in enumerate(json.loads(Path(args.urls).read_text())):
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        (out / f"page_{index:02d}.html").write_text(response.text, encoding="utf-8")
        rows = extract_html(response.text, response.url)
        results.extend(rows)
        print(f"{index + 1}: {response.status_code}, {len(rows)} records, {sum(r['description_quality']=='full' for r in rows)} full", flush=True)
        if not rows: failures.append({"url": url, "reason": "rendered_browser_required"})
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else None
        failures.append({"url": url, "reason": type(exc).__name__, "status": status})
        print(f"{index + 1}: {type(exc).__name__}, status={status}", flush=True)
(out / "vacancies.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
