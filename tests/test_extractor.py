import pytest
from src.layers.route_dna.extractor import (
    extract_route_features, _haversine_km, _bearing, RideRouteFeatures
)


def make_activity(distance=50000, moving_time=7200, elevation=800, pr_count=3, name="Morning Ride"):
    return {
        "id": 1,
        "start_date": "2024-01-15T07:30:00Z",
        "distance": distance,
        "moving_time": moving_time,
        "total_elevation_gain": elevation,
        "pr_count": pr_count,
        "name": name,
    }


def make_flat_streams(n=200):
    latlng = [[37.7 + i * 0.001, -122.4 + i * 0.001] for i in range(n)]
    alt    = [100.0] * n
    dist   = [i * 250.0 for i in range(n)]
    return {"latlng": {"data": latlng}, "altitude": {"data": alt}, "distance": {"data": dist}}


def make_climb_streams(n=200):
    latlng = [[37.7 + i * 0.001, -122.4] for i in range(n)]
    alt    = [100.0 + i * 5.0 for i in range(n)]  # 5m per point = steep
    dist   = [i * 50.0 for i in range(n)]
    return {"latlng": {"data": latlng}, "altitude": {"data": alt}, "distance": {"data": dist}}


class TestHaversine:
    def test_same_point(self):
        assert _haversine_km([37.7, -122.4], [37.7, -122.4]) == pytest.approx(0.0, abs=1e-6)

    def test_known_distance(self):
        # SF to Oakland ~13km
        d = _haversine_km([37.7749, -122.4194], [37.8044, -122.2712])
        assert 12 < d < 15


class TestExtractRouteFeatures:
    def test_basic_flat_ride(self):
        activity = make_activity()
        streams  = make_flat_streams()
        feat = extract_route_features(activity, streams)

        assert feat.activity_id == 1
        assert feat.distance_km == pytest.approx(50.0, rel=0.05)
        assert feat.duration_hours == pytest.approx(2.0, rel=0.01)
        assert feat.elevation_gain_m == 800
        assert feat.start_hour == 7
        assert isinstance(feat.grade_distribution, dict)
        assert set(feat.grade_distribution.keys()) == {"flat", "rolling", "steep"}
        assert abs(sum(feat.grade_distribution.values()) - 1.0) < 0.01

    def test_loop_detection_true(self):
        activity = make_activity()
        streams  = make_flat_streams(100)
        # Close start/end
        streams["latlng"]["data"][-1] = streams["latlng"]["data"][0]
        feat = extract_route_features(activity, streams)
        assert feat.is_loop is True

    def test_loop_detection_false(self):
        activity = make_activity()
        streams  = make_flat_streams(100)
        # End far from start
        streams["latlng"]["data"][-1] = [40.0, -74.0]
        feat = extract_route_features(activity, streams)
        assert feat.is_loop is False

    def test_steep_ride_grade_distribution(self):
        activity = make_activity()
        streams  = make_climb_streams()
        feat = extract_route_features(activity, streams)
        assert feat.grade_distribution["steep"] > 0.5

    def test_pr_density(self):
        activity = make_activity(distance=50000, pr_count=5)
        feat = extract_route_features(activity, make_flat_streams())
        # 5 PRs / (50km / 10) = 1.0
        assert feat.pr_density == pytest.approx(1.0, rel=0.01)

    def test_group_detection(self):
        activity = make_activity(name="Group Ride Saturday")
        feat = extract_route_features(activity, make_flat_streams())
        assert feat.had_group is True

    def test_empty_streams(self):
        activity = make_activity()
        feat = extract_route_features(activity, {})
        assert feat.distance_km > 0
        assert feat.grade_distribution["flat"] == 1.0
