"""Private HH snapshots, freshness validation, and embedding cache (no network)."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def matching_text(resume):
    return "\n\n".join([normalize(resume["title"]), *[
        f"{normalize(section['heading'])}\n{normalize(section['text'])}"
        for section in resume["sections"]]])


def content_hash(resume):
    return hashlib.sha256(matching_text(resume).encode("utf-8")).hexdigest()


def load_hh_resumes(bundle_path, policy_path, *, now=None):
    """Require a recent primary snapshot; optional unavailable reserves are skipped."""
    try:
        bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("Обнови резюме в расширении и экспортируй hh_resumes.json перед запуском.") from exc
    now = now or datetime.now(timezone.utc)
    if bundle.get("schema_version", 1) == 2:
        return _load_resume_bundle(bundle, now=now)
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    max_age = timedelta(hours=policy.get("max_age_hours", 24))
    primary_id = policy["primary_id"]
    accepted = {}
    roles = {r["id"]: r["role"] for r in policy["resumes"]}
    for resume in bundle.get("resumes", []):
        rid = resume.get("id")
        if rid not in roles:
            continue
        try:
            checked = datetime.fromisoformat(str(resume["checked_at"]).replace("Z", "+00:00"))
            if checked.tzinfo is None or not -timedelta(minutes=5) <= now - checked <= max_age:
                raise ValueError("Снимок резюме устарел. Обнови его в расширении перед запуском.")
            if resume.get("quality") != "full" or not normalize(resume.get("title")):
                raise ValueError("Резюме прочитано не полностью.")
            if not any(s.get("key") == "experience" and len(normalize(s.get("text"))) > 100
                       for s in resume.get("sections", [])):
                raise ValueError("В резюме отсутствует полный раздел опыта.")
            digest = content_hash(resume)
            if resume.get("content_hash") != digest:
                raise ValueError("Содержимое снимка резюме не совпадает с его версией.")
            accepted[rid] = {**resume, "role": roles[rid], "matching_text": matching_text(resume)}
        except (KeyError, TypeError, ValueError) as exc:
            if rid == primary_id:
                raise ValueError(f"Основное резюме не готово: {exc}") from exc
    if primary_id not in accepted:
        raise ValueError("Актуальное основное резюме обязательно; резервные его не заменяют.")
    return {"primary": accepted[primary_id], "resumes": list(accepted.values()), "policy": policy}


def _load_resume_bundle(bundle, *, now):
    """Explicit primary across HH, reviewed Google Docs and immutable file imports."""
    primary_id = bundle.get("primary_id")
    accepted = {}
    for resume in bundle.get("resumes", []):
        rid = resume.get("id")
        try:
            source = resume.get("source_type", "hh")
            url = urlsplit(resume.get("source_url", ""))
            if source == "hh":
                if not re.fullmatch(r"[a-f0-9]{32,64}", rid or "") or url.scheme != "https" or url.netloc != "hh.ru" or url.path.rstrip("/") != f"/resume/{rid}":
                    raise ValueError("Некорректный источник HH.")
                if "catalog_resumes" in bundle and rid not in {r["id"] for r in bundle["catalog_resumes"]}:
                    raise ValueError("Резюме больше нет в каталоге HH.")
                if not any(s.get("key") == "experience" and len(normalize(s.get("text"))) > 100 for s in resume.get("sections", [])):
                    raise ValueError("В HH отсутствует полный раздел опыта.")
            elif source == "google_docs":
                gid = (rid or "").removeprefix("gdoc_")
                if not re.fullmatch(r"gdoc_[A-Za-z0-9_-]{10,200}", rid or "") or url.scheme != "https" or url.netloc != "docs.google.com" or url.path != f"/document/d/{gid}/edit":
                    raise ValueError("Некорректный источник Google Docs.")
            elif source == "file":
                if not re.fullmatch(r"file_[a-f0-9]{64}", rid or "") or resume.get("file_hash") != rid[5:]:
                    raise ValueError("Некорректная версия загруженного файла.")
            else:
                raise ValueError("Неизвестный источник резюме.")
            checked = datetime.fromisoformat(str(resume["checked_at"]).replace("Z", "+00:00"))
            if checked.tzinfo is None or now - checked < -timedelta(minutes=5):
                raise ValueError("Некорректная дата проверки резюме.")
            if source != "file" and now - checked > timedelta(hours=24):
                raise ValueError("Снимок устарел: обнови HH или Google Docs в расширении.")
            if resume.get("quality") != "full" or not normalize(resume.get("title")):
                raise ValueError("Резюме не прочитано полностью.")
            if source != "hh":
                reviewed = datetime.fromisoformat(str(resume["reviewed_at"]).replace("Z", "+00:00"))
                if reviewed.tzinfo is None or reviewed > now + timedelta(minutes=5):
                    raise ValueError("Текст документа не проверен.")
                if not any(s.get("key") == "document" and len(normalize(s.get("text"))) >= 100 for s in resume.get("sections", [])):
                    raise ValueError("Нет проверенного текста документа.")
            text = matching_text(resume)
            if len(text) > 260000 or content_hash(resume) != resume.get("content_hash"):
                raise ValueError("Текст снимка не соответствует его версии.")
            if rid in accepted:
                raise ValueError("Дублирующийся идентификатор резюме.")
            accepted[rid] = {**resume, "role": "primary" if rid == primary_id else "secondary", "matching_text": text}
        except (KeyError, TypeError, ValueError) as exc:
            if rid == primary_id:
                raise ValueError(f"Основное резюме не готово: {exc}") from exc
    if primary_id not in accepted:
        raise ValueError("Выбери загруженное основное резюме в расширении и экспортируй resumes.json.")
    return {"primary": accepted[primary_id], "resumes": list(accepted.values()),
            "policy": {"primary_id": primary_id, "max_age_hours": 24, "secondary_min_advantage": .05}}


def resume_chunks(resume):
    chunks = [normalize(resume["title"])]
    for section in resume["sections"]:
        heading = normalize(section["heading"])
        words, count = [], 0
        for word in normalize(section["text"]).split():
            if words and count + len(word) + 1 > 950:
                chunks.append(heading + "\n" + " ".join(words))
                words, count = [], 0
            words.append(word); count += len(word) + 1
        if words: chunks.append(heading + "\n" + " ".join(words))
    return chunks


class CachedEmbeddings:
    """Cache individual CV chunks, shared across versions and reserve resumes."""
    def __init__(self, backend, cache_dir, version="v1", vector_store=None):
        self.backend = backend
        self.vector_store = vector_store
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        identity = {"class": f"{type(backend).__module__}.{type(backend).__name__}",
                    "model": getattr(backend, "model", None),
                    "endpoint": getattr(backend, "base_url", getattr(backend, "url", None)),
                    "dimensions": getattr(backend, "dimensions", None), "version": version}
        self.namespace = json.dumps(identity, sort_keys=True, default=str)

    def keys(self, texts):
        return [hashlib.sha256((self.namespace + "\n" + normalize(t)).encode()).hexdigest() for t in texts]

    def embed_documents(self, texts):
        keys = self.keys(texts)
        vectors, missing = {}, {}
        for key, value in zip(keys, texts):
            if key in vectors or key in missing:
                continue
            try:
                vector = self.vector_store.vector(key) if self.vector_store else None
                if vector is None:
                    vector = json.loads((self.cache_dir / f"{key}.json").read_text())
                if not isinstance(vector, list) or not vector or not all(
                    isinstance(n, (int, float)) and math.isfinite(n) for n in vector):
                    raise ValueError("invalid embedding")
                vectors[key] = vector
                if self.vector_store:self.vector_store.save_vector(key,self.namespace,value,vector)
            except (OSError, ValueError):
                missing[key] = value
        if missing:
            generated = self.backend.embed_documents(list(missing.values()))
            if len(generated) != len(missing):
                raise ValueError("Embedding backend returned an incomplete batch")
            for key, vector in zip(missing, generated):
                vectors[key] = vector
                if self.vector_store:
                    self.vector_store.save_vector(key,self.namespace,missing[key],vector)
                    continue
                target = self.cache_dir / f"{key}.json"
                temporary = target.with_suffix(".tmp")
                temporary.write_text(json.dumps(vector), encoding="utf-8")
                temporary.replace(target)
        return [vectors[key] for key in keys]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def search_hh_resumes(db, bundle, *, top_k=40, pooling="min", include_secondary=False):
    """One selected resume per vacancy. A reserve needs a meaningful distance advantage."""
    primary = bundle["primary"]
    primary_rows = db.search_similar_vacancies_multi_chunk(resume_chunks(primary), top_k=top_k, pooling=pooling)
    by_id = {row["id"]: {**row, "_resume": primary} for row in primary_rows}
    if include_secondary:
        margin = bundle["policy"].get("secondary_min_advantage", 0.05)
        for resume in bundle["resumes"]:
            if resume["id"] == primary["id"]:
                continue
            rows = db.search_similar_vacancies_multi_chunk(resume_chunks(resume), top_k=top_k, pooling=pooling)
            for row in rows:
                previous = by_id.get(row["id"])
                if previous is not None and row["distance"] < previous["distance"] - margin:
                    by_id[row["id"]] = {**row, "_resume": resume}
    return sorted(by_id.values(), key=lambda row: row["distance"])[:top_k]
