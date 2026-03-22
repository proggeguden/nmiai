# Astar Island — Final Solution

**Team**: People Made Machines
**Best result**: R22 = 91.12 (rank 1/278), weighted score 266.6 (#1 on leaderboard)
**Model**: 5-snapshot wide MLP ensemble, 32 features, numpy-only inference

---

## The Problem

Observe a black-box Norse civilisation simulator through limited viewport queries (50 total across 5 seeds), then predict the probability distribution of 6 terrain types across each 40x40 map. Scored on entropy-weighted KL divergence — only dynamic cells matter, and higher-entropy cells count more.

Each round has 5 seeds sharing the same hidden parameters (winter severity, expansion rate, etc.) but different terrain layouts and stochastic outcomes.

## Solution Overview

Our approach evolved through three major phases:

1. **Bucket spatial model** (R5–R16): Hand-crafted spatial features → bucket keys → count-based probability estimation
2. **Single MLP** (R17–R21): 28-feature MLP trained on cross-round ground truth data with noisy rate augmentation
3. **Wide ensemble** (R22–R23): 5-snapshot 32-feature MLP ensemble — our final and best model

The wide ensemble scored **91.12 on R22 (rank 1/278)** and achieved a simulated-production KL of **0.0177**, representing a 48% improvement over the single MLP and a 64% improvement over the bucket model.

## Architecture

```
Input(32) → Linear(256) → ReLU → Dropout(0.1)
         → Linear(128) → ReLU → Dropout(0.1)
         → Linear(64)  → ReLU
         → Linear(6)   → Softmax
```

- **5 snapshots** trained with different torch seeds (42, 49, 56, 63, 70), predictions averaged
- **KL divergence loss** (matches the scoring metric directly)
- **Cosine annealing LR** schedule over 80 epochs, Adam optimizer (lr=1e-3)
- **Early stopping** with patience=10
- **Dropout 0.1** on first two layers only
- Weights exported as numpy arrays (990KB), inference is pure numpy matmuls — zero PyTorch dependency in production

## Features (32 total)

| # | Feature | Description |
|---|---------|-------------|
| 0–5 | Terrain one-hot | 6 classes: Empty, Settlement, Port, Ruin, Forest, Mountain |
| 6 | dist_to_settlement | BFS distance to nearest settlement/port, capped at 20 |
| 7 | is_coastal | Has adjacent ocean cell (8-connected) |
| 8 | adj_forest_count | Count of adjacent forest cells (0–8) |
| 9 | adj_settlement_count | Count of adjacent settlement/port cells (0–8) |
| 10 | adj_ocean_count | Count of adjacent ocean cells (0–8) |
| 11 | is_clustered | ≥2 settlements within Manhattan distance 5 |
| 12 | is_interior_forest | Forest cell with ≥4 adjacent forest cells |
| 13 | survival_rate | Estimated fraction of initial settlements still alive |
| 14 | expansion_rate | Estimated fraction of non-settlement cells that became settlements |
| 15 | port_formation_rate | Estimated fraction of coastal cells that became ports |
| 16 | forest_reclamation_rate | Estimated fraction of non-forest cells that became forest |
| 17 | ruin_rate | Estimated fraction of settlements that became ruins |
| 18 | dist_to_coast | BFS distance to nearest ocean cell, capped at 20 |
| 19 | adj_mountain_count | Count of adjacent mountain cells (0–8) |
| 20 | settlement_count_r3 | Settlements within Manhattan distance 3 |
| 21 | forest_density_r2 | Forest cells within Manhattan distance 2 |
| 22 | dist_to_forest | BFS distance to nearest forest, capped at 10 |
| 23 | settlement_count_r5 | Settlements within Manhattan distance 5 |
| 24 | adj_ruin_count | Count of adjacent ruin cells (0–8) |
| 25 | survival × expansion | Rate interaction |
| 26 | survival / expansion | Rate ratio (captures R7/R12 anomaly) |
| 27 | expansion × port | Rate interaction |
| 28 | expansion / (dist+1) | Expansion rate scaled by inverse distance to settlement |
| 29 | survival / (dist+1) | Survival rate scaled by inverse distance to settlement |
| 30 | expansion × sett_r3 | Expansion rate × nearby settlement count |
| 31 | forest_clearing_rate | P(non-forest \| initially forest) estimated from observations |

Features 0–12 and 18–24 are **spatial** (derived from the initial grid). Features 13–17, 25–31 are **round-level rates** estimated from the 50 viewport observations. The rate features, especially the interaction terms, allow the model to adapt to each round's unique hidden parameters.

## Training

### Data
- Ground truth probability distributions from all completed rounds (22 rounds × 5 seeds)
- Only dynamic cells included (static ocean/mountain cells excluded)
- **Noisy rate augmentation** (10× per round): Instead of using perfect GT rates, we simulate production noise by sampling discrete observations from GT and estimating rates from those. This makes the model robust to the 2–4× rate estimation noise inherent in the 50-query budget.
- Total: ~1.12M training examples

### Key Innovation: Noisy Rate Augmentation

The biggest challenge is that production only gets 50 viewport queries (yielding noisy rate estimates), while training has access to perfect ground truth distributions. Without augmentation, the model overfits to clean rates and degrades in production.

Our `simulate_noisy_rates()` function creates realistic production conditions during training:
1. Sample discrete terrain from GT distributions (simulating what a viewport query returns)
2. Create viewport-like observations (15×15 tiles sorted by settlement density)
3. Run the same rate estimation functions used in production
4. Train on these noisy rates

This single technique was responsible for much of the ML model's advantage over the bucket model.

### Retraining

After each round completes (ground truth becomes available):

```bash
rm training_data.npz  # force rebuild with new round data
python3 train_model.py --rebuild-data --augmentations 10 --n-snapshots 5 --output model_weights.npz
```

## Production Pipeline

### 1. Observation Phase (50 queries)

- Allocate 10 queries per seed across all 5 seeds (proportional to settlement density)
- Each query requests a 15×15 viewport (maximum size)
- Coverage-first strategy: unique tile positions sorted by dynamic cell count, then repeat top tiles
- Rate-limit retry on 429 errors

### 2. Rate Estimation

From the 50 observations, estimate 6 round-level rates:
- `survival_rate`: fraction of initial settlements still alive
- `expansion_rate`: fraction of non-settlement cells that became settlements
- `port_formation_rate`: fraction of coastal cells that became ports
- `forest_reclamation_rate`: fraction of non-forest cells near forest that became forest
- `ruin_rate`: fraction of settlements that became ruins
- `forest_clearing_rate`: fraction of forest cells that are no longer forest

### 3. ML Prediction

- Extract 32 features per cell from initial grid + estimated rates
- Z-score normalize using training-set statistics
- Forward pass through all 5 snapshots (numpy matmuls + ReLU + softmax)
- Average the 5 softmax outputs
- **Survival-conditional temperature**: T=0.85 when survival < 10% (sharpens predictions on collapse rounds)
- Override static cells (Ocean → Empty, Mountain → Mountain)

### 4. Probability Floor

- Apply floor of 0.0005 to all predictions, then renormalize
- Prevents KL divergence → infinity for zero-probability predictions
- Lower floor preserves more mass for the dominant class (monotonically better down to 0.0005)

### 5. Per-Cell Blending (DISABLED)

Per-cell observation blending was part of the bucket model pipeline but was **disabled** for the ML model. The ensemble is accurate enough that 1–2 noisy discrete observations per cell only add noise. Disabling blending gave a 6.6% KL improvement across all rounds.

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, `/solve` endpoint, full pipeline orchestration |
| `predictor.py` | Rate estimation, spatial model, probability floor, blending logic |
| `ml_predictor.py` | Feature extraction (32 features), numpy forward pass, ensemble I/O |
| `train_model.py` | GT data fetch, noisy augmentation, PyTorch training, cross-validation |
| `model_weights.npz` | Trained ensemble weights (990KB, 5 snapshots) |
| `api_client.py` | API client for all astar-island endpoints |
| `test_local.py` | Local testing, submission, backtesting against real API |
| `test_backtest.py` | Simulated-production backtest (the only reliable validation method) |
| `test_predictor_unit.py` | 39 unit tests |
| `test_predictor_integration.py` | 27 integration tests |

## Reproducing Results

### Prerequisites

```bash
pip3 install -r requirements.txt  # fastapi, numpy, requests, python-dotenv, pytest
pip3 install torch                 # for training only (not needed for inference)
```

### Running Inference

```bash
cp .env.example .env  # add ACCESS_TOKEN from app.ainm.no cookies
python3 test_local.py --submit  # full pipeline: observe + predict + submit
```

### Retraining from Scratch

```bash
rm -f training_data.npz model_weights.npz
python3 train_model.py --rebuild-data --augmentations 10 --n-snapshots 5 --output model_weights.npz
```

This fetches GT from all completed rounds via the API, builds the augmented training set, and trains 5 snapshots. Takes ~10 minutes on a modern laptop.

### Running Tests

```bash
python3 -m pytest test_predictor_unit.py test_predictor_integration.py -v  # <1s, no API needed
```

### Backtesting

```bash
# Simulated-production backtest (the ONLY reliable validation method)
python3 test_backtest.py --simulate-production --sim-runs 3 --output sim_results.json
```

## Score History

| Round | Score | Rank | Model |
|-------|-------|------|-------|
| R5 | 13.1 | 130/144 | naive |
| R6 | 78.5 | 28/186 | bucket spatial |
| R7 | 60.4 | 83/199 | bucket spatial |
| R8 | 82.4 | 55/214 | bucket spatial |
| R9 | 8.5 | 205/221 | broken submission |
| R10 | 82.0 | 60/238 | bucket spatial |
| R11 | 79.7 | 61/171 | bucket spatial |
| R12 | 59.4 | 38/146 | bucket spatial |
| R13 | 73.2 | 126/186 | bucket spatial |
| R14 | 74.1 | 71/244 | bucket spatial |
| R15 | 86.1 | 97/262 | bucket + k-boost |
| R16 | 84.0 | 48/272 | bucket + k-boost |
| R17 | 90.0 | 47/283 | ML 28-feat single |
| R18 | 84.9 | 43/265 | ML 28-feat single |
| R19 | 93.5 | 31/228 | ML 28-feat single |
| R20 | 90.5 | 36/181 | ML 28-feat single |
| R21 | 86.3 | 90/225 | ML 28-feat single |
| R22 | **91.1** | **1/278** | ML 32-feat wide ensemble |
| R23 | pending | — | ML 32-feat wide ensemble (22-round retrain) |

## Lessons Learned

1. **Simulated-production backtest is essential** (rho=0.964 with real scores). Oracle backtest (rho=0.750) actively misled us — improvements in oracle sometimes hurt production. Several days of work were wasted optimizing the wrong metric.

2. **Noisy rate augmentation** was the single biggest unlock for the ML model. Without it, the model overfits to clean training conditions and degrades with real 50-query noise.

3. **Ensemble averaging** is free variance reduction. 5 snapshots trained with different seeds, averaged softmax — simple and effective (-5% KL).

4. **Wide > narrow**: 256→128→64 was 17% better than 128→64→32. More capacity helps when you have 1M+ training examples.

5. **Less is more for post-processing**: Disabling per-cell blending (-6.6%), removing focused query strategy (+5-23% regression when used), removing extra bucket features (+5-9% regression) — the ML model works best with minimal interference.

6. **Forest clearing rate** (r=-0.94 with forest outcome) was the most impactful single feature, directly addressing the #1 error source (forest stability overestimation).

7. **Rate interaction features** (survival×expansion, etc.) capture round-regime dynamics that raw rates miss. Rounds with high survival but low expansion (R7, R12) behave very differently from typical rounds.

## Dead Ends

These approaches were tested and confirmed to hurt or not help:

- MRF-style spatial smoothing (blurs across terrain boundaries)
- Focused/repeat query strategy (less coverage = worse rate estimates)
- Post-hoc temperature scaling (KL-trained model is already well-calibrated)
- Test-time augmentation via rate perturbation (double-perturbing adds noise)
- LightGBM distillation (MLP is 2× better on this task)
- Residual MLP (overfits at this data scale)
- Forward model / Monte Carlo simulation (uncalibrated mechanics add noise)
- Terrain-aware A* distance (mountains never create barriers on competition maps)
- Per-cell observation blending with ML model (noisy discrete observations add noise)
