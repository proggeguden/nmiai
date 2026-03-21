# ML Predictor for Astar Island

## Problem

Our bucket-based spatial model scores 82-86 raw. Top teams score 90-94. The bucket model cannot learn feature interactions (e.g., coastal AND near settlement AND near forest) and within-bucket variance accounts for ~60% of remaining error. We have 16 rounds of ground truth data (~92k dynamic cells) that enable cross-round transfer learning.

## Approach

Train a PyTorch MLP on GT data from all completed rounds. The model predicts P(class | spatial_features, round_level_rates). Export weights as numpy arrays for zero-dependency production inference.

Key innovation: train with simulated-noisy rate estimates (not GT rates) so the model learns to handle the 2-4x noise in production rate estimation from 50 queries.

## Training Data Pipeline

**Script**: `train_model.py` (offline, run once + after each new round completes)

1. Fetch GT via `api_client.get_analysis()` for all completed rounds (16) x 5 seeds = 80 grids
2. For each grid-seed pair:
   - Extract spatial features per cell using existing helpers (BFS distances, adjacency counts)
   - Filter to dynamic cells (GT max_prob < 1.0)
3. Compute round-level GT rates (survival, expansion, port, forest, ruin) from full GT distributions
4. Noisy rate augmentation (N=10 per round):
   - Sample discrete terrain from GT distributions (one sample per "observation")
   - Simulate actual viewport strategy: tile grid into 15x15 viewports sorted by settlement density, select ~50 viewport observations (matching production `observe_seed` logic)
   - Estimate rates using existing `estimate_*_rate()` functions on these spatially-realistic noisy observations
   - Each cell appears 10x with different noisy rate vectors
5. Save to `training_data.npz`: X (N x F features), Y (N x 6 targets)
6. Total: ~920k training examples

## Feature Engineering

**Per-cell spatial features (exact from initial grid):**

| Feature | Type | Description |
|---------|------|-------------|
| terrain_onehot | 6 binary | One-hot of initial terrain code |
| dist_to_settlement | float | Manhattan distance (BFS), continuous, capped at 20 |
| is_coastal | binary | Any adjacent ocean cell |
| adj_forest_count | int 0-8 | 8-connected forest neighbors |
| adj_settlement_count | int 0-8 | 8-connected settlement neighbors |
| adj_ocean_count | int 0-8 | 8-connected ocean neighbors |
| is_clustered | binary | >=2 settlements within d<=5 |
| is_interior_forest | binary | adj_forest >= 4 |

**Round-level features (estimated from observations, noisy in production):**

| Feature | Type | Description |
|---------|------|-------------|
| survival_rate | float 0-1 | Fraction of settlements surviving |
| expansion_rate | float 0-0.3 | New settlements / non-settlement cells |
| port_formation_rate | float 0-0.15 | Ports formed / coastal non-port cells |
| forest_reclamation_rate | float 0-0.4 | Forest reclaimed / non-forest cells |
| ruin_rate | float 0-0.95 | Settlements collapsed / initial settlements |

**Total: 18 features** (6 one-hot + 7 spatial + 5 round-level)

**Normalization**: Z-score standardize all features at training time. Store mean/std vectors in `model_weights.npz` alongside layer weights. Apply same normalization at inference. One-hot features and binaries are included in normalization (centering helps the MLP).

## Model Architecture

```
Input(18) -> Linear(128) -> ReLU -> Dropout(0.1)
          -> Linear(64)  -> ReLU -> Dropout(0.1)
          -> Linear(32)  -> ReLU
          -> Linear(6)   -> Softmax
```

- **Loss**: `F.kl_div(log_pred, GT, reduction='batchmean')` -- PyTorch's KL div handles GT zeros correctly (0*log(0)=0 convention). Add eps=1e-8 to pred before log to avoid log(0).
- **Optimizer**: Adam, lr=1e-3, cosine annealing
- **Batch size**: 4096
- **Epochs**: 50-100, early stopping on validation KL
- **Weight export**: Save as `model_weights.npz` (numpy arrays). Production inference uses numpy matmuls only.

## Production Integration

**New file**: `ml_predictor.py`
- `load_model(path)` -- load numpy weight arrays
- `extract_features(initial_grid, rates)` -- spatial + round features per cell
- `predict(features, weights)` -- numpy forward pass (matmul + ReLU + softmax)

**Modified pipeline in `build_prediction()`:**
1. Query phase (unchanged): 50 queries -> observations
2. Rate estimation (unchanged): `estimate_all_rates()`
3. **ML prediction** (replaces bucket model): features + rates -> numpy forward pass -> base predictions
4. Per-cell observation blending (kept): adaptive k blending with direct observations
5. Probability floor (kept): `apply_floor(0.0005)`

**Removed post-model adjustments**: Port calibration (1.5), winter calibration (1.6), expansion modulation (1.75), temperature scaling (1.8), forest entropy injection (1.85). The ML model learns these corrections implicitly from GT data. Post-model adjustments are kept as toggleable code (not deleted) so individual steps can be re-enabled if the ML model misses a specific correction.

**Deployment**: `model_weights.npz` is committed to git (small file, <1MB). Baked into Docker image automatically.

## Validation Strategy

Backtesting is the source of truth. Three gates before deploying any change:

### Gate 1: Leave-one-round-out CV (offline, ~5 min)
Train on 15 rounds, predict 16th, compute entropy-weighted KL. Repeat for all 16. Reports per-round KL and mean. Built into `train_model.py --cv`.

### Gate 2: Simulated-production backtest (existing infra, ~5 min)
Run `python3 test_backtest.py --simulate-production --sim-runs 5` with ML model plugged in. Direct comparison with bucket model baseline (current avg KL: 0.0504).

### Gate 3: Regression detection
Compare ML model sim-prod results against saved bucket model baseline. Must improve average KL. No round can regress by more than 15%. If Gate 3 fails: try ensemble fallback (see Fallback section). If ensemble also fails Gate 3, do not deploy.

**Baseline to beat**: Sim-prod avg KL 0.0504 (bucket model, 16 rounds, 5 runs each).

### Backtest workflow
```bash
# 1. Train model
python3 train_model.py

# 2. Cross-validation (offline)
python3 train_model.py --cv

# 3. Simulated-production backtest
python3 test_backtest.py --simulate-production --sim-runs 5 --output ml_results.json

# 4. Compare with bucket model baseline
# ml_results.json avg_kl vs 0.0504
```

## Fallback

If the ML model underperforms on certain round types, ensemble with bucket model: `final = alpha * ml_pred + (1 - alpha) * bucket_pred` with alpha tuned via sim-prod backtest.

## Files

| File | Action | Purpose |
|------|--------|---------|
| `ml_predictor.py` | New | Feature extraction, numpy forward pass, model loading |
| `train_model.py` | New | Training data pipeline, PyTorch training, CV, weight export |
| `model_weights.npz` | New (generated) | Trained model weights for production |
| `training_data.npz` | New (generated) | Cached training dataset |
| `predictor.py` | Modify | Swap bucket model call for ML model in build_prediction() |
| `test_backtest.py` | Modify | Add `--model ml` flag to use ML predictor |
| `requirements.txt` | No change | numpy-only inference, PyTorch only needed for training |
