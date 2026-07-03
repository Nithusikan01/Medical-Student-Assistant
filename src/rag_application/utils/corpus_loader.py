# corpus_loader.py
import json
from typing import List, Dict

def load_bm25_corpus(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)