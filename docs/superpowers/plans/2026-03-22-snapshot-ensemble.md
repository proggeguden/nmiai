# Snapshot Ensemble + Retrain on 20 Rounds

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce prediction variance by averaging 5 MLP snapshots trained with different random seeds, and retrain on all 20 completed rounds of GT data.

**Architecture:** Train N independent MLPs (same architecture, different torch seeds) → save all weight sets in a single `.npz` → at inference time, run each snapshot's forward pass and average the softmax outputs. The ensemble prediction is more calibrated because individual model errors are uncorrelated.

**Tech Stack:** PyTorch (training), NumPy (inference), existing `train_model.py` / `ml_predictor.py` / `predictor.py` pipeline.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `ml_predictor.py` | Modify | Add `numpy_forward_ensemble()`, update `save_model`/`load_model` for ensemble format |
| `train_model.py` | Modify | Add `--n-snapshots` flag, train N models with different seeds |
| `predictor.py` | Modify | Update `build_prediction_ml()` to call ensemble forward |
| `main.py` | Modify | Update weight loading to detect ensemble format |
| `test_backtest.py` | Modify | Pass ensemble weights through simulated-production path |
| `test_ml_predictor.py` | Modify | Add tests for ensemble forward + save/load |

---

### Task 1: Add ensemble inference to ml_predictor.py

**Files:**
- Modify: `ml_predictor.py:346-388` (numpy_forward, save_model, load_model)
- Test: `test_ml_predictor.py`

- [ ] **Step 1: Write failing test for `numpy_forward_ensemble`**

Add to `test_ml_predictor.py`:

```python
class TestEnsembleForward:
    """Tests for numpy_forward_ensemble averaging multiple snapshots."""

    def _make_random_weights(self, seed=0):
        """Create random weights dict matching MLP architecture."""
        rng = np.random.default_rng(seed)
        return {
            "fc1_w": rng.standard_normal((128, 28)).astype(np.float32),
            "fc1_b": rng.standard_normal(128).astype(np.float32),
            "fc2_w": rng.standard_normal((64, 128)).astype(np.float32),
            "fc2_b": rng.standard_normal(64).astype(np.float32),
            "fc3_w": rng.standard_normal((32, 64)).astype(np.float32),
            "fc3_b": rng.standard_normal(32).astype(np.float32),
            "fc4_w": rng.standard_normal((6, 32)).astype(np.float32),
            "fc4_b": rng.standard_normal(6).astype(np.float32),
            "feat_mean": rng.standard_normal(28).astype(np.float32),
            "feat_std": np.abs(rng.standard_normal(28)).astype(np.float32) + 0.1,
        }

    def test_ensemble_averages_snapshots(self):
        """Ensemble output is mean of individual snapshot outputs."""
        from ml_predictor import numpy_forward, numpy_forward_ensemble
        grid = _make_grid(3, 3)
        features = extract_features(grid)

        w1 = self._make_random_weights(seed=1)
        w2 = self._make_random_weights(seed=2)

        p1 = numpy_forward(features, w1)
        p2 = numpy_forward(features, w2)
        expected = (p1 + p2) / 2.0

        result = numpy_forward_ensemble(features, [w1, w2])
        np.testing.assert_allclose(result, expected, atol=1e-10)

    def test_ensemble_sums_to_one(self):
        """Ensemble output probabilities sum to 1 per cell."""
        from ml_predictor import numpy_forward_ensemble
        grid = _make_grid(4, 4)
        features = extract_features(grid)
        snapshots = [self._make_random_weights(seed=i) for i in range(3)]
        result = numpy_forward_ensemble(features, snapshots)
        sums = result.sum(axis=2)
        np.testing.assert_allclose(sums, 1.0, atol=1e-6)

    def test_ensemble_single_snapshot_matches_forward(self):
        """Ensemble with 1 snapshot equals numpy_forward."""
        from ml_predictor import numpy_forward, numpy_forward_ensemble
        grid = _make_grid(3, 3)
        features = extract_features(grid)
        w = self._make_random_weights(seed=42)
        single = numpy_forward(features, w)
        ensemble = numpy_forward_ensemble(features, [w])
        np.testing.assert_allclose(ensemble, single, atol=1e-10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_ml_predictor.py::TestEnsembleForward -v`
