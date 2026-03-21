# ML Predictor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers-extended-cc:subagent-driven-development (if subagents available) or superpowers-extended-cc:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bucket-based spatial model with a PyTorch MLP trained on 92k GT cells, targeting 90+ raw score.

**Architecture:** Offline training script fetches GT data, extracts features, trains MLP with KL loss and noisy rate augmentation. Model weights exported as numpy arrays. Production inference uses numpy-only forward pass in ml_predictor.py, integrated into existing build_prediction() pipeline.

**Tech Stack:** PyTorch (training only), NumPy (inference), existing predictor.py helpers

**Spec:** `docs/superpowers/specs/2026-03-21-ml-predictor-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `ml_predictor.py` | Create | Feature extraction + numpy inference. Single-purpose: turn (initial_grid, rates) into H×W×6 predictions |
| `train_model.py` | Create | Offline training: fetch GT, build dataset, train PyTorch MLP, export weights, CV |
| `model_weights.npz` | Generated | Trained weights + normalization stats |
| `predictor.py` | Modify | Add `build_prediction_ml()` that uses ml_predictor, keep bucket model as fallback |
| `test_backtest.py` | Modify | Add `--model ml` flag to route through ML predictor |
| `test_ml_predictor.py` | Create | Unit tests for feature extraction and numpy forward pass |

---

### Task 1: Feature Extraction Module (ml_predictor.py)

**Files:**
- Create: `astar-island/ml_predictor.py`
- Create: `astar-island/test_ml_predictor.py`
- Read: `astar-island/predictor.py:65-215` (existing BFS/adjacency helpers)

- [ ] **Step 1: Write failing tests for extract_features()**

```python
# test_ml_predictor.py
import numpy as np
from ml_predictor import extract_features, FEATURE_NAMES

def test_extract_features_shape():
    """18 features per cell: 6 one-hot + 7 spatial + 5 rates."""
    grid = [[11, 4, 10], [1, 11, 11], [4, 11, 5]]
    rates = {"survival": 0.5, "expansion": 0.1, "port_formation": 0.05,
             "forest_reclamation": 0.2, "ruin": 0.3}
    features = extract_features(grid, rates)
    assert features.shape == (3, 3, 18)
    assert features.dtype == np.float32

def test_extract_features_onehot():
    """Settlement cell should have one-hot [0,1,0,0,0,0]."""
    grid = [[11, 11, 11], [11, 1, 11], [11, 11, 11]]
    rates = {"survival": 0.5, "expansion": 0.1, "port_formation": 0.05,
             "forest_reclamation": 0.2, "ruin": 0.3}
    features = extract_features(grid, rates)
    # Settlement (code 1) → class 1 → one-hot index 1
    assert features[1, 1, 1] == 1.0  # Settlement one-hot
    assert features[1, 1, 0] == 0.0  # Not Empty

def test_extract_features_distance_capped():
    """Distance to settlement capped at 20."""
    # No settlements → distance should be 20 (capped from 999)
    grid = [[11] * 5 for _ in range(5)]
    rates = {"survival": 0.5, "expansion": 0.1, "port_formation": 0.05,
             "forest_reclamation": 0.2, "ruin": 0.3}
    features = extract_features(grid, rates)
    assert features[0, 0, 6] == 20.0  # dist_to_settlement capped

def test_extract_features_rates_appended():
    """Round-level rates appear in last 5 features."""
    grid = [[1]]
    rates = {"survival": 0.5, "expansion": 0.1, "port_formation": 0.05,
             "forest_reclamation": 0.2, "ruin": 0.3}
    features = extract_features(grid, rates)
    assert features[0, 0, 13] == 0.5   # survival
    assert features[0, 0, 17] == 0.3   # ruin

def test_extract_features_none_rates():
    """None rates default to 0.5 (neutral)."""
    grid = [[1]]
    rates = {"survival": None, "expansion": None, "port_formation": None,
             "forest_reclamation": None, "ruin": None}
    features = extract_features(grid, rates)
    assert features[0, 0, 13] == 0.5  # default
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest test_ml_predictor.py -v`
Expected: ImportError (ml_predictor doesn't exist yet)

- [ ] **Step 3: Implement extract_features()**

```python
# ml_predictor.py
"""ML predictor for Astar Island — feature extraction and numpy inference."""

import numpy as np
from predictor import (
    _precompute_settlement_distances,
    _precompute_cluster_density,
    terrain_code_to_class,
    TERRAIN_TO_CLASS,
    STATIC_CODES,
    NUM_CLASSES,
)

