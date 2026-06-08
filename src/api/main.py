import os
import secrets
import time
import uuid
import dataclasses
from typing import Optional
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from src.platform.strava_client import StravaMCPClient, STRAVA_TOKEN, map_match_to_segments
from src.platform.logger import GenerationLogger
from src.layers.route_dna.extractor import extract_route_features
from src.layers.route_dna.taste_profile import (
    TasteProfile, build_taste_profile,
    taste_profile_to_dict, taste_profile_from_dict
)
from src.layers.dream_generator.recipe_builder import build_route_recipe
from src.layers.route_builder.routing_client import generate_candidates, CandidateRoute, RoutingRateLimitError
from src.layers.route_builder.scorer import score_candidate
from src.builds.dream_ride.generator import generate_dream_ride
from src.builds.training_planner.adaptations import build_training_recipe, ADAPTATIONS
from src.builds.irl_engine.engine import MaxEntropyIRL, RoadSegment
from src.api.db import (
    load_taste_profile_json, save_taste_profile_json,
    save_ride_bbox, load_ride_bboxes,
    load_library_route_stubs, load_library_routes,
    save_route, delete_route,
    load_library_for_cleanup, delete_routes_batch, load_library_bboxes,
    load_strava_tokens, save_strava_tokens, delete_strava_tokens,
    save_irl_weights, load_irl_weights,
)
from src.api.auth import get_current_user
from src.api import rate_limit

load_dotenv()
log = structlog.get_logger()

