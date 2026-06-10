"""
Route generation using waypoint triangle routing.

Architecture: home → wp1 → wp2 → home (triangle loop).
Three variants explore directions 120° apart for genuine geographic diversity.
Waypoint radius: r = target_km / (3 × 1.2) — detour index of 1.2 per
Lewis & Corcoran (2024) "Fast Algorithms for Fixed-Length Round Trips".

Primary engine: OpenRouteService (10K req/day free, steepness controls).
Fallback: GraphHopper (500 req/day free, custom model weighting).
"""
import math
import os
import httpx
import asyncio
import structlog
from dataclasses import dataclass

from src.layers.dream_generator.recipe import RouteRecipe
from src.layers.route_builder.custom_model import recipe_to_custom_model

log = structlog.get_logger()

GRAPHHOPPER_API = "https://graphhopper.com/api/1"
ORS_API = "https://api.openrouteservice.org/v2"


class RoutingRateLimitError(RuntimeError):
    """Raised when a routing engine returns HTTP 429 (daily quota exhausted)."""

# Road network detour index: actual road distance ÷ straight-line distance.
# 1.2 fits mixed urban/suburban cycling (Lewis & Corcoran, 2024).
_DI = 1.2

# Steepness levels for ORS (0=novice/flat → 3=expert/steep)
_ORS_STEEPNESS = {"match": 1, "harder": 3, "scenic": 0}


def _irl_steepness_levels(irl_weights: list) -> dict:
    """
    Map IRL grade weight → per-variant ORS steepness levels.
    FEATURE_NAMES index 2 = grade (positive = rider seeks climbing).
    """
    grade_w = irl_weights[2] if len(irl_weights) > 2 else 0.0
    if grade_w > 0.25:   base = 2
    elif grade_w > 0.1:  base = 1
    elif grade_w < -0.3: base = 0
    else:                base = 1
    return {"match": base, "harder": min(3, base + 1), "scenic": max(0, base - 1)}


@dataclass
class CandidateRoute:
    variant: str
    distance_km: float
    elevation_m: int
    geojson: dict
    raw: dict


def _destination(lat: float, lng: float, bearing_deg: float, dist_km: float) -> tuple:
    """Great-circle destination point given start, bearing (°), distance (km)."""
    R = 6371.0
    d = dist_km / R
    lat_r, lng_r, b_r = map(math.radians, (lat, lng, bearing_deg))
    lat2 = math.asin(
        math.sin(lat_r) * math.cos(d) +
        math.cos(lat_r) * math.sin(d) * math.cos(b_r)
    )
    lng2 = lng_r + math.atan2(
        math.sin(b_r) * math.sin(d) * math.cos(lat_r),
        math.cos(d) - math.sin(lat_r) * math.sin(lat2)
    )
    return math.degrees(lat2), math.degrees(lng2)


def _triangle_points(home: tuple, center_bearing: float, target_km: float) -> list:
    """
    Return [home, wp1, wp2, home] as [lng, lat] lists for an equilateral triangle loop.

    wp1 and wp2 are placed at ±30° from center_bearing, each at radius r.
    A 60° spread gives an equilateral triangle: all 3 legs ≈ r, so
    total straight-line perimeter = 3r → routed distance ≈ 3r × DI = target_km.
    Formula: r = target_km / (3 × DI).
    """
    lat, lng = home
    r = target_km / (3 * _DI)
    wp1 = _destination(lat, lng, center_bearing - 30, r)
    wp2 = _destination(lat, lng, center_bearing + 30, r)
    return [
        [lng, lat],
        [wp1[1], wp1[0]],
        [wp2[1], wp2[0]],
        [lng, lat],
    ]


