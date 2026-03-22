# Astar Island — Norse World Prediction

## Task Summary
Observe a black-box Norse civilisation simulator through limited viewport queries,
then predict the probability distribution of terrain types across the full map.
Scored on entropy-weighted KL divergence — only dynamic cells matter.

## How It Works
1. A round starts with 5 seeds (different terrain layouts, same hidden parameters)
2. Each seed has an initial 40×40 grid + settlements
3. You get max 50 queries total — each returns a viewport after simulation of 50 years
4. Each query uses a different random sim seed → different stochastic outcome
5. Submit a W×H×6 probability tensor per seed predicting terrain distributions
6. Your score is based on how well your predictions match ground truth

## Terrain Types
| Internal Code | Terrain    | Class Index | Description                              |
|--------------|-----------|-------------|------------------------------------------|
| 10           | Ocean     | 0 (Empty)   | Impassable water, borders the map        |
| 11           | Plains    | 0 (Empty)   | Flat land, buildable                     |
| 0            | Empty     | 0 (Empty)   | Generic empty cell                       |
| 1            | Settlement| 1           | Active Norse settlement                  |
| 2            | Port      | 2           | Coastal settlement with harbour          |
| 3            | Ruin      | 3           | Collapsed settlement                     |
| 4            | Forest    | 4           | Provides food to adjacent settlements    |
| 5            | Mountain  | 5           | Impassable, static (never changes)       |

**6 Prediction Classes**: Empty(0), Settlement(1), Port(2), Ruin(3), Forest(4), Mountain(5)

## Simulation Mechanics (50 years, 5 phases per year)

### Map Generation (from map seed — visible to us)
- Ocean borders surround the map
- Fjords cut inland from random edges
- Mountain chains form via random walks
- Forest patches cover land with clustered groves
- Initial settlements placed on land cells, spaced apart

### Phase 1: Growth
- Settlements produce food based on **adjacent terrain** (forests provide food!)
- Prosperous settlements grow population, develop ports along coastlines, build longships
- Settlements expand by founding **new settlements on nearby land**

### Phase 2: Conflict
- Settlements raid each other; longships extend raiding range
- Desperate settlements (low food) raid more aggressively
- Successful raids loot resources and damage defender
- Conquered settlements can change allegiance (owner_id changes)

### Phase 3: Trade
- Ports within range trade if not at war
- Trade generates wealth and food for both parties
- Technology diffuses between trading partners

### Phase 4: Winter
- Each year ends with winter of **varying severity** (hidden parameter!)
- All settlements lose food
- Settlements collapse from starvation, raids, or harsh winters → become **Ruins**
- Population disperses to nearby friendly settlements

### Phase 5: Environment
- Forests **reclaim abandoned land** (ruins → forest if no settlement reclaims)
- Nearby thriving settlements **reclaim/rebuild ruined sites** → new outposts
- Coastal ruins can be restored as ports
- Unreclaimed ruins eventually become forest or plains

### Settlement Properties (visible in query results)
position, population, food, wealth, defense, tech level, port status, longship ownership, faction (owner_id)

**Initial states only show position + port status. Full stats visible only via simulate queries.**

## Key Concepts
- **Map seed**: Determines terrain layout (fixed per seed, visible to us)
- **Sim seed**: Random seed for simulation run (different every query)
- **Hidden parameters**: Control world behavior — winter severity, expansion rate, etc. (same for all seeds in a round)
- **Entropy weighting**: Static cells (ocean, mountain) excluded from scoring
- **Probability floor**: NEVER assign 0.0 — use floor (0.01) and renormalize
- **Query budget is SHARED** across all seeds — 50 total
- **Viewport is controllable**: viewport_x, viewport_y, viewport_w (5–15), viewport_h (5–15)
- **Rate limit**: max 5 req/sec

## Prediction Strategy

**Current approach (wide ML ensemble)**: 5-snapshot wide MLP ensemble trained on GT data
from all completed rounds. Each snapshot is the same architecture trained with a different
torch seed. Predictions are the average of all 5 softmax outputs — reduces variance.
32 features per cell, noisy rate augmentation for production robustness.
Numpy-only inference (990KB weights). Per-cell observation blending DISABLED.
Survival-conditional temperature: T=0.85 when estimated survival < 10%.
Auto-detects feature count from weights for backward compatibility.

**Pipeline**:
1. Observe all 5 seeds (50 queries total, 10 per seed, full coverage)
2. Estimate round-level rates from observations (survival, expansion, port, forest, ruin, forest_clearing)
3. ML ensemble: extract 32 features per cell → numpy_forward_ensemble (avg 5 snapshots)
4. Probability floor (0.0005)
5. NO per-cell blending (disabled — ML model is accurate enough)

