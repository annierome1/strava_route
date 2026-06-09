# Reference: Ziebart et al. 2008; Oyama & Hato 2022
import numpy as np
import json
from dataclasses import dataclass
import structlog

log = structlog.get_logger()

FEATURE_NAMES = [
    "cycleway",       # 1 if road_class == CYCLEWAY
    "paved",          # 1 if surface is paved
    "grade",          # avg absolute grade % (positive = rider seeks grade, negative = avoids)
    "traffic",        # 0–3 proxy (0=residential, 3=primary) — usually negative weight
    "turn_penalty",   # bearing change at segment entry (radians)
    "length_km",      # segment length — always negative (cost of distance)
]


@dataclass
class RoadSegment:
    segment_id: str
    has_cycleway: bool
    is_paved: bool
    avg_grade_pct: float
    traffic_level: int      # 0=residential, 1=secondary, 2=primary, 3=trunk
    entry_turn_rad: float
    length_km: float

    def to_features(self) -> np.ndarray:
        return np.array([
            1.0 if self.has_cycleway else 0.0,
            1.0 if self.is_paved     else 0.0,
            self.avg_grade_pct,
            float(self.traffic_level),
            self.entry_turn_rad,
            self.length_km,
        ])


class MaxEntropyIRL:
    """
    Tabular linear max-entropy IRL for route choice.
    Given a set of observed GPS trajectories (sequences of road segments the rider
    chose to travel), learns a reward weight vector w such that the observed routes
    are (softmax-)optimal under R(segment) = w · features(segment).

    Gradient update: w += lr * (empirical_feature_counts - expected_feature_counts)
    Expected counts are computed as the feature-weighted softmax over all segments.

    Production upgrade path:
    - Replace linear w with a 2-layer MLP (deep IRL — Oyama & Hato 2022)
    - Add individual covariate embedding for multi-rider generalization (MEDIRL-IC 2024)
    - Use proper map-matched segments via Valhalla or GraphHopper map-matching API
    """

    def __init__(self, lr: float = 0.02, l2: float = 0.001):
        self.weights = np.zeros(len(FEATURE_NAMES))
        self.lr = lr
        self.l2 = l2    # L2 regularization to prevent weight explosion

    def reward(self, seg: RoadSegment) -> float:
        return float(self.weights @ seg.to_features())

    def fit(
        self,
        observed_trajectories: list,
        all_segments: list,
        n_epochs: int = 150
    ) -> list:
        """Returns loss history for convergence monitoring."""
        all_feat = np.array([s.to_features() for s in all_segments])

        # Guard against corrupt segment data before any gradient work
        if not np.isfinite(all_feat).all():
            n_bad = int((~np.isfinite(all_feat)).sum())
            log.warning("irl_invalid_features_replaced", count=n_bad)
            all_feat = np.nan_to_num(all_feat, nan=0.0, posinf=0.0, neginf=0.0)

        # Empirical feature counts: average per-segment features across observed routes
        empirical_fc = np.zeros(len(FEATURE_NAMES))
        for traj in observed_trajectories:
            for seg in traj:
                feat = np.nan_to_num(seg.to_features(), nan=0.0, posinf=0.0, neginf=0.0)
                empirical_fc += feat
        empirical_fc /= max(len(observed_trajectories), 1)

        loss_history = []

        for epoch in range(n_epochs):
            # Expected feature counts under current policy (softmax normalization)
            rewards = all_feat @ self.weights
            rewards -= rewards.max()                # numerical stability
            probs = np.exp(rewards)
            probs /= probs.sum()
            expected_fc = all_feat.T @ probs

            # MaxEnt gradient (positive = increase log-likelihood of observed paths)
            gradient = empirical_fc - expected_fc - self.l2 * self.weights
            self.weights += self.lr * gradient

            # Log-likelihood of observed trajectories
            if epoch % 25 == 0:
                ll = sum(
                    sum(self.reward(s) for s in traj)
                    for traj in observed_trajectories
                )
                loss_history.append(ll)
                log.info("irl_epoch", epoch=epoch, log_likelihood=round(ll, 4),
                         weights={k: round(float(v), 3)
                                  for k, v in zip(FEATURE_NAMES, self.weights)})

        return loss_history

    def to_graphhopper_custom_model(self) -> dict:
        """
        Converts learned weights to GraphHopper priority/distance_influence rules.
        Positive weight → preferred (multiply_by > 1.0)
        Negative weight → penalized (multiply_by near 0)
        """
        w = dict(zip(FEATURE_NAMES, self.weights))
        priority = []

        # Cycleway preference
        if abs(w["cycleway"]) > 0.05:
            mult = round(min(max(1.0 + w["cycleway"] * 0.8, 0.1), 3.0), 2)
            priority.append({"if": "road_class == CYCLEWAY", "multiply_by": str(mult)})

        # Traffic aversion
        if w["traffic"] < -0.05:
            aversion = abs(w["traffic"])
            priority += [
                {"if": "road_class == PRIMARY",  "multiply_by": str(round(max(0.05, 1 - aversion * 0.4), 2))},
                {"if": "road_class == SECONDARY", "multiply_by": str(round(max(0.1,  1 - aversion * 0.25), 2))},
                {"if": "road_class == TRUNK",     "multiply_by": str(round(max(0.02, 1 - aversion * 0.6), 2))},
            ]
        elif w["traffic"] > 0.1:
            # Rare case: rider seems to prefer main roads (urban commuter pattern)
            priority.append({"if": "road_class == PRIMARY", "multiply_by": "1.3"})

        # Surface preference
        if w["paved"] > 0.1:
            priority.append({"if": "road_class == TRACK", "multiply_by": "0.2"})

        # Distance influence: stronger distance-aversion → higher value
        distance_influence = max(50, min(300, int(100 + abs(w["length_km"]) * 80)))

        return {
            "priority": priority,
            "distance_influence": distance_influence
        }

    def explain_weights(self) -> dict:
        """Human-readable interpretation of what the rider implicitly values."""
        w = dict(zip(FEATURE_NAMES, self.weights))
        profile = {
            "loves_cycleways":    bool(w["cycleway"]     > 0.3),
            "avoids_traffic":     bool(w["traffic"]      < -0.2),
            "seeks_climbing":     bool(w["grade"]        > 0.1),
            "avoids_climbing":    bool(w["grade"]        < -0.3),
            "prefers_paved":      bool(w["paved"]        > 0.2),
            "minimizes_turns":    bool(w["turn_penalty"] < -0.1),
            "distance_sensitive": bool(w["length_km"]    < -0.3),
        }
        tags = [k.replace("_", " ") for k, v in profile.items() if v]
        return {
            "profile":     profile,
            "tags":        tags,
            "raw_weights": {k: round(float(v), 4) for k, v in w.items()}
        }

    def save(self, db_path: str = ".route_planner.db"):
        import sqlite3
        from datetime import datetime, timezone
        db = sqlite3.connect(db_path)
        db.execute("CREATE TABLE IF NOT EXISTS irl_models (id TEXT PRIMARY KEY, weights TEXT, trained_at TEXT)")
        db.execute("INSERT OR REPLACE INTO irl_models VALUES (?,?,?)",
                   ("current", json.dumps(self.weights.tolist()),
                    datetime.now(timezone.utc).isoformat()))
        db.commit()

    @classmethod
    def load(cls, db_path: str = ".route_planner.db") -> "MaxEntropyIRL":
        import sqlite3
        db = sqlite3.connect(db_path)
        try:
            row = db.execute("SELECT weights FROM irl_models WHERE id='current'").fetchone()
        except sqlite3.OperationalError:
            raise FileNotFoundError("No trained IRL model found. POST /irl/train first.")
        if not row:
            raise FileNotFoundError("No trained IRL model found. POST /irl/train first.")
        model = cls()
        model.weights = np.array(json.loads(row[0]))
        return model