async def _fetch_ors(
    variant: str, points: list, target_km: float, ors_key: str,
    avoid_surface: str = "none", steepness: int | None = None,
) -> CandidateRoute | None:
    """Route via OpenRouteService cycling-road profile with steepness tuning per variant."""
    effective_steepness = steepness if steepness is not None else _ORS_STEEPNESS.get(variant, 1)
    payload = {
        "coordinates": points,
        "elevation": True,
        "instructions": False,
        "preference": "recommended",
        "profile_params": {
            "weightings": {
                "steepness_difficulty": {"level": effective_steepness}
            }
        },
    }
    if avoid_surface in ("unpaved", "gravel"):
        payload["options"] = {"avoid_features": ["unpavedroads"]}
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                f"{ORS_API}/directions/cycling-road/geojson",
                json=payload,
                headers={
                    "Authorization": ors_key,
                    "Content-Type": "application/json",
                }
            )
        if resp.status_code == 429:
            log.error("ors_rate_limited", variant=variant)
            raise RoutingRateLimitError("OpenRouteService daily quota exhausted (10K req/day free tier).")
        if not resp.is_success:
            log.warning("ors_error", variant=variant,
                        status=resp.status_code, body=resp.text[:400])
            return None
        data = resp.json()
        feature = data["features"][0]
        summary = feature["properties"].get("summary", {})
        return CandidateRoute(
            variant=variant,
            distance_km=round(summary.get("distance", 0) / 1000, 1),
            elevation_m=int(summary.get("ascent", 0)),
            geojson=feature["geometry"],
            raw=feature,
        )
    except Exception as e:
        log.warning("ors_error", variant=variant, error=str(e))
        return None


async def _fetch_graphhopper(
    variant: str, points: list, recipe: RouteRecipe, gh_key: str
) -> CandidateRoute | None:
    """
    Route via GraphHopper bike profile.
    Note: custom_model requires ch.disable=true (paid tier only), so we rely on
    the built-in bike profile defaults (prefers cycleways, avoids motorways)
    plus direction-based variant differentiation.
    """
    payload = {
        "points": points,
        "profile": "bike",
        "locale": "en",
        "instructions": False,
        "calc_points": True,
        "points_encoded": False,
        "elevation": True,
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                f"{GRAPHHOPPER_API}/route",
                json=payload,
                params={"key": gh_key}
            )
        if resp.status_code == 429:
            log.error("graphhopper_rate_limited", variant=variant,
                      hint="Add ORS_API_KEY to .env — openrouteservice.org offers 10K free req/day")
            raise RoutingRateLimitError(
                "GraphHopper daily quota exhausted (500 req/day on the free tier). "
                "Add ORS_API_KEY to your .env file — OpenRouteService gives you 10,000 free "
                "requests/day. Get a key at https://account.heigit.org"
            )
        if not resp.is_success:
            log.warning("graphhopper_error", variant=variant,
                        status=resp.status_code, body=resp.text[:400])
            return None
        data = resp.json()
        path = data["paths"][0]
        return CandidateRoute(
            variant=variant,
            distance_km=round(path["distance"] / 1000, 1),
            elevation_m=int(path.get("ascend", 0)),
            geojson=path["points"],
            raw=path,
        )
    except Exception as e:
        log.warning("graphhopper_error", variant=variant, error=str(e))
        return None


def _bearing(start: tuple, end: tuple) -> float:
    """Compass bearing from start to end (degrees, 0=N)."""
    lat1, lng1 = map(math.radians, start)
    lat2, lng2 = map(math.radians, end)
    dlon = lng2 - lng1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _smart_bearings(home: tuple, library_bboxes: list) -> tuple:
    """
    Return 3 center_bearings (120° apart) that minimise overlap with already-explored
    compass directions.

    Tests 12 candidate triplets at 10° base increments (0→110°) — each triplet's
    three arms are 120° apart, so they tile the compass without gaps.  The triplet
    whose three 60°-wide sectors contain the fewest library-route centroids is chosen.

    A random ±8° jitter is applied to the winning base so repeated calls with the
    same library still produce geometrically distinct routes.
    """
    import random

    if not library_bboxes:
        base = random.randint(0, 119)
        return (base % 360, (base + 120) % 360, (base + 240) % 360)

    # Precompute centroid bearings from home for every saved route
    lib_bearings: list[float] = []
    for bbox in library_bboxes:
        try:
            clat = (bbox[0] + bbox[2]) / 2
            clng = (bbox[1] + bbox[3]) / 2
            lib_bearings.append(_bearing(home, (clat, clng)))
        except Exception:
            pass

    def _angular_diff(a: float, b: float) -> float:
        return abs((a - b + 180) % 360 - 180)

    def score_triplet(base: int) -> int:
        arms = [base % 360, (base + 120) % 360, (base + 240) % 360]
        return sum(
            1 for lb in lib_bearings
            if any(_angular_diff(lb, arm) < 60 for arm in arms)
        )

    best_base = min(range(0, 120, 10), key=score_triplet)
    jitter = random.randint(-8, 8)
    b1 = (best_base + jitter) % 360
    return (b1, (b1 + 120) % 360, (b1 + 240) % 360)


