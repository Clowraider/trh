"""Simple in-memory rate limiter with sliding window.

This implementation is suitable for single-process deployments. For
multi-process or multi-instance deployments, replace it with a shared
store such as Redis.
"""

import threading
from datetime import datetime, timedelta


class RateLimiter:
    def __init__(self, max_attempts: int, window_minutes: int):
        self.max_attempts = max_attempts
        self.window = timedelta(minutes=window_minutes)
        self._store: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Return True if the key is within its attempt budget."""
        now = datetime.utcnow()
        with self._lock:
            attempts = [t for t in self._store.get(key, []) if now - t < self.window]
            if len(attempts) >= self.max_attempts:
                self._store[key] = attempts
                return False
            attempts.append(now)
            self._store[key] = attempts
            return True

    def reset(self, key: str) -> None:
        """Clear attempts for a key (useful in tests)."""
        with self._lock:
            self._store.pop(key, None)

    def attempt_count(self, key: str) -> int:
        """Return the current number of attempts in the window."""
        now = datetime.utcnow()
        with self._lock:
            return len([t for t in self._store.get(key, []) if now - t < self.window])
