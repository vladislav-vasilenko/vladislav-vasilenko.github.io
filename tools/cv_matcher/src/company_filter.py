import json
import re
from functools import lru_cache
from pathlib import Path
from .resume_source import normalize

@lru_cache(maxsize=1)
def groups():
    from .company_catalog import defaults
    return defaults()
def clean(value):return re.sub(r'[\W_]+','',normalize(value).lower())
def company_key(value,catalog=None):
    text=clean(value)
    matches=[(len(clean(alias)),g['id']) for g in (catalog if catalog is not None else groups()) for alias in g['aliases'] if clean(alias) in text]
    return max(matches,key=lambda r:r[0])[1] if matches else 'other:'+text
