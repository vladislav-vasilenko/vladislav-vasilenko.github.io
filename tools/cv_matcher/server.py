"""Local FastAPI scraping server — runs on http://localhost:8787.

Start with:
    uv run python server.py

Endpoints:
    GET  /health               — smoke check
    GET  /scrape/sources       — available SOURCE_GROUPS
    POST /scrape/start         — launch a scraping job → {job_id}
    GET  /scrape/stream/{id}   — SSE live events for a job
    GET  /scrape/jobs          — list of all jobs (status + counts)
"""

import asyncio
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Add project root to sys.path so we can import src.*
sys.path.insert(0, os.path.dirname(__file__))

from src.scrapers import SCRAPER_REGISTRY, SOURCE_GROUPS
from src.rag_db import RAGDatabase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_QUERIES: List[str] = [
    "ML",
    "LLM",
    "Audio ML",
    "Multi-Modal",
    "GenAI",
    "Diffusion",
    "RLHF",
    "Kandinsky",
    "Machine Learning Engineer",
]

# Relative to this file — matches cv_matcher.py output_dir
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "public")

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="CV Matcher Scraping Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
        "https://vladislav-vasilenko.github.io",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------

# job_id → {"status", "queue", "loop", "sources", "queries", "counts", "started_at", "finished_at"}
JOBS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class StartRequest(BaseModel):
    sources: List[str]
    queries: List[str] = []
    mode: str = "custom"       # "custom" | "cv-matched"
    limit: int = 20


class StartResponse(BaseModel):
    job_id: str


# ---------------------------------------------------------------------------
# Thread-safe event push helper
# ---------------------------------------------------------------------------

def _push(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue, event: dict) -> None:
    """Put an event onto the asyncio queue from a worker thread."""
    asyncio.run_coroutine_threadsafe(queue.put(event), loop)


# ---------------------------------------------------------------------------
# Scraping job runner (runs in a daemon thread)
# ---------------------------------------------------------------------------

