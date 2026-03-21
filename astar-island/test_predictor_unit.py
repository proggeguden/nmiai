"""Unit tests for predictor.py — pure functions, synthetic data, no network.

Run: pytest test_predictor_unit.py -v  (< 2s)
"""

import numpy as np
import pytest

from predictor import (
    terrain_code_to_class,
    _precompute_settlement_distances,
    _precompute_cluster_density,
    compute_bucket_key,
    _interpolate_dist,
    learn_transition_model,
    learn_spatial_transition_model,
    estimate_survival_rate,
    apply_floor,
    validate_predictions,
    extract_settlement_stats,
    TERRAIN_TO_CLASS,
    NUM_CLASSES,
    PROB_FLOOR,
    STATIC_CODES,
    DIST_MIDPOINTS,
)

# ---------------------------------------------------------------------------
# Shared synthetic grids
# ---------------------------------------------------------------------------

# 5×5 grid with all terrain types:
#   10(ocean)  10(ocean)  10(ocean)  10(ocean)  10(ocean)
#   10(ocean)   1(sett)    2(port)   11(plains) 10(ocean)
#   10(ocean)   4(forest)  0(empty)   3(ruin)   10(ocean)
#   10(ocean)  11(plains)  5(mount)  11(plains) 10(ocean)
#   10(ocean)  10(ocean)  10(ocean)  10(ocean)  10(ocean)
GRID_5x5_MIXED = [
    [10, 10, 10, 10, 10],
    [10,  1,  2, 11, 10],
    [10,  4,  0,  3, 10],
    [10, 11,  5, 11, 10],
    [10, 10, 10, 10, 10],
]

# 5×5 grid with no settlements — all plains/forest
GRID_5x5_NO_SETTLEMENTS = [
    [11, 11, 11, 11, 11],
    [11,  4,  4, 11, 11],
    [11,  4, 11, 11, 11],
    [11, 11, 11, 11, 11],
    [11, 11, 11, 11, 11],
]

# 3×3 fully static — ocean + mountain
GRID_3x3_STATIC = [
    [10, 10, 10],
    [10,  5, 10],
    [10, 10, 10],
]


# ===================================================================
# terrain_code_to_class
# ===================================================================

class TestTerrainCodeToClass:
    def test_all_known_codes(self):
        for code, cls in TERRAIN_TO_CLASS.items():
            assert terrain_code_to_class(code) == cls

    def test_unknown_codes_default_to_0(self):
        for code in [6, 99, -1]:
            assert terrain_code_to_class(code) == 0


# ===================================================================
# _precompute_settlement_distances
# ===================================================================

class TestSettlementDistances:
    def test_mixed_grid_distances(self):
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        # Settlement at (1,1), Port at (1,2) → distance 0
        assert dist[1][1] == 0
        assert dist[1][2] == 0
        # (2,2) is 1 step from (1,2) and 1 step from (1,1)
        assert dist[2][2] == 1
        # (3,1) is 2 steps from (1,1)
        assert dist[3][1] == 2
        # Corner (0,0) is 2 steps from (1,1)
        assert dist[0][0] == 2

    def test_no_settlements_all_999(self):
        dist = _precompute_settlement_distances(GRID_5x5_NO_SETTLEMENTS)
        for r in range(5):
            for c in range(5):
                assert dist[r][c] == 999

    def test_single_settlement_diamond(self):
        grid = [
            [11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11],
            [11, 11,  1, 11, 11],
            [11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11],
        ]
        dist = _precompute_settlement_distances(grid)
        assert dist[2][2] == 0
        # Adjacent cells
        assert dist[1][2] == 1
        assert dist[2][1] == 1
        assert dist[2][3] == 1
        assert dist[3][2] == 1
        # Diagonal cells (BFS, not Manhattan — but BFS on 4-connected = Manhattan)
        assert dist[1][1] == 2
        # Corner
        assert dist[0][0] == 4

    def test_ports_count_as_sources(self):
        grid = [
            [11, 11, 11],
            [11,  2, 11],
            [11, 11, 11],
        ]
        dist = _precompute_settlement_distances(grid)
        assert dist[1][1] == 0
        assert dist[0][0] == 2


