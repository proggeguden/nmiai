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
**Current approach**: Allocate queries proportional to settlement density across all 5 seeds →
learn spatial transition model P(final_class | bucket_key) with Bayesian smoothing → apply to all seeds.
Per-cell observations blended with adaptive k (terrain-dependent).

**Why this works**: Hidden parameters are shared across all seeds. More seeds give
more diverse terrain layouts → better spatial bucket coverage → better model.

**Key spatial features (implemented)**:
- Manhattan distance to nearest settlement: 3-level bucket (≤2, 3-4, 5+) with continuous interpolation
- Settlement cluster density: binary `is_clustered` for Settlement and Plains bucket keys
- Binary forest adjacency for settlements, coastal-only for ports
- Coastal adjacency for plains and settlements
- Adjacent forest for plains, empty cells
- 3-level adjacent settlement for forest (0/1/2+), interior flag (adj_forest≥4)
- Adjacent settlement for ruin cells
- BFS-precomputed distances for efficiency
- Bayesian smoothing towards global prior (K=3-10 per terrain)

**Post-model adjustments (applied after spatial model, before floor)**:
- Rate-adaptive port calibration (Step 1.5): uses observed port_formation_rate to scale port minimums for coastal cells d≤5. Conservative multipliers (1.0x near, 0.5x mid, cap 25%/15%).
- Winter severity calibration (Step 1.6): estimate survival rate from observations, scale settlement/port predictions. Harsh winter → boost Ruin+Forest.
- Continuous distance interpolation: blend between adjacent distance brackets based on raw distance
- Expansion modulation (Step 1.75): 30% dampened correction (not full override) of Settlement+Port predictions for d≤8 cells, clamp [0.7, 1.5]. The spatial model already encodes expansion from observations — full override was double-counting.
- Forest entropy injection (Step 1.85): shrink over-confident Forest predictions when observed retention < 0.85
- Distance-based temperature scaling (Step 1.8): T=1.10 near settlements (spread), T=0.92 far (sharpen)
- Monte Carlo blending (Step 2.5): DISABLED — hurts +1.1% in simulated production due to uncalibrated mechanics.

**Query strategy**: Full coverage first, then repeats. All unique tile positions queried (sorted by settlement density), remaining queries repeat top tiles. Every query MUST be used. Rate-limit retry with backoff on 429 errors.

**Adaptive smoothing**: Per-cell blending uses terrain-dependent k values:
- Settlements k=8 (high variance → trust model more)
- Ports k=15 (very few observations per cell → trust model much more)
- Plains/forest/empty k=3 (predictable → trust observations more)

**Backtest performance** (simulated-production KL, lower is better):
- Rounds 1–14 avg: **0.0612** (simulated production, 3 runs)
- Best: 0.033 (R8), 0.041 (R4), Worst: 0.119 (R12), 0.102 (R7)
- Oracle backtest avg: 0.044 (but misleading — see below)
- Probability floor: 0.0005

**CRITICAL: Use simulated-production backtest for validation, not oracle.**
The oracle backtest trains on full GT distributions and evaluates on same data.
Simulated-production (`--simulate-production`) has rho=0.964 rank correlation
with actual production scores; oracle only has rho=0.750.
Oracle improvements can be production regressions (confirmed empirically).

**Known issues**:
- Plains cells are largest error source (~60% of KL loss) — within-bucket variance
- R7 and R12 are 2-3x worse than other rounds — high-survival, high expansion
- Gap to top teams: ~10-15 raw points (we score ~74-82, top teams ~89-94)

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
