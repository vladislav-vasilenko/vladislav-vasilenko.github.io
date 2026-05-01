import os
import sys
from pathlib import Path
import numpy as np

ROOT = Path("/Users/vladmac/Code/NodeJS/vladislav-vasilenko.github.io/tools/cv_matcher")
sys.path.insert(0, str(ROOT))

# Set provider to ollama to avoid hitting cv-api if not needed, 
# though we just want to see the stored embeddings.
os.environ["EMBEDDINGS_PROVIDER"] = "ollama"
os.environ["OLLAMA_EMBEDDING_MODEL"] = "bge-m3"

from src.rag_db import RAGDatabase

db = RAGDatabase(db_path=str(ROOT / "chroma_db"))
data = db.collection.get(include=["embeddings"])
if data["embeddings"] and len(data["embeddings"]) > 0:
    vec = np.array(data["embeddings"][0])
    print(f"Embedding dimension: {vec.shape[0]}")
    print(f"Number of embeddings: {len(data['embeddings'])}")
else:
    print("No embeddings found.")