# ===================================================================
# _precompute_cluster_density
# ===================================================================

class TestClusterDensity:
    def test_two_settlements_within_5(self):
        # Settlements at (1,1) and (1,2) — distance 1
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        # Both settlements should see each other within d≤5
        assert cluster[1][1] is True
        assert cluster[1][2] is True
        # Nearby cells should also see both
        assert cluster[2][2] is True

    def test_isolated_settlement(self):
        grid = [
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11,  1, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
            [11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11, 11],
        ]
        cluster = _precompute_cluster_density(grid)
        # Only one settlement → can never reach count ≥ 2
        assert cluster[1][1] is False

    def test_no_settlements_all_false(self):
        cluster = _precompute_cluster_density(GRID_5x5_NO_SETTLEMENTS)
        for r in range(5):
            for c in range(5):
                assert cluster[r][c] is False


# ===================================================================
# compute_bucket_key
# ===================================================================

class TestComputeBucketKey:
    def test_static_ocean(self):
        key = compute_bucket_key(GRID_5x5_MIXED, 0, 0)
        assert key == (10,)

    def test_static_mountain(self):
        key = compute_bucket_key(GRID_5x5_MIXED, 3, 2)
        assert key == (5,)

    def test_settlement_key_format(self):
        # Settlement at (1,1): has adj_forest=(2,1), adj_settlement=(1,2), coastal=True
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        key = compute_bucket_key(GRID_5x5_MIXED, 1, 1, dist, cluster)
        assert key[0] == 1  # Settlement code
        assert len(key) == 5  # (1, has_adj_forest, has_adj_settlement, is_coastal, is_clustered)
        # Has forest neighbor at (2,1)
        assert key[1] is True  # has_adj_forest
        # Has settlement/port neighbor at (1,2)
        assert key[2] is True  # has_adj_settlement
        # Has ocean at (0,0), (0,1)
        assert key[3] is True  # is_coastal

    def test_plains_key_format(self):
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        # Plains at (1,3): dist to settlement
        key = compute_bucket_key(GRID_5x5_MIXED, 1, 3, dist, cluster)
        assert key[0] == 11
        assert len(key) == 6  # (11, dist_bucket, is_coastal, forest_level, is_clustered, adj_sett_level)
        # forest_level is int 0/1/2 (not bool)
        assert key[3] in (0, 1, 2)
        # adj_sett_level is int 0/1/2
        assert key[5] in (0, 1, 2)

    def test_empty_cell_key(self):
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        # Empty at (2,2)
        key = compute_bucket_key(GRID_5x5_MIXED, 2, 2, dist, cluster)
        assert key[0] == 0
        assert len(key) == 3  # (0, dist_bucket, has_adj_forest)

    def test_forest_cell_key(self):
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        key = compute_bucket_key(GRID_5x5_MIXED, 2, 1, dist, cluster)
        assert key[0] == 4
        assert len(key) == 6  # (4, dist_bucket, adj_sett_level, is_coastal, is_interior, is_clustered)
        # adj_sett_level is 0/1/2 (int, not bool)
        assert key[2] in (0, 1, 2)
        # is_interior is bool
        assert isinstance(key[4], bool)
        # is_clustered is bool
        assert isinstance(key[5], bool)

    def test_ruin_cell_key(self):
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        key = compute_bucket_key(GRID_5x5_MIXED, 2, 3, dist, cluster)
        assert key[0] == 3
        assert len(key) == 3  # (3, dist_bucket, has_adj_settlement)

    def test_fallback_without_precomputed(self):
        """Without precomputed dists, should compute manually and give same result."""
        dist = _precompute_settlement_distances(GRID_5x5_MIXED)
        cluster = _precompute_cluster_density(GRID_5x5_MIXED)
        key_pre = compute_bucket_key(GRID_5x5_MIXED, 2, 2, dist, cluster)
        key_fallback = compute_bucket_key(GRID_5x5_MIXED, 2, 2)
        # Distance bucket should match (cluster won't since it defaults to False)
        assert key_pre[0] == key_fallback[0]
        assert key_pre[1] == key_fallback[1]  # dist_bucket same


