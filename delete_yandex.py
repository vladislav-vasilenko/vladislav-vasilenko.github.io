import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append('tools/cv_matcher')

from src.rag_db import RAGDatabase

print("Loading DB...")
db = RAGDatabase(db_path='tools/cv_matcher/chroma_db')
print("DB loaded. Fetching IDs...")
all_ids = db.get_all_ids()
yandex_ids = [i for i in all_ids if i.startswith('yandex_')]
print(f'Total Yandex IDs to delete: {len(yandex_ids)}')
if yandex_ids:
    db.collection.delete(ids=yandex_ids)
    print('Deleted.')
print("Done.")
