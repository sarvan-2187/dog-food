"""In-process token bucket (PLAN.md Phase 3: no external service).

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
    # Hard cap on remembered keys. Without it an attacker who varies the key
    # (a new IP, a new email address) per request grows this dict until the
    # process runs out of memory - a DoS through the limiter itself.
    max_keys: int = 50_000
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
                if len(self._buckets) >= self.max_keys:
                    self._prune(current)
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

    def _prune(self, now: float) -> None:
        """Make room (caller holds the lock). First drop every bucket that has
        refilled completely - forgetting it changes nothing, since a new
        bucket starts full. If a flood of distinct keys leaves none idle, drop
        the least recently used half: under that kind of attack a fresh key
        costs the attacker nothing anyway, so losing old state is the lesser
        harm next to exhausting memory."""
        for key, bucket in list(self._buckets.items()):
            if bucket.tokens + (now - bucket.updated_at) * bucket.refill_rate >= bucket.capacity:
                del self._buckets[key]
        if len(self._buckets) >= self.max_keys:
            oldest = sorted(self._buckets.items(), key=lambda kv: kv[1].updated_at)
            for key, _ in oldest[: len(oldest) // 2 + 1]:
                del self._buckets[key]

    def __len__(self) -> int:
        return len(self._buckets)

    def peek(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Would `check` allow `key` right now? Spends nothing. Login uses it to
        refuse a throttled attempt BEFORE checking the password - otherwise a
        guesser could ignore the 429s and still be let in by a right guess."""
        current = self._now() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return True, 0.0
            elapsed = max(0.0, current - bucket.updated_at)
            tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            if tokens >= 1.0:
                return True, 0.0
            return False, (1.0 - tokens) / bucket.refill_rate

    def forget(self, key: str) -> None:
        """Drop one key's bucket - e.g. a successful login clears that account's
        failed-attempt count (PLAN.md 10.4)."""
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
# Email-confirmed voting links, per client and per address, per hour.
voter_email_limiter = TokenBucketLimiter(capacity=5, per_seconds=3600.0)

# Password recovery (PLAN.md Phase 9). Per hour: tight per address so nobody
# can flood one inbox, looser per IP because a venue shares one address.
forgot_email_limiter = TokenBucketLimiter(capacity=3, per_seconds=3600.0)
forgot_ip_limiter = TokenBucketLimiter(capacity=20, per_seconds=3600.0)
# Caps what a compromised organizer account could hand out, while leaving a
# busy help desk plenty of room on a bad Saturday morning.
reset_issue_limiter = TokenBucketLimiter(capacity=30, per_seconds=3600.0)

# PLAN.md Phase 10. Login counts FAILED attempts only (a success forgets the
# account's bucket): 10 per account and 30 per IP per 15 minutes.
login_account_limiter = TokenBucketLimiter(capacity=10, per_seconds=900.0)
login_ip_limiter = TokenBucketLimiter(capacity=30, per_seconds=900.0)
# Every sign-up runs bcrypt, the most expensive thing an anonymous client can
# make this process do, so an unthrottled register endpoint is a CPU
# exhaustion vector. Per IP per hour; a venue on one address still fits.
register_ip_limiter = TokenBucketLimiter(capacity=20, per_seconds=3600.0)
judge_reminder_limiter = TokenBucketLimiter(capacity=1, per_seconds=3600.0)
verify_email_limiter = TokenBucketLimiter(capacity=3, per_seconds=3600.0)
announcement_email_limiter = TokenBucketLimiter(capacity=1, per_seconds=600.0)


def reset_all() -> None:
    for limiter in (
        vote_limiter,
        comment_limiter,
        voter_email_limiter,
        forgot_email_limiter,
        forgot_ip_limiter,
        reset_issue_limiter,
        login_account_limiter,
        login_ip_limiter,
        register_ip_limiter,
        judge_reminder_limiter,
        verify_email_limiter,
        announcement_email_limiter,
    ):
        limiter.reset()