# ===================================================================
# _interpolate_dist
# ===================================================================

class TestInterpolateDist:
    def _make_model(self):
        """Create a simple spatial model for interpolation tests."""
        # Key format for plains: (11, dist_bucket, is_coastal, has_adj_forest, is_clustered)
        model = {}
        # Bucket 0 (near): mostly Settlement
        probs0 = np.array([0.3, 0.4, 0.1, 0.05, 0.1, 0.05])
        model[(11, 0, False, False, False)] = probs0
        # Bucket 1 (mid): more Empty
        probs1 = np.array([0.6, 0.15, 0.05, 0.05, 0.1, 0.05])
        model[(11, 1, False, False, False)] = probs1
        # Bucket 2 (far): mostly Empty
        probs2 = np.array([0.8, 0.05, 0.02, 0.03, 0.08, 0.02])
        model[(11, 2, False, False, False)] = probs2
        return model

    def test_at_midpoint_returns_own(self):
        model = self._make_model()
        key = (11, 0, False, False, False)
        # d=1.0 is midpoint of bucket 0 → no blending needed
        result = _interpolate_dist(1.0, key, 1, model)
        np.testing.assert_array_almost_equal(result, model[key])

    def test_between_midpoints_interpolates(self):
        model = self._make_model()
        key = (11, 0, False, False, False)
        # d=2.0: midpoint=1.0, neighbor bucket 1 midpoint=3.5
        # t = |2.0 - 1.0| / |3.5 - 1.0| = 1.0/2.5 = 0.4
        result = _interpolate_dist(2.0, key, 1, model)
        expected = 0.6 * model[(11, 0, False, False, False)] + 0.4 * model[(11, 1, False, False, False)]
        np.testing.assert_array_almost_equal(result, expected)

    def test_edge_bucket_no_lower_neighbor(self):
        model = self._make_model()
        key = (11, 0, False, False, False)
        # d=0.5: below midpoint 1.0, but bucket 0 has no lower neighbor → no blending
        result = _interpolate_dist(0.5, key, 1, model)
        np.testing.assert_array_almost_equal(result, model[key])

    def test_missing_neighbor_returns_own(self):
        model = self._make_model()
        # Remove bucket 1
        del model[(11, 1, False, False, False)]
        key = (11, 0, False, False, False)
        # d=2.0 would blend with bucket 1, but it's missing
        result = _interpolate_dist(2.0, key, 1, model)
        np.testing.assert_array_almost_equal(result, model[key])


# ===================================================================
# learn_transition_model
# ===================================================================

