"""Unit tests for ml_predictor.extract_features().

Run with: pytest test_ml_predictor.py -v
"""
import numpy as np
import pytest

from ml_predictor import extract_features, NUM_FEATURES, FEATURE_NAMES, RATE_KEYS, numpy_forward, numpy_forward_ensemble, save_model, load_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_grid(H=5, W=5, fill=11):
    """Return H×W list-of-lists filled with a terrain code."""
    return [[fill] * W for _ in range(H)]


def _set(grid, r, c, code):
    grid[r][c] = code
    return grid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExtractFeaturesShape:
    """test_extract_features_shape: returns H×W×28 float32 array."""

    def test_shape(self):
        grid = _make_grid(6, 8)
        result = extract_features(grid)
        assert result.shape == (6, 8, 28), f"Expected (6,8,25), got {result.shape}"

    def test_dtype(self):
        grid = _make_grid(4, 4)
        result = extract_features(grid)
        assert result.dtype == np.float32, f"Expected float32, got {result.dtype}"

    def test_num_features_constant(self):
        assert NUM_FEATURES == 28

    def test_feature_names_length(self):
        assert len(FEATURE_NAMES) == 28


class TestExtractFeaturesOnehot:
    """test_extract_features_onehot: Settlement cell has correct one-hot encoding."""

    def test_settlement_onehot(self):
        # Place a settlement at (2, 2) in a plains grid
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 2, 2, 1)  # code 1 = Settlement → class index 1
        result = extract_features(grid)
        onehot = result[2, 2, :6]
        expected = np.array([0, 1, 0, 0, 0, 0], dtype=np.float32)
        np.testing.assert_array_equal(onehot, expected,
            err_msg=f"Settlement one-hot wrong: {onehot}")

    def test_forest_onehot(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 1, 1, 4)  # Forest → class 4
        result = extract_features(grid)
        onehot = result[1, 1, :6]
        expected = np.array([0, 0, 0, 0, 1, 0], dtype=np.float32)
        np.testing.assert_array_equal(onehot, expected,
            err_msg=f"Forest one-hot wrong: {onehot}")

    def test_ocean_maps_to_empty(self):
        # Ocean (10) → class 0 (Empty)
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 0, 0, 10)
        result = extract_features(grid)
        onehot = result[0, 0, :6]
        expected = np.array([1, 0, 0, 0, 0, 0], dtype=np.float32)
        np.testing.assert_array_equal(onehot, expected,
            err_msg=f"Ocean→Empty one-hot wrong: {onehot}")

    def test_mountain_onehot(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 3, 3, 5)  # Mountain → class 5
        result = extract_features(grid)
        onehot = result[3, 3, :6]
        expected = np.array([0, 0, 0, 0, 0, 1], dtype=np.float32)
        np.testing.assert_array_equal(onehot, expected,
            err_msg=f"Mountain one-hot wrong: {onehot}")


class TestExtractFeaturesDistanceCapped:
    """test_extract_features_distance_capped: Distance capped at 20 when no settlements."""

    def test_no_settlements_distance_is_20(self):
        # Grid with only Plains (no settlements) → raw dist=999, capped at 20
        grid = _make_grid(5, 5, fill=11)
        result = extract_features(grid)
        dist_feature = result[:, :, 6]  # feature index 6
        assert np.all(dist_feature == 20.0), \
            f"Expected all distances=20 (capped), got min={dist_feature.min()}, max={dist_feature.max()}"

    def test_settlement_at_distance_zero(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 2, 2, 1)
        result = extract_features(grid)
        # Settlement cell itself → distance 0
        assert result[2, 2, 6] == 0.0, f"Expected dist=0 for settlement cell, got {result[2, 2, 6]}"

    def test_distance_caps_at_20(self):
        # 40×40 grid with settlement only at corner → far cells have raw dist > 20
        grid = _make_grid(40, 40, fill=11)
        _set(grid, 0, 0, 1)  # settlement at top-left corner
        result = extract_features(grid)
        dist_feature = result[:, :, 6]
        assert dist_feature.max() <= 20.0, \
            f"Distance not capped at 20, max={dist_feature.max()}"
        # Cell at (39, 39) would be raw dist=78, should be capped
        assert result[39, 39, 6] == 20.0