**ML model details** (`ml_predictor.py` + `train_model.py`):
- 32 features: 6 terrain one-hot + 12 spatial + 5 round rates + 4 rate interactions + 3 distance interactions + forest_clearing_rate + 1 distance
  - Spatial: dist_settlement, coastal, adj_forest/settlement/ocean/mountain/ruin, cluster, interior, settlement_count_r3/r5, forest_density_r2, dist_to_forest, dist_to_coast
  - Rate interactions: survival×expansion, survival/expansion, expansion×port, expansion×invdist, survival×invdist, expansion×sett_r3
  - New: forest_clearing_rate (P(non-forest | initially forest) estimated from observations)
- Architecture: Input(32) → 256 → 128 → 64 → Softmax(6), KL divergence loss
- Ensemble: 5 snapshots with different torch seeds, averaged softmax at inference
- Training: 1.1M cells from 21 rounds × 5 seeds × 10 noisy rate augmentations
- Weights: `model_weights.npz` (990KB, committed to git)
- Production inference: numpy matmuls only, zero PyTorch dependency
- Retrain after each round: `rm training_data.npz && python3 train_model.py --rebuild-data --augmentations 10 --n-snapshots 5 --output model_weights.npz`

**Backtest performance** (simulated-production KL, lower is better):
- Wide ML ensemble: R21 SimProd KL **0.0177** — **32% better than old 28-feat ensemble (0.0260), 48% better than single model (0.0341)**
- Probability floor: 0.0005

**Known dead ends** (do NOT retry):
- MRF-style spatial smoothing (blurs across terrain boundaries, +10% regression)
- Focused/repeat query strategy (less coverage = worse buckets, -5 to -23%)
- Extra bucket features with 50 queries (more buckets = less data per bucket)
- Terrain-aware A* distance (mountains never create barriers on competition maps)
- Forward model / Monte Carlo sim (uncalibrated mechanics add noise, +1.1%)
- TTA via rate perturbation (model already trained on noisy rates, double-perturbing adds noise)
- Post-hoc temperature scaling (T=1.0 already optimal — KL-trained model is self-calibrated)
- Per-cell observation blending with ML model (noisy discrete obs add noise, -6.6% when disabled)
- LightGBM distillation (MLP is 2x better than LightGBM on this task — strictly dominates)
- Residual MLP (worse than plain Wide due to overfitting at this data scale)
- Narrow MLP 128→64→32 (wide 256→128→64 is 17% better with same training)

**Bucket model (fallback)**: Still in predictor.py as `build_prediction()`. ML model in
`build_prediction_ml()`. main.py auto-selects ML if `model_weights.npz` exists.

**CRITICAL: Use simulated-production backtest for validation, not oracle.**
Simulated-production has rho=0.964 rank correlation with actual production scores; oracle only 0.750.

**Retraining**: After each round completes, retrain on all GT data:
```bash
rm training_data.npz  # force rebuild with new round
python3 train_model.py --augmentations 10 --output model_weights.npz
python3 test_backtest.py --simulate-production --sim-runs 3 --model ml --output ml_results.json
```

See `PLAN.md` for error analysis, improvement roadmap, and round-by-round changelog.

## API
- **Base URL**: `https://api.ainm.no`
- **Auth**: Bearer token (JWT from app.ainm.no cookies)
- **Endpoints**:
  - `GET /astar-island/rounds` — list all rounds (public)
  - `GET /astar-island/rounds/{round_id}` — detail with initial states for all seeds
  - `POST /astar-island/simulate` — run simulation, observe viewport (1 query, max 5 req/sec)
    - Body: `{round_id, seed_index, viewport_x, viewport_y, viewport_w (5–15), viewport_h (5–15)}`
    - Returns: grid (viewport region), settlements (with full stats), viewport bounds, queries_used/max
  - `POST /astar-island/submit` — submit prediction for one seed (resubmit overwrites)
    - Body: `{round_id, seed_index, prediction}` — prediction is H×W×6 tensor
  - `GET /astar-island/my-rounds` — team rounds with scores, ranks, query usage
  - `GET /astar-island/my-predictions/{round_id}` — submitted predictions with argmax/confidence grids
  - `GET /astar-island/analysis/{round_id}/{seed_index}` — prediction vs ground truth (after round completes)
  - `GET /astar-island/leaderboard` — public leaderboard (weighted_score, hot_streak_score)

## Stack
- Python + FastAPI + NumPy
- Cloud Run (GCP) for deployment

## Key Files
| File                          | Purpose                                         |
|-------------------------------|--------------------------------------------------|
| `main.py`                     | FastAPI app with /solve endpoint                |
| `api_client.py`               | API client for astar-island endpoints           |
| `predictor.py`                | Prediction logic (observations → tensor)        |
| `test_local.py`               | Local testing against real API                  |
| `test_predictor_unit.py`      | 39 unit tests, synthetic data, no network (<1s) |
| `test_predictor_integration.py` | 27 integration tests, synthetic data, no network (<1s) |
| `test_backtest.py`            | Enhanced backtest: JSON output, per-terrain KL, regression detection |

