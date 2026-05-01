import os
import sys
from pathlib import Path

ROOT = Path("/Users/vladmac/Code/NodeJS/vladislav-vasilenko.github.io/tools/cv_matcher")
sys.path.insert(0, str(ROOT))

from src.rag_db import RAGDatabase

db = RAGDatabase(db_path=str(ROOT / "chroma_db"))
data = db.collection.get(include=["metadatas"])
ids = data["ids"]
prefixes = set(id.split("_")[0] + "_" for id in ids if "_" in id)
print(f"Total IDs: {len(ids)}")
print(f"Prefixes: {prefixes}")
if ids:
    print(f"Sample IDs: {ids[:5]}")
