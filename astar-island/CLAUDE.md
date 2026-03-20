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
- Manhattan distance to nearest settlement: 3-level bucket (≤2, 3-4, 5+)
- Graduated forest adjacency (0/1/2/3+) for settlements/ports
- Coastal adjacency for plains and settlements
- Adjacent forest for plains, empty, ruin cells
- Adjacent settlement for forest, ruin cells
- BFS-precomputed distances for efficiency
- ~30 spatial buckets with Bayesian smoothing towards global prior (K=5)

**Adaptive smoothing**: Per-cell blending uses terrain-dependent k values:
- Settlements/ports k=8 (high variance → trust model more)
- Plains/forest/empty k=3 (predictable → trust observations more)

**Backtest performance** (weighted KL, lower is better):
- Rounds 1–6 avg: ~0.059 (5-seed spatial model)
- Best: 0.039 (round 4), Worst: 0.071 (round 5)

**Known issues**:
- Port probability is systematically under-predicted (per-cell KL 0.83!)
- Plains cells cause 55.7% of total KL loss; forest cells 30.1%
- Viewport positions waste 26% of observation capacity (bug: last tile at x=30 not x=25)
- Settlement stats from query responses are completely unused

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
| File             | Purpose                                    |
|------------------|--------------------------------------------|
| `main.py`        | FastAPI app with /solve endpoint           |
| `api_client.py`  | API client for astar-island endpoints      |
| `predictor.py`   | Prediction logic (observations → tensor)   |
| `test_local.py`  | Local testing against real API             |

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

## Scoring
- Entropy-weighted KL divergence
- Only dynamic cells (those that change between sim runs) count
- Higher entropy cells count more
- Score is normalized: 1.0 = perfect, 0.0 = worst
- Critical: probability floor of 0.01, or KL divergence → infinity