async def _fetch_overpass_waypoint(home: tuple, geographic_target: str) -> tuple | None:
    """Return (lat, lng) of the nearest OSM feature matching geographic_target, or None."""
    lat, lng = home
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    queries = {
        "coastal":  f'[out:json];node["natural"="beach"](around:60000,{lat},{lng});out 10;',
        "mountain": f'[out:json];node["natural"="peak"](around:60000,{lat},{lng});out 10;',
        "forest":   f'[out:json];(way["landuse"="forest"](around:40000,{lat},{lng}););out center 10;',
        "park":     f'[out:json];node["leisure"="park"](around:40000,{lat},{lng});out 10;',
        "ridge":    f'[out:json];node["natural"="ridge"](around:60000,{lat},{lng});out 10;',
    }
    q = queries.get(geographic_target)
    if not q:
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(OVERPASS_URL, params={"data": q})
        if not resp.is_success:
            log.warning("overpass_error", status=resp.status_code, target=geographic_target)
            return None
        elements = resp.json().get("elements", [])
        if not elements:
            log.info("overpass_no_results", target=geographic_target)
            return None

        def _dist(e):
            elat = e.get("lat") or (e.get("center") or {}).get("lat")
            elng = e.get("lon") or (e.get("center") or {}).get("lon")
            if elat is None or elng is None:
                return float("inf")
            return (elat - lat) ** 2 + (elng - lng) ** 2

        nearest = min(elements, key=_dist)
        nlat = nearest.get("lat") or (nearest.get("center") or {}).get("lat")
        nlng = nearest.get("lon") or (nearest.get("center") or {}).get("lon")
        if nlat and nlng:
            log.info("overpass_waypoint_found", target=geographic_target, lat=round(nlat, 4), lng=round(nlng, 4))
            return (nlat, nlng)
    except Exception as e:
        log.warning("overpass_error", error=str(e), target=geographic_target)
    return None


def _p2p_points(start: tuple, end: tuple, variant: str) -> list:
    """
    Point-to-point waypoints with variant detour.
    match  → direct A→B
    harder → detour left of midpoint (typically hillier)
    scenic → detour right of midpoint (typically quieter)
    """
    s = [start[1], start[0]]
    e = [end[1],   end[0]]
    if variant == "match":
        return [s, e]

    mid_lat = (start[0] + end[0]) / 2
    mid_lng = (start[1] + end[1]) / 2
    direct_km = math.sqrt(
        ((end[0] - start[0]) * 111) ** 2 +
        ((end[1] - start[1]) * 111 * math.cos(math.radians(mid_lat))) ** 2
    )
    b = _bearing(start, end)
    perp = (b + (90 if variant == "harder" else -90)) % 360
    offset_km = max(2.0, direct_km * 0.18)
    wp = _destination(mid_lat, mid_lng, perp, offset_km)
    return [s, [wp[1], wp[0]], e]


