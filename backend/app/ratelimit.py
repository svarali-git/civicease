"""Small in-memory rate limit so a public deployment cannot burn through your API quota.

Privacy: the client address is hashed with a random per-process salt and kept only in memory
for one minute (timestamps only). It is never logged or written anywhere.
"""
from __future__ import annotations

import hashlib
import os
import time
from collections import deque

from . import config

_SALT = os.urandom(16)
_WINDOW = 60.0
_clients: dict[str, deque] = {}
_global: deque = deque()
_last_sweep = 0.0


def client_key(forwarded_for: str | None, peer: str | None) -> str:
    # Behind a host such as Render the real address arrives in X-Forwarded-For (first entry).
    address = (forwarded_for or "").split(",")[0].strip() or (peer or "unknown")
    return hashlib.sha256(_SALT + address.encode()).hexdigest()[:16]


def _trim(q: deque, now: float) -> None:
    while q and now - q[0] > _WINDOW:
        q.popleft()


def check(key: str) -> int:
    """Record a call. Return 0 if allowed, otherwise seconds to wait."""
    global _last_sweep
    per_client = config.get_int("RATE_LIMIT_PER_MINUTE", 20)
    overall = config.get_int("RATE_LIMIT_GLOBAL_PER_MINUTE", 120)
    if per_client <= 0 and overall <= 0:
        return 0
    now = time.monotonic()
    if now - _last_sweep > _WINDOW:  # forget idle clients
        for k in [k for k, q in _clients.items() if not q or now - q[-1] > _WINDOW]:
            del _clients[k]
        _last_sweep = now
    q = _clients.setdefault(key, deque())
    _trim(q, now)
    _trim(_global, now)
    if per_client > 0 and len(q) >= per_client:
        return max(1, int(_WINDOW - (now - q[0])))
    if overall > 0 and len(_global) >= overall:
        return max(1, int(_WINDOW - (now - _global[0])))
    q.append(now)
    _global.append(now)
    return 0


def reset() -> None:
    _clients.clear()
    _global.clear()