# Feature order: 6 one-hot + 7 spatial + 5 round-level = 18 total
FEATURE_NAMES = [
    # One-hot (6)
    "is_empty", "is_settlement", "is_port", "is_ruin", "is_forest", "is_mountain",
    # Spatial (7)
    "dist_to_settlement", "is_coastal", "adj_forest_count", "adj_settlement_count",
    "adj_ocean_count", "is_clustered", "is_interior_forest",
    # Round-level (5)
    "survival_rate", "expansion_rate", "port_formation_rate",
    "forest_reclamation_rate", "ruin_rate",
]
NUM_FEATURES = len(FEATURE_NAMES)
RATE_KEYS = ["survival", "expansion", "port_formation", "forest_reclamation", "ruin"]
RATE_DEFAULT = 0.5


def extract_features(initial_grid, rates):
    """Extract feature tensor from initial grid and round-level rates.

    Args:
        initial_grid: H×W list of terrain codes
        rates: dict with keys survival, expansion, port_formation,
               forest_reclamation, ruin. Values can be None (defaults to 0.5).

    Returns:
        H×W×18 float32 numpy array
    """
    H = len(initial_grid)
    W = len(initial_grid[0])
    features = np.zeros((H, W, NUM_FEATURES), dtype=np.float32)

    settlement_dists = _precompute_settlement_distances(initial_grid)
    cluster_density = _precompute_cluster_density(initial_grid)

    # Rate values (default 0.5 for None)
    rate_vals = [float(rates.get(k) if rates.get(k) is not None else RATE_DEFAULT)
                 for k in RATE_KEYS]

    for r in range(H):
        for c in range(W):
            code = initial_grid[r][c]
            cls = terrain_code_to_class(code)

            # One-hot terrain (6 features)
            features[r, c, cls] = 1.0

            # Distance to nearest settlement, capped at 20
            features[r, c, 6] = min(settlement_dists[r][c], 20.0)

            # 8-connected adjacency counts
            adj_forest = 0
            adj_ocean = 0
            adj_settlement = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < H and 0 <= nc < W:
                        n = initial_grid[nr][nc]
                        if n == 4:
                            adj_forest += 1
                        elif n == 10:
                            adj_ocean += 1
                        elif n in (1, 2):
                            adj_settlement += 1

            features[r, c, 7] = 1.0 if adj_ocean > 0 else 0.0  # is_coastal
            features[r, c, 8] = float(adj_forest)
            features[r, c, 9] = float(adj_settlement)
            features[r, c, 10] = float(adj_ocean)
            features[r, c, 11] = 1.0 if cluster_density[r][c] else 0.0
            features[r, c, 12] = 1.0 if adj_forest >= 4 else 0.0  # is_interior_forest

            # Round-level rates (same for all cells)
            for i, val in enumerate(rate_vals):
                features[r, c, 13 + i] = val

    return features
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest test_ml_predictor.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astar-island/ml_predictor.py astar-island/test_ml_predictor.py
git commit -m "feat: add ML feature extraction (18 features per cell)"
```

---

### Task 2: Numpy Forward Pass (ml_predictor.py)

**Files:**
- Modify: `astar-island/ml_predictor.py`
- Modify: `astar-island/test_ml_predictor.py`

- [ ] **Step 1: Write failing tests for numpy forward pass**

```python
# Add to test_ml_predictor.py
from ml_predictor import numpy_forward, load_model, save_model

def test_numpy_forward_shape():
    """Forward pass produces H×W×6 with valid probabilities."""
    # Create dummy weights for 18→128→64→32→6
    rng = np.random.default_rng(42)
    weights = {
        "fc1_w": rng.standard_normal((128, 18)).astype(np.float32) * 0.1,
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": rng.standard_normal((64, 128)).astype(np.float32) * 0.1,
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": rng.standard_normal((32, 64)).astype(np.float32) * 0.1,
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": rng.standard_normal((6, 32)).astype(np.float32) * 0.1,
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(18, dtype=np.float32),
        "feat_std": np.ones(18, dtype=np.float32),
    }
    features = rng.standard_normal((5, 5, 18)).astype(np.float32)
    preds = numpy_forward(features, weights)
    assert preds.shape == (5, 5, 6)
    # All rows sum to 1 (softmax)
    sums = preds.sum(axis=2)
    np.testing.assert_allclose(sums, 1.0, atol=1e-5)
    # All values >= 0
    assert (preds >= 0).all()

