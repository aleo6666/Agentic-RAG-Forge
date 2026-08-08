"""Simple in-memory token-bucket rate limiter.

ponytail: in-memory dict, not Redis — single-process FastAPI, < 1000 req/s.
Add Redis bucket if multi-worker deployment is needed.
"""

import inspect
import time
from functools import wraps
from fastapi import HTTPException, Request


_buckets: dict[str, tuple[int, float]] = {}  # key → (tokens, last_refill)


def rate_limiter(limit: int = 10, window: int = 60):
    """Decorator: allow `limit` requests per `window` seconds per tenant.
    Works with both sync and async endpoint functions.
    """

    def decorator(fn):
        is_async = inspect.iscoroutinefunction(fn)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request") or next(
                (a for a in args if isinstance(a, Request)), None
            )
            tenant = kwargs.get("tenant", "default")
            key = f"{tenant}"

            now = time.time()
            tokens, last = _buckets.get(key, (limit, now))
            elapsed = now - last
            tokens = min(limit, tokens + int(elapsed * (limit / window)))

            if tokens <= 0:
                raise HTTPException(429, f"Rate limit exceeded: {limit}/{window}s")

            _buckets[key] = (tokens - 1, now)
            result = fn(*args, **kwargs)
            if is_async:
                result = await result
            return result

        return wrapper

    return decorator