app = FastAPI(
    title="Strava AI Route Planner",
    description="Routes based on who you are as a rider.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

gen_logger = GenerationLogger()

# Short-lived in-memory state store for Strava OAuth (state → {user_id, exp})
_oauth_states: dict[str, dict] = {}

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_SCOPE    = "read_all,activity:read_all,activity:write"


# --- Request / Response models ---

class DreamRideRequest(BaseModel):
    prompt: str
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    end_lat:   Optional[float] = None
    end_lng:   Optional[float] = None
    is_loop:   bool = True


class TrainingRouteRequest(BaseModel):
    adaptation: str


class RouteResponse(BaseModel):
    user_prompt: str
    recipe_explanation: str
    recipe: dict
    routes: list
    generation_id: str
    thinking_trace: list = []


# --- Pure helpers (no DB) ---

def _geojson_bbox(geojson: dict) -> Optional[list]:
    coords = geojson.get("coordinates", [])
    if not coords:
        return None
    lats = [c[1] for c in coords]
    lngs = [c[0] for c in coords]
    return [min(lats), min(lngs), max(lats), max(lngs)]


def _bbox_overlap(b1: list, b2: list) -> float:
    i_min_lat = max(b1[0], b2[0]); i_max_lat = min(b1[2], b2[2])
    i_min_lng = max(b1[1], b2[1]); i_max_lng = min(b1[3], b2[3])
    if i_min_lat >= i_max_lat or i_min_lng >= i_max_lng:
        return 0.0
    i_area = (i_max_lat - i_min_lat) * (i_max_lng - i_min_lng)
    b1_area = (b1[2] - b1[0]) * (b1[3] - b1[1])
    return i_area / b1_area if b1_area > 0 else 0.0


# --- Business logic helpers ---

def _save_routes_to_library(user_id: str, routes: list, user_prompt: str, start: tuple):
    lat, lng = start
    library = load_library_route_stubs(user_id)

    saved = skipped = 0
    for r in routes:
        bbox = _geojson_bbox(r.get("geojson", {}))
        if bbox:
            for lib_dist, lib_bbox in library:
                if lib_bbox is None:
                    continue
                overlap = _bbox_overlap(bbox, lib_bbox)
                dist_diff = abs(r.get("distance_km", 0) - lib_dist) / max(lib_dist, 1)
                if overlap > 0.65 and dist_diff < 0.15:
                    skipped += 1
                    log.info("library_skip_duplicate", variant=r.get("variant"))
                    break
            else:
                save_route(user_id, {
                    "user_prompt": user_prompt,
                    "variant": r.get("variant", ""),
                    "distance_km": r.get("distance_km", 0),
                    "elevation_m": r.get("elevation_m", 0),
                    "start_lat": lat,
                    "start_lng": lng,
                    "geojson_json": r.get("geojson", {}),
                    "score_total": r.get("score", {}).get("total", 0),
                    "explanation": r.get("explanation", ""),
                    "bbox_json": bbox,
                })
                saved += 1
        else:
            save_route(user_id, {
                "user_prompt": user_prompt,
                "variant": r.get("variant", ""),
                "distance_km": r.get("distance_km", 0),
                "elevation_m": r.get("elevation_m", 0),
                "start_lat": lat,
                "start_lng": lng,
                "geojson_json": r.get("geojson", {}),
                "score_total": r.get("score", {}).get("total", 0),
                "explanation": r.get("explanation", ""),
                "bbox_json": None,
            })
            saved += 1
    log.info("library_saved", saved=saved, skipped=skipped)


def _flag_duplicates(user_id: str, routes: list) -> list:
    library = load_library_route_stubs(user_id)
    for r in routes:
        bbox = _geojson_bbox(r.get("geojson", {}))
        r["is_similar_to_saved"] = False
        if not bbox:
            continue
        for lib_dist, lib_bbox in library:
            if lib_bbox is None:
                continue
            overlap = _bbox_overlap(bbox, lib_bbox)
            dist_diff = abs(r.get("distance_km", 0) - lib_dist) / max(lib_dist, 1)
            if overlap > 0.65 and dist_diff < 0.15:
                r["is_similar_to_saved"] = True
                break
    return routes


async def _load_taste_profile(user_id: str) -> TasteProfile:
    data = load_taste_profile_json(user_id)
    if not data:
        raise HTTPException(
            status_code=404,
            detail="No taste profile found. POST /dna/build first."
        )
    return taste_profile_from_dict(data)


async def _infer_home(user_id: str) -> tuple:
    data = load_taste_profile_json(user_id)
    if data and data.get("home_coords"):
        hc = data["home_coords"]
        return (hc[0], hc[1])
    raise HTTPException(
        status_code=422,
        detail="Could not determine home location. Re-run POST /dna/build."
    )


async def _infer_home_from_activities(activities: list) -> Optional[tuple]:
    lats, lngs = [], []
    for a in activities:
        sl = a.get("start_latlng")
        if sl and len(sl) == 2 and sl[0] and sl[1]:
            lats.append(sl[0])
            lngs.append(sl[1])
    if not lats:
        return None
    import statistics
    return (statistics.median(lats), statistics.median(lngs))


def _package_results(user_prompt: str, recipe, explanation: str, candidates: list, taste: TasteProfile, bboxes: list) -> dict:
    scores = {c.variant: score_candidate(c, recipe, taste, bboxes) for c in candidates}
    ranked = sorted(candidates, key=lambda c: scores[c.variant].total, reverse=True)
    generation_id = gen_logger.log("irl_route", user_prompt, recipe, list(scores.values()))
    return {
        "user_prompt": user_prompt,
        "recipe_explanation": explanation,
        "recipe": recipe.to_dict(),
        "routes": [
            {
                "variant":     c.variant,
                "rank":        i + 1,
                "distance_km": c.distance_km,
                "elevation_m": c.elevation_m,
                "score":       scores[c.variant].__dict__,
                "explanation": f"IRL-personalized {c.variant} route.",
                "geojson":     c.geojson,
            }
            for i, c in enumerate(ranked)
        ],
        "generation_id": generation_id
    }


async def _generate_with_custom_model(recipe, home: tuple, custom_model: dict) -> list:
    from src.layers.route_builder.routing_client import (
        GRAPHHOPPER_API, _triangle_points, _fetch_ors
    )
    import httpx, asyncio

    d_lo, d_hi = recipe.distance_km
    mid = (d_lo + d_hi) / 2
    gh_key = os.environ.get("GRAPHHOPPER_API_KEY", "")
    ors_key = os.environ.get("ORS_API_KEY", "")
    variants = {
        "match":  {"target_km": mid,         "center_bearing": 0},
        "harder": {"target_km": d_hi * 1.08, "center_bearing": 120},
        "scenic": {"target_km": mid,         "center_bearing": 240},
    }

    async def fetch_one(variant: str, cfg: dict):
        points = _triangle_points(home, cfg["center_bearing"], cfg["target_km"])
        if ors_key:
            result = await _fetch_ors(variant, points, cfg["target_km"], ors_key)
            if result:
                return result
        payload = {
            "points": points, "profile": "bike", "locale": "en",
            "instructions": False, "calc_points": True,
            "points_encoded": False, "elevation": True,
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    f"{GRAPHHOPPER_API}/route", json=payload, params={"key": gh_key}
                )
            if not resp.is_success:
                return None
            path = resp.json()["paths"][0]
            return CandidateRoute(
                variant=variant,
                distance_km=round(path["distance"] / 1000, 1),
                elevation_m=int(path.get("ascend", 0)),
                geojson=path["points"],
                raw=path,
            )
        except Exception as e:
            log.warning("graphhopper_irl_error", variant=variant, error=str(e))
            return None

    results = await asyncio.gather(*[fetch_one(v, p) for v, p in variants.items()])
    return [r for r in results if r is not None]


async def _recent_fatigue_index() -> Optional[float]:
    return None


def _route_to_gpx(route: dict, geojson: dict) -> str:
    coords = geojson.get("coordinates", [])
    name   = f"AI Route — {route.get('variant', '').capitalize()} {route.get('distance_km', 0):.0f}km"
    now    = datetime.now(timezone.utc).isoformat()
    trkpts = []
    for c in coords:
        lng, lat = c[0], c[1]
        ele_tag = f"\n        <ele>{c[2]:.1f}</ele>" if len(c) > 2 and c[2] is not None else ""
        trkpts.append(f'      <trkpt lat="{lat:.7f}" lon="{lng:.7f}">{ele_tag}\n      </trkpt>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="RouteAI" xmlns="http://www.topografix.com/GPX/1/1">\n'
        f'  <metadata><name>{name}</name><time>{now}</time></metadata>\n'
        f'  <trk><name>{name}</name><type>cycling</type><trkseg>\n'
        + "\n".join(trkpts) +
        '\n  </trkseg></trk>\n</gpx>'
    )


async def _train_irl_background(user_id: str, latlng_streams: list, gh_key: str) -> None:
    """
    Background task: map-match GPS streams to OSM road segments then fit the
    MaxEntropy IRL model. Saves per-user weights to Supabase.
    Called automatically after a successful DNA build.
    """
    all_segments = []
    trajectories = []
    for latlng in latlng_streams:
        try:
            segments = await map_match_to_segments(latlng, gh_key)
            if segments:
                all_segments.extend(segments)
                trajectories.append(segments)
        except Exception as e:
            log.warning("irl_map_match_error", error=str(e))

    if not trajectories or not all_segments:
        log.info("irl_background_skipped", user_id=user_id, reason="no_map_match_data")
        return

    model = MaxEntropyIRL()
    model.fit(trajectories, all_segments)
    try:
        save_irl_weights(user_id, model.weights.tolist())
        log.info("irl_trained", user_id=user_id, n_trajectories=len(trajectories),
                 weights=model.explain_weights()["tags"])
    except Exception as e:
        log.warning("irl_save_failed", error=str(e))


# --- Endpoints ---

# ── Strava OAuth ──────────────────────────────────────────────────────────────

@app.post("/strava/connect")
async def strava_connect(request: Request, user_id: str = Depends(get_current_user)):
    """Return the Strava authorization URL. Frontend navigates the browser there."""
    client_id = os.environ.get("STRAVA_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=500, detail="STRAVA_CLIENT_ID not configured on server.")

    redirect_uri = os.environ.get(
        "STRAVA_REDIRECT_URI",
        str(request.base_url).rstrip("/") + "/strava/callback"
    )
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {"user_id": user_id, "exp": time.time() + 600}

    url = (
        f"{STRAVA_AUTH_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope={STRAVA_SCOPE}"
        f"&state={state}"
    )
    return {"url": url}


@app.get("/strava/callback")
async def strava_callback(code: str = "", state: str = "", error: str = ""):
    """Strava redirects here after the user authorizes (or denies)."""
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")

    if error or not code:
        return RedirectResponse(f"{frontend_url}/settings?strava=denied")

    entry = _oauth_states.pop(state, None)
    if not entry or entry["exp"] < time.time():
        return RedirectResponse(f"{frontend_url}/settings?strava=expired")

    user_id       = entry["user_id"]
    client_id     = os.environ.get("STRAVA_CLIENT_ID", "")
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(STRAVA_TOKEN, data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "code":          code,
            "grant_type":    "authorization_code",
        })

    if resp.status_code != 200:
        log.error("strava_token_exchange_failed", status=resp.status_code)
        return RedirectResponse(f"{frontend_url}/settings?strava=error")

    data    = resp.json()
    athlete = data.get("athlete", {})
    save_strava_tokens(user_id, {
        "access_token":  data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at":    data["expires_at"],
        "athlete_id":    athlete.get("id"),
        "athlete_name":  f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
    })
    log.info("strava_connected", user_id=user_id, athlete_id=athlete.get("id"))
    return RedirectResponse(f"{frontend_url}/settings?strava=connected")


@app.get("/strava/status")
async def strava_status(user_id: str = Depends(get_current_user)):
    tokens = load_strava_tokens(user_id)
    if not tokens:
        return {"connected": False}
    return {
        "connected":    True,
        "athlete_id":   tokens.get("athlete_id"),
        "athlete_name": tokens.get("athlete_name"),
    }


@app.delete("/strava/disconnect")
async def strava_disconnect(user_id: str = Depends(get_current_user)):
    delete_strava_tokens(user_id)
    return {"disconnected": True}


@app.post("/routes/library/{route_id}/push-to-strava")
async def push_route_to_strava(route_id: str, user_id: str = Depends(get_current_user)):
    """
    Upload a saved route to Strava as a private ride activity.
    Requires activity:write scope — if the user connected Strava before this feature
    was added, they should disconnect and reconnect in Settings.
    """
    tokens = load_strava_tokens(user_id)
    if not tokens:
        raise HTTPException(status_code=400, detail="Connect Strava first in Settings.")

    rows  = load_library_routes(user_id)
    route = next((r for r in rows if r["id"] == route_id), None)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found.")

    geojson = route.get("geojson_json") or {}
    if not geojson.get("coordinates"):
        raise HTTPException(status_code=422, detail="Route has no coordinates.")

    gpx         = _route_to_gpx(route, geojson)
    name        = f"AI Route — {route.get('variant', '').capitalize()} {route.get('distance_km', 0):.0f}km"
    description = f"Generated by RouteAI: \"{route.get('user_prompt', '')}\" • {route.get('explanation', '')}"

    def _on_refresh(new_tokens: dict):
        save_strava_tokens(user_id, new_tokens)

    strava_client = StravaMCPClient.from_tokens(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=tokens["expires_at"],
        on_refresh=_on_refresh,
    )

    try:
        upload = await strava_client.upload_route_as_activity(gpx, name, description)
        return {
            "upload_id": upload.get("id"),
            "status":    upload.get("status", "processing"),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class InlineStravaUploadRequest(BaseModel):
    variant: str
    distance_km: float
    user_prompt: str
    explanation: str = ""
    geojson: dict


@app.post("/strava/upload-route")
async def upload_route_inline(req: InlineStravaUploadRequest, user_id: str = Depends(get_current_user)):
    """
    Upload a route directly from GeoJSON (no library ID needed).
    Used by the DreamRide route cards immediately after generation.
    """
    tokens = load_strava_tokens(user_id)
    if not tokens:
        raise HTTPException(status_code=400, detail="Connect Strava first in Settings.")

    if not req.geojson.get("coordinates"):
        raise HTTPException(status_code=422, detail="Route has no coordinates.")

    route_meta = {"variant": req.variant, "distance_km": req.distance_km,
                  "user_prompt": req.user_prompt, "explanation": req.explanation}
    gpx         = _route_to_gpx(route_meta, req.geojson)
    name        = f"AI Route — {req.variant.capitalize()} {req.distance_km:.0f}km"
    description = f"Generated by RouteAI: \"{req.user_prompt}\" • {req.explanation}"

    def _on_refresh(new_tokens: dict):
        save_strava_tokens(user_id, new_tokens)

    strava_client = StravaMCPClient.from_tokens(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=tokens["expires_at"],
        on_refresh=_on_refresh,
    )

    try:
        upload = await strava_client.upload_route_as_activity(gpx, name, description)
        return {
            "upload_id": upload.get("id"),
            "status":    upload.get("status", "processing"),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/strava/upload/{upload_id}")
async def strava_upload_status(upload_id: int, user_id: str = Depends(get_current_user)):
    """Poll for Strava upload completion. activity_id is populated when done."""
    tokens = load_strava_tokens(user_id)
    if not tokens:
        raise HTTPException(status_code=400, detail="Strava not connected.")

    def _on_refresh(new_tokens: dict):
        save_strava_tokens(user_id, new_tokens)

    strava_client = StravaMCPClient.from_tokens(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=tokens["expires_at"],
        on_refresh=_on_refresh,
    )

    try:
        data = await strava_client.get_upload_status(upload_id)
        return {
            "upload_id":   data.get("id"),
            "status":      data.get("status"),
            "activity_id": data.get("activity_id"),
            "error":       data.get("error"),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Route generation ──────────────────────────────────────────────────────────

@app.post("/route/dream", response_model=RouteResponse)
async def dream_route(req: DreamRideRequest, user_id: str = Depends(get_current_user)):
    rate_limit.check(user_id, "route", per_user=10, global_limit=40)
    taste       = await _load_taste_profile(user_id)
    irl_weights = load_irl_weights(user_id)

    if req.start_lat is not None and req.start_lng is not None:
        start = (req.start_lat, req.start_lng)
    else:
        start = taste.home_coords or await _infer_home(user_id)

    end = None
    if not req.is_loop and req.end_lat is not None and req.end_lng is not None:
        end = (req.end_lat, req.end_lng)

    ride_bboxes = load_ride_bboxes(user_id)
    lib_bboxes  = load_library_bboxes(user_id)
    bboxes = ride_bboxes + lib_bboxes

    try:
        result = await generate_dream_ride(
            req.prompt, taste, start, bboxes,
            os.environ.get("GRAPHHOPPER_API_KEY", ""), gen_logger,
            end=end, is_loop=req.is_loop,
            irl_weights=irl_weights,
        )
    except RoutingRateLimitError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        if "no valid routes" in msg.lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    "No routes could be generated — routing API quota may be exhausted. "
                    "Add ORS_API_KEY to your .env file (openrouteservice.org — 10K free req/day)."
                )
            )
        raise HTTPException(status_code=500, detail=msg)

    result["routes"] = _flag_duplicates(user_id, result["routes"])
    _save_routes_to_library(user_id, result["routes"], req.prompt, start)
    result["generation_id"] = gen_logger.log("dream_ride_api", req.prompt,
        type("R", (), {"to_dict": lambda self: result["recipe"]})(), [])
    return result


@app.get("/routes/library")
async def get_library(user_id: str = Depends(get_current_user)):
    rows = load_library_routes(user_id)
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "user_prompt": r["user_prompt"],
            "variant": r["variant"],
            "distance_km": r["distance_km"],
            "elevation_m": r["elevation_m"],
            "start_lat": r["start_lat"],
            "start_lng": r["start_lng"],
            "geojson": r["geojson_json"] or {},
            "score_total": r["score_total"],
            "explanation": r["explanation"],
        }
        for r in rows
    ]


