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
- Binary forest adjacency for settlements, coastal-only for ports (~25-28 buckets)
- Coastal adjacency for plains and settlements
- Adjacent forest for plains, empty cells
- 3-level adjacent settlement for forest (0/1/2+), interior flag (adj_forest≥4)
- Adjacent settlement for ruin cells
- BFS-precomputed distances for efficiency
- Bayesian smoothing towards global prior (K=5)

**Post-model adjustments (applied after spatial model, before floor)**:
- Port probability boost: coastal cells near settlements (d≤3) get minimum 5%/3% Port mass
- Winter severity calibration: estimate settlement survival rate from observations, scale predictions
- Continuous distance interpolation: blend between adjacent distance brackets based on raw distance
- Expansion modulation (Step 1.75): scale Settlement+Port predictions for d≤8 cells, wider clamp [0.3, 3.5]
- Forest entropy injection (Step 1.85): shrink over-confident Forest predictions when observed retention < 0.85
- Distance-based temperature scaling (Step 1.8): T=1.10 near settlements (spread), T=0.92 far (sharpen)

**Adaptive smoothing**: Per-cell blending uses terrain-dependent k values:
- Settlements/ports k=8 (high variance → trust model more)
- Plains/forest/empty k=3 (predictable → trust observations more)

**Backtest performance** (weighted KL, lower is better):
- Rounds 1–12 avg: ~0.0446
- Best: 0.018 (R8), Worst: 0.121 (R12), 0.101 (R7)
- Rounds 1–6 avg: ~0.038
- Probability floor: 0.001 (optimized down from 0.003)

**Settlement cluster density** (Phase 4f):
- Binary `is_clustered` (≥2 settlements within Manhattan d≤5) added to Settlement, Plains, and Forest bucket keys
- Helps most on harsh winter rounds (R7: 0.147→0.142)

**Settlement stats extraction** (Phase 4g):
- Parses food/population/wealth from simulate query responses
- Modulates winter calibration scale based on avg food (±20%)
- Schema discovery pending (rate-limited), wired but no-op until confirmed

**Forward model** (Phase 4h):
- Rate estimation functions implemented (expansion, port_formation, forest_reclamation, ruin)
- Physics-based forward probabilities computed but NOT applied in production
- Backtesting showed consistent regression — bucket model is more accurate
- Code kept for potential future use with better rate formulas

**Known issues**:
- Plains cells are largest error source (~60% of KL loss)
- R7 and R12 are 2-3x worse than other rounds (KL ~0.10-0.12) — moderate expansion rounds
- Within-bucket variance is the dominant remaining error source
- Forward model doesn't improve on data-driven bucket model
- Post-model adjustments have diminishing returns — need better features for next step change
- Gap to top teams: ~11 raw points (we score ~82, top teams ~93)

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

### Backtest with regression detection (requires API, ~30s)
```bash
python3 test_backtest.py --output results.json                      # generate baseline
python3 test_backtest.py --output results.json --baseline baseline.json  # compare
```
- Outputs machine-readable JSON with per-round, per-terrain, and per-cell diagnostics
- `--baseline baseline.json` compares against saved results, fails (exit 1) on regression
- `--threshold 0.10` controls per-round regression sensitivity (default 10% relative)
- Exit codes: 0 = pass, 1 = regression, 2 = error

### Overnight self-improvement loop sequence
```bash
# 1. Make model change
# 2. Fast gate (< 1s):
pytest test_predictor_unit.py test_predictor_integration.py -x --tb=short
# 3. Backtest gate (~30s):
python3 test_backtest.py --output results.json --baseline baseline.json --threshold 0.10
# 4. If improved: cp results.json baseline.json
# 5. If active round: python3 test_local.py --submit
```
Key: step 2 catches broken logic instantly; step 3 catches regressions against real GT.
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
