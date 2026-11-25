import time
from typing import Callable


class CooldownCache:
    """In-memory TTL deduplication cache keyed by (alertname, namespace, pod)."""

    def __init__(
        self,
        ttl_seconds: int = 900,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._time_fn = time_fn
        self._store: dict[tuple[str, str, str], float] = {}

    def _prune(self, now: float) -> None:
        expired = [k for k, exp in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]

    def should_process(self, alertname: str, namespace: str, pod: str) -> bool:
        now = self._time_fn()
        self._prune(now)
        key = (alertname, namespace, pod)
        if key in self._store:
            return False
        self._store[key] = now + self.ttl_seconds
        return True