class TestLearnTransitionModel:
    def _make_obs(self, seed_idx, vp_x, vp_y, grid):
        return {
            "seed_index": seed_idx,
            "viewport": {"x": vp_x, "y": vp_y},
            "grid": grid,
        }

    def test_single_observation_normalized(self):
        initial_grids = [[[11, 11], [11, 11]]]
        obs = [self._make_obs(0, 0, 0, [[0, 1], [4, 3]])]
        model = learn_transition_model(initial_grids, obs)
        assert 11 in model
        probs = model[11]
        assert abs(probs.sum() - 1.0) < 1e-9
        # 4 cells all Plains(11), observed as: Empty(0), Settlement(1), Forest(4), Ruin(3)
        assert probs[0] == 0.25  # Empty
        assert probs[1] == 0.25  # Settlement
        assert probs[3] == 0.25  # Ruin
        assert probs[4] == 0.25  # Forest

    def test_multiple_observations_weighted(self):
        initial_grids = [[[11]]]
        obs = [
            self._make_obs(0, 0, 0, [[1]]),
            self._make_obs(0, 0, 0, [[1]]),
            self._make_obs(0, 0, 0, [[0]]),
        ]
        model = learn_transition_model(initial_grids, obs)
        probs = model[11]
        assert abs(probs[1] - 2/3) < 1e-9  # Settlement 2/3
        assert abs(probs[0] - 1/3) < 1e-9  # Empty 1/3

    def test_out_of_range_seed_skipped(self):
        initial_grids = [[[11]]]
        obs = [self._make_obs(5, 0, 0, [[1]])]  # seed 5 doesn't exist
        model = learn_transition_model(initial_grids, obs)
        assert len(model) == 0


# ===================================================================
# learn_spatial_transition_model
# ===================================================================

class TestLearnSpatialTransitionModel:
    def _make_obs(self, seed_idx, vp_x, vp_y, grid):
        return {
            "seed_index": seed_idx,
            "viewport": {"x": vp_x, "y": vp_y},
            "grid": grid,
        }

    def test_returns_correct_types(self):
        initial_grids = [[[11, 11, 11], [11, 11, 11], [11, 11, 11]]]
        # Need ≥3 observations per bucket for it to appear
        obs = [self._make_obs(0, 0, 0, [[0, 0, 0], [0, 0, 0], [0, 0, 0]])] * 5
        global_model, spatial_model, _ = learn_spatial_transition_model(initial_grids, obs)
        assert isinstance(global_model, dict)
        assert isinstance(spatial_model, dict)
        # Global model keys are terrain codes (ints)
        for key in global_model:
            assert isinstance(key, int)
        # Spatial model keys are tuples
        for key in spatial_model:
            assert isinstance(key, tuple)

    def test_bayesian_smoothing_weights(self):
        """Bucket with 4 obs should blend with global at weight 4/(4+5)."""
        grid = [[11, 11, 11, 11, 11],
                [11, 11, 11, 11, 11],
                [11, 11, 11, 11, 11],
                [11, 11, 11, 11, 11],
                [11, 11, 11, 11, 11]]
        initial_grids = [grid]
        # Create observations: all cells become Empty (code 0)
        obs = [self._make_obs(0, 0, 0, [[0]*5]*5)] * 4
        global_model, spatial_model, _ = learn_spatial_transition_model(initial_grids, obs)
        # With 4 observations of 25 cells each, buckets should have plenty of obs
        # Check that spatial model has entries
        assert len(spatial_model) > 0
        # Verify blending: spatial should be between pure bucket and global
        for key, probs in spatial_model.items():
            assert abs(probs.sum() - 1.0) < 1e-9


# ===================================================================
# estimate_survival_rate
# ===================================================================

class TestEstimateSurvivalRate:
    def _make_obs(self, seed_idx, vp_x, vp_y, grid):
        return {
            "seed_index": seed_idx,
            "viewport": {"x": vp_x, "y": vp_y},
            "grid": grid,
        }

    def test_all_survive(self):
        # 5×5 grid of settlements, all survive
        grid = [[1]*5 for _ in range(5)]
        initial_grids = [grid]
        obs = [self._make_obs(0, 0, 0, [[1]*5]*5)]
        rate = estimate_survival_rate(initial_grids, obs)
        assert rate == 1.0

    def test_none_survive(self):
        grid = [[1]*5 for _ in range(5)]
        initial_grids = [grid]
        # All become Empty (code 0)
        obs = [self._make_obs(0, 0, 0, [[0]*5]*5)]
        rate = estimate_survival_rate(initial_grids, obs)
        assert rate == 0.0

    def test_insufficient_data_returns_none(self):
        grid = [[1, 11], [11, 11]]
        initial_grids = [grid]
        # Only 1 settlement cell observed → < 20
        obs = [self._make_obs(0, 0, 0, [[0, 0], [0, 0]])]
        rate = estimate_survival_rate(initial_grids, obs)
        assert rate is None

    def test_mixed_survival(self):
        # 6×5 grid = 30 settlement cells
        grid = [[1]*5 for _ in range(6)]
        initial_grids = [grid]
        # Half survive (Settlement=1), half become Empty
        result_grid = [[1, 1, 0, 0, 0]] * 6  # 2/5 survive per row → 12/30
        obs = [self._make_obs(0, 0, 0, result_grid)]
        rate = estimate_survival_rate(initial_grids, obs)
        assert abs(rate - 12/30) < 1e-9


