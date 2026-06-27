import asyncio
import random

async def retry_async(fn, retries=3, base_delay=1):
    last_error = None

    for attempt in range(retries):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            await asyncio.sleep(base_delay * (2 ** attempt) + random.uniform(0, 1))

    raise last_error