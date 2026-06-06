import pytest
from src.layers.route_dna.extractor import RideRouteFeatures
from src.layers.route_dna.taste_profile import (
    build_taste_profile, taste_profile_to_dict, taste_profile_from_dict
)


def make_feature(
    distance_km=80.0,
    elevation_gain_m=1500,
    is_loop=True,
    start_hour=7,
    grade_dist=None,
    climb_count=3,
    longest_climb_m=300,
    effort_thirds=(0.33, 0.33, 0.34),
    had_group=False,
    pr_density=0.3,
    novelty_score=0.7,
    activity_id=1,
):
    return RideRouteFeatures(
        activity_id=activity_id,
        date="2024-01-15",
        distance_km=distance_km,
        duration_hours=distance_km / 25,
        elevation_gain_m=elevation_gain_m,
        grade_distribution=grade_dist or {"flat": 0.3, "rolling": 0.4, "steep": 0.3},
        avg_grade_pct=4.5,
        max_grade_pct=12.0,
        climb_count=climb_count,
        longest_climb_m=longest_climb_m,
        steepest_5pct_grade=10.0,
        turn_rate=2.5,
        longest_straight_km=3.0,
        effort_thirds=effort_thirds,
        time_in_threshold_pct=0.25,
        start_hour=start_hour,
        is_loop=is_loop,
        repeat_road_pct=1.0 - novelty_score,
        novelty_score=novelty_score,
        pr_density=pr_density,
        had_group=had_group,
    )


def make_10_features(**kwargs):
    return [make_feature(activity_id=i, **kwargs) for i in range(10)]


class TestBuildTasteProfile:
    def test_basic_build(self):
        features = make_10_features()
        profile = build_taste_profile(features)
        assert profile.median_distance_km == pytest.approx(80.0)
        assert profile.preferred_distance_km[0] <= 80.0 <= profile.preferred_distance_km[1]

    def test_filters_short_rides(self):
        short = [make_feature(distance_km=10.0, activity_id=i) for i in range(5)]
        with pytest.raises(ValueError, match="at least 5"):
            build_taste_profile(short)

    def test_loop_rider_tag(self):
        features = make_10_features(is_loop=True)
        profile = build_taste_profile(features)
        assert profile.prefers_loops is True
        assert "loop rider" in profile.signature_tags

    def test_dawn_patrol_tag(self):
        features = make_10_features(start_hour=5)
        profile = build_taste_profile(features)
        assert "dawn patrol" in profile.signature_tags

    def test_climber_tag(self):
        features = make_10_features(elevation_gain_m=1600, longest_climb_m=250, climb_count=2)
        profile = build_taste_profile(features)
        assert "climber" in profile.signature_tags or profile.favors_sustained

    def test_negative_split_tag(self):
        features = make_10_features(effort_thirds=(0.30, 0.33, 0.37))
        profile = build_taste_profile(features)
        assert profile.effort_shape == "negative_split"
        assert "strong finisher" in profile.signature_tags

    def test_vert_per_km(self):
        features = make_10_features(distance_km=100.0, elevation_gain_m=2000)
        profile = build_taste_profile(features)
        assert profile.vert_per_km == pytest.approx(20.0, rel=0.05)

    def test_home_coords_preserved(self):
        features = make_10_features()
        profile = build_taste_profile(features, home_coords=(37.77, -122.41))
        assert profile.home_coords == (37.77, -122.41)


class TestSerialization:
    def test_round_trip(self):
        features = make_10_features()
        profile = build_taste_profile(features, home_coords=(51.5, -0.1))
        d = taste_profile_to_dict(profile)
        restored = taste_profile_from_dict(d)
        assert restored.median_distance_km == profile.median_distance_km
        assert restored.signature_tags == profile.signature_tags
        assert restored.home_coords == profile.home_coords

    def test_json_serializable(self):
        import json
        features = make_10_features()
        profile = build_taste_profile(features)
        d = taste_profile_to_dict(profile)
        json.dumps(d)  # must not raise
