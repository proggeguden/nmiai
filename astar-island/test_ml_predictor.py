"""Unit tests for ml_predictor.extract_features().

Run with: pytest test_ml_predictor.py -v
"""
import numpy as np
import pytest

from ml_predictor import extract_features, NUM_FEATURES, FEATURE_NAMES, RATE_KEYS, numpy_forward, save_model, load_model


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
    """test_extract_features_shape: returns H×W×18 float32 array."""

    def test_shape(self):
        grid = _make_grid(6, 8)
        result = extract_features(grid)
        assert result.shape == (6, 8, 20), f"Expected (6,8,20), got {result.shape}"

    def test_dtype(self):
        grid = _make_grid(4, 4)
        result = extract_features(grid)
        assert result.dtype == np.float32, f"Expected float32, got {result.dtype}"

    def test_num_features_constant(self):
        assert NUM_FEATURES == 20

    def test_feature_names_length(self):
        assert len(FEATURE_NAMES) == 20


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


def test_numpy_forward_shape():
    """Forward pass produces H×W×6 with valid probabilities."""
    rng = np.random.default_rng(42)
    weights = {
        "fc1_w": rng.standard_normal((128, 20)).astype(np.float32) * 0.1,
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": rng.standard_normal((64, 128)).astype(np.float32) * 0.1,
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": rng.standard_normal((32, 64)).astype(np.float32) * 0.1,
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": rng.standard_normal((6, 32)).astype(np.float32) * 0.1,
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(20, dtype=np.float32),
        "feat_std": np.ones(20, dtype=np.float32),
    }
    features = rng.standard_normal((5, 5, 20)).astype(np.float32)
    preds = numpy_forward(features, weights)
    assert preds.shape == (5, 5, 6)
    sums = preds.sum(axis=2)
    np.testing.assert_allclose(sums, 1.0, atol=1e-5)
    assert (preds >= 0).all()


def test_save_load_model_roundtrip(tmp_path):
    """Weights survive save/load roundtrip."""
    weights = {
        "fc1_w": np.ones((128, 20), dtype=np.float32),
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": np.ones((64, 128), dtype=np.float32),
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": np.ones((32, 64), dtype=np.float32),
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": np.ones((6, 32), dtype=np.float32),
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(20, dtype=np.float32),
        "feat_std": np.ones(20, dtype=np.float32),
    }
    path = str(tmp_path / "test_weights.npz")
    save_model(weights, path)
    loaded = load_model(path)
    for key in weights:
        np.testing.assert_array_equal(weights[key], loaded[key])