## Running Locally
```bash
cp .env.example .env  # add ACCESS_TOKEN
pip3 install -r requirements.txt
python3 test_local.py                    # full pipeline test
python3 test_local.py --submit           # full pipeline + submit
python3 test_local.py --backtest all     # backtest against ground truth
python3 test_local.py --my-rounds        # check scores
python3 -m uvicorn main:app --port 8080  # run server
```

## Testing

### Offline tests (no API needed, < 1s total)
```bash
pytest test_predictor_unit.py test_predictor_integration.py -v
```
- Unit tests cover every public function in predictor.py with synthetic grids
- Integration tests verify end-to-end pipeline properties (sum-to-1, floor, shape, ordering)
- Safe to run on every code change — deterministic and fast

### Simulated-production backtest (requires API, ~5 min) — USE THIS FOR VALIDATION
```bash
python3 test_backtest.py --simulate-production --sim-runs 5 --output sim_results.json
```
- Samples discrete terrain from GT distributions, limits to 50 queries with viewport strategy
- Runs the full production pipeline: learn_spatial_transition_model → build_prediction
- **rho=0.964 rank correlation with actual production scores** (oracle only 0.750)
- Outputs comparison table of oracle vs simulated-production KL per round
- This is the ONLY reliable way to validate model changes before submission

### Oracle backtest with regression detection (requires API, ~30s)
```bash
python3 test_backtest.py --output results.json                      # generate baseline
python3 test_backtest.py --output results.json --baseline baseline.json  # compare
```
- Trains on full GT distributions — useful as ceiling but NOT for A/B testing changes
- Oracle improvements can be production regressions (confirmed empirically)
- Outputs machine-readable JSON with per-round, per-terrain, and per-cell diagnostics
- `--baseline baseline.json` compares against saved results, fails (exit 1) on regression
- `--threshold 0.10` controls per-round regression sensitivity (default 10% relative)
- Exit codes: 0 = pass, 1 = regression, 2 = error

### Overnight self-improvement loop sequence
```bash
# 1. Make model change
# 2. Fast gate (< 1s):
pytest test_predictor_unit.py test_predictor_integration.py -x --tb=short
# 3. Simulated-production gate (~5 min):
python3 test_backtest.py --simulate-production --sim-runs 3 --output sim_results.json
# 4. If improved: cp sim_results.json sim_baseline.json
# 5. If active round: python3 test_local.py --submit
```
Key: step 2 catches broken logic instantly; step 3 validates in realistic production conditions.
The JSON output includes `per_terrain_kl` (which terrain types improved/regressed),
`worst_cells` (top 10 worst-predicted cells with bucket keys), and `model_variants`
(comparison of spatial vs spatial+forward). Parse these to guide the next hypothesis.

## Scoring
- Entropy-weighted KL divergence
- Only dynamic cells (those that change between sim runs) count
- Higher entropy cells count more
- Score is normalized: 1.0 = perfect, 0.0 = worst
- Critical: probability floor of 0.01, or KL divergence → infinity

## Weight System & Leaderboard
```
round_weight = 1.05 ^ round_number
leaderboard_score = max(round_score × round_weight) across all rounds
```

| Round | Weight | If score=82 | If score=85 | If score=90 |
|-------|--------|-------------|-------------|-------------|
| 8     | 1.478  | 121.2       | 125.6       | 133.0       |
| 10    | 1.629  | 133.6       | 138.4       | 146.6       |
| 12    | 1.796  | 147.3       | 152.6       | 161.6       |
| 13    | 1.886  | 154.7       | 160.3       | 169.7       |

**Key insight**: Later rounds are worth exponentially more. Even maintaining the same raw score on a later round dramatically improves leaderboard position.

## Overnight Autonomous Workflow

Three custom skills for autonomous overnight operation:

- `/astar-submit` — Check for active round, submit if not already submitted
- `/astar-analyze` — Analyze scores, backtest, identify improvement opportunities
- `/astar-improve` — Make one targeted predictor.py change, test, commit if improved

### Loop setup
```bash
# In separate terminal: prevent Mac sleep
caffeinate -dims

# Auto-submit every 10 minutes
/loop 10m /astar-submit

# Between rounds (~2.5h gap): iterate on model
/astar-analyze
/astar-improve  # repeat multiple times
```

### Self-improvement cycle (~2 min each)
1. Read baseline.json → identify dominant error pattern
2. Make ONE change to predictor.py
3. Fast gate: `pytest test_predictor_unit.py test_predictor_integration.py -x` (<1s)
4. Backtest gate: `python3 test_backtest.py --output results_improve.json --baseline baseline.json` (~30s)
5. If improved: `cp results_improve.json baseline.json && git commit`
6. If regressed: `git checkout -- predictor.py` and try different approach