def test_save_load_model_roundtrip(tmp_path):
    """Weights survive save/load roundtrip."""
    weights = {
        "fc1_w": np.ones((128, 18), dtype=np.float32),
        "fc1_b": np.zeros(128, dtype=np.float32),
        "fc2_w": np.ones((64, 128), dtype=np.float32),
        "fc2_b": np.zeros(64, dtype=np.float32),
        "fc3_w": np.ones((32, 64), dtype=np.float32),
        "fc3_b": np.zeros(32, dtype=np.float32),
        "fc4_w": np.ones((6, 32), dtype=np.float32),
        "fc4_b": np.zeros(6, dtype=np.float32),
        "feat_mean": np.zeros(18, dtype=np.float32),
        "feat_std": np.ones(18, dtype=np.float32),
    }
    path = str(tmp_path / "test_weights.npz")
    save_model(weights, path)
    loaded = load_model(path)
    for key in weights:
        np.testing.assert_array_equal(weights[key], loaded[key])
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest test_ml_predictor.py::test_numpy_forward_shape test_ml_predictor.py::test_save_load_model_roundtrip -v`
Expected: ImportError

- [ ] **Step 3: Implement numpy_forward, save_model, load_model**

```python
# Add to ml_predictor.py

def numpy_forward(features, weights):
    """Numpy-only MLP forward pass: Input(18) → 128 → 64 → 32 → Softmax(6).

    Args:
        features: H×W×18 float32 array
        weights: dict with fc*_w, fc*_b, feat_mean, feat_std

    Returns:
        H×W×6 float64 probability array
    """
    H, W, F = features.shape
    x = features.reshape(-1, F).astype(np.float64)

    # Z-score normalize
    x = (x - weights["feat_mean"].astype(np.float64)) / (
        weights["feat_std"].astype(np.float64) + 1e-8)

    # Layer 1: Linear + ReLU
    x = x @ weights["fc1_w"].astype(np.float64).T + weights["fc1_b"].astype(np.float64)
    x = np.maximum(x, 0)

    # Layer 2: Linear + ReLU
    x = x @ weights["fc2_w"].astype(np.float64).T + weights["fc2_b"].astype(np.float64)
    x = np.maximum(x, 0)

    # Layer 3: Linear + ReLU
    x = x @ weights["fc3_w"].astype(np.float64).T + weights["fc3_b"].astype(np.float64)
    x = np.maximum(x, 0)

    # Layer 4: Linear + Softmax
    x = x @ weights["fc4_w"].astype(np.float64).T + weights["fc4_b"].astype(np.float64)

    # Stable softmax
    x_max = x.max(axis=1, keepdims=True)
    exp_x = np.exp(x - x_max)
    x = exp_x / exp_x.sum(axis=1, keepdims=True)

    return x.reshape(H, W, 6)


def save_model(weights, path):
    """Save model weights to .npz file."""
    np.savez(path, **weights)


def load_model(path):
    """Load model weights from .npz file."""
    data = np.load(path)
    return {key: data[key] for key in data.files}
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `pytest test_ml_predictor.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add astar-island/ml_predictor.py astar-island/test_ml_predictor.py
git commit -m "feat: add numpy MLP forward pass and model save/load"
```

---

### Task 3: Training Data Pipeline (train_model.py)

**Files:**
- Create: `astar-island/train_model.py`
- Read: `astar-island/test_backtest.py:480-575` (simulated production pipeline for reference)
- Read: `astar-island/predictor.py:428-570` (rate estimation functions)

- [ ] **Step 1: Implement GT data fetching and feature extraction**