Expected: FAIL — `numpy_forward_ensemble` not defined

- [ ] **Step 3: Implement `numpy_forward_ensemble` in ml_predictor.py**

Add after `numpy_forward`:

```python
def numpy_forward_ensemble(features, snapshot_weights_list, temperature=None):
    """Average predictions from multiple MLP snapshots.

    Args:
        features: H×W×F float32 array
        snapshot_weights_list: list of weight dicts (one per snapshot)
        temperature: optional override temperature (applied to each snapshot)
    Returns:
        H×W×6 float64 probability array (mean of snapshot softmax outputs)
    """
    preds = []
    for weights in snapshot_weights_list:
        if temperature is not None:
            w = dict(weights)
            w["temperature"] = np.array([temperature], dtype=np.float64)
        else:
            w = weights
        preds.append(numpy_forward(features, w))
    return np.mean(preds, axis=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_ml_predictor.py::TestEnsembleForward -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add ml_predictor.py test_ml_predictor.py
git commit -m "feat(astar): add numpy_forward_ensemble for snapshot averaging"
```

---

### Task 2: Add ensemble save/load format

**Files:**
- Modify: `ml_predictor.py:381-388` (save_model, load_model)
- Test: `test_ml_predictor.py`

The ensemble format stores N snapshot weight sets in a single `.npz`. Keys are prefixed: `snap0_fc1_w`, `snap0_fc1_b`, ..., `snap1_fc1_w`, etc. Metadata key `n_snapshots` stores the count. Backward-compatible: files without `n_snapshots` load as single-snapshot.

- [ ] **Step 1: Write failing test for ensemble save/load**

Add to `test_ml_predictor.py`:

```python
class TestEnsembleSaveLoad:
    """Tests for saving/loading ensemble weight files."""

    def _make_random_weights(self, seed=0):
        rng = np.random.default_rng(seed)
        return {
            "fc1_w": rng.standard_normal((128, 28)).astype(np.float32),
            "fc1_b": rng.standard_normal(128).astype(np.float32),
            "fc2_w": rng.standard_normal((64, 128)).astype(np.float32),
            "fc2_b": rng.standard_normal(64).astype(np.float32),
            "fc3_w": rng.standard_normal((32, 64)).astype(np.float32),
            "fc3_b": rng.standard_normal(32).astype(np.float32),
            "fc4_w": rng.standard_normal((6, 32)).astype(np.float32),
            "fc4_b": rng.standard_normal(6).astype(np.float32),
            "feat_mean": rng.standard_normal(28).astype(np.float32),
            "feat_std": np.abs(rng.standard_normal(28)).astype(np.float32) + 0.1,
        }

    def test_save_load_ensemble(self, tmp_path):
        from ml_predictor import save_ensemble, load_ensemble
        snapshots = [self._make_random_weights(seed=i) for i in range(3)]
        path = str(tmp_path / "ensemble.npz")
        save_ensemble(snapshots, path)
        loaded = load_ensemble(path)
        assert len(loaded) == 3
        for i, (orig, loaded_w) in enumerate(zip(snapshots, loaded)):
            for key in orig:
                np.testing.assert_array_equal(loaded_w[key], orig[key],
                    err_msg=f"Snapshot {i} key {key} mismatch")

    def test_load_model_backward_compat(self, tmp_path):
        """load_ensemble on a single-model file returns list of 1."""
        from ml_predictor import save_model, load_ensemble
        w = self._make_random_weights(seed=42)
        path = str(tmp_path / "single.npz")
        save_model(w, path)
        loaded = load_ensemble(path)
        assert len(loaded) == 1
        for key in w:
            np.testing.assert_array_equal(loaded[0][key], w[key])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_ml_predictor.py::TestEnsembleSaveLoad -v`
Expected: FAIL — `save_ensemble` / `load_ensemble` not defined

- [ ] **Step 3: Implement `save_ensemble` and `load_ensemble`**

Add to `ml_predictor.py` after existing `save_model`/`load_model`:

