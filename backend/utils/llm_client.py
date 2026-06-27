import os
from groq import AsyncGroq

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY missing")
        _client = AsyncGroq(api_key=api_key)
    return _client