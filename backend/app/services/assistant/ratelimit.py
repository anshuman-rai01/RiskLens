"""
In-memory sliding-window per-user rate limiter for the AI Assistant.

Note:
    This limiter is per-process and in-memory. In a multi-worker production
    deployment, an external store like Redis would be required to enforce global
    rate limits across worker instances.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Tuple

from app.config import settings


class SlidingWindowRateLimiter:
    """
    Thread/coroutine safe in-memory sliding-window rate limiter.
    Tracks timestamps per user within a 60-second window.
    """

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._user_timestamps: Dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def acquire(self, user_id: str, limit: int) -> Tuple[bool, int]:
        """
        Check if user can make a request.
        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            timestamps = self._user_timestamps[user_id]

            # Evict timestamps outside the sliding window
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                oldest = timestamps[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)) + 1)
                return False, retry_after

            timestamps.append(now)
            return True, 0

    def reset(self) -> None:
        """Clear all rate limit tracking (useful for test isolation)."""
        self._user_timestamps.clear()


# Global singleton instance
assistant_rate_limiter = SlidingWindowRateLimiter()