@app.delete("/routes/library/{route_id}")
async def delete_library_route(route_id: str, user_id: str = Depends(get_current_user)):
    delete_route(user_id, route_id)
    return {"deleted": route_id}


@app.post("/routes/library/cleanup")
async def cleanup_library_duplicates(user_id: str = Depends(get_current_user)):
    rows = load_library_for_cleanup(user_id)
    to_delete = []
    kept = []  # (id, dist, bbox)
    for rid, dist, bbox in rows:
        if bbox is None:
            kept.append((rid, dist, None))
            continue
        is_dupe = False
        for _, kept_dist, kept_bbox in kept:
            if kept_bbox is None:
                continue
            overlap = _bbox_overlap(bbox, kept_bbox)
            dist_diff = abs(dist - kept_dist) / max(kept_dist, 1)
            if overlap > 0.65 and dist_diff < 0.15:
                to_delete.append(rid)
                is_dupe = True
                break
        if not is_dupe:
            kept.append((rid, dist, bbox))
    delete_routes_batch(user_id, to_delete)
    log.info("library_cleanup", deleted=len(to_delete))
    return {"deleted": len(to_delete), "remaining": len(kept)}


@app.post("/route/training", response_model=RouteResponse)
async def training_route(req: TrainingRouteRequest, user_id: str = Depends(get_current_user)):
    rate_limit.check(user_id, "route", per_user=10, global_limit=40)
    if req.adaptation not in ADAPTATIONS:
        raise HTTPException(status_code=400, detail=f"Unknown adaptation. Choose: {list(ADAPTATIONS.keys())}")
    taste       = await _load_taste_profile(user_id)
    irl_weights = load_irl_weights(user_id)
    fatigue     = await _recent_fatigue_index()
    recipe      = build_training_recipe(req.adaptation, taste, fatigue)
    home        = taste.home_coords or await _infer_home(user_id)
    bboxes      = load_ride_bboxes(user_id)
    try:
        result = await generate_dream_ride(
            recipe.mood, taste, home, bboxes,
            os.environ.get("GRAPHHOPPER_API_KEY", ""), gen_logger,
            irl_weights=irl_weights,
        )
    except RoutingRateLimitError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    result["generation_id"] = gen_logger.log("training_route_api", recipe.mood, recipe, [])
    return result


