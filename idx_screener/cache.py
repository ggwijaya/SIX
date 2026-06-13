from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    created_at: float
    expires_at: float
    expired: bool


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._values: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            self._values[key] = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + self.ttl_seconds,
                expired=False,
            )

    def get(self, key: str, allow_stale: bool = False) -> Optional[CacheEntry]:
        now = time.monotonic()
        with self._lock:
            entry = self._values.get(key)
            if not entry:
                return None
            expired = now >= entry.expires_at
            if expired and not allow_stale:
                return None
            return CacheEntry(
                value=entry.value,
                created_at=entry.created_at,
                expires_at=entry.expires_at,
                expired=expired,
            )
