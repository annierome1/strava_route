"""
Strava data client — uses the Strava REST API directly.

Setup (one-time):
  1. Create a Strava API app at https://www.strava.com/settings/api
  2. Note your CLIENT_ID and CLIENT_SECRET
  3. Get an access + refresh token via:
       https://www.strava.com/oauth/authorize?client_id=<ID>&redirect_uri=http://localhost&response_type=code&approval_prompt=force&scope=read_all,activity:read_all
     → copy the `code` param from the redirect URL, then:
       curl -X POST https://www.strava.com/oauth/token \
         -d client_id=<ID> -d client_secret=<SECRET> \
         -d code=<CODE> -d grant_type=authorization_code
  4. Add to .env:
       STRAVA_CLIENT_ID=<id>
       STRAVA_CLIENT_SECRET=<secret>
       STRAVA_REFRESH_TOKEN=<refresh_token>
     (STRAVA_ACCESS_TOKEN is auto-managed after that)
"""
import os
import time
import httpx
from typing import Any, Optional
import structlog

log = structlog.get_logger()

STRAVA_API   = "https://www.strava.com/api/v3"
STRAVA_TOKEN = "https://www.strava.com/oauth/token"

_token_cache: dict = {}   # {"access_token": str, "expires_at": int}


class StravaMCPClient:
    """Strava data client using the REST API with auto token refresh."""

    def __init__(self, mcp_url: str = "https://mcp.strava.com/sse"):
        self.mcp_url = mcp_url  # kept for API compatibility

    async def _access_token(self) -> str:
        """Returns a valid access token, refreshing if needed."""
        # If cached token is still valid (with 5-min buffer), use it
        if _token_cache.get("access_token") and _token_cache.get("expires_at", 0) > time.time() + 300:
            return _token_cache["access_token"]

        # Try to refresh using refresh token
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
                _token_cache["access_token"] = data["access_token"]
                _token_cache["expires_at"]   = data["expires_at"]
                log.info("strava_token_refreshed", expires_at=data["expires_at"])
                return data["access_token"]
            log.warning("strava_token_refresh_failed", status=resp.status_code, body=resp.text[:200])

        # Fall back to static token
        token = os.environ.get("STRAVA_ACCESS_TOKEN", "")
        if token:
            return token

        raise RuntimeError(
            "No valid Strava credentials. Add STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, "
            "and STRAVA_REFRESH_TOKEN to your .env file. "
            "See instructions at https://developers.strava.com/docs/getting-started/"
        )

    def _headers(self) -> dict:
        raise RuntimeError("Use async _headers_async() instead.")

    async def _headers_async(self) -> dict:
        return {"Authorization": f"Bearer {await self._access_token()}"}

    async def _get(self, path: str, params: dict = None) -> Any:
        try:
            headers = await self._headers_async()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{STRAVA_API}{path}",
                    headers=headers,
                    params=params or {}
                )
            if resp.status_code == 401:
                _token_cache.clear()  # invalidate cached token
                raise RuntimeError(
                    "Strava token is invalid or expired. "
                    "If you have STRAVA_REFRESH_TOKEN set, the next request will auto-refresh. "
                    "Otherwise update STRAVA_ACCESS_TOKEN in .env."
                )
            if resp.status_code == 429:
                raise RuntimeError("Strava rate limit hit — wait 15 minutes and try again.")
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            raise RuntimeError("Strava API timed out — check your connection.")

    # ── Public interface ───────────────────────────────────────────────

    async def get_all_cycling_activities(self) -> list:
        """Fetch all Ride activities (paginated)."""
        all_activities, page = [], 1
        while True:
            batch = await self._get("/athlete/activities", {
                "per_page": 200,
                "page": page
            })
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
        """Returns per-second GPS, altitude, watts, HR, cadence, distance, time."""
        keys = "latlng,altitude,watts,heartrate,distance,cadence,time"
        try:
            raw = await self._get(f"/activities/{activity_id}/streams", {
                "keys": keys,
                "key_by_type": "true"
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

    async def get_athlete_home(self) -> Optional[tuple]:
        """Returns (lat, lng) if athlete's city is set — geocoded from city name."""
        athlete = await self.get_athlete()
        # Strava doesn't expose lat/lng directly; infer home from ride start cluster
        return None

    async def get_athlete_stats(self) -> dict:
        athlete = await self.get_athlete()
        athlete_id = athlete.get("id")
        if not athlete_id:
            return {}
        try:
            return await self._get(f"/athletes/{athlete_id}/stats")
        except Exception:
            return {}

    # Legacy MCP compatibility shim
    async def call_tool(self, tool_name: str, params: dict) -> Any:
        if tool_name == "get-activities":
            return await self.get_all_cycling_activities()
        if tool_name == "get-activity-streams":
            return await self.get_activity_streams(params["id"])
        if tool_name == "get-athlete":
            return await self.get_athlete()
        if tool_name == "get-athlete-stats":
            return await self.get_athlete_stats()
        raise NotImplementedError(f"Tool not implemented: {tool_name}")