```python
# train_model.py
"""Offline training script for ML predictor.

Usage:
    python3 train_model.py                    # Train on all GT data, export weights
    python3 train_model.py --cv               # Leave-one-round-out cross-validation
    python3 train_model.py --rebuild-data     # Rebuild training_data.npz from API
"""

import argparse
import os
import sys
import time

import numpy as np

import api_client
from ml_predictor import extract_features, NUM_FEATURES, RATE_KEYS
from predictor import (
    terrain_code_to_class,
    estimate_survival_rate,
    estimate_expansion_rate,
    estimate_port_formation_rate,
    estimate_all_rates,
    STATIC_CODES,
    TERRAIN_TO_CLASS,
    NUM_CLASSES,
)


def compute_gt_rates(gt, initial_grid):
    """Compute ground-truth round-level rates from GT probability tensor.

    Args:
        gt: H×W×6 probability array (ground truth)
        initial_grid: H×W terrain code list

    Returns:
        dict with survival, expansion, port_formation, forest_reclamation, ruin rates
    """
    H, W = len(initial_grid), len(initial_grid[0])
    sett_alive, sett_total = 0.0, 0.0
    new_sett, non_sett = 0.0, 0.0
    port_formed, coastal_non_port = 0.0, 0.0
    forest_reclaimed, non_forest_near = 0.0, 0.0
    ruin_count = 0.0

    for r in range(H):
        for c in range(W):
            code = initial_grid[r][c]
            if code in STATIC_CODES:
                continue
            gt_dist = gt[r, c]

            if code in (1, 2):  # Initial settlement/port
                sett_total += 1.0
                sett_alive += gt_dist[1] + gt_dist[2]  # P(Settlement) + P(Port)
                ruin_count += gt_dist[3]  # P(Ruin)

            if code in (0, 11, 4):  # Non-settlement
                non_sett += 1.0
                new_sett += gt_dist[1]  # P(Settlement)

            # Coastal non-port for port formation
            is_coastal = False
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr, dc) != (0, 0):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < H and 0 <= nc < W and initial_grid[nr][nc] == 10:
                            is_coastal = True
            if is_coastal and code != 2:
                coastal_non_port += 1.0
                port_formed += gt_dist[2]

            # Forest reclamation: non-forest cells near forest
            has_adj_forest = False
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (dr, dc) != (0, 0):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < H and 0 <= nc < W and initial_grid[nr][nc] == 4:
                            has_adj_forest = True
            if has_adj_forest and code != 4:
                non_forest_near += 1.0
                forest_reclaimed += gt_dist[4]

    return {
        "survival": sett_alive / max(sett_total, 1),
        "expansion": min(new_sett / max(non_sett, 1), 0.30),
        "port_formation": min(port_formed / max(coastal_non_port, 1), 0.15),
        "forest_reclamation": min(forest_reclaimed / max(non_forest_near, 1), 0.40),
        "ruin": min(ruin_count / max(sett_total, 1), 0.95),
    }


def simulate_noisy_rates(gt, initial_grid, rng, n_queries=50):
    """Simulate production rate estimation from n_queries viewport observations.

    Samples discrete terrain from GT, creates viewport-like observations,
    then runs existing rate estimators on them.

    Args:
        gt: H×W×6 probability array
        initial_grid: H×W terrain code list
        rng: numpy random generator
        n_queries: number of simulated queries

    Returns:
        dict with noisy rate estimates (matching production noise profile)
    """
    H, W = len(initial_grid), len(initial_grid[0])

    # Sample a discrete terrain realization from GT distributions
    flat_gt = gt.reshape(-1, 6)
    sampled_classes = np.array([rng.choice(6, p=row) for row in flat_gt])
    # Map classes back to terrain codes for rate estimation
    CLASS_TO_CODE = {0: 11, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}  # Empty→Plains
    sampled_grid = [[CLASS_TO_CODE[sampled_classes[r * W + c]]
                     for c in range(W)] for r in range(H)]

    # Create viewport-like observations (15×15 tiles, sorted by settlement density)
    vp_size = 15
    tiles = []
    for y in range(0, H, vp_size):
        for x in range(0, W, vp_size):
            h = min(vp_size, H - y)
            w = min(vp_size, W - x)
            sett_count = sum(1 for dr in range(h) for dc in range(w)
                             if initial_grid[y + dr][x + dc] in (1, 2))
            dynamic = sum(1 for dr in range(h) for dc in range(w)
                          if initial_grid[y + dr][x + dc] not in STATIC_CODES)
            tiles.append((dynamic + sett_count * 3, x, y, w, h))
    tiles.sort(reverse=True)

    # Select up to n_queries tiles (with repeats of top tiles)
    observations = []
    unique_tiles = tiles[:n_queries]
    remaining = n_queries - len(unique_tiles)
    repeat_tiles = tiles[:max(1, len(tiles) // 3)]
    all_tiles = unique_tiles + [repeat_tiles[i % len(repeat_tiles)]
                                 for i in range(remaining)]

    for _, vp_x, vp_y, vp_w, vp_h in all_tiles[:n_queries]:
        # Re-sample for each observation (different stochastic outcome)
        sampled_classes_obs = np.array([
            rng.choice(6, p=gt[r, c]) for r in range(vp_y, vp_y + vp_h)
            for c in range(vp_x, vp_x + vp_w)
        ])
        grid_obs = [[CLASS_TO_CODE[sampled_classes_obs[dr * vp_w + dc]]
                      for dc in range(vp_w)] for dr in range(vp_h)]
        observations.append({
            "viewport": {"x": vp_x, "y": vp_y, "w": vp_w, "h": vp_h},
            "grid": grid_obs,
            "seed_index": 0,
        })

    # Estimate rates using existing production functions
    initial_grids = [initial_grid]
    rates = {
        "survival": estimate_survival_rate(initial_grids, observations),
        "expansion": estimate_expansion_rate(initial_grids, observations),
        "port_formation": estimate_port_formation_rate(initial_grids, observations),
    }
    all_rates = estimate_all_rates(initial_grids, observations)
    rates["forest_reclamation"] = all_rates.get("forest_reclamation")
    rates["ruin"] = all_rates.get("ruin")

    return rates


def build_training_data(n_augmentations=10, cache_path="training_data.npz"):
    """Fetch GT from all completed rounds and build training dataset.

    Returns:
        X: (N, 18) feature array
        Y: (N, 6) target probability array
        round_ids: (N,) round index per example (for CV)
    """
    if os.path.exists(cache_path):
        print(f"Loading cached training data from {cache_path}")
        data = np.load(cache_path)
        return data["X"], data["Y"], data["round_ids"]

    rounds = api_client.get_rounds()
    completed = [r for r in rounds if r["status"] == "completed"]
    print(f"Found {len(completed)} completed rounds")

    all_X, all_Y, all_round_ids = [], [], []

    for round_idx, round_info in enumerate(completed):
        round_id = round_info["id"]
        round_num = round_info.get("round_number", round_idx + 1)
        detail = api_client.get_round_detail(round_id)
        seeds_count = len(detail.get("initial_states", []))
        initial_states = detail["initial_states"]

        print(f"\nRound {round_num} ({round_id[:8]}): {seeds_count} seeds")

        # Fetch GT for all seeds
        all_gt = {}
        for seed_idx in range(seeds_count):
            analysis = api_client.get_analysis(round_id, seed_idx)
            all_gt[seed_idx] = np.array(analysis["ground_truth"])
            time.sleep(0.25)  # Rate limit

        # Compute GT rates (one per round, averaged across seeds)
        gt_rates_list = []
        for seed_idx in range(seeds_count):
            gt_rates_list.append(
                compute_gt_rates(all_gt[seed_idx], initial_states[seed_idx]["grid"])
            )
        avg_gt_rates = {k: np.mean([r[k] for r in gt_rates_list])
                        for k in RATE_KEYS}

        rng = np.random.default_rng(seed=42 + round_idx)

        for aug_idx in range(n_augmentations):
            # Generate noisy rates for this augmentation
            # Pick a random seed for rate estimation
            rate_seed = rng.integers(0, seeds_count)
            noisy_rates = simulate_noisy_rates(
                all_gt[rate_seed], initial_states[rate_seed]["grid"], rng
            )

            for seed_idx in range(seeds_count):
                gt = all_gt[seed_idx]
                init_grid = initial_states[seed_idx]["grid"]
                H, W = gt.shape[0], gt.shape[1]

                # Extract features with noisy rates
                features = extract_features(init_grid, noisy_rates)

                # Collect dynamic cells only
                for r in range(H):
                    for c in range(W):
                        if init_grid[r][c] in STATIC_CODES:
                            continue
                        if gt[r, c].max() >= 1.0:
                            continue  # Static cell
                        all_X.append(features[r, c])
                        all_Y.append(gt[r, c].astype(np.float32))
                        all_round_ids.append(round_idx)

            if (aug_idx + 1) % 5 == 0:
                print(f"  Aug {aug_idx + 1}/{n_augmentations}, "
                      f"samples so far: {len(all_X)}")

    X = np.array(all_X, dtype=np.float32)
    Y = np.array(all_Y, dtype=np.float32)
    round_ids = np.array(all_round_ids, dtype=np.int32)

    print(f"\nTotal training examples: {len(X)}")
    print(f"Feature shape: {X.shape}, Target shape: {Y.shape}")

    np.savez(cache_path, X=X, Y=Y, round_ids=round_ids)
    print(f"Saved to {cache_path}")

    return X, Y, round_ids
```

