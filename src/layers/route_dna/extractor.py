from dataclasses import dataclass, field
import numpy as np
from math import atan2, degrees, radians, cos, sin, sqrt


@dataclass
class RideRouteFeatures:
    activity_id: int
    date: str

    # Volume
    distance_km: float
    duration_hours: float
    elevation_gain_m: int

    # Grade profile
    grade_distribution: dict            # {'flat': 0.45, 'rolling': 0.35, 'steep': 0.20}
    avg_grade_pct: float
    max_grade_pct: float
    climb_count: int                    # distinct climbs > 30m gain
    longest_climb_m: int                # elevation gain of single longest climb
    steepest_5pct_grade: float          # 95th-percentile grade segment

    # Road character
    turn_rate: float                    # turns per km (bearing changes > 30°)
    longest_straight_km: float          # longest segment < 5° bearing change

    # Effort distribution
    effort_thirds: tuple                # power/HR ratio first:mid:last
    time_in_threshold_pct: float        # % time in Z3+Z4

    # Behavioral signals
    start_hour: int
    is_loop: bool                       # start/end within 500m
    repeat_road_pct: float              # populated by novelty indexer
    novelty_score: float                # 1 - repeat_road_pct
    pr_density: float                   # PRs per 10km
    had_group: bool


def _bearing(p1: list, p2: list) -> float:
    lat1, lon1 = radians(p1[0]), radians(p1[1])
    lat2, lon2 = radians(p2[0]), radians(p2[1])
    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    return (degrees(atan2(x, y)) + 360) % 360


def _haversine_km(p1: list, p2: list) -> float:
    R = 6371.0
    lat1, lon1 = radians(p1[0]), radians(p1[1])
    lat2, lon2 = radians(p2[0]), radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def extract_route_features(activity: dict, streams: dict) -> RideRouteFeatures:
    latlng = streams.get("latlng",    {}).get("data", [])
    alt    = streams.get("altitude",  {}).get("data", [])
    watts  = streams.get("watts",     {}).get("data", [])
    hr     = streams.get("heartrate", {}).get("data", [])
    dist   = streams.get("distance",  {}).get("data", [])

    # --- Grade distribution ---
    grades = []
    for i in range(1, len(alt)):
        dx = (dist[i] - dist[i-1]) if dist else 10.0
        if dx > 0:
            grades.append((alt[i] - alt[i-1]) / dx * 100)

    abs_g = [abs(g) for g in grades]
    if not abs_g:
        grade_dist = {"flat": 1.0, "rolling": 0.0, "steep": 0.0}
    else:
        n = len(abs_g)
        grade_dist = {
            "flat":    sum(1 for g in abs_g if g < 2)      / n,
            "rolling": sum(1 for g in abs_g if 2 <= g < 6) / n,
            "steep":   sum(1 for g in abs_g if g >= 6)     / n,
        }

    # --- Climb detection ---
    climbs, gain, active = [], 0.0, False
    for g in grades:
        if g > 1.5:
            gain += g * 10 / 100
            active = True
        elif g < -0.5 and active:
            if gain > 30:
                climbs.append(gain)
            gain, active = 0.0, False

    # --- Turn rate ---
    turns = 0
    if len(latlng) > 2:
        for i in range(1, len(latlng) - 1):
            b1 = _bearing(latlng[i-1], latlng[i])
            b2 = _bearing(latlng[i],   latlng[i+1])
            if abs((b2 - b1 + 180) % 360 - 180) > 30:
                turns += 1

    dist_km = activity["distance"] / 1000
    turn_rate = turns / max(dist_km, 1)

    # --- Longest straight ---
    longest_straight = 0.0
    current_straight = 0.0
    if len(latlng) > 2:
        for i in range(1, len(latlng) - 1):
            b1 = _bearing(latlng[i-1], latlng[i])
            b2 = _bearing(latlng[i],   latlng[i+1])
            if abs((b2 - b1 + 180) % 360 - 180) < 5:
                current_straight += _haversine_km(latlng[i-1], latlng[i])
            else:
                longest_straight = max(longest_straight, current_straight)
                current_straight = 0.0

    # --- Effort thirds ---
    effort_thirds = (1/3, 1/3, 1/3)
    source = watts if watts and len(watts) > 90 else hr if hr and len(hr) > 90 else []
    if source:
        t = len(source) // 3
        thirds_raw = [np.mean(source[:t]), np.mean(source[t:2*t]), np.mean(source[2*t:])]
        total = sum(thirds_raw) or 1
        effort_thirds = tuple(round(x / total, 3) for x in thirds_raw)

    # --- Threshold time ---
    threshold_pct = 0.0
    if hr and len(hr) > 60:
        max_hr = max(hr)
        threshold_pct = round(sum(1 for h in hr if h > max_hr * 0.76) / len(hr), 3)

    # --- Loop detection ---
    is_loop = False
    if latlng and len(latlng) > 10:
        is_loop = _haversine_km(latlng[0], latlng[-1]) < 0.5

    return RideRouteFeatures(
        activity_id=activity["id"],
        date=activity["start_date"][:10],
        distance_km=round(dist_km, 1),
        duration_hours=round(activity["moving_time"] / 3600, 2),
        elevation_gain_m=int(activity["total_elevation_gain"]),
        grade_distribution=grade_dist,
        avg_grade_pct=round(float(np.mean(abs_g)), 2) if abs_g else 0.0,
        max_grade_pct=round(float(max(abs_g)), 1)     if abs_g else 0.0,
        climb_count=len(climbs),
        longest_climb_m=int(max(climbs)) if climbs else 0,
        steepest_5pct_grade=round(float(np.percentile(abs_g, 95)), 1) if abs_g else 0.0,
        turn_rate=round(turn_rate, 2),
        longest_straight_km=round(longest_straight, 2),
        effort_thirds=effort_thirds,
        time_in_threshold_pct=threshold_pct,
        start_hour=int(activity["start_date"][11:13]),
        is_loop=is_loop,
        repeat_road_pct=0.0,
        novelty_score=1.0,
        pr_density=round(activity.get("pr_count", 0) / max(dist_km / 10, 1), 2),
        had_group="group" in activity.get("name", "").lower()
    )
