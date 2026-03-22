# ML Feature Engineering + Retrain Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `distance_to_coast` and `adj_mountain_count` features to the ML predictor, retrain on 18 rounds of GT data, and validate with sim-prod backtest.

**Architecture:** Extend the 18-feature vector to 20 features by adding two spatial features that directly address port under-prediction (distance_to_coast) and expansion calibration (adj_mountain_count). Retrain the same MLP architecture (Input(20) → 128 → 64 → 32 → Softmax(6)) on rebuilt training data including R17+R18 GT. Validate improvement with simulated-production backtest (rho=0.964 with actual production scores).

**Tech Stack:** Python, NumPy, PyTorch (training only), pytest

**Validation rule:** ALL changes must pass sim-prod backtest. If the new model regresses, we keep the old weights.

---

### File Structure

| File | Action | Purpose |
|------|--------|---------|
| `ml_predictor.py` | Modify | Add 2 features, update NUM_FEATURES 18→20, update FEATURE_NAMES |
| `test_ml_predictor.py` | Modify | Add tests for new features |
| `train_model.py` | Modify | Update weight dimensions (18→20 in numpy_forward calls) |
| `predictor.py` | No change | BFS helpers already exist, build_prediction_ml uses ml_predictor |
| `model_weights.npz` | Replace | New weights from retrained model |
| `training_data.npz` | Replace | Rebuilt with 18 rounds + new features |

---

### Task 1: Add `distance_to_coast` feature to ml_predictor.py

**Files:**
- Modify: `astar-island/ml_predictor.py`
- Modify: `astar-island/test_ml_predictor.py`

**Why:** R18 analysis showed coastal Plains cells near settlements have GT Port=20-35% but model predicts <1%. The model has `is_coastal` (binary) but no continuous distance — it can't distinguish "right on coast" from "1 cell inland". `distance_to_coast` (BFS from ocean cells, capped at 20) gives the model a gradient to learn port formation probability.

- [ ] **Step 1: Write failing tests for distance_to_coast**

In `test_ml_predictor.py`, add:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jakobtiller/Desktop/nmiai/code/nmiai/.claude/worktrees/astar-island/astar-island && pytest test_ml_predictor.py::TestDistanceToCoast -v`
Expected: FAIL (index 18 out of bounds or wrong value)

- [ ] **Step 3: Implement distance_to_coast**

In `ml_predictor.py`:
1. Update `NUM_FEATURES = 20`
2. Add `"dist_to_coast"` to `FEATURE_NAMES` at index 18
3. Add `_precompute_coast_distances()` function (BFS from all ocean cells, identical pattern to `_precompute_settlement_distances` but seeds are ocean cells code=10)
4. Call it in `extract_features()` and pass to `_compute_cell_features()`
5. In `_compute_cell_features()`: `vec[18] = float(min(coast_dists[r][c], _DIST_CAP))`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_ml_predictor.py::TestDistanceToCoast -v`
Expected: PASS

- [ ] **Step 5: Verify existing tests still pass with updated feature count**

Run: `pytest test_ml_predictor.py -v`
Expected: Some existing tests FAIL because they hardcode NUM_FEATURES=18. Fix them:
- `TestExtractFeaturesShape.test_num_features_constant` → update to 20
- `TestExtractFeaturesShape.test_shape` → update expected shape to (6, 8, 20)
- `test_numpy_forward_shape` → update weight dimensions to 20
- `test_save_load_model_roundtrip` → update weight dimensions to 20

- [ ] **Step 6: Run full test suite**

Run: `pytest test_ml_predictor.py test_predictor_unit.py test_predictor_integration.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add ml_predictor.py test_ml_predictor.py
git commit -m "feat(astar): add distance_to_coast feature (index 18) to ML predictor"
```

---

### Task 2: Add `adj_mountain_count` feature to ml_predictor.py

**Files:**
- Modify: `astar-island/ml_predictor.py`
- Modify: `astar-island/test_ml_predictor.py`

**Why:** Mountains block expansion and reduce food availability for adjacent settlements. Currently the model has no mountain awareness — it treats mountain-adjacent Plains the same as open Plains. This feature helps calibrate expansion predictions.

- [ ] **Step 1: Write failing tests for adj_mountain_count**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_ml_predictor.py::TestAdjMountainCount -v`
Expected: FAIL

- [ ] **Step 3: Implement adj_mountain_count**

In `ml_predictor.py` `_compute_cell_features()`:
1. Add `"adj_mountain_count"` to `FEATURE_NAMES` at index 19
2. Add mountain counting in the existing neighbor loop: `if n == 5: adj_mountain += 1`
3. Set `vec[19] = float(adj_mountain)`

- [ ] **Step 4: Run all ml_predictor tests**

Run: `pytest test_ml_predictor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full offline test suite**

