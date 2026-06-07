"""
Strava data client — uses the Strava REST API with per-user OAuth tokens.

Each user connects their own Strava account via /strava/connect.
Tokens are stored in Supabase and auto-refreshed as needed.
"""
import os
import time
import httpx
from typing import Any, Callable, Optional
import structlog

log = structlog.get_logger()

STRAVA_API   = "https://www.strava.com/api/v3"
STRAVA_TOKEN = "https://www.strava.com/oauth/token"

# In-process cache for the app-level token (dev/fallback only)
_global_token_cache: dict = {}


class StravaMCPClient:
    """
    Strava client with auto token refresh.

    Two construction modes:
    - StravaMCPClient()                    — reads credentials from env (dev / admin use)
    - StravaMCPClient.from_tokens(...)     — per-user tokens from Supabase
    """

    def __init__(
        self,
        mcp_url: str = "",
        _access_token: str = "",
        _refresh_token: str = "",
        _expires_at: int = 0,
        _on_refresh: Optional[Callable[[dict], None]] = None,
    ):
        self._user_access  = _access_token
        self._user_refresh = _refresh_token
        self._user_expires = _expires_at
        self._on_refresh   = _on_refresh
        self._token_cache: dict = {}

    @classmethod
    def from_tokens(
        cls,
        access_token: str,
        refresh_token: str,
        expires_at: int,
        on_refresh: Optional[Callable[[dict], None]] = None,
    ) -> "StravaMCPClient":
        return cls(
            _access_token=access_token,
            _refresh_token=refresh_token,
            _expires_at=expires_at,
            _on_refresh=on_refresh,
        )

    async def _access_token(self) -> str:
        # ── User-specific token path ──────────────────────────────────────
        if self._user_refresh:
            if self._user_access and self._user_expires > time.time() + 300:
                return self._user_access

            client_id     = os.environ.get("STRAVA_CLIENT_ID", "")
            client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(STRAVA_TOKEN, data={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "refresh_token": self._user_refresh,
                    "grant_type":    "refresh_token",
                })
            if resp.status_code == 200:
                data = resp.json()
                self._user_access  = data["access_token"]
                self._user_refresh = data.get("refresh_token", self._user_refresh)
                self._user_expires = data["expires_at"]
                if self._on_refresh:
                    self._on_refresh({
                        "access_token":  self._user_access,
                        "refresh_token": self._user_refresh,
                        "expires_at":    self._user_expires,
                    })
                log.info("strava_user_token_refreshed")
                return self._user_access

            raise RuntimeError(f"Strava token refresh failed ({resp.status_code}). Reconnect Strava in Settings.")

        # ── Env-based token path (dev / fallback) ─────────────────────────
        if _global_token_cache.get("access_token") and _global_token_cache.get("expires_at", 0) > time.time() + 300:
            return _global_token_cache["access_token"]

        client_id     = os.environ.get("STRAVA_CLIENT_ID", "")
        client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "")
        refresh_token = os.environ.get("STRAVA_REFRESH_TOKEN", "")

        if client_id and client_secret and refresh_token:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(STRAVA_TOKEN, data={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type":    "refresh_token",
                })
            if resp.status_code == 200:
                data = resp.json()
                _global_token_cache["access_token"] = data["access_token"]
                _global_token_cache["expires_at"]   = data["expires_at"]
                return data["access_token"]

        token = os.environ.get("STRAVA_ACCESS_TOKEN", "")
        if token:
            return token

        raise RuntimeError(
            "No Strava connection. Connect your Strava account in Settings."
        )

    async def _get(self, path: str, params: dict = None) -> Any:
        try:
            token = await self._access_token()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{STRAVA_API}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params or {}
                )
            if resp.status_code == 401:
                self._user_access = ""
                raise RuntimeError("Strava token invalid. Reconnect Strava in Settings.")
            if resp.status_code == 429:
                raise RuntimeError("Strava rate limit hit — wait 15 minutes and try again.")
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise RuntimeError("Strava API timed out.")

    async def get_all_cycling_activities(self) -> list:
        all_activities, page = [], 1
        while True:
            batch = await self._get("/athlete/activities", {"per_page": 200, "page": page})
            if not batch:
                break
            rides = [a for a in batch if a.get("type") in ("Ride", "VirtualRide")]
            all_activities.extend(rides)
            if len(batch) < 200:
                break
            page += 1
        log.info("strava_activities_fetched", count=len(all_activities))
        return all_activities

    async def get_activity_streams(self, activity_id: int) -> dict:
        keys = "latlng,altitude,watts,heartrate,distance,cadence,time"
        try:
            raw = await self._get(f"/activities/{activity_id}/streams", {
                "keys": keys, "key_by_type": "true"
            })
            return raw if isinstance(raw, dict) else {}
        except Exception as e:
            log.warning("stream_fetch_failed", activity_id=activity_id, error=str(e))
            return {}

    async def get_athlete(self) -> dict:
        try:
            return await self._get("/athlete")
        except Exception:
            return {}
