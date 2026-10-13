"""Brakes in front of the reading: how many at once, and how many a person may ask.

The model is the slowest and most expensive thing the API can ask for, and a CPU reads one photo at
a time. Both limits are IN THE MEMORY OF THIS PROCESS: with several API processes each one has its
own count, so the real ceiling is the limit times the processes (docs/expenses.md, "Reading a
receipt"). The OCR container is the real bottleneck and also answers one request at a time.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from uuid import UUID

WINDOW_SECONDS = 60.0
# How long a request waits for a free slot before it answers "busy".
WAIT_FOR_SLOT_SECONDS = 2.0


class UserRateLimiter:
    """At most `per_minute` readings per person in any 60 seconds (a sliding window)."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._seen: dict[UUID, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def take(self, user_id: UUID) -> int:
        """0 when the person may read now (and the reading is counted), else the seconds to wait."""
        now = self._clock()
        with self._lock:
            window = self._seen[user_id]
            while window and now - window[0] >= WINDOW_SECONDS:
                window.popleft()
            if len(window) >= self._per_minute:
                return max(1, int(WINDOW_SECONDS - (now - window[0])) + 1)
            window.append(now)
            if len(self._seen) > 10_000:  # a long-running process forgets people who stopped asking
                for key in [
                    k for k, w in self._seen.items() if not w or now - w[-1] >= WINDOW_SECONDS
                ]:
                    del self._seen[key]
            return 0


class ConcurrencyGate:
    """At most `slots` readings at the same time; the others wait a little and then give up."""

    def __init__(self, slots: int) -> None:
        self._semaphore = threading.BoundedSemaphore(slots)

    def acquire(self, wait: float = WAIT_FOR_SLOT_SECONDS) -> bool:
        return self._semaphore.acquire(timeout=wait)

    def release(self) -> None:
        self._semaphore.release()