class TestExtractFeaturesRatesAppended:
    """test_extract_features_rates_appended: Round-level rates appear in last 5 features."""

    def test_rates_in_last_5_features(self):
        grid = _make_grid(4, 4, fill=11)
        rates = {
            "survival": 0.7,
            "expansion": 0.3,
            "port_formation": 0.1,
            "forest_reclamation": 0.6,
            "ruin": 0.2,
        }
        result = extract_features(grid, rates=rates)
        # Last 5 features should equal the rate values (broadcast to all cells)
        expected = np.array([0.7, 0.3, 0.1, 0.6, 0.2], dtype=np.float32)
        for r in range(4):
            for c in range(4):
                actual_rates = result[r, c, 13:18]
                np.testing.assert_array_almost_equal(actual_rates, expected,
                    err_msg=f"Rate features wrong at ({r},{c}): {actual_rates}")

    def test_rate_keys(self):
        assert RATE_KEYS == ["survival", "expansion", "port_formation", "forest_reclamation", "ruin"]

    def test_partial_rates_order(self):
        """Order of rates must match RATE_KEYS exactly."""
        grid = _make_grid(3, 3, fill=11)
        rates = {"survival": 0.9}  # only one key provided, others default to 0.5
        result = extract_features(grid, rates=rates)
        # survival=0.9, rest=0.5
        expected_last5 = np.array([0.9, 0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        np.testing.assert_array_almost_equal(result[1, 1, 13:18], expected_last5)


class TestExtractFeaturesNoneRates:
    """test_extract_features_none_rates: None rates default to 0.5."""

    def test_none_rates_defaults_to_half(self):
        grid = _make_grid(4, 4, fill=11)
        result = extract_features(grid, rates=None)
        expected = np.array([0.5, 0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        for r in range(4):
            for c in range(4):
                np.testing.assert_array_equal(result[r, c, 13:18], expected,
                    err_msg=f"None rates should default to 0.5, got {result[r, c, 13:18]}")

    def test_none_value_in_dict_defaults_to_half(self):
        grid = _make_grid(4, 4, fill=11)
        rates = {"survival": None, "expansion": 0.4}
        result = extract_features(grid, rates=rates)
        # survival is None → 0.5, expansion → 0.4, rest → 0.5
        expected = np.array([0.5, 0.4, 0.5, 0.5, 0.5], dtype=np.float32)
        np.testing.assert_array_almost_equal(result[0, 0, 13:18], expected)


class TestDistanceToCoast:
    """Feature 18: BFS distance to nearest ocean cell, capped at 20."""

    def test_ocean_cell_distance_zero(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 0, 0, 10)  # ocean
        result = extract_features(grid)
        assert result[0, 0, 18] == 0.0

    def test_adjacent_to_ocean(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 0, 0, 10)
        result = extract_features(grid)
        assert result[0, 1, 18] == 1.0  # adjacent
        assert result[1, 0, 18] == 1.0

    def test_no_ocean_capped_at_20(self):
        grid = _make_grid(5, 5, fill=11)  # all plains, no ocean
        result = extract_features(grid)
        assert result[2, 2, 18] == 20.0

    def test_distance_gradient(self):
        # Ocean on left edge
        grid = _make_grid(1, 10, fill=11)
        _set(grid, 0, 0, 10)
        result = extract_features(grid)
        for c in range(10):
            assert result[0, c, 18] == float(min(c, 20))


class TestAdjMountainCount:
    """Feature 19: count of adjacent mountain cells (8-connected, 0-8)."""

    def test_no_mountains(self):
        grid = _make_grid(5, 5, fill=11)
        result = extract_features(grid)
        assert result[2, 2, 19] == 0.0

    def test_one_adjacent_mountain(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 1, 2, 5)  # mountain above (2,2)
        result = extract_features(grid)
        assert result[2, 2, 19] == 1.0

    def test_surrounded_by_mountains(self):
        grid = _make_grid(5, 5, fill=5)  # all mountains
        _set(grid, 2, 2, 11)  # plains cell surrounded
        result = extract_features(grid)
        assert result[2, 2, 19] == 8.0

    def test_corner_cell_max_3(self):
        grid = _make_grid(3, 3, fill=5)
        _set(grid, 0, 0, 11)  # corner cell
        result = extract_features(grid)
        assert result[0, 0, 19] == 3.0  # 3 adjacent mountains


class TestSettlementCountR3:
    """Feature 20: count of settlement cells within Manhattan distance 3."""

    def test_no_settlements(self):
        grid = _make_grid(7, 7, fill=11)
        result = extract_features(grid)
        assert result[3, 3, 20] == 0.0

    def test_settlement_counts_itself(self):
        # A settlement cell should count itself (distance 0 <= 3)
        grid = _make_grid(7, 7, fill=11)
        _set(grid, 3, 3, 1)
        result = extract_features(grid)
        assert result[3, 3, 20] == 1.0

    def test_settlement_at_exact_distance_3(self):
        # Settlement at Manhattan distance exactly 3 should be counted
        grid = _make_grid(9, 9, fill=11)
        _set(grid, 4, 4, 11)   # center cell
        _set(grid, 4, 7, 1)    # distance 3 (right)
        result = extract_features(grid)
        assert result[4, 4, 20] == 1.0

    def test_settlement_at_distance_4_not_counted(self):
        # Settlement at Manhattan distance 4 should NOT be counted
        grid = _make_grid(9, 9, fill=11)
        _set(grid, 4, 0, 1)    # distance 4 from (4, 4)
        result = extract_features(grid)
        assert result[4, 4, 20] == 0.0

    def test_multiple_settlements_in_radius(self):
        # 3 settlements within Manhattan distance 3 of center
        grid = _make_grid(9, 9, fill=11)
        _set(grid, 4, 5, 1)  # distance 1
        _set(grid, 4, 6, 1)  # distance 2
        _set(grid, 4, 7, 1)  # distance 3
        result = extract_features(grid)
        assert result[4, 4, 20] == 3.0

    def test_port_counts_as_settlement(self):
        # Port (code 2) should also count as settlement
        grid = _make_grid(7, 7, fill=11)
        _set(grid, 3, 4, 2)  # port at distance 1
        result = extract_features(grid)
        assert result[3, 3, 20] == 1.0


class TestForestDensityR2:
    """Feature 21: count of forest cells within Manhattan distance 2 (max 13)."""

    def test_no_forest(self):
        grid = _make_grid(5, 5, fill=11)
        result = extract_features(grid)
        assert result[2, 2, 21] == 0.0

    def test_cell_itself_is_forest(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 2, 2, 4)
        result = extract_features(grid)
        # The forest cell itself at dist 0 counts
        assert result[2, 2, 21] >= 1.0

    def test_forest_at_exact_distance_2(self):
        # Forest at Manhattan distance exactly 2 should be counted
        grid = _make_grid(7, 7, fill=11)
        _set(grid, 3, 5, 4)  # distance 2 from (3,3)
        result = extract_features(grid)
        assert result[3, 3, 21] == 1.0

    def test_forest_at_distance_3_not_counted(self):
        # Forest at Manhattan distance 3 should NOT be counted
        grid = _make_grid(9, 9, fill=11)
        _set(grid, 4, 7, 4)  # distance 3 from (4,4)
        result = extract_features(grid)
        assert result[4, 4, 21] == 0.0

    def test_max_13_in_solid_forest(self):
        # Center of a solid forest block: all 13 cells in radius-2 diamond are forest
        grid = _make_grid(7, 7, fill=4)  # all forest
        result = extract_features(grid)
        assert result[3, 3, 21] == 13.0

    def test_corner_reduces_count(self):
        # Corner cell: part of diamond is out of bounds
        grid = _make_grid(5, 5, fill=4)
        result = extract_features(grid)
        # Corner (0,0): valid cells in r=2 diamond clipped to grid
        assert result[0, 0, 21] < 13.0


class TestDistToForest:
    """Feature 22: BFS distance to nearest forest cell (code 4), capped at 10."""

    def test_forest_cell_distance_zero(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 2, 2, 4)
        result = extract_features(grid)
        assert result[2, 2, 22] == 0.0

    def test_adjacent_to_forest(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 2, 2, 4)
        result = extract_features(grid)
        assert result[2, 3, 22] == 1.0  # adjacent (right)
        assert result[3, 2, 22] == 1.0  # adjacent (below)

    def test_no_forest_capped_at_10(self):
        grid = _make_grid(5, 5, fill=11)  # no forest
        result = extract_features(grid)
        assert result[2, 2, 22] == 10.0

    def test_distance_gradient(self):
        # Forest on left edge, measure gradient
        grid = _make_grid(1, 15, fill=11)
        _set(grid, 0, 0, 4)
        result = extract_features(grid)
        for c in range(15):
            assert result[0, c, 22] == float(min(c, 10))

    def test_cap_at_10(self):
        # Large grid with forest only at corner
        grid = _make_grid(30, 30, fill=11)
        _set(grid, 0, 0, 4)
        result = extract_features(grid)
        assert result[29, 29, 22] == 10.0


class TestSettlementCountR5:
    """Feature 23: count of settlement cells within Manhattan distance 5."""

    def test_no_settlements(self):
        grid = _make_grid(11, 11, fill=11)
        result = extract_features(grid)
        assert result[5, 5, 23] == 0.0

    def test_settlement_at_exact_distance_5(self):
        grid = _make_grid(13, 13, fill=11)
        _set(grid, 6, 11, 1)  # distance 5 from (6,6)
        result = extract_features(grid)
        assert result[6, 6, 23] == 1.0

    def test_settlement_at_distance_6_not_counted(self):
        grid = _make_grid(13, 13, fill=11)
        _set(grid, 6, 12, 1)  # distance 6 from (6,6)
        result = extract_features(grid)
        assert result[6, 6, 23] == 0.0

    def test_count_r5_geq_count_r3(self):
        # r5 count must be >= r3 count for all cells
        grid = _make_grid(15, 15, fill=11)
        _set(grid, 5, 5, 1)
        _set(grid, 7, 7, 1)
        _set(grid, 9, 9, 1)
        result = extract_features(grid)
        r3 = result[:, :, 20]
        r5 = result[:, :, 23]
        assert np.all(r5 >= r3), "settlement_count_r5 must be >= settlement_count_r3 everywhere"


class TestAdjRuinCount:
    """Feature 24: count of adjacent ruin cells (code 3, 8-connected)."""

    def test_no_ruins(self):
        grid = _make_grid(5, 5, fill=11)
        result = extract_features(grid)
        assert result[2, 2, 24] == 0.0

    def test_one_adjacent_ruin(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 1, 2, 3)  # ruin above (2,2)
        result = extract_features(grid)
        assert result[2, 2, 24] == 1.0

    def test_diagonal_ruin_counts(self):
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 1, 1, 3)  # diagonal ruin
        result = extract_features(grid)
        assert result[2, 2, 24] == 1.0

    def test_surrounded_by_ruins(self):
        grid = _make_grid(5, 5, fill=3)  # all ruins
        _set(grid, 2, 2, 11)  # plains cell surrounded by ruins
        result = extract_features(grid)
        assert result[2, 2, 24] == 8.0

    def test_corner_cell_max_3_ruins(self):
        grid = _make_grid(3, 3, fill=3)  # all ruins
        _set(grid, 0, 0, 11)  # corner cell with 3 ruin neighbors
        result = extract_features(grid)
        assert result[0, 0, 24] == 3.0

    def test_ruin_cell_counts_adjacent_ruins(self):
        # A ruin itself should still count its ruin neighbors
        grid = _make_grid(5, 5, fill=11)
        _set(grid, 2, 2, 3)  # ruin at center
        _set(grid, 2, 3, 3)  # ruin to the right
        result = extract_features(grid)
        assert result[2, 2, 24] == 1.0


def _make_weights(rng=None):
    """Return a minimal set of valid MLP weights for testing."""
    if rng is None:
        rng = np.random.default_rng(42)
    return {
        "fc1_w": rng.standard_normal((128, 28)).astype(np.float32) * 0.1,
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": rng.standard_normal((64, 128)).astype(np.float32) * 0.1,
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": rng.standard_normal((32, 64)).astype(np.float32) * 0.1,
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": rng.standard_normal((6, 32)).astype(np.float32) * 0.1,
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(28, dtype=np.float32),
        "feat_std": np.ones(28, dtype=np.float32),
    }


class TestEnsembleForward:
    """Tests for numpy_forward_ensemble."""

    def test_ensemble_averages_snapshots(self):
        """Ensemble output equals mean of individual forwards."""
        rng = np.random.default_rng(0)
        features = rng.standard_normal((5, 5, 28)).astype(np.float32)
        w1 = _make_weights(np.random.default_rng(1))
        w2 = _make_weights(np.random.default_rng(2))
        w3 = _make_weights(np.random.default_rng(3))
        snapshot_list = [w1, w2, w3]

        result = numpy_forward_ensemble(features, snapshot_list)
        expected = np.mean([numpy_forward(features, w) for w in snapshot_list], axis=0)
        np.testing.assert_allclose(result, expected, atol=1e-10,
            err_msg="Ensemble must equal mean of individual numpy_forward outputs")

    def test_ensemble_sums_to_one(self):
        """Ensemble output sums to 1 per cell."""
        rng = np.random.default_rng(7)
        features = rng.standard_normal((4, 6, 28)).astype(np.float32)
        w1 = _make_weights(np.random.default_rng(10))
        w2 = _make_weights(np.random.default_rng(11))
        result = numpy_forward_ensemble(features, [w1, w2])
        sums = result.sum(axis=2)
        np.testing.assert_allclose(sums, 1.0, atol=1e-5,
            err_msg="Ensemble probabilities must sum to 1 per cell")

    def test_ensemble_single_snapshot_matches_forward(self):
        """1-snapshot ensemble equals plain numpy_forward."""
        rng = np.random.default_rng(99)
        features = rng.standard_normal((3, 3, 28)).astype(np.float32)
        w = _make_weights(np.random.default_rng(5))
        result_ensemble = numpy_forward_ensemble(features, [w])
        result_forward = numpy_forward(features, w)
        np.testing.assert_allclose(result_ensemble, result_forward, atol=1e-10,
            err_msg="Single-snapshot ensemble must match numpy_forward exactly")


def test_numpy_forward_shape():
    """Forward pass produces H×W×6 with valid probabilities."""
    rng = np.random.default_rng(42)
    weights = {
        "fc1_w": rng.standard_normal((128, 28)).astype(np.float32) * 0.1,
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": rng.standard_normal((64, 128)).astype(np.float32) * 0.1,
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": rng.standard_normal((32, 64)).astype(np.float32) * 0.1,
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": rng.standard_normal((6, 32)).astype(np.float32) * 0.1,
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(28, dtype=np.float32),
        "feat_std": np.ones(28, dtype=np.float32),
    }
    features = rng.standard_normal((5, 5, 28)).astype(np.float32)
    preds = numpy_forward(features, weights)
    assert preds.shape == (5, 5, 6)
    sums = preds.sum(axis=2)
    np.testing.assert_allclose(sums, 1.0, atol=1e-5)
    assert (preds >= 0).all()


def test_save_load_model_roundtrip(tmp_path):
    """Weights survive save/load roundtrip."""
    weights = {
        "fc1_w": np.ones((128, 28), dtype=np.float32),
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": np.ones((64, 128), dtype=np.float32),
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": np.ones((32, 64), dtype=np.float32),
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": np.ones((6, 32), dtype=np.float32),
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(28, dtype=np.float32),
        "feat_std": np.ones(28, dtype=np.float32),
    }
    path = str(tmp_path / "test_weights.npz")
    save_model(weights, path)
    loaded = load_model(path)
    for key in weights:
        np.testing.assert_array_equal(weights[key], loaded[key])