def _run_job(job_id: str, sources: List[str], queries: List[str], limit: int,
             loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    emit = lambda event: _push(loop, queue, event)  # noqa: E731

    try:
        db = RAGDatabase(db_path=os.path.join(os.path.dirname(__file__), "chroma_db"))
        existing_ids = db.get_all_ids()

        total_sources = len(sources)
        done_count = 0
        all_vacancies: List[Dict[str, Any]] = []

        # Auth state paths from env (same as cv_matcher.py)
        auth_env = {
            "linkedin":  os.environ.get("LINKEDIN_STORAGE_STATE"),
            "wellfound": os.environ.get("WELLFOUND_STORAGE_STATE"),
            "indeed":    os.environ.get("INDEED_STORAGE_STATE"),
            "google":    os.environ.get("GOOGLE_STORAGE_STATE"),
            "meta":      os.environ.get("META_STORAGE_STATE"),
        }

        for source_key in sources:
            cls = SCRAPER_REGISTRY.get(source_key)
            if cls is None:
                emit({"type": "error", "source": source_key,
                      "message": f"Unknown source '{source_key}'"})
                continue

            done_count += 1
            emit({
                "type": "progress",
                "source": source_key,
                "done": done_count,
                "total": total_sources,
            })

            kwargs: Dict[str, Any] = {
                "limit": limit,
                "event_sink": emit,
            }
            storage_state = auth_env.get(source_key)
            if storage_state:
                kwargs["storage_state_path"] = storage_state

            scraper = cls(**kwargs)

            source_vacancies: List[Dict[str, Any]] = []
            for q in queries:
                try:
                    jobs = scraper.fetch_jobs(q, existing_ids=existing_ids)
                    source_vacancies.extend(jobs)
                except Exception as e:
                    emit({"type": "error", "source": source_key,
                          "message": f"Error on query '{q}': {e}"})

            # Dedupe within this source run
            seen: Dict[str, Dict[str, Any]] = {}
            for j in source_vacancies:
                jid = j["id"]
                if jid not in seen:
                    seen[jid] = j
            unique = list(seen.values())
            all_vacancies.extend(unique)

            if unique:
                try:
                    db.add_vacancies(unique)
                    existing_ids |= {j["id"] for j in unique}
                except Exception as e:
                    emit({"type": "error", "source": source_key,
                          "message": f"DB write error: {e}"})

        # Write a lightweight matcher_data.json update
        try:
            _write_matcher_json(db, all_vacancies)
        except Exception as e:
            emit({"type": "error", "source": "server",
                  "message": f"JSON export error: {e}"})

        total_new = len(all_vacancies)
        emit({
            "type": "done",
            "total_new": total_new,
            "total_in_db": db.collection.count(),
        })
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        JOBS[job_id]["total_new"] = total_new

    except Exception as e:
        emit({"type": "error", "source": "server", "message": str(e)})
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()


def _write_matcher_json(db: RAGDatabase, new_vacancies: List[Dict[str, Any]]) -> None:
    """Append new vacancies to matcher_data.json (preserves existing entries)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "matcher_data.json")

    existing_data: Dict[str, Any] = {"vacancies": [], "scatter_3d": []}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            pass

    # Build id→vacancy map so we can upsert without full duplicate check
    vac_map: Dict[str, Any] = {v["id"]: v for v in existing_data.get("vacancies", [])}
    for v in new_vacancies:
        if v["id"] not in vac_map:
            # Scraped raw vacancies don't have ATS scores yet — add defaults
            entry = dict(v)
            entry.setdefault("ats_score", None)
            entry.setdefault("reasoning", "Scraping complete — run cv_matcher.py for ATS scoring")
            entry.setdefault("missing_skills", [])
            vac_map[v["id"]] = entry

    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_jobs_in_db": db.collection.count(),
        "vacancies": list(vac_map.values()),
        "scatter_3d": existing_data.get("scatter_3d", []),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✅ matcher_data.json updated → {json_path}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "registry_size": len(SCRAPER_REGISTRY)}


@app.get("/scrape/sources")
def get_sources() -> dict:
    return {
        "groups": SOURCE_GROUPS,
        "registry": list(SCRAPER_REGISTRY.keys()),
        "auth_env": {
            k: bool(os.environ.get(v))
            for k, v in {
                "linkedin": "LINKEDIN_STORAGE_STATE",
                "wellfound": "WELLFOUND_STORAGE_STATE",
                "google": "GOOGLE_STORAGE_STATE",
                "meta": "META_STORAGE_STATE",
            }.items()
        },
        "default_queries": DEFAULT_QUERIES,
    }


@app.post("/scrape/start", response_model=StartResponse)
async def start_scrape(req: StartRequest) -> StartResponse:
    # Resolve group names to individual source keys
    sources: List[str] = []
    seen_sources: set = set()
    for s in req.sources:
        if s in SOURCE_GROUPS:
            for key in SOURCE_GROUPS[s]:
                if key not in seen_sources:
                    sources.append(key)
                    seen_sources.add(key)
        elif s in SCRAPER_REGISTRY:
            if s not in seen_sources:
                sources.append(s)
                seen_sources.add(s)

    if not sources:
        raise HTTPException(400, "No valid sources specified")

    queries = req.queries if req.queries else DEFAULT_QUERIES
    job_id = str(uuid.uuid4())[:8]
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    JOBS[job_id] = {
        "status": "running",
        "queue": queue,
        "loop": loop,
        "sources": sources,
        "queries": queries,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "total_new": None,
    }

    t = threading.Thread(
        target=_run_job,
        args=(job_id, sources, queries, req.limit, loop, queue),
        daemon=True,
    )
    t.start()
    return StartResponse(job_id=job_id)


@app.get("/scrape/stream/{job_id}")
async def stream_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    queue: asyncio.Queue = job["queue"]

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {"data": json.dumps(event, ensure_ascii=False)}
                if event.get("type") in ("done", "error") and event.get("source") in (None, "server"):
                    break
            except asyncio.TimeoutError:
                # Keepalive ping so the browser doesn't close the connection
                yield {"data": json.dumps({"type": "ping"})}
                if job.get("status") in ("done", "error"):
                    break

    return EventSourceResponse(event_generator())


@app.get("/scrape/jobs")
def list_jobs() -> dict:
    return {
        job_id: {
            "status": j["status"],
            "sources": j["sources"],
            "queries": j["queries"],
            "started_at": j["started_at"],
            "finished_at": j["finished_at"],
            "total_new": j.get("total_new"),
        }
        for job_id, j in JOBS.items()
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