```python
def save_ensemble(snapshot_weights_list, path):
    """Save N snapshot weight sets into a single .npz file.

    Format: snap{i}_{key} for each snapshot, plus n_snapshots metadata.
    """
    combined = {"n_snapshots": np.array([len(snapshot_weights_list)])}
    for i, weights in enumerate(snapshot_weights_list):
        for key, val in weights.items():
            combined[f"snap{i}_{key}"] = val
    np.savez(path, **combined)


def load_ensemble(path):
    """Load ensemble weights from .npz file.

    Returns list of weight dicts. Backward-compatible with single-model files
    (returns a list of 1 weight dict).
    """
    data = np.load(path)
    keys = list(data.files)

    if "n_snapshots" not in keys:
        # Backward compat: single-model file
        return [{key: data[key] for key in keys}]

    n = int(data["n_snapshots"].item())
    snapshots = []
    for i in range(n):
        prefix = f"snap{i}_"
        w = {k[len(prefix):]: data[k] for k in keys if k.startswith(prefix)}
        snapshots.append(w)
    return snapshots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_ml_predictor.py::TestEnsembleSaveLoad -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add ml_predictor.py test_ml_predictor.py
git commit -m "feat(astar): add ensemble save/load with backward compat"
```

---

### Task 3: Update train_model.py to train N snapshots

**Files:**
- Modify: `train_model.py:470-506` (main function, argparse, training loop)

- [ ] **Step 1: Add `--n-snapshots` argument and ensemble training loop**

In the `main()` function, add argument:
```python
parser.add_argument("--n-snapshots", type=int, default=1,
                    help="Number of ensemble snapshots to train (different seeds)")
```

Replace the final model training block (the `else` branch of `if args.cv`) with:

```python
    else:
        n_snap = args.n_snapshots
        if n_snap > 1:
            print(f"\nTraining {n_snap}-snapshot ensemble on {len(X)} samples...")
            from ml_predictor import save_ensemble
            snapshots = []
            for snap_idx in range(n_snap):
                print(f"\n--- Snapshot {snap_idx + 1}/{n_snap} (seed offset={snap_idx * 7}) ---")
                # Set different torch seed for each snapshot
                import torch
                torch.manual_seed(42 + snap_idx * 7)
                weights = train_model(X, Y, epochs=args.epochs, lr=args.lr, verbose=True)
                snapshots.append(weights)
            save_ensemble(snapshots, args.output)
            print(f"\nEnsemble ({n_snap} snapshots) saved to {args.output}")
        else:
            print(f"\nTraining final model on all {len(X)} samples...")
            weights = train_model(X, Y, epochs=args.epochs, lr=args.lr, verbose=True)
            save_model(weights, args.output)
            print(f"\nModel saved to {args.output}")
        print(f"Weights file size: {os.path.getsize(args.output) / 1024:.1f} KB")
```

- [ ] **Step 2: Verify the script parses args correctly**

Run: `python3 train_model.py --help`
Expected: Shows `--n-snapshots` in help output

- [ ] **Step 3: Commit**

```bash
git add train_model.py
git commit -m "feat(astar): add --n-snapshots flag for ensemble training"
```

---

### Task 4: Wire ensemble into production pipeline

**Files:**
- Modify: `main.py:29-37` (weight loading)
- Modify: `predictor.py:1397-1513` (build_prediction_ml)
- Modify: `test_backtest.py:670-674` (weight loading)

- [ ] **Step 1: Update `main.py` to load ensemble weights**

Replace the ML model loading block (lines 29-37):

```python
# ML model: load weights at startup if available
ML_WEIGHTS = None  # list of weight dicts (ensemble) or None
ML_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "model_weights.npz")
if os.path.exists(ML_WEIGHTS_PATH):
    from ml_predictor import load_ensemble
    ML_WEIGHTS = load_ensemble(ML_WEIGHTS_PATH)
    print(f"ML model loaded from {ML_WEIGHTS_PATH} ({len(ML_WEIGHTS)} snapshot(s))")
else:
    print(f"ML model not found at {ML_WEIGHTS_PATH}, using bucket model")
```

