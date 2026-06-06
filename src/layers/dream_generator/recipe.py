from dataclasses import dataclass, field
import dataclasses
from typing import Optional


@dataclass
class RouteRecipe:
    # Target ranges
    distance_km:  list    # [float, float]
    elevation_m:  list    # [int, int]

    # Climb character
    climb_profile:  str    # 'flat' | 'rolling' | 'one_big_climb' | 'punchy'
    climb_position: str    # 'early' | 'middle' | 'late' | 'distributed'
    min_climbs: int
    max_climbs: int

    # Road character
    traffic_tolerance: str    # 'low' | 'medium' | 'high'
    surface:           str    # 'paved' | 'mixed' | 'any'
    route_shape:       str    # 'loop' | 'out_and_back' | 'either'

    # Experience
    novelty:       str    # 'new_roads' | 'familiar' | 'mixed'
    effort_intent: str    # 'endurance' | 'threshold' | 'recovery' | 'adventure'
    mood:          str    # original mood phrase, preserved verbatim

    # GraphHopper translation params
    distance_influence: int   # 50 (scenic) – 300 (efficient)
    target_distance_m:  int

    # Geographic / surface constraints extracted from user language
    geographic_target: Optional[str] = None   # 'coastal'|'mountain'|'forest'|'park'|'ridge'|None
    avoid_surface:     str = "none"            # 'none' | 'unpaved' | 'gravel'

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RouteRecipe":
        d = dict(data)
        for f in ("distance_km", "elevation_m"):
            if f in d and not isinstance(d[f], list):
                d[f] = list(d[f])
        # Normalise null / "null" strings from LLM
        if d.get("geographic_target") in (None, "null", "none", ""):
            d["geographic_target"] = None
        if "avoid_surface" not in d:
            d["avoid_surface"] = "none"
        # Strip fields unknown to this version
        known = {f.name for f in dataclasses.fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)