Run: `pytest test_ml_predictor.py test_predictor_unit.py test_predictor_integration.py -x --tb=short`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ml_predictor.py test_ml_predictor.py
git commit -m "feat(astar): add adj_mountain_count feature (index 19) to ML predictor"
```

---

### Task 3: Update numpy_forward and weight dimensions for 20 features

**Files:**
- Modify: `astar-island/ml_predictor.py` (docstring only — numpy_forward is already generic on F)
- Modify: `astar-island/train_model.py` (TerrainMLP n_features default)

**Why:** `numpy_forward` reads F from `features.shape` so it's already dimension-agnostic. But `train_model.py`'s `TerrainMLP` defaults to `n_features=18` — must update to 20. Also update docstring in `numpy_forward`.

- [ ] **Step 1: Update TerrainMLP default**

In `train_model.py` line ~303: change `n_features=18` to `n_features=20`.

- [ ] **Step 2: Update numpy_forward docstring**

In `ml_predictor.py` line ~185: change `Input(18)` to `Input(20)` in docstring.

- [ ] **Step 3: Run tests**

Run: `pytest test_ml_predictor.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add ml_predictor.py train_model.py
git commit -m "chore(astar): update MLP dimensions 18→20 for new features"
```

---

### Task 4: Rebuild training data and retrain model

**Files:**
- Replace: `astar-island/training_data.npz` (rebuilt with 20 features, 18 rounds)
- Replace: `astar-island/model_weights.npz` (retrained)

**Why:** New features require rebuilding training data. Adding R17+R18 GT data gives the model more training examples including high-expansion rounds.

- [ ] **Step 1: Archive current weights**

```bash
cp model_weights.npz model_weights_v1_18feat.npz
```

- [ ] **Step 2: Delete cached training data to force rebuild**

```bash
rm -f training_data.npz
```

- [ ] **Step 3: Rebuild training data + retrain**

```bash
python3 train_model.py --rebuild-data --augmentations 10 --epochs 80 --output model_weights.npz
```

Expected: ~1M+ training examples (18 rounds × 5 seeds × ~5800 dynamic cells × 10 augmentations), model trains to convergence.

- [ ] **Step 4: Verify model file size is reasonable**

```bash
ls -la model_weights.npz
```

Expected: ~55-60KB (slightly larger than 54KB due to 2 extra input features).

- [ ] **Step 5: Commit new weights**

```bash
git add model_weights.npz
git commit -m "retrain ML model: 20 features, 18 rounds of GT data"
```

---

### Task 5: Validate with simulated-production backtest

**Files:**
- Output: `astar-island/sim_r18_new.json`

**Why:** This is the ONLY reliable validation gate. Oracle backtest has rho=0.750, sim-prod has rho=0.964 with actual production scores.

- [ ] **Step 1: Run sim-prod backtest**

```bash
python3 test_backtest.py --simulate-production --sim-runs 3 --output sim_r18_new.json
```

Expected: ~5 min. Check avg KL vs previous sim baseline of 0.0493.

- [ ] **Step 2: Compare results**

Read `sim_r18_new.json` and compare:
- Overall avg KL: must be ≤ 0.0493 (previous baseline)
- Per-round KL: check no severe regressions (>15% worse on any round)
- Specifically check R18 and other high-expansion rounds (R7, R12)

- [ ] **Step 3: If improved — update baseline**

```bash
cp sim_r18_new.json sim_baseline.json
```

- [ ] **Step 4: If regressed — rollback to archived weights**

```bash
cp model_weights_v1_18feat.npz model_weights.npz
```

Then investigate: was the regression from features or training data? Try retrain without new features but with R17+R18 data to isolate.

- [ ] **Step 5: Commit baseline update**

```bash
git add sim_baseline.json
git commit -m "update sim-prod baseline after feature+retrain improvement"
```

---

### Task 6: Update documentation

**Files:**
- Modify: `astar-island/CLAUDE.md`
- Modify: `astar-island/PLAN.md`

- [ ] **Step 1: Update CLAUDE.md**

Update the ML model section:
- Feature count: 18 → 20
- Add new features to the feature list description
- Update training data stats (18 rounds)

- [ ] **Step 2: Update PLAN.md**

Add findings section with:
- New feature names and rationale
- Sim-prod backtest results (before/after)
- Per-round comparison

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md PLAN.md
git commit -m "docs(astar): update ML model docs for 20-feature retrain"
```
