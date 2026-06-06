from dataclasses import dataclass
import numpy as np

from src.layers.route_dna.extractor import _haversine_km
from src.layers.dream_generator.recipe import RouteRecipe
from src.layers.route_dna.taste_profile import TasteProfile


@dataclass
class RouteScore:
    variant: str
    total: float             # 0–1 composite
    distance_fit: float
    elevation_fit: float
    grade_fit: float
    novelty_fit: float
    notes: list


def score_candidate(
    route,
    recipe: RouteRecipe,
    taste: TasteProfile,
    historical_bboxes: list   # (min_lat, min_lng, max_lat, max_lng) of past routes
) -> RouteScore:
    notes = []

    # Distance fit: linear penalty for deviation outside recipe range
    d_lo, d_hi = recipe.distance_km
    d = route.distance_km
    if d_lo <= d <= d_hi:
        dist_fit = 1.0
    else:
        miss = min(abs(d - d_lo), abs(d - d_hi))
        span = max(d_hi - d_lo, 1)
        dist_fit = max(0.0, 1 - miss / span)
        notes.append(f"distance {d:.1f}km vs target {d_lo}–{d_hi}km")

    # Elevation fit
    e_lo, e_hi = recipe.elevation_m
    e = route.elevation_m
    if e_lo <= e <= e_hi:
        elev_fit = 1.0
    else:
        miss = min(abs(e - e_lo), abs(e - e_hi))
        span = max(e_hi - e_lo, 1)
        elev_fit = max(0.0, 1 - miss / span)
        pct = int((e / max((e_lo + e_hi) / 2, 1) - 1) * 100)
        notes.append(f"elevation {e}m ({'+' if pct >= 0 else ''}{pct}% vs target)")

    # Grade fit: compare route grade distribution against taste profile
    coords = route.geojson.get("coordinates", [])
    route_abs_grades = []
    for i in range(1, len(coords)):
        if len(coords[i]) > 2:
            dx_km = _haversine_km(
                [coords[i-1][1], coords[i-1][0]],
                [coords[i][1],   coords[i][0]]
            )
            if dx_km > 0:
                dalt = coords[i][2] - coords[i-1][2]
                route_abs_grades.append(abs(dalt / (dx_km * 1000) * 100))

    if route_abs_grades:
        n = len(route_abs_grades)
        route_gd = {
            "flat":    sum(1 for g in route_abs_grades if g < 2)   / n,
            "rolling": sum(1 for g in route_abs_grades if 2 <= g < 6) / n,
            "steep":   sum(1 for g in route_abs_grades if g >= 6)  / n,
        }
        target_gd = taste.grade_distribution
        grade_fit = max(0.0, 1 - sum(abs(route_gd[k] - target_gd.get(k, 0))
                                     for k in ("flat", "rolling", "steep")) / 2)
    else:
        grade_fit = 0.5

    # Novelty fit: bbox overlap proxy
    if coords:
        route_bbox = (
            min(c[1] for c in coords), min(c[0] for c in coords),
            max(c[1] for c in coords), max(c[0] for c in coords)
        )
        overlaps = sum(1 for b in historical_bboxes if _bbox_overlap(route_bbox, b))
        historical_novelty = max(0.0, 1 - overlaps / max(len(historical_bboxes), 1))
    else:
        historical_novelty = 0.5

    if   recipe.novelty == "new_roads": novelty_fit = historical_novelty
    elif recipe.novelty == "familiar":  novelty_fit = 1 - historical_novelty
    else:                               novelty_fit = 1 - abs(historical_novelty - 0.5) * 2

    total = (
        dist_fit   * 0.30 +
        elev_fit   * 0.30 +
        grade_fit  * 0.25 +
        novelty_fit * 0.15
    )

    return RouteScore(
        variant=route.variant,
        total=round(total, 3),
        distance_fit=round(dist_fit, 3),
        elevation_fit=round(elev_fit, 3),
        grade_fit=round(grade_fit, 3),
        novelty_fit=round(novelty_fit, 3),
        notes=notes
    )


def _bbox_overlap(a: tuple, b: tuple) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
