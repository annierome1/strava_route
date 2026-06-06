from dataclasses import dataclass
import numpy as np
from collections import Counter
from typing import Optional

from src.layers.route_dna.extractor import RideRouteFeatures


@dataclass
class TasteProfile:
    # Distance
    preferred_distance_km: tuple       # (p25, p75)
    median_distance_km: float

    # Elevation
    preferred_elevation_m: tuple       # (p25, p75)
    vert_per_km: float                 # median elevation gain per km

    # Climbing character
    grade_distribution: dict           # weighted avg across all rides
    avg_climbs_per_ride: float
    favors_sustained: bool
    favors_punchy: bool

    # Road character
    avg_turn_rate: float
    prefers_loops: bool

    # Effort pattern
    effort_shape: str                  # 'negative_split' | 'positive_split' | 'even'
    avg_threshold_time_pct: float

    # Behavioral
    preferred_start_hour: tuple        # (p25, p75)
    avg_novelty_score: float
    avg_pr_density: float

    # Human-readable
    signature_tags: list
    home_coords: Optional[tuple]       # most frequent ride start cluster


def build_taste_profile(
    features: list,
    home_coords: Optional[tuple] = None
) -> TasteProfile:
    rides = [f for f in features if f.distance_km >= 20]

    if not rides:
        raise ValueError("Need at least 5 outdoor rides >= 20km to build a taste profile")

    dists  = [r.distance_km     for r in rides]
    elevs  = [r.elevation_gain_m for r in rides]
    hours  = [r.start_hour       for r in rides]

    # Weighted grade distribution (weight by distance ridden)
    total_dist = sum(dists)
    agg = {"flat": 0.0, "rolling": 0.0, "steep": 0.0}
    for r in rides:
        w = r.distance_km / total_dist
        for k in agg:
            agg[k] += r.grade_distribution.get(k, 0) * w

    # Effort shape
    shapes = []
    for r in rides:
        a, _, c = r.effort_thirds
        if   c > a * 1.05: shapes.append("negative_split")
        elif a > c * 1.05: shapes.append("positive_split")
        else:              shapes.append("even")
    effort_shape = Counter(shapes).most_common(1)[0][0]

    # Sustained vs punchy climbing
    big_rides = [r for r in rides if r.elevation_gain_m > 1200]
    favors_sustained = (
        len(big_rides) >= 3 and
        float(np.mean([r.longest_climb_m for r in big_rides])) > 200
    )
    favors_punchy = (
        not favors_sustained and
        float(np.mean([r.climb_count for r in rides])) > 4
    )

    # Signature tags
    tags = []
    if float(np.percentile(hours, 50)) < 8:
        tags.append("dawn patrol")
    med_elev = float(np.median(elevs))
    med_dist = float(np.median(dists))
    if med_elev > 1500:
        tags.append("big climber")
    elif med_elev < 500 and med_dist > 60:
        tags.append("flat-road hunter")
    if favors_sustained:
        tags.append("climber")
    elif favors_punchy:
        tags.append("puncheur")
    if float(np.mean([r.novelty_score for r in rides])) > 0.6:
        tags.append("explorer")
    if float(np.mean([r.is_loop for r in rides])) > 0.6:
        tags.append("loop rider")
    if effort_shape == "negative_split":
        tags.append("strong finisher")
    if float(np.mean([r.pr_density for r in rides])) > 0.5:
        tags.append("segment hunter")
    if float(np.mean([r.had_group for r in rides])) > 0.4:
        tags.append("group rider")

    return TasteProfile(
        preferred_distance_km=(
            round(float(np.percentile(dists, 25)), 1),
            round(float(np.percentile(dists, 75)), 1)
        ),
        median_distance_km=round(float(np.median(dists)), 1),
        preferred_elevation_m=(
            int(np.percentile(elevs, 25)),
            int(np.percentile(elevs, 75))
        ),
        vert_per_km=round(float(np.median(elevs)) / max(float(np.median(dists)), 1), 1),
        grade_distribution={k: round(v, 3) for k, v in agg.items()},
        avg_climbs_per_ride=round(float(np.mean([r.climb_count for r in rides])), 1),
        favors_sustained=favors_sustained,
        favors_punchy=favors_punchy,
        avg_turn_rate=round(float(np.mean([r.turn_rate for r in rides])), 2),
        prefers_loops=float(np.mean([r.is_loop for r in rides])) > 0.6,
        effort_shape=effort_shape,
        avg_threshold_time_pct=round(float(np.mean([r.time_in_threshold_pct for r in rides])), 3),
        preferred_start_hour=(int(np.percentile(hours, 25)), int(np.percentile(hours, 75))),
        avg_novelty_score=round(float(np.mean([r.novelty_score for r in rides])), 2),
        avg_pr_density=round(float(np.mean([r.pr_density for r in rides])), 2),
        signature_tags=tags,
        home_coords=home_coords
    )


def taste_profile_to_dict(profile: TasteProfile) -> dict:
    import dataclasses
    d = dataclasses.asdict(profile)
    return d


def taste_profile_from_dict(data: dict) -> TasteProfile:
    data = dict(data)
    # Convert lists back to tuples for range fields
    for field in ("preferred_distance_km", "preferred_elevation_m", "preferred_start_hour"):
        if field in data and isinstance(data[field], list):
            data[field] = tuple(data[field])
    if "home_coords" in data and isinstance(data["home_coords"], list):
        data["home_coords"] = tuple(data["home_coords"])
    return TasteProfile(**data)