Update the call to `build_prediction_ml` (line ~191) — change `ml_weights=ML_WEIGHTS` parameter name to `ml_snapshots=ML_WEIGHTS`.

- [ ] **Step 2: Update `build_prediction_ml` in predictor.py to accept ensemble**

Change function signature:
```python
def build_prediction_ml(height, width, initial_grid, observations,
                        ml_snapshots, rates=None,
                        spatial_obs=None, skip_blending=False):
```

Replace the ML forward pass section (lines 1423-1436):

```python
    from ml_predictor import extract_features, numpy_forward_ensemble

    # Step 1: Base predictions from ML ensemble
    survival = rates.get("survival", 0.5) if rates else 0.5

    # Survival-conditional temperature: sharpen on harsh rounds (surv < 10%)
    temperature = 0.85 if survival < 0.10 else None

    features = extract_features(initial_grid, rates=rates)
    predictions = numpy_forward_ensemble(features, ml_snapshots, temperature=temperature)
```

- [ ] **Step 3: Update `test_backtest.py` to load ensemble**

Replace line ~672-673:

```python
            if args.model == "ml":
                from ml_predictor import load_ensemble
                ml_weights = load_ensemble(args.ml_weights)
                print(f"Using ML ensemble from {args.ml_weights} ({len(ml_weights)} snapshot(s))")
```

And update the call to `build_prediction_ml` at line ~545 to use `ml_snapshots=ml_weights`.

- [ ] **Step 4: Run offline tests to verify nothing is broken**

Run: `pytest test_predictor_unit.py test_predictor_integration.py test_ml_predictor.py -x --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add main.py predictor.py test_backtest.py
git commit -m "feat(astar): wire ensemble inference into production pipeline"
```

---

### Task 5: Retrain ensemble on 20 rounds and validate

**Files:**
- Modify: `model_weights.npz` (overwritten with ensemble weights)

- [ ] **Step 1: Archive current weights**

```bash
cp model_weights.npz model_weights_single_20rounds.npz
```

- [ ] **Step 2: Rebuild training data with R20 and train 5-snapshot ensemble**

```bash
rm -f training_data.npz
python3 train_model.py --rebuild-data --augmentations 10 --n-snapshots 5 --output model_weights.npz
```

Expected: ~1.17M training samples (20 rounds × 5 seeds × 10 augmentations), 5 snapshots trained, file ~290KB.

- [ ] **Step 3: Run simulated-production backtest**

```bash
python3 test_backtest.py --simulate-production --sim-runs 3 --model ml --output sim_ensemble.json
```

Expected: SimProd avg KL should improve vs. baseline 0.0473 (target: < 0.046).

- [ ] **Step 4: Compare to single-model baseline**

```bash
python3 -c "
import json
with open('sim_ensemble.json') as f:
    ens = json.load(f)
print(f'Ensemble SimProd avg KL: {ens[\"overall\"][\"sim_prod_avg_kl\"]:.4f}')
print(f'Baseline (single model): 0.0473')
delta = (ens['overall']['sim_prod_avg_kl'] - 0.0473) / 0.0473 * 100
print(f'Change: {delta:+.1f}%')
"
```

- [ ] **Step 5: If improved, commit. If regressed, revert to archived weights.**

```bash
# If improved:
git add model_weights.npz
git commit -m "feat(astar): retrain 5-snapshot ensemble on 20 rounds — SimProd KL X.XXXX"

# If regressed:
cp model_weights_single_20rounds.npz model_weights.npz
```

---

### Task 6: Update documentation

**Files:**
- Modify: `CLAUDE.md` (prediction strategy section)
- Modify: `PLAN.md` (add ensemble findings)

- [ ] **Step 1: Update CLAUDE.md prediction strategy**

Add to the prediction strategy section:
- Ensemble architecture: 5 snapshots, averaged softmax
- Retrained on 20 rounds
- New SimProd KL result

- [ ] **Step 2: Update PLAN.md with findings**

Add a new section documenting:
- Ensemble implementation details
- Backtest results (improvement %)
- Updated SimProd baseline number

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md PLAN.md
git commit -m "docs(astar): update for 5-snapshot ensemble on 20 rounds"
```
