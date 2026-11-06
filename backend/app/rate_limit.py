"""Project adapter over the shared rate-limit engine, plus a small flood guard.

The engine (`rate_limit_engine.py`) is vendored unmodified from
`shared/rate-limit/engine/fastapi/`. This adapter only supplies the project slug
and its single LLM bucket; the engine handles X-Forwarded-For, central config,
event mode, the kill switch (503), and fail-open behaviour.

`/api/product` does not call the model (it only fetches one shop page), so it is
not counted against the club limit; it gets a cheap per-instance flood guard
instead, so the backend cannot be used as a free page fetcher.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.rate_limit_engine import RateLimiter, client_ip


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


limiter = RateLimiter(
    # Slug = full project folder name (matches the central control sheet rows).
    project="ail-ay2627-s1-emily-sg-wardrobe",
    buckets={"style": _env_int("RATE_LIMIT_STYLE_MAX", 5)},
    redis_url=os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_URL", ""),
    redis_token=os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("UPSTASH_REDIS_TOKEN", ""),
    default_window=_env_int("RATE_LIMIT_WINDOW_SECONDS", 432000),
)


def check_rate_limit(request: Request, bucket: str) -> None:
    limiter.enforce(request, bucket)


_PRODUCT_MAX = _env_int("PRODUCT_FLOOD_MAX", 20)
_PRODUCT_WINDOW = _env_int("PRODUCT_FLOOD_WINDOW_SECONDS", 600)
_hits: dict[str, deque] = defaultdict(deque)


def check_product_flood(request: Request) -> None:
    """In-memory sliding window per IP. Resets on cold start, which is fine for a flood guard."""
    now, ip = time.monotonic(), client_ip(request)
    q = _hits[ip]
    while q and q[0] <= now - _PRODUCT_WINDOW:
        q.popleft()
    if len(q) >= _PRODUCT_MAX:
        # 423 rather than 429: the browser reserves 429 for the club rate-limit CTA modal
        raise HTTPException(status_code=423, detail={"code": "slow_down", "error": "Too many shop pages just now. Paste the size chart instead."})
    q.append(now)
    if len(_hits) > 5000:
        for k in [k for k, v in _hits.items() if not v]:
            del _hits[k]
