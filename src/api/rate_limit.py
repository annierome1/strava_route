"""
In-memory daily rate limiter. Resets at midnight UTC.
Works correctly for a single-process deployment (Railway, single dyno).

Limits are intentionally conservative to protect free-tier API quotas:
  - GraphHopper / ORS free tier: ~500 routing requests/day
  - Mapbox free tier: 50k map loads/month, 100k geocoding/month
  - Anthropic: billed per token — cap per-user to prevent surprise bills
"""
import threading
from collections import defaultdict
from datetime import date, datetime, timezone
from fastapi import HTTPException

_lock = threading.Lock()
_day: date = datetime.now(timezone.utc).date()
_counts: dict[str, int] = defaultdict(int)


def _maybe_reset() -> None:
    global _day, _counts
    today = datetime.now(timezone.utc).date()
    if today != _day:
        _counts = defaultdict(int)
        _day = today


def check(user_id: str, action: str, per_user: int, global_limit: int) -> None:
    """Raise HTTP 429 if the per-user or global daily cap is exceeded."""
    with _lock:
        _maybe_reset()
        u_key = f"u:{user_id}:{action}"
        g_key = f"g:{action}"
        if _counts[u_key] >= per_user:
            raise HTTPException(
                status_code=429,
                detail=f"You've reached your daily limit of {per_user} {action} request(s). Resets at midnight UTC.",
            )
        if _counts[g_key] >= global_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily service limit reached. Try again tomorrow.",
            )
        _counts[u_key] += 1
        _counts[g_key] += 1


def status(user_id: str) -> dict:
    """Return remaining quota for the current user."""
    with _lock:
        _maybe_reset()
        limits = {
            "route":     (10, 40),
            "dna_build": (3,  15),
        }
        result = {}
        for action, (per_user, global_limit) in limits.items():
            used_user   = _counts.get(f"u:{user_id}:{action}", 0)
            used_global = _counts.get(f"g:{action}", 0)
            result[action] = {
                "user_remaining":   per_user    - used_user,
                "global_remaining": global_limit - used_global,
            }
        return {"resets": "midnight UTC", "limits": result}
