"""Offline Transformer shortlist. Similarity is not an ATS percentage or probability."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.board_import import load_board_export
from src.resume_source import load_hh_resumes, matching_text

p = argparse.ArgumentParser()
p.add_argument("--vacancies", required=True)
cv = p.add_mutually_exclusive_group(required=True)
cv.add_argument("--resume-bundle", "--hh-resumes", dest="hh_resumes", help="Fresh full extension export (normal operation)")
cv.add_argument("--audit-cv", help="Explicit audited excerpt for this integration test only")
p.add_argument("--policy", default="hh-research-extension/resume-profile.local.json")
p.add_argument("--model-path", required=True, help="Existing local model directory; never downloads")
p.add_argument("--output", required=True)
p.add_argument("--top-k", type=int, default=10)
args = p.parse_args()
jobs, rejected = load_board_export(args.vacancies)
if not jobs: p.error("Нет полных проверенных описаний; карточки/needs_review нельзя оценивать.")
if args.hh_resumes:
    bundle = load_hh_resumes(args.hh_resumes, args.policy)
    resume = bundle["primary"]
    resume_text = matching_text(resume)
    provenance = {"quality": "full", "content_hash": resume["content_hash"], "checked_at": resume["checked_at"]}
else:
    audit = json.loads(Path(args.audit_cv).read_text())
    checked = datetime.fromisoformat(audit["captured_at"].replace("Z", "+00:00"))
    if not -timedelta(minutes=5) <= datetime.now(timezone.utc) - checked <= timedelta(hours=24):
        p.error("Аудит устарел: перечитай актуальное резюме.")
    resume_text = audit["text"]
    provenance = {"quality": audit["quality"], "checked_at": audit["captured_at"],
                  "content_hash": hashlib.sha256(resume_text.encode()).hexdigest(), "method": audit["method"]}

import numpy as np
from sentence_transformers import SentenceTransformer
print("Loading offline Transformer…", flush=True)
model = SentenceTransformer(args.model_path, local_files_only=True, device="cpu")
model.max_seq_length = 384
# Chunk before encoding to avoid silently losing the end of the resume or JD.
def chunks(text, size=950):
    words = text.split()
    out, current, count = [], [], 0
    for word in words:
        if count + len(word) + 1 > size:
            out.append(" ".join(current)); current, count = [], 0
        current.append(word); count += len(word) + 1
    if current: out.append(" ".join(current))
    return out

cv_chunks = chunks(resume_text)
intent = "Исследователь инженер Research Engineer generative modelling обучение генеративных моделей. Transformer pre-training continual pre-training post-training SFT RLHF. Diffusion DiT Flow Matching мультимодальные модели аудио видео изображения PyTorch воспроизводимые эксперименты распределённое обучение."
texts = cv_chunks + [intent]
ranges = []
for job in jobs:
    start = len(texts)
    texts.extend(chunks(job["title"] + "\n" + job["description"]))
    ranges.append((start, len(texts)))
print(f"Encoding {len(texts)} chunks / {len(jobs)} vacancies…", flush=True)
vecs = model.encode(texts, batch_size=4, normalize_embeddings=True, show_progress_bar=False)
resume_vectors, intent_vector = vecs[:len(cv_chunks)], vecs[len(cv_chunks)]
ranked = []
for job, (start, stop) in zip(jobs, ranges):
    v = vecs[start:stop]
    # Average two strongest JD chunks, each matched to the closest professional CV chunk.
    skill = float(np.sort((v @ resume_vectors.T).max(axis=1))[-min(2,len(v)):].mean())
    direction = float(np.sort(v @ intent_vector)[-min(2,len(v)):].mean())
    ranked.append({**job, "cv_similarity": round(skill,4), "goal_similarity": round(direction,4),
                   "shortlist_score": round(.55*skill + .45*direction,4)})
ranked.sort(key=lambda r:r["shortlist_score"], reverse=True)
payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "resume": provenance,
           "model_path": str(Path(args.model_path).resolve()), "method": "mean pooling, normalized vectors; chunked similarity; 55% CV, 45% goal; no LLM assessment",
           "score_warning": "Cosine similarities, not probability, skill coverage or 100% match",
           "input_count": len(jobs), "rejected": rejected, "top": ranked[:args.top_k], "all": ranked}
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
for index, job in enumerate(ranked, 1):
    print(index, job["id"], job["shortlist_score"], job["title"], flush=True)
