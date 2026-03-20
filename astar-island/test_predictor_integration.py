"""Integration tests for predictor.py — end-to-end pipeline, synthetic data, no network.

Run: pytest test_predictor_integration.py -v  (< 3s)
"""

import numpy as np
import pytest

from predictor import (
    build_prediction,
    learn_transition_model,
    learn_spatial_transition_model,
    compute_feature_map,
    validate_predictions,
    terrain_code_to_class,
    score_predictions,
    apply_floor,
    NUM_CLASSES,
    CLASS_NAMES,
    PROB_FLOOR,
    STATIC_CODES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_grid(H, W, fill=11, overrides=None):
    """Create an H×W grid filled with `fill`, with optional cell overrides."""
    grid = [[fill] * W for _ in range(H)]
    if overrides:
        for (r, c), code in overrides.items():
            grid[r][c] = code
    return grid


def make_observation(seed_idx, vp_x, vp_y, grid):
    """Wrap a grid into an observation dict."""
    return {
        "seed_index": seed_idx,
        "viewport": {"x": vp_x, "y": vp_y},
        "grid": grid,
    }


def make_gt(H, W, initial_grid, class_map=None):
    """Create synthetic ground truth from a terrain mapping.

    class_map: dict of terrain_code → class_index. Defaults to one-hot on terrain_code_to_class.
    """
    gt = np.zeros((H, W, NUM_CLASSES), dtype=np.float64)
    for r in range(H):
        for c in range(W):
            code = initial_grid[r][c]
            if class_map and code in class_map:
                cls = class_map[code]
            else:
                cls = terrain_code_to_class(code)
            gt[r, c, cls] = 1.0
    return gt


# ---------------------------------------------------------------------------
# Scenario Fixtures
# ---------------------------------------------------------------------------

def _build_mild_scenario():
    """10×10, ocean border, 4 settlements center, forest, plains, ~80% survival."""
    overrides = {}
    # Ocean border
    for i in range(10):
        overrides[(0, i)] = 10
        overrides[(9, i)] = 10
        overrides[(i, 0)] = 10
        overrides[(i, 9)] = 10
    # 4 settlements in center
    overrides[(3, 4)] = 1
    overrides[(4, 4)] = 1
    overrides[(5, 4)] = 1
    overrides[(4, 5)] = 2  # port (but no ocean adj — that's fine for synthetic)
    # Forest patches
    overrides[(3, 3)] = 4
    overrides[(4, 3)] = 4
    overrides[(5, 3)] = 4
    overrides[(6, 4)] = 4
    grid = make_grid(10, 10, fill=11, overrides=overrides)
    return grid


def _build_harsh_scenario():
    """Same layout as mild, but observations show ~20% survival."""
    return _build_mild_scenario()  # same initial, different observations


def _build_no_settlements():
    """10×10 plains+forest, no settlements."""
    overrides = {}
    for r in range(10):
        for c in range(10):
            if (r + c) % 3 == 0:
                overrides[(r, c)] = 4  # forest
    return make_grid(10, 10, fill=11, overrides=overrides)


def _build_all_static():
    """8×8 ocean+mountain only."""
    overrides = {}
    for r in range(8):
        for c in range(8):
            if r in (3, 4) and c in (3, 4):
                overrides[(r, c)] = 5  # mountain
    return make_grid(8, 8, fill=10, overrides=overrides)


def _build_coastal_dense():
    """10×10, ocean on left, settlements along coast."""
    overrides = {}
    for r in range(10):
        overrides[(r, 0)] = 10
        overrides[(r, 1)] = 10
    # Settlements along coast (column 2)
    for r in range(2, 8):
        overrides[(r, 2)] = 1
    overrides[(3, 2)] = 2  # one port
    overrides[(5, 2)] = 2  # another port
    # Some forest inland
    for r in range(3, 7):
        overrides[(r, 5)] = 4
    return make_grid(10, 10, fill=11, overrides=overrides)


@pytest.fixture
def mild_grid():
    return _build_mild_scenario()


@pytest.fixture
def harsh_grid():
    return _build_harsh_scenario()


@pytest.fixture
def no_settle_grid():
    return _build_no_settlements()


@pytest.fixture
def static_grid():
    return _build_all_static()


@pytest.fixture
def coastal_grid():
    return _build_coastal_dense()


ALL_GRIDS = {
    "mild": _build_mild_scenario,
    "harsh": _build_harsh_scenario,
    "no_settlements": _build_no_settlements,
    "all_static": _build_all_static,
    "coastal_dense": _build_coastal_dense,
}


# ---------------------------------------------------------------------------
# Helpers for building models from synthetic observations
# ---------------------------------------------------------------------------

def _mild_observations(grid, survival_fraction=0.8):
    """Simulate mild observations: settlements mostly survive."""
    H, W = len(grid), len(grid[0])
    obs = []
    for trial in range(5):
        result = []
        for r in range(H):
            row = []
            for c in range(W):
                code = grid[r][c]
                if code in STATIC_CODES:
                    row.append(code)
                elif code in (1, 2):
                    # 80% survive, 20% become ruin
                    if (r * 7 + c * 13 + trial * 3) % 10 < int(survival_fraction * 10):
                        row.append(code)
                    else:
                        row.append(3)  # ruin
                elif code == 4:
                    row.append(4)  # forest stays
                else:
                    row.append(code)  # plains stays
            result.append(row)
        obs.append(make_observation(0, 0, 0, result))
    return obs


def _harsh_observations(grid):
    """Simulate harsh observations: only 20% settlements survive."""
    return _mild_observations(grid, survival_fraction=0.2)


# ===================================================================
# Property tests — always hold, every scenario
# ===================================================================

class TestPropertyTests:
    @pytest.mark.parametrize("name,builder", list(ALL_GRIDS.items()))
    def test_predictions_sum_to_one(self, name, builder):
        grid = builder()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        sums = pred.sum(axis=2)
        np.testing.assert_allclose(sums, 1.0, atol=1e-4)

    @pytest.mark.parametrize("name,builder", list(ALL_GRIDS.items()))
    def test_predictions_above_floor(self, name, builder):
        grid = builder()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        assert (pred >= PROB_FLOOR - 1e-6).all()

    @pytest.mark.parametrize("name,builder", list(ALL_GRIDS.items()))
    def test_predictions_correct_shape(self, name, builder):
        grid = builder()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        assert pred.shape == (H, W, NUM_CLASSES)

    def test_static_cells_near_deterministic(self):
        grid = _build_all_static()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        for r in range(H):
            for c in range(W):
                code = grid[r][c]
                if code == 10:  # Ocean → Empty
                    assert pred[r, c, 0] >= 0.93
                elif code == 5:  # Mountain → Mountain
                    assert pred[r, c, 5] >= 0.93


# ===================================================================
# Relative ordering tests
# ===================================================================

class TestRelativeOrdering:
    def test_harsh_vs_mild_settlement_survival(self):
        grid = _build_mild_scenario()
        H, W = len(grid), len(grid[0])

        mild_obs = _mild_observations(grid, survival_fraction=0.8)
        harsh_obs = _harsh_observations(grid)

        _, mild_spatial = learn_spatial_transition_model([grid], mild_obs)
        _, harsh_spatial = learn_spatial_transition_model([grid], harsh_obs)

        mild_pred = build_prediction(H, W, grid, mild_obs, spatial_model=mild_spatial)
        harsh_pred = build_prediction(H, W, grid, harsh_obs, spatial_model=harsh_spatial)

        # Settlement cells: P(Settlement+Port) should be lower for harsh
        mild_sp_sum = 0
        harsh_sp_sum = 0
        count = 0
        for r in range(H):
            for c in range(W):
                if grid[r][c] in (1, 2):
                    mild_sp_sum += mild_pred[r, c, 1] + mild_pred[r, c, 2]
                    harsh_sp_sum += harsh_pred[r, c, 1] + harsh_pred[r, c, 2]
                    count += 1
        if count > 0:
            assert harsh_sp_sum / count < mild_sp_sum / count

    def test_near_vs_far_settlement_probability(self):
        grid = _build_mild_scenario()
        H, W = len(grid), len(grid[0])
        obs = _mild_observations(grid)
        gm, sm = learn_spatial_transition_model([grid], obs)
        pred = build_prediction(H, W, grid, obs, transition_model=gm, spatial_model=sm)

        from predictor import _precompute_settlement_distances
        dist = _precompute_settlement_distances(grid)

        near_p_sett = []
        far_p_sett = []
        for r in range(H):
            for c in range(W):
                if grid[r][c] == 11:  # Plains only
                    d = dist[r][c]
                    if d <= 2:
                        near_p_sett.append(pred[r, c, 1])
                    elif d >= 5:
                        far_p_sett.append(pred[r, c, 1])

        if near_p_sett and far_p_sett:
            assert np.mean(near_p_sett) > np.mean(far_p_sett)

    def test_coastal_port_boost(self):
        grid = _build_coastal_dense()
        H, W = len(grid), len(grid[0])
        obs = _mild_observations(grid)
        gm, sm = learn_spatial_transition_model([grid], obs)
        pred = build_prediction(H, W, grid, obs, transition_model=gm, spatial_model=sm)

        from predictor import _precompute_settlement_distances
        dist = _precompute_settlement_distances(grid)

        # Check coastal cells near settlements have minimum port probability
        for r in range(H):
            for c in range(W):
                if grid[r][c] not in STATIC_CODES and dist[r][c] <= 3:
                    # Check if coastal
                    is_coastal = any(
                        0 <= r + dr < H and 0 <= c + dc < W
                        and grid[r + dr][c + dc] == 10
                        for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                        if (dr, dc) != (0, 0)
                    )
                    if is_coastal:
                        assert pred[r, c, 2] >= PROB_FLOOR  # port boost ensures above floor

    def test_spatial_vs_global_on_divergent_terrain(self):
        """Spatial model should beat global on a scenario with terrain-dependent outcomes."""
        grid = _build_coastal_dense()
        H, W = len(grid), len(grid[0])
        obs = _mild_observations(grid)
        gm, sm = learn_spatial_transition_model([grid], obs)

        # Create GT where settlements survive
        gt = np.zeros((H, W, NUM_CLASSES))
        for r in range(H):
            for c in range(W):
                code = grid[r][c]
                gt[r, c, terrain_code_to_class(code)] = 1.0

        pred_global = build_prediction(H, W, grid, obs, transition_model=gm)
        pred_spatial = build_prediction(H, W, grid, obs, transition_model=gm, spatial_model=sm)

        kl_global, _ = score_predictions(pred_global, gt)
        kl_spatial, _ = score_predictions(pred_spatial, gt)

        # Spatial should be at least as good (lower KL)
        assert kl_spatial <= kl_global + 0.001  # small tolerance


# ===================================================================
# Edge case tests
# ===================================================================

class TestEdgeCases:
    def test_no_observations_with_spatial_model(self):
        """With model but no observations, predictions should still be model-based."""
        grid = _build_mild_scenario()
        H, W = len(grid), len(grid[0])
        obs = _mild_observations(grid)
        gm, sm = learn_spatial_transition_model([grid], obs)
        # Build prediction with model but NO observations
        pred = build_prediction(H, W, grid, [], transition_model=gm, spatial_model=sm)
        # Should not be uniform — model should apply
        for r in range(H):
            for c in range(W):
                if grid[r][c] not in STATIC_CODES:
                    assert not np.allclose(pred[r, c], 1/NUM_CLASSES, atol=0.01)

    def test_no_model_no_observations_one_hot(self):
        """Without model or observations, should be one-hot on initial class (after floor)."""
        grid = _build_mild_scenario()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        for r in range(H):
            for c in range(W):
                code = grid[r][c]
                cls = terrain_code_to_class(code)
                # The initial class should dominate
                assert pred[r, c, cls] > 0.9

    def test_no_settlements_valid(self):
        grid = _build_no_settlements()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        assert pred.shape == (H, W, NUM_CLASSES)
        sums = pred.sum(axis=2)
        np.testing.assert_allclose(sums, 1.0, atol=1e-4)

    def test_all_static_near_zero_entropy(self):
        grid = _build_all_static()
        H, W = len(grid), len(grid[0])
        pred = build_prediction(H, W, grid, [])
        # Entropy should be very low for static cells
        for r in range(H):
            for c in range(W):
                entropy = -np.sum(pred[r, c] * np.log(pred[r, c] + 1e-10))
                assert entropy < 0.30  # low entropy (floor adds some)


# ===================================================================
# Regression baseline tests
# ===================================================================

class TestRegressionBaseline:
    def test_kl_on_known_synthetic(self):
        """Hardcoded synthetic scenario with known GT — KL must stay below threshold."""
        grid = _build_mild_scenario()
        H, W = len(grid), len(grid[0])
        obs = _mild_observations(grid)
        gm, sm = learn_spatial_transition_model([grid], obs)
        pred = build_prediction(H, W, grid, obs, transition_model=gm, spatial_model=sm)

        # GT: same as mild observations (deterministic for known cells)
        gt = np.zeros((H, W, NUM_CLASSES))
        for r in range(H):
            for c in range(W):
                code = grid[r][c]
                gt[r, c, terrain_code_to_class(code)] = 1.0
        gt = apply_floor(gt)

        kl, _ = score_predictions(pred, gt)
        # Threshold — generous initial bound; tighten as model improves
        assert kl < 0.5, f"KL {kl:.4f} exceeds threshold 0.5"

    def test_score_predictions_hand_computed(self):
        """Verify score_predictions against hand-computed KL on a 3×3 case."""
        # GT: uniform [1/6] * 6 for all cells
        gt = np.full((1, 1, 6), 1/6)
        # Pred: same → KL should be 0
        pred = np.full((1, 1, 6), 1/6)
        kl, dyn = score_predictions(pred, gt)
        assert abs(kl) < 1e-6
        assert dyn == 1  # uniform has entropy > 0.01

    def test_score_predictions_asymmetric(self):
        """KL(gt || pred) should increase when pred diverges from gt."""
        gt = np.zeros((1, 1, 6))
        gt[0, 0] = [0.5, 0.3, 0.1, 0.05, 0.03, 0.02]
        pred_good = gt.copy()
        pred_bad = np.full((1, 1, 6), 1/6)

        kl_good, _ = score_predictions(pred_good, gt)
        kl_bad, _ = score_predictions(pred_bad, gt)
        assert kl_good < kl_bad