@app.post("/irl/train")
async def irl_train(user_id: str = Depends(get_current_user)):
    activities = await strava.get_all_cycling_activities()
    if not activities:
        raise HTTPException(status_code=422, detail="No road segments to train on.")
    all_segments = []
    trajectories = []
    for activity in activities[:20]:
        seg = RoadSegment(
            segment_id=str(activity.get("id", 0)),
            has_cycleway=False, is_paved=True,
            avg_grade_pct=float(activity.get("average_grade", 2.0)),
            traffic_level=1, entry_turn_rad=0.5,
            length_km=float(activity.get("distance", 10000)) / 1000
        )
        all_segments.append(seg)
        trajectories.append([seg])
    model = MaxEntropyIRL()
    loss_history = model.fit(trajectories, all_segments)
    model.save(".irl_model")
    return {"weights": model.explain_weights(), "loss_history": loss_history}


@app.post("/irl/route", response_model=RouteResponse)
async def irl_route(req: DreamRideRequest, user_id: str = Depends(get_current_user)):
    irl_weights = load_irl_weights(user_id)
    if not irl_weights:
        raise HTTPException(status_code=404, detail="No IRL model found. Build your Route DNA first.")
    taste  = await _load_taste_profile(user_id)
    home   = taste.home_coords or await _infer_home(user_id)
    bboxes = load_ride_bboxes(user_id)
    recipe, explanation, thinking_trace = await build_route_recipe(
        req.prompt, taste,
        home=home, ride_bboxes=bboxes, irl_weights=irl_weights,
    )
    model = MaxEntropyIRL()
    import numpy as np
    model.weights = np.array(irl_weights)
    irl_custom_model = model.to_graphhopper_custom_model()
    candidates = await _generate_with_custom_model(recipe, home, irl_custom_model)
    result = _package_results(req.prompt, recipe, explanation, candidates, taste, bboxes)
    result["thinking_trace"] = thinking_trace
    return result