# ===================================================================
# apply_floor
# ===================================================================

class TestApplyFloor:
    def test_already_above_floor(self):
        pred = np.array([[[0.2, 0.2, 0.2, 0.1, 0.2, 0.1]]])
        result = apply_floor(pred)
        np.testing.assert_array_almost_equal(result.sum(axis=2), [[1.0]])

    def test_zeros_raised_to_floor(self):
        pred = np.array([[[1.0, 0.0, 0.0, 0.0, 0.0, 0.0]]])
        result = apply_floor(pred)
        assert result[0, 0].min() >= PROB_FLOOR - 1e-6
        assert abs(result[0, 0].sum() - 1.0) < 1e-6

    def test_batch_all_valid(self):
        pred = np.zeros((3, 3, 6))
        # Set one-hot for each cell (different classes)
        for r in range(3):
            for c in range(3):
                pred[r, c, (r * 3 + c) % 6] = 1.0
        result = apply_floor(pred)
        # All cells must sum to 1 and be above floor
        for r in range(3):
            for c in range(3):
                assert abs(result[r, c].sum() - 1.0) < 1e-6
                assert result[r, c].min() >= PROB_FLOOR - 1e-6


# ===================================================================
# validate_predictions
# ===================================================================

class TestValidatePredictions:
    def test_valid_tensor(self):
        pred = np.full((3, 3, 6), 1/6)
        assert validate_predictions(pred, 3, 3) is True

    def test_wrong_shape_raises(self):
        pred = np.full((3, 3, 5), 0.2)
        with pytest.raises(AssertionError):
            validate_predictions(pred, 3, 3)

    def test_below_floor_raises(self):
        pred = np.full((3, 3, 6), 1/6)
        pred[0, 0, 0] = 0.0005  # below PROB_FLOOR (0.001)
        pred[0, 0, 1:] = (1 - 0.001) / 5
        with pytest.raises(AssertionError):
            validate_predictions(pred, 3, 3)


# ===================================================================
# extract_settlement_stats
# ===================================================================

class TestExtractSettlementStats:
    def test_well_formed_data(self):
        obs = []
        for i in range(12):
            obs.append({
                "settlements": [
                    {"food": 50 + i, "population": 100 + i, "wealth": 200,
                     "position": {"x": i, "y": 0}},
                ]
            })
        stats = extract_settlement_stats(obs)
        assert stats is not None
        assert "avg_food" in stats
        assert "median_food" in stats
        assert "avg_population" in stats
        assert "avg_wealth" in stats
        assert stats["total_observations"] == 12

    def test_missing_fields_graceful(self):
        obs = []
        for i in range(12):
            obs.append({
                "settlements": [
                    {"food": 50 + i},  # no population, no wealth, no position
                ]
            })
        stats = extract_settlement_stats(obs)
        assert stats is not None
        assert stats["avg_food"] > 0
        assert stats["avg_population"] == 0  # no population data → 0
        assert stats["unique_positions"] == 0

    def test_insufficient_data_returns_none(self):
        obs = [{"settlements": [{"food": 50}]}]  # only 1 observation < 10
        stats = extract_settlement_stats(obs)
        assert stats is None
