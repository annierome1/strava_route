"""
Strava data client — uses the Strava REST API with per-user OAuth tokens.

Each user connects their own Strava account via /strava/connect.
Tokens are stored in Supabase and auto-refreshed as needed.
"""
import io
import math
import os
import time
import httpx
from typing import Any, Callable, Optional
import structlog

log = structlog.get_logger()

STRAVA_API   = "https://www.strava.com/api/v3"
STRAVA_TOKEN = "https://www.strava.com/oauth/token"
_GH_API      = "https://graphhopper.com/api/1"

# In-process cache for the app-level token (dev/fallback only)
_global_token_cache: dict = {}

# Road class → traffic level for IRL RoadSegment
_RC_TRAFFIC = {
    "MOTORWAY": 3, "TRUNK": 3, "PRIMARY": 2, "SECONDARY": 1,
    "TERTIARY": 0, "RESIDENTIAL": 0, "CYCLEWAY": 0,
    "UNCLASSIFIED": 0, "TRACK": 0, "PATH": 0, "LIVING_STREET": 0,
}
_PAVED_SURFACES = {"ASPHALT", "PAVING_STONES", "CONCRETE", "SETT", "COMPACTED"}


async def map_match_to_segments(latlng: list, gh_key: str) -> list:
    """
    Map-match a GPS latlng stream to real OSM road edges via GraphHopper.
    Returns a list of RoadSegment objects built from actual OSM tags.

    Each point in latlng should be [lat, lng] or (lat, lng).
    Downsamples to 80 points max for free-tier compatibility.
    """
    from src.builds.irl_engine.engine import RoadSegment

    pts = latlng
    if len(pts) > 80:
        step = max(1, len(pts) // 80)
        pts = pts[::step][:80]

    coordinates = [[p[1], p[0]] for p in pts]  # GH wants [lng, lat]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_GH_API}/match",
                params={"profile": "bike", "key": gh_key, "points_encoded": "false"},
                json={"points": coordinates, "details": ["road_class", "surface"]},
            )
        if not resp.is_success:
            log.warning("map_match_failed", status=resp.status_code, body=resp.text[:200])
            return []

        path = resp.json()["paths"][0]
        details = path.get("details", {})
        road_classes = details.get("road_class", [])
        surfaces     = details.get("surface", [])
        coords       = path.get("points", {}).get("coordinates", [])

        # Build per-point surface lookup
        surface_map: dict[int, str] = {}
        for s_start, s_end, surf in surfaces:
            for i in range(s_start, s_end):
                surface_map[i] = (surf or "ASPHALT").upper()

        segments = []
        for start_idx, end_idx, road_class in road_classes:
            rc   = (road_class or "").upper()
            span = coords[start_idx : end_idx + 1]
            if len(span) < 2:
                continue

            dist_m = 0.0
            for j in range(len(span) - 1):
                dlat = (span[j + 1][1] - span[j][1]) * 111000
                dlng = (span[j + 1][0] - span[j][0]) * 111000 * math.cos(math.radians(span[j][1]))
                dist_m += math.sqrt(dlat ** 2 + dlng ** 2)

            ele_diff = 0.0
            if len(span[0]) > 2 and len(span[-1]) > 2:
                ele_diff = span[-1][2] - span[0][2]

            grade = (ele_diff / dist_m * 100) if dist_m > 0 else 0.0
            surf  = surface_map.get(start_idx, "ASPHALT")

            segments.append(RoadSegment(
                segment_id=f"{start_idx}_{end_idx}",
                has_cycleway=(rc == "CYCLEWAY"),
                is_paved=(surf in _PAVED_SURFACES),
                avg_grade_pct=abs(grade),
                traffic_level=_RC_TRAFFIC.get(rc, 1),
                entry_turn_rad=0.5,
                length_km=max(dist_m / 1000, 0.001),
            ))

        log.info("map_match_ok", n_segments=len(segments))
        return segments

    except Exception as e:
        log.warning("map_match_error", error=str(e))
        return []


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

    async def upload_route_as_activity(
        self, gpx_content: str, name: str, description: str = ""
    ) -> dict:
        """
        Upload a GPX route to Strava as a private ride activity.
        Requires activity:write scope — user must have reconnected Strava after scope change.
        Returns the upload object; poll /strava/upload/{id} for completion.
        """
        token = await self._access_token()
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(
                f"{STRAVA_API}/uploads",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "data_type":     "gpx",
                    "name":          name,
                    "description":   description,
                    "activity_type": "ride",
                    "private":       "1",
                },
                files={"file": ("route.gpx", io.BytesIO(gpx_content.encode("utf-8")), "application/gpx+xml")},
            )
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 401:
            raise RuntimeError(
                "activity:write permission missing. Disconnect and reconnect Strava in Settings to enable uploads."
            )
        raise RuntimeError(f"Strava upload failed ({resp.status_code}): {resp.text[:200]}")

    async def get_upload_status(self, upload_id: int) -> dict:
        """Poll for upload completion. activity_id is set when processing is done."""
        return await self._get(f"/uploads/{upload_id}")