@app.post("/dna/build")
async def build_dna(background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user)):
    rate_limit.check(user_id, "dna_build", per_user=3, global_limit=15)
    tokens = load_strava_tokens(user_id)
    if not tokens:
        raise HTTPException(
            status_code=400,
            detail="Connect your Strava account first — go to Settings and click 'Connect Strava'."
        )

    def _on_refresh(new_tokens: dict):
        save_strava_tokens(user_id, new_tokens)

    client = StravaMCPClient.from_tokens(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=tokens["expires_at"],
        on_refresh=_on_refresh,
    )

    try:
        activities = await client.get_all_cycling_activities()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("strava_fetch_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Strava fetch failed: {e}")

    if not activities:
        raise HTTPException(status_code=422, detail="No Strava cycling activities found.")

    features       = []
    latlng_streams = []   # cached for IRL training (avoids re-fetching)

    for a in activities:
        try:
            streams = await client.get_activity_streams(a["id"])
            feat    = extract_route_features(a, streams)
            features.append(feat)
            latlng  = streams.get("latlng", {}).get("data", [])
            if latlng:
                coords = latlng
                bbox = (
                    min(c[0] for c in coords), min(c[1] for c in coords),
                    max(c[0] for c in coords), max(c[1] for c in coords)
                )
                save_ride_bbox(user_id, a["id"], bbox)
                if len(latlng) >= 10:
                    latlng_streams.append(latlng)
        except Exception as e:
            log.warning("activity_extraction_error", activity_id=a.get("id"), error=str(e))

    if not features:
        raise HTTPException(status_code=422, detail="Could not extract features from any activity.")

    try:
        home  = await _infer_home_from_activities(activities)
        taste = build_taste_profile(features, home)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    save_taste_profile_json(user_id, taste_profile_to_dict(taste))

    # Schedule IRL training in background — map-matches GPS streams to OSM road segments.
    # Does not block this response; weights are available for the next route generation.
    gh_key = os.environ.get("GRAPHHOPPER_API_KEY", "")
    if gh_key and latlng_streams:
        background_tasks.add_task(
            _train_irl_background, user_id, latlng_streams[:10], gh_key
        )
        log.info("irl_training_scheduled", n_streams=min(len(latlng_streams), 10))

    return {"taste_profile": taste_profile_to_dict(taste), "rides_analyzed": len(features)}