async def generate_candidates(
    recipe: RouteRecipe,
    home: tuple,
    api_key: str,
    end: tuple = None,
    is_loop: bool = True,
    library_bboxes: list = None,
    irl_weights: list = None,
) -> list:
    """
    Generate 3 route candidates.

    Loop mode (default): triangle routing from home in 3 independent directions.
      - Smart bearings: picks the 120°-separated sector triplet with fewest library routes.
      - Geographic waypoints: queries Overpass API when recipe.geographic_target is set and
        inserts the nearest matching OSM feature as a required waypoint.
    P2P mode (end provided, is_loop=False): routes start→end with variant detours.

    Surface avoidance: passes avoid_features=unpavedroads to ORS when recipe.avoid_surface
    is "unpaved" or "gravel".

    Uses ORS (10K req/day free) if ORS_API_KEY env var is set, else GraphHopper (500/day).
    """
    d_lo, d_hi = recipe.distance_km
    mid = (d_lo + d_hi) / 2
    ors_key = os.environ.get("ORS_API_KEY", "")
    use_ors = bool(ors_key)
    avoid_surface = getattr(recipe, "avoid_surface", "none") or "none"
    irl_levels = _irl_steepness_levels(irl_weights) if irl_weights else None

    # Geographic waypoint lookup (Overpass API)
    geo_waypoint = None
    geographic_target = getattr(recipe, "geographic_target", None)
    if geographic_target:
        geo_waypoint = await _fetch_overpass_waypoint(home, geographic_target)

    if not is_loop and end is not None:
        # ── Point-to-point mode ────────────────────────────────────────────
        async def fetch_p2p(variant: str) -> CandidateRoute | None:
            points = _p2p_points(home, end, variant)
            if use_ors:
                steepness = irl_levels[variant] if irl_levels else None
                result = await _fetch_ors(variant, points, mid, ors_key, avoid_surface, steepness)
                if result:
                    return result
            return await _fetch_graphhopper(variant, points, recipe, api_key)

        results = await asyncio.gather(*[fetch_p2p(v) for v in ("match", "harder", "scenic")])

    else:
        # ── Loop mode: equilateral triangles in 3 independent directions ──
        # Smart bearing selection: avoid compass sectors already explored in library.
        b1, b2, b3 = _smart_bearings(home, library_bboxes or [])
        variants = {
            "match":  {"target_km": mid,         "center_bearing": b1},
            "harder": {"target_km": d_hi * 1.08, "center_bearing": b2},
            "scenic": {"target_km": mid,         "center_bearing": b3},
        }

        async def fetch_loop(variant: str, cfg: dict) -> CandidateRoute | None:
            for attempt in range(6):
                center = (cfg["center_bearing"] + attempt * 60) % 360
                points = _triangle_points(home, center, cfg["target_km"])
                # Inject geographic waypoint: home → geo_wp → wp2 → home
                if geo_waypoint:
                    geo_pt = [geo_waypoint[1], geo_waypoint[0]]  # [lng, lat]
                    points = [points[0], geo_pt, points[2], points[3]]
                if use_ors:
                    steepness = irl_levels[variant] if irl_levels else None
                    result = await _fetch_ors(variant, points, cfg["target_km"], ors_key, avoid_surface, steepness)
                    if result:
                        if attempt > 0:
                            log.info("bearing_fallback_succeeded", variant=variant,
                                     attempt=attempt, center=center)
                        return result
                    log.warning("ors_failed_falling_back_to_gh", variant=variant)
                # RoutingRateLimitError propagates immediately — no retries on 429
                result = await _fetch_graphhopper(variant, points, recipe, api_key)
                if result:
                    if attempt > 0:
                        log.info("bearing_fallback_succeeded", variant=variant,
                                 attempt=attempt, center=center)
                    return result
                log.info("bearing_failed_retrying", variant=variant, attempt=attempt, center=center)
            return None

        results = await asyncio.gather(*[fetch_loop(v, c) for v, c in variants.items()])

    valid = [r for r in results if r is not None]
    log.info("candidates_generated", count=len(valid),
             engine="ors" if use_ors else "graphhopper",
             mode="p2p" if (not is_loop and end) else "loop",
             geographic_target=geographic_target,
             avoid_surface=avoid_surface,
             distances=[r.distance_km for r in valid])
    return valid