- [ ] **Step 2: Test data pipeline manually**

Run: `python3 -c "from train_model import build_training_data; X, Y, R = build_training_data(n_augmentations=1, cache_path='test_data.npz'); print(f'X={X.shape}, Y={Y.shape}, rounds={len(set(R))}')" && rm -f test_data.npz`
Expected: X=(~92000, 18), Y=(~92000, 6), rounds=16

- [ ] **Step 3: Commit**

```bash
git add astar-island/train_model.py
git commit -m "feat: add training data pipeline with noisy rate augmentation"
```

---

### Task 4: PyTorch Training Loop (train_model.py)

**Files:**
- Modify: `astar-island/train_model.py`

- [ ] **Step 1: Add PyTorch model definition and training**

```python
# Add to train_model.py
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader


class TerrainMLP(nn.Module):
    """MLP for predicting terrain class distributions."""

    def __init__(self, n_features=18, n_classes=6):
        super().__init__()
        self.fc1 = nn.Linear(n_features, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 32)
        self.fc4 = nn.Linear(32, n_classes)
        self.dropout = nn.Dropout(0.1)

    def forward(self, x):
        x = self.dropout(F.relu(self.fc1(x)))
        x = self.dropout(F.relu(self.fc2(x)))
        x = F.relu(self.fc3(x))
        x = F.softmax(self.fc4(x), dim=-1)
        return x


def train_model(X, Y, round_ids=None, exclude_round=None,
                epochs=80, batch_size=4096, lr=1e-3, verbose=True):
    """Train MLP on feature/target data.

    Args:
        X: (N, 18) features
        Y: (N, 6) target distributions
        round_ids: (N,) round index per sample (for CV filtering)
        exclude_round: round index to exclude (for LOOCV)
        epochs: training epochs
        batch_size: batch size
        lr: learning rate
        verbose: print progress

    Returns:
        dict of numpy weight arrays + normalization stats
    """
    # Filter for CV
    if exclude_round is not None and round_ids is not None:
        mask = round_ids != exclude_round
        X_train = X[mask]
        Y_train = Y[mask]
    else:
        X_train = X
        Y_train = Y

    # Compute normalization stats
    feat_mean = X_train.mean(axis=0)
    feat_std = X_train.std(axis=0)
    feat_std[feat_std < 1e-6] = 1.0  # Avoid div by zero

    # Normalize
    X_norm = (X_train - feat_mean) / feat_std

    # Convert to tensors
    X_t = torch.tensor(X_norm, dtype=torch.float32)
    Y_t = torch.tensor(Y_train, dtype=torch.float32)

    dataset = TensorDataset(X_t, Y_t)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    model = TerrainMLP()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_loss = float("inf")
    patience = 10
    patience_counter = 0

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        n_batches = 0
        for X_batch, Y_batch in loader:
            pred = model(X_batch)
            # KL divergence: sum(GT * log(GT / pred))
            # Using F.kl_div which expects log(pred) as input
            log_pred = torch.log(pred + 1e-8)
            loss = F.kl_div(log_pred, Y_batch, reduction="batchmean")

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_loss = total_loss / n_batches

        if avg_loss < best_loss - 1e-6:
            best_loss = avg_loss
            patience_counter = 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1

        if verbose and (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch + 1}/{epochs}: loss={avg_loss:.6f} "
                  f"best={best_loss:.6f} lr={scheduler.get_last_lr()[0]:.6f}")

        if patience_counter >= patience:
            if verbose:
                print(f"  Early stopping at epoch {epoch + 1}")
            break

    # Load best state
    model.load_state_dict(best_state)
    model.eval()

    # Export weights as numpy
    weights = {
        "fc1_w": model.fc1.weight.detach().numpy(),
        "fc1_b": model.fc1.bias.detach().numpy(),
        "fc2_w": model.fc2.weight.detach().numpy(),
        "fc2_b": model.fc2.bias.detach().numpy(),
        "fc3_w": model.fc3.weight.detach().numpy(),
        "fc3_b": model.fc3.bias.detach().numpy(),
        "fc4_w": model.fc4.weight.detach().numpy(),
        "fc4_b": model.fc4.bias.detach().numpy(),
        "feat_mean": feat_mean,
        "feat_std": feat_std,
    }
    return weights


def cross_validate(X, Y, round_ids, verbose=True):
    """Leave-one-round-out cross-validation.

    Returns:
        dict mapping round_index → avg KL divergence
    """
    from predictor import score_predictions
    unique_rounds = sorted(set(round_ids))
    results = {}

    print(f"\nCross-validation: {len(unique_rounds)} folds")

    for round_idx in unique_rounds:
        if verbose:
            print(f"\n--- Fold: exclude round {round_idx} ---")

        weights = train_model(X, Y, round_ids, exclude_round=round_idx,
                              verbose=verbose)

        # Evaluate on held-out round
        mask = round_ids == round_idx
        X_test = X[mask]
        Y_test = Y[mask]

        # Normalize with training stats
        X_norm = (X_test - weights["feat_mean"]) / (weights["feat_std"] + 1e-8)

        # Forward pass
        from ml_predictor import numpy_forward
        # Reshape to (1, N, 18) → (1, N, 6) hack — just use flat
        N = X_test.shape[0]
        preds = numpy_forward(X_norm.reshape(1, N, 18), weights).reshape(N, 6)

        # Compute KL per cell
        kl_per_cell = np.sum(Y_test * np.log((Y_test + 1e-10) / (preds + 1e-10)),
                             axis=1)
        avg_kl = float(kl_per_cell.mean())
        results[round_idx] = avg_kl

        if verbose:
            print(f"  Round {round_idx}: avg KL = {avg_kl:.6f} "
                  f"({mask.sum()} cells)")

    overall = np.mean(list(results.values()))
    if verbose:
        print(f"\n=== CV Overall: avg KL = {overall:.6f} ===")

    return results


def main():
    parser = argparse.ArgumentParser(description="Train ML predictor")
    parser.add_argument("--cv", action="store_true",
                        help="Run leave-one-round-out cross-validation")
    parser.add_argument("--rebuild-data", action="store_true",
                        help="Rebuild training data from API (ignore cache)")
    parser.add_argument("--augmentations", type=int, default=10,
                        help="Number of noisy rate augmentations per round")
    parser.add_argument("--output", default="model_weights.npz",
                        help="Output path for trained weights")
    args = parser.parse_args()

    cache = "training_data.npz"
    if args.rebuild_data and os.path.exists(cache):
        os.remove(cache)

    X, Y, round_ids = build_training_data(
        n_augmentations=args.augmentations, cache_path=cache
    )

    if args.cv:
        cross_validate(X, Y, round_ids)
    else:
        print("\nTraining final model on all data...")
        weights = train_model(X, Y, verbose=True)
        from ml_predictor import save_model
        save_model(weights, args.output)
        print(f"\nModel saved to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run training with 1 augmentation as smoke test**

Run: `python3 train_model.py --augmentations 1 --output test_weights.npz`
Expected: Trains for ~80 epochs, saves test_weights.npz, loss decreasing

- [ ] **Step 3: Commit**

```bash
git add astar-island/train_model.py
git commit -m "feat: add PyTorch MLP training with KL loss and LOOCV"
```

---

### Task 5: Production Integration (predictor.py)

**Files:**
- Modify: `astar-island/predictor.py` (add build_prediction_ml)
- Read: `astar-island/predictor.py:1068-1394` (existing build_prediction)

- [ ] **Step 1: Add build_prediction_ml() to predictor.py**

Add a new function that uses the ML model for base predictions, then applies per-cell blending and floor. Insert after `build_prediction()` (after line 1394):

```python
def build_prediction_ml(height, width, initial_grid, observations,
                        ml_weights, rates=None,
                        spatial_model=None, spatial_obs=None,
                        use_post_adjustments=False,
                        survival_rate=None, expansion_rate=None,
                        port_formation_rate=None):
    """Build predictions using ML model instead of bucket model.

    Uses ml_predictor for base predictions, then applies:
    - Per-cell observation blending (Step 2 from build_prediction)
    - Probability floor

    Post-model adjustments are OFF by default (ML model learns them).
    Set use_post_adjustments=True to re-enable as fallback.
    """
    from ml_predictor import extract_features, numpy_forward

    # Step 1: ML model base predictions
    if rates is None:
        rates = {}
    features = extract_features(initial_grid, rates)
    predictions = numpy_forward(features, ml_weights)

    # Override static cells (model may not predict these perfectly)
    for r in range(height):
        for c in range(width):
            code = initial_grid[r][c]
            if code in STATIC_CODES:
                predictions[r, c] = 0.0
                predictions[r, c, terrain_code_to_class(code)] = 1.0

    # Optional: re-enable specific post-model adjustments
    if use_post_adjustments:
        fmap, settlement_dists, _ = compute_feature_map(initial_grid)
        # ... (port calibration, winter calibration etc. can be toggled here)

    # Step 2: Per-cell observation blending (same as build_prediction)
    if observations:
        fmap_for_blend = None
        if spatial_obs:
            fmap_for_blend, _, _ = compute_feature_map(initial_grid)

        cell_counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)
        cell_obs_count = np.zeros((height, width), dtype=np.float64)

        for obs in observations:
            vp = obs["viewport"]
            grid = obs["grid"]
            vp_x, vp_y = vp["x"], vp["y"]
            vp_h = len(grid)
            vp_w = len(grid[0]) if vp_h > 0 else 0
            for dr in range(vp_h):
                for dc in range(vp_w):
                    r = vp_y + dr
                    c = vp_x + dc
                    if 0 <= r < height and 0 <= c < width:
                        cls = terrain_code_to_class(grid[dr][dc])
                        cell_counts[r, c, cls] += 1
                        cell_obs_count[r, c] += 1

        observed_mask = cell_obs_count > 0
        if observed_mask.any():
            cell_totals = cell_obs_count[..., np.newaxis]
            cell_probs = np.zeros_like(cell_counts)
            np.divide(cell_counts, cell_totals, out=cell_probs,
                      where=(cell_totals > 0))

            k_grid = np.full((height, width), K_DEFAULT)
            for r in range(height):
                for c in range(width):
                    base_k = K_PER_CODE.get(initial_grid[r][c], K_DEFAULT)
                    if spatial_obs and fmap_for_blend and fmap_for_blend[r][c] in spatial_obs:
                        bucket_n = spatial_obs[fmap_for_blend[r][c]]
                        confidence_scale = 1.0 + 0.5 * min(bucket_n / 100.0, 3.0)
                        base_k *= confidence_scale
                    n_obs = cell_obs_count[r, c]
                    if n_obs <= 2 and initial_grid[r][c] in (0, 11, 4):
                        base_k *= 3.0
                    k_grid[r, c] = base_k

            alpha = cell_obs_count / (cell_obs_count + k_grid)
            alpha = alpha[..., np.newaxis]

            for r in range(height):
                for c in range(width):
                    if observed_mask[r, c] and initial_grid[r][c] not in STATIC_CODES:
                        predictions[r, c] = (
                            alpha[r, c, 0] * cell_probs[r, c]
                            + (1 - alpha[r, c, 0]) * predictions[r, c]
                        )

    # Step 3: Probability floor
    predictions = apply_floor(predictions)
    return predictions
