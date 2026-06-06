import pytest
import numpy as np
from src.builds.irl_engine.engine import MaxEntropyIRL, RoadSegment, FEATURE_NAMES


def make_segment(cycleway=False, paved=True, grade=2.0, traffic=1, turn=0.3, length=1.0, sid="s1"):
    return RoadSegment(
        segment_id=sid,
        has_cycleway=cycleway,
        is_paved=paved,
        avg_grade_pct=grade,
        traffic_level=traffic,
        entry_turn_rad=turn,
        length_km=length
    )


class TestRoadSegment:
    def test_features_shape(self):
        seg = make_segment()
        feat = seg.to_features()
        assert feat.shape == (len(FEATURE_NAMES),)

    def test_cycleway_encoding(self):
        seg = make_segment(cycleway=True)
        assert seg.to_features()[0] == 1.0

    def test_paved_encoding(self):
        seg = make_segment(paved=False)
        assert seg.to_features()[1] == 0.0


class TestMaxEntropyIRL:
    def make_segments(self, n=10):
        segs = []
        for i in range(n):
            segs.append(make_segment(
                cycleway=(i % 3 == 0),
                grade=float(i),
                traffic=i % 4,
                sid=f"s{i}"
            ))
        return segs

    def test_init_zero_weights(self):
        model = MaxEntropyIRL()
        assert np.all(model.weights == 0.0)
        assert len(model.weights) == len(FEATURE_NAMES)

    def test_fit_updates_weights(self):
        model = MaxEntropyIRL()
        segments = self.make_segments(20)
        # Rider always chooses cycleway segments
        cycleway_segs = [s for s in segments if s.has_cycleway]
        trajectories = [[s] for s in cycleway_segs] * 5

        model.fit(trajectories, segments, n_epochs=50)
        # Cycleway weight should be positive
        w = dict(zip(FEATURE_NAMES, model.weights))
        assert w["cycleway"] > 0.0

    def test_fit_returns_loss_history(self):
        model = MaxEntropyIRL()
        segments = self.make_segments(10)
        trajectories = [[segments[0]]]
        loss = model.fit(trajectories, segments, n_epochs=50)
        assert isinstance(loss, list)
        assert len(loss) > 0

    def test_reward_function(self):
        model = MaxEntropyIRL()
        model.weights = np.array([1.0, 0.5, -0.2, -0.3, 0.0, -1.0])
        seg = make_segment(cycleway=True, paved=True, grade=3.0, traffic=2, turn=0.5, length=2.0)
        r = model.reward(seg)
        expected = 1.0*1 + 0.5*1 + (-0.2)*3 + (-0.3)*2 + 0.0*0.5 + (-1.0)*2
        assert r == pytest.approx(expected, rel=1e-5)

    def test_to_graphhopper_custom_model_traffic_aversion(self):
        model = MaxEntropyIRL()
        model.weights = np.array([0.0, 0.0, 0.0, -0.5, 0.0, -0.2])
        cm = model.to_graphhopper_custom_model()
        assert "priority" in cm
        assert "distance_influence" in cm
        # Traffic aversion should create priority rules for primary/trunk roads
        road_classes = [r["if"] for r in cm["priority"]]
        assert any("PRIMARY" in rc for rc in road_classes)

    def test_explain_weights(self):
        model = MaxEntropyIRL()
        model.weights = np.array([0.5, 0.3, 0.2, -0.4, -0.2, -0.5])
        explanation = model.explain_weights()
        assert "profile" in explanation
        assert "tags" in explanation
        assert "raw_weights" in explanation
        assert explanation["profile"]["loves_cycleways"] is True
        assert explanation["profile"]["avoids_traffic"] is True

    def test_save_and_load(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        model = MaxEntropyIRL()
        model.weights = np.array([0.1, 0.2, 0.3, -0.1, 0.0, -0.5])
        model.save(db_path)

        loaded = MaxEntropyIRL.load(db_path)
        np.testing.assert_array_almost_equal(loaded.weights, model.weights)

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            MaxEntropyIRL.load(str(tmp_path / "nonexistent.db"))
