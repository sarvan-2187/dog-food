"""In-process token bucket (PLAN.md Phase 3: no external service).

Shared by voting/commenting (Phase 3) and by sign-in (Phase 10.4). It lives at
the app root rather than under voting/ because authentication is not a voting
concern and importing across sibling feature packages to reach it would be the
wrong dependency direction.

Deliberately process-local. The app runs as a single Uvicorn worker, so one
process is the whole rate limiter; a multi-worker deployment would need shared
state, which would mean a network service and is therefore out of scope by
constraint.

Pure and time-injectable so the tests can prove refill behaviour without
sleeping through it.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Bucket:
    capacity: float
    # Tokens added per second. capacity / refill_seconds, precomputed.
    refill_rate: float
    tokens: float
    updated_at: float


@dataclass
class TokenBucketLimiter:
    """`capacity` actions allowed per `per_seconds`, refilling continuously."""

    capacity: int
    per_seconds: float
    _buckets: dict[str, Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _now(self) -> float:
        return time.monotonic()

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Take one token for `key`.

        Returns (allowed, retry_after_seconds). retry_after is 0 when allowed.
        """
        current = self._now() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = Bucket(
                    capacity=float(self.capacity),
                    refill_rate=self.capacity / self.per_seconds,
                    tokens=float(self.capacity),
                    updated_at=current,
                )
                self._buckets[key] = bucket

            elapsed = max(0.0, current - bucket.updated_at)
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.updated_at = current

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0

            missing = 1.0 - bucket.tokens
            return False, missing / bucket.refill_rate

    def reset_key(self, key: str) -> None:
        """Forget one key's bucket. Used when an action succeeds and its earlier
        failures should stop counting against it."""
        with self._lock:
            self._buckets.pop(key, None)

    def reset(self) -> None:
        """Clear all buckets. Used between tests so one test's spending cannot
        starve the next."""
        with self._lock:
            self._buckets.clear()


# Generous enough that a real person browsing the gallery never sees them, tight
# enough that a script hammering the endpoints does.
vote_limiter = TokenBucketLimiter(capacity=20, per_seconds=60.0)
comment_limiter = TokenBucketLimiter(capacity=10, per_seconds=60.0)

# Sign-in (Phase 10.4). Two buckets, because they defend different things and a
# single one cannot do both:
#  - per account, against many machines working on one account;
#  - per client fingerprint, against one machine spraying many accounts.
#
# Only FAILED attempts are charged to the client bucket, and a successful sign-in
# clears the account bucket. That distinction matters: everyone behind one office
# or campus NAT address shares a fingerprint, so charging successful sign-ins to
# it would lock out a whole building on a busy morning. Guessing produces
# failures by definition, so counting only those loses nothing defensively.
login_ip_limiter = TokenBucketLimiter(capacity=30, per_seconds=300.0)
login_account_limiter = TokenBucketLimiter(capacity=6, per_seconds=300.0)


def reset_all() -> None:
    vote_limiter.reset()
    comment_limiter.reset()
    login_ip_limiter.reset()
    login_account_limiter.reset()