```

- [ ] **Step 2: Test integration with dummy weights**

Run: `python3 -c "
from predictor import build_prediction_ml
from ml_predictor import save_model
import numpy as np
rng = np.random.default_rng(42)
weights = {
    'fc1_w': rng.standard_normal((128, 18)).astype(np.float32) * 0.1,
    'fc1_b': np.zeros(128, dtype=np.float32),
    'fc2_w': rng.standard_normal((64, 128)).astype(np.float32) * 0.1,
    'fc2_b': np.zeros(64, dtype=np.float32),
    'fc3_w': rng.standard_normal((32, 64)).astype(np.float32) * 0.1,
    'fc3_b': np.zeros(32, dtype=np.float32),
    'fc4_w': rng.standard_normal((6, 32)).astype(np.float32) * 0.1,
    'fc4_b': np.zeros(6, dtype=np.float32),
    'feat_mean': np.zeros(18, dtype=np.float32),
    'feat_std': np.ones(18, dtype=np.float32),
}
grid = [[11, 4, 10], [1, 11, 11], [4, 11, 5]]
pred = build_prediction_ml(3, 3, grid, [], weights, rates={'survival': 0.5, 'expansion': 0.1, 'port_formation': 0.05, 'forest_reclamation': 0.2, 'ruin': 0.3})
print(f'Shape: {pred.shape}, sums: {pred.sum(axis=2)}')
assert pred.shape == (3, 3, 6)
assert np.allclose(pred.sum(axis=2), 1.0, atol=1e-4)
print('Integration test PASSED')
"`
Expected: Shape (3,3,6), sums all ~1.0, PASSED

