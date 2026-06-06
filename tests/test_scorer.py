import pytest
from src.layers.route_builder.scorer import score_candidate, _bbox_overlap, RouteScore
from src.layers.dream_generator.recipe import RouteRecipe
from tests.test_taste_profile import make_10_features
from src.layers.route_dna.taste_profile import build_taste_profile


def make_recipe(**overrides):
    defaults = dict(
        distance_km=[60.0, 80.0],
        elevation_m=[800, 1200],
        climb_profile="rolling",
        climb_position="distributed",
        min_climbs=1,
        max_climbs=4,
        traffic_tolerance="low",
        surface="paved",
        route_shape="loop",
        novelty="mixed",
        effort_intent="endurance",
        mood="test",
        distance_influence=100,
        target_distance_m=70000
    )
    defaults.update(overrides)
    return RouteRecipe(**defaults)


class FakeCandidateRoute:
    def __init__(self, variant="match", distance_km=70.0, elevation_m=1000, coords=None):
        self.variant = variant
        self.distance_km = distance_km
        self.elevation_m = elevation_m
        self.geojson = {"coordinates": coords or []}
        self.raw = {}


class TestBboxOverlap:
    def test_overlapping(self):
        a = (0, 0, 2, 2)
        b = (1, 1, 3, 3)
        assert _bbox_overlap(a, b) is True

    def test_non_overlapping(self):
        a = (0, 0, 1, 1)
        b = (2, 2, 3, 3)
        assert _bbox_overlap(a, b) is False

    def test_touching_edge(self):
        a = (0, 0, 1, 1)
        b = (1, 0, 2, 1)
        assert _bbox_overlap(a, b) is True


class TestScoreCandidate:
    def setup_method(self):
        self.taste = build_taste_profile(make_10_features())
        self.recipe = make_recipe()

    def test_perfect_fit(self):
        route = FakeCandidateRoute(distance_km=70.0, elevation_m=1000)
        score = score_candidate(route, self.recipe, self.taste, [])
        assert score.distance_fit == 1.0
        assert score.elevation_fit == 1.0
        assert 0.0 <= score.total <= 1.0

    def test_distance_miss_penalized(self):
        route = FakeCandidateRoute(distance_km=200.0, elevation_m=1000)
        score = score_candidate(route, self.recipe, self.taste, [])
        assert score.distance_fit < 1.0
        assert any("distance" in n for n in score.notes)

    def test_elevation_miss_penalized(self):
        route = FakeCandidateRoute(distance_km=70.0, elevation_m=3000)
        score = score_candidate(route, self.recipe, self.taste, [])
        assert score.elevation_fit < 1.0
        assert any("elevation" in n for n in score.notes)

    def test_novelty_new_roads(self):
        recipe = make_recipe(novelty="new_roads")
        # Route in San Francisco area
        coords = [[-122.4, 37.7, 0], [-122.39, 37.71, 0], [-122.38, 37.72, 0]]
        route = FakeCandidateRoute(coords=coords)
        # bbox that covers exactly this route → 100% overlap
        bboxes = [(37.6, -122.5, 37.8, -122.3)]
        score = score_candidate(route, recipe, self.taste, bboxes)
        # All bboxes overlap → historical_novelty = 0 → novelty_fit = 0 for "new_roads"
        assert score.novelty_fit < 0.5

    def test_novelty_familiar(self):
        recipe = make_recipe(novelty="familiar")
        # Route in San Francisco area
        coords = [[-122.4, 37.7, 0], [-122.39, 37.71, 0], [-122.38, 37.72, 0]]
        route = FakeCandidateRoute(coords=coords)
        bboxes = []  # no historical rides → novelty = 1.0 (very novel route)
        score = score_candidate(route, recipe, self.taste, bboxes)
        # Novel route but rider wants familiar → low fit
        assert score.novelty_fit < 0.5

    def test_score_with_elevation_coords(self):
        coords = [
            [-122.4, 37.7, 100.0],
            [-122.39, 37.71, 105.0],
            [-122.38, 37.72, 110.0],
        ]
        route = FakeCandidateRoute(coords=coords)
        score = score_candidate(route, self.recipe, self.taste, [])
        assert score.grade_fit >= 0.0
