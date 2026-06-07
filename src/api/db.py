"""Supabase client and all database operations."""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from supabase import create_client, Client

log = structlog.get_logger()

_client: Optional[Client] = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


# ── Taste profiles ────────────────────────────────────────────────────────────

def load_taste_profile_json(user_id: str) -> Optional[dict]:
    result = (
        get_supabase()
        .table("taste_profiles")
        .select("profile_json")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["profile_json"] if result.data else None


def save_taste_profile_json(user_id: str, profile_dict: dict):
    get_supabase().table("taste_profiles").insert({
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile_json": profile_dict,
    }).execute()


# ── Ride bboxes ───────────────────────────────────────────────────────────────

def save_ride_bbox(user_id: str, activity_id: int, bbox: tuple):
    get_supabase().table("ride_bboxes").upsert({
        "user_id": user_id,
        "activity_id": activity_id,
        "bbox_json": list(bbox),
    }).execute()


def load_ride_bboxes(user_id: str) -> list:
    result = (
        get_supabase()
        .table("ride_bboxes")
        .select("bbox_json")
        .eq("user_id", user_id)
        .execute()
    )
    bboxes = []
    for row in result.data:
        b = row["bbox_json"]
        try:
            bboxes.append(tuple(b) if isinstance(b, list) else tuple(b))
        except Exception:
            pass
    return bboxes


# ── Saved routes ──────────────────────────────────────────────────────────────

def load_library_route_stubs(user_id: str) -> list[tuple]:
    """Return [(distance_km, bbox)] pairs for duplicate checking."""
    result = (
        get_supabase()
        .table("saved_routes")
        .select("distance_km, bbox_json")
        .eq("user_id", user_id)
        .execute()
    )
    return [
        (r["distance_km"], r["bbox_json"])
        for r in result.data
        if r.get("bbox_json") is not None
    ]


def load_library_routes(user_id: str) -> list[dict]:
    result = (
        get_supabase()
        .table("saved_routes")
        .select(
            "id, created_at, user_prompt, variant, distance_km, elevation_m, "
            "start_lat, start_lng, geojson_json, score_total, explanation"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def save_route(user_id: str, route_row: dict):
    get_supabase().table("saved_routes").insert({
        **route_row,
        "user_id": user_id,
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def delete_route(user_id: str, route_id: str):
    get_supabase().table("saved_routes").delete().eq("id", route_id).eq("user_id", user_id).execute()


def load_library_for_cleanup(user_id: str) -> list[tuple]:
    """Return (id, distance_km, bbox) ordered oldest first."""
    result = (
        get_supabase()
        .table("saved_routes")
        .select("id, distance_km, bbox_json")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    return [
        (r["id"], r["distance_km"], r["bbox_json"])
        for r in result.data
        if r.get("bbox_json") is not None
    ]


def delete_routes_batch(user_id: str, ids: list):
    if not ids:
        return
    get_supabase().table("saved_routes").delete().in_("id", ids).eq("user_id", user_id).execute()


def load_library_bboxes(user_id: str) -> list:
    """Return all saved-route bbox lists for smart bearing selection."""
    result = (
        get_supabase()
        .table("saved_routes")
        .select("bbox_json")
        .eq("user_id", user_id)
        .execute()
    )
    return [r["bbox_json"] for r in result.data if r.get("bbox_json") is not None]


# ── Strava connections ────────────────────────────────────────────────────────

def load_strava_tokens(user_id: str) -> Optional[dict]:
    result = (
        get_supabase()
        .table("strava_connections")
        .select("access_token, refresh_token, expires_at, athlete_id, athlete_name")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def save_strava_tokens(user_id: str, tokens: dict):
    get_supabase().table("strava_connections").upsert({
        "user_id": user_id,
        **tokens,
    }).execute()


def delete_strava_tokens(user_id: str):
    get_supabase().table("strava_connections").delete().eq("user_id", user_id).execute()