- [ ] **Step 3: Commit**

```bash
git add astar-island/predictor.py
git commit -m "feat: add build_prediction_ml() using ML model with per-cell blending"
```

---

### Task 6: Backtest Integration (test_backtest.py)

**Files:**
- Modify: `astar-island/test_backtest.py`

- [ ] **Step 1: Add --model ml flag and ML prediction path**

In test_backtest.py, modify the simulated-production pipeline (around line 525-555) to optionally use the ML model. Add argument parsing:

```python
# Add to argument parser (around line 633):
parser.add_argument("--model", choices=["bucket", "ml"], default="bucket",
                    help="Which prediction model to use")
parser.add_argument("--ml-weights", default="model_weights.npz",
                    help="Path to ML model weights")
```

In the sim-prod pipeline function, add ML model path. The key change is in the prediction loop (around line 536-553): if model=="ml", use `build_prediction_ml()` instead of `build_prediction()`.

- [ ] **Step 2: Test with bucket model (no regression)**

Run: `python3 test_backtest.py --simulate-production --sim-runs 1 --model bucket 2>&1 | tail -5`
Expected: Same results as before

- [ ] **Step 3: Commit**

```bash
git add astar-island/test_backtest.py
git commit -m "feat: add --model ml flag to backtest for A/B testing"
```