@app.get("/dna/status")
async def dna_status(user_id: str = Depends(get_current_user)):
    has_token = bool(os.environ.get("STRAVA_ACCESS_TOKEN"))
    data = load_taste_profile_json(user_id)
    if data:
        taste = taste_profile_from_dict(data)
        return {
            "profile_built": True,
            "has_strava_token": has_token,
            "signature_tags": taste.signature_tags,
            "median_distance_km": taste.median_distance_km,
        }
    return {"profile_built": False, "has_strava_token": has_token}


@app.get("/dna/profile")
async def get_profile(user_id: str = Depends(get_current_user)):
    taste = await _load_taste_profile(user_id)
    return taste_profile_to_dict(taste)


@app.get("/rate-limits")
async def get_rate_limits(user_id: str = Depends(get_current_user)):
    return rate_limit.status(user_id)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/config")
async def config():
    return {
        "mapbox_token": os.environ.get("MAPBOX_TOKEN", ""),
        "has_graphhopper": bool(os.environ.get("GRAPHHOPPER_API_KEY")),
        "has_anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_strava_token": bool(os.environ.get("STRAVA_ACCESS_TOKEN")),
    }


def _root_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


@app.get("/")
async def serve_interface():
    react_index = os.path.join(_root_dir(), "web", "dist", "index.html")
    if os.path.exists(react_index):
        return FileResponse(react_index, media_type="text/html")
    return {"message": "Run 'cd web && npm run build' to build the frontend."}


from fastapi.staticfiles import StaticFiles as _SF
_react_assets = os.path.join(_root_dir(), "web", "dist", "assets")
if os.path.isdir(_react_assets):
    app.mount("/assets", _SF(directory=_react_assets), name="react-assets")
