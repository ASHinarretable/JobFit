import re
from typing import List

def normalize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.split()

def smart_truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit//2] + "\n...\n" + text[-limit//2:]

def dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result