---

### Task 7: Train, Validate, and Deploy

**Files:**
- Run: `astar-island/train_model.py`
- Run: `astar-island/test_backtest.py`

- [ ] **Step 1: Build full training data (10 augmentations)**

Run: `python3 train_model.py --rebuild-data --augmentations 10 --output model_weights.npz`
Expected: ~920k training examples, model trains, weights saved

- [ ] **Step 2: Run cross-validation**

Run: `python3 train_model.py --cv --augmentations 10`
Expected: Per-round KL results for all 16 folds

- [ ] **Step 3: Run simulated-production backtest with ML model**

Run: `python3 test_backtest.py --simulate-production --sim-runs 5 --model ml --output ml_results.json`
Expected: Per-round KL results. Target: avg KL < 0.0504 (bucket model baseline)

- [ ] **Step 4: Compare with bucket model baseline**

Run: `python3 test_backtest.py --simulate-production --sim-runs 5 --model bucket --output bucket_results.json`
Then compare `ml_results.json` vs `bucket_results.json` avg KL.

- [ ] **Step 5: If ML wins — commit weights and update PLAN.md**

```bash
git add astar-island/model_weights.npz
git commit -m "feat: trained ML model weights (avg KL: X.XXXX vs bucket: 0.0504)"
```

- [ ] **Step 6: If ML loses on some rounds — try ensemble**

In predictor.py, add ensemble: `final = alpha * ml_pred + (1 - alpha) * bucket_pred`. Tune alpha via sim-prod backtest.

- [ ] **Step 7: Run unit tests to verify nothing broken**

Run: `pytest test_predictor_unit.py test_predictor_integration.py test_ml_predictor.py -v`
Expected: All tests pass

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "ML predictor: validated and ready for production"
```
