from dataclasses import dataclass
from src.layers.dream_generator.recipe import RouteRecipe
from src.layers.route_dna.taste_profile import TasteProfile


@dataclass
class AdaptationConfig:
    dist_multiplier: float       # × rider's median distance
    vert_per_km: float           # target elevation per km
    climb_profile: str
    climb_position: str
    traffic_tolerance: str
    novelty: str
    effort_intent: str
    coach_rationale: str         # shown to rider


ADAPTATIONS: dict = {
    "aerobic_base": AdaptationConfig(
        dist_multiplier=1.25,
        vert_per_km=8.0,
        climb_profile="flat",
        climb_position="distributed",
        traffic_tolerance="low",
        novelty="familiar",
        effort_intent="endurance",
        coach_rationale="Long, steady, low-stress. Build the aerobic engine without spiking fatigue."
    ),
    "threshold": AdaptationConfig(
        dist_multiplier=0.85,
        vert_per_km=15.0,
        climb_profile="one_big_climb",
        climb_position="middle",
        traffic_tolerance="medium",
        novelty="mixed",
        effort_intent="threshold",
        coach_rationale="One sustained climb in the middle third. Threshold effort on the ascent."
    ),
    "vo2max": AdaptationConfig(
        dist_multiplier=0.65,
        vert_per_km=22.0,
        climb_profile="punchy",
        climb_position="distributed",
        traffic_tolerance="medium",
        novelty="new_roads",
        effort_intent="threshold",
        coach_rationale="Short, hard, punchy. Multiple sharp climbs, nothing sustained."
    ),
    "muscular_endurance": AdaptationConfig(
        dist_multiplier=1.1,
        vert_per_km=12.0,
        climb_profile="rolling",
        climb_position="distributed",
        traffic_tolerance="low",
        novelty="familiar",
        effort_intent="endurance",
        coach_rationale="Continuous moderate grade. Builds leg strength over time without blowing up."
    ),
    "recovery": AdaptationConfig(
        dist_multiplier=0.5,
        vert_per_km=4.0,
        climb_profile="flat",
        climb_position="distributed",
        traffic_tolerance="low",
        novelty="familiar",
        effort_intent="recovery",
        coach_rationale="Spin the legs. Flat, familiar, zero stress."
    ),
}


def build_training_recipe(
    adaptation_key: str,
    taste: TasteProfile,
    recent_fatigue_index: float = None
) -> RouteRecipe:
    cfg = ADAPTATIONS[adaptation_key]
    base_dist = taste.median_distance_km * cfg.dist_multiplier

    # Cap distance if rider is fatigued
    if recent_fatigue_index and recent_fatigue_index < 0.88:
        base_dist = min(base_dist, taste.preferred_distance_km[0] * 0.9)

    target_elev = int(base_dist * cfg.vert_per_km)

    return RouteRecipe(
        distance_km=[round(base_dist * 0.9, 1), round(base_dist * 1.1, 1)],
        elevation_m=[int(target_elev * 0.85), int(target_elev * 1.15)],
        climb_profile=cfg.climb_profile,
        climb_position=cfg.climb_position,
        min_climbs=1 if cfg.climb_profile in ("punchy", "one_big_climb") else 0,
        max_climbs=6 if cfg.climb_profile == "punchy" else 2,
        traffic_tolerance=cfg.traffic_tolerance,
        surface="paved",
        route_shape="loop" if taste.prefers_loops else "either",
        novelty=cfg.novelty,
        effort_intent=cfg.effort_intent,
        mood=cfg.coach_rationale,
        distance_influence=100,
        target_distance_m=int(base_dist * 1000)
    )
