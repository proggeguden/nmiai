# Astar Island — Roadmap

## Completed Work

### Phase 1: MVP Pipeline
- [x] Project scaffold (FastAPI, api_client, predictor, test_local)
- [x] Correct API endpoints (simulate, submit, my-rounds, my-predictions, analysis, leaderboard)

### Phase 2: Transition Model
- [x] P(final_class | initial_terrain_code) from observations
- [x] Per-cell blending: observed cells mix local counts with global model
- [x] Smart query allocation: skip static tiles, prioritize settlement-heavy areas

### Phase 3: Spatial Feature Model
- [x] Spatial bucketing: P(class | terrain_code, spatial_features)
- [x] 3-level Manhattan distance to nearest settlement (≤2, 3-4, 5+)
- [x] Coastal adjacency, adjacent forest/settlement for settlement/port cells
- [x] Multi-seed observation: 10 queries per seed across all 5 seeds
- [x] BFS-precomputed distances for efficiency
- [x] ~14 spatial buckets with fallback to global model if <10 observations

### Phase 3.5: Richer Features + Smoothing (Round 7 submission)
- [x] Graduated forest adjacency (0/1/2/3+) for settlements/ports
- [x] Forest adjacency for plains, empty, ruin cells
- [x] Settlement adjacency for forest, ruin cells
- [x] Coastal flag for settlements
- [x] Adaptive k per terrain type (settlements k=8, plains/forest k=3)
- [x] Bayesian bucket smoothing (K=5) blends sparse buckets towards global prior
- [x] Cross-seed query allocation proportional to settlement density
- [x] ~30 spatial buckets (up from 14)

### Backtest Results (5-seed spatial, weighted KL — lower is better)
| Round | Phase 3 (R6) | Phase 3.5 (R7) | Delta | Notes |
|-------|-------------|---------------|-------|-------|
| 1     | 0.0671      | 0.0664        | -0.001 | |
| 2     | 0.0500      | 0.0495        | -0.001 | |
| 3     | 0.0747      | 0.0666        | -0.008 | Harsh winter — biggest improvement |
| 4     | 0.0396      | 0.0392        | -0.000 | Best round, already good |
| 5     | 0.0715      | 0.0706        | -0.001 | |
| 6     | 0.0643      | 0.0641        | -0.000 | |
| **Avg** | **0.0612** | **0.0594**  | **-0.002** | |

### Key Insights
- **Hidden params are unique per round** — historical priors don't help, must learn fresh
- **Multi-seed observation beats single-seed** on 4/5 rounds (more diverse terrain coverage)
- **Distance-to-settlement is the strongest spatial feature** — settlement proximity drives expansion, food, and survival
- **Settlement survival ranges 2–44%** across rounds depending on hidden params
- **4-level distance buckets hurt** — fragments data too much, especially for harsh-winter rounds
- **Forest adjacency on empty cells helps a lot for harsh winters** (forest reclamation)
- **Bayesian smoothing helps more than hard min-obs threshold** — prevents overfitting sparse buckets

### Scoring Context
- Our round 5 score: 13.1/100 (naive predictor, submitted before model was ready)
- Round 6 score: **78.5** (rank 28/186) — first real submission with spatial model
- Round 7: submitted with Phase 3.5 improvements (score pending)
- Top teams: ~115-119 weighted score → ~80-87+ raw per round
- Gap to close: ~5-10 raw points per round. Current backtest avg KL ~0.059; need ~0.04

---

## Phase 4: Close the Gap to Top Teams (NEXT)

Gap: ~5-10 raw points per round. Need avg KL from ~0.059 to ~0.04.
Top teams score 80-87+ per round consistently.

### What we tried in Round 7 and what we learned:
- **Graduated forest adjacency (0/1/2/3+)**: Tiny improvement, forest count matters less than presence
- **Forest adjacency on empty/ruin cells**: **Big win** for harsh winters (R3: 0.075→0.067)
- **4-level distance buckets**: **Consistently hurts** — fragments data, R5 regressed 15%. Don't try again.
- **Bayesian bucket smoothing (K=5)**: Small but consistent wins. K=20 was too aggressive.
- **Adjacent mountain**: No effect (counted but unused in bucket keys currently)

### 4a. Continuous distance interpolation (HIGH IMPACT — UNTRIED)
**Problem**: 3 discrete distance buckets lose info. 4 buckets fragment. Solution: interpolate.

**Approach**: For a cell at distance d=3.5, blend between bucket-1 (≤2) and bucket-2 (3-4)
distributions using linear interpolation. This gives smooth distance effects without
creating more buckets.

Implementation:
1. Compute raw distance d for each cell
2. Find two nearest bucket boundaries
3. Interpolate: `pred = w * bucket_near + (1-w) * bucket_far` where w = fractional position
4. Apply per bucket key (distance is just one component)

**Why this might work**: It gives us the equivalent of infinite distance buckets without
any data fragmentation. The backtest showed 4 levels helped R3 dramatically (0.075→0.041)
but killed R5 — interpolation would capture the R3 gains without the R5 regression.

### 4b. Settlement cluster density (HIGH IMPACT — UNTRIED)
Count settlements within radius 3-5 (from initial grid). Dense clusters have more
conflict (raids) + trade → different survival curves than isolated settlements.
Binary feature: `dense_cluster = settlements_within_r5 >= 3`.

### 4c. Viewport optimization: smaller viewports for more observations (HIGH IMPACT)
**Problem**: 15×15 viewports × 10 queries = 2250 cells observed per seed. But with
10×10 viewports, we get 10×100 = 1000 cells but can observe settlement-heavy areas
3-4 times instead of 1-2 times. More observations per cell = better per-cell blending.

**Approach**: Use 10×10 viewports for repeat queries on settlement-heavy tiles.
The model already handles per-cell blending — more observations would directly help.

### 4d. Exploit settlement stats from simulate responses (MEDIUM IMPACT)
Parse population/food/wealth/defense from simulate response. Use average food level
as soft signal for settlement survival. High food → survives winter → stays Settlement.
Low food → collapses → becomes Ruin/Empty/Forest.

**Risk**: Noisy with only ~2 observations per cell. Maybe useful as tie-breaker.

### 4e. Simulation-informed priors (HIGH EFFORT, HIGH REWARD)
Build a lightweight forward model:
1. Estimate food supply per settlement (count adj forests)
2. Estimate winter severity from observation data (what % of settlements collapsed?)
3. Use estimated severity to adjust all settlement survival probabilities
4. This directly addresses the biggest variance source (winter severity)

The key insight: **winter severity is the same for all cells in a round**. If we can
estimate it from our observations (e.g., 30% of observed settlements survived → harsh winter),
we can shift ALL settlement predictions accordingly, even for unobserved cells.

### 4f. Deploy to Cloud Run (DO WHEN MODEL IS GOOD)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

### Priority for Round 8
1. **4a** — Continuous distance interpolation (best risk/reward)
2. **4e winter severity estimation** — global calibration from observations
3. **4c** — Smaller viewports for settlement areas
4. **4b** — Settlement cluster density

---

## Simulation Phase Summary (for modeling reference)

Each of 50 years runs these phases in order:
1. **Growth** — food from adjacent terrain, population growth, port development, expansion
2. **Conflict** — raids (longships extend range), desperate raids if low food, allegiance changes
3. **Trade** — ports trade if not at war, generates wealth+food, tech diffusion
4. **Winter** — severity varies (hidden param!), food loss, collapse → Ruin
5. **Environment** — forest reclaims ruins, settlements reclaim/rebuild nearby ruins, unreclaimed ruins → forest/plains

Key dynamics:
- Settlement survival = f(food from forests, winter severity, raid exposure)
- Expansion = f(prosperity, available nearby land)
- Port formation = f(coastal position, settlement prosperity)
- Ruin fate = f(nearby settlement strength, time) → either reclaimed or overgrown

---

## How to Iterate

### Workflow for each improvement:
1. Make the code change in a worktree
2. Run `python3 test_local.py --backtest all` — compare all 4 model variants
3. Keep only if 5seed-Spatial improves on avg without regressing any round >5%
4. Commit and merge

### When a new round starts:
```bash
python3 test_local.py --list-rounds          # find the active round
python3 test_local.py --round ROUND_ID       # quick test (uses 4 queries)
python3 test_local.py --submit               # full pipeline: 50 queries + submit
```

### After a round completes:
```bash
python3 test_local.py --my-rounds            # check our score and rank
python3 test_local.py --backtest ROUND_ID    # compare our model vs ground truth
python3 test_local.py --backtest all         # backtest all completed rounds
python3 test_local.py --leaderboard          # check standings
```

### To debug a specific round:
```python
import api_client, numpy as np
# Get ground truth
analysis = api_client.get_analysis(round_id, seed_index)
gt = np.array(analysis['ground_truth'])
pred = np.array(analysis['prediction'])  # our submitted prediction

# Compare
kl = np.sum(gt * np.log((gt + 1e-10) / (pred + 1e-10)), axis=2)
# Look at worst cells
worst = np.unravel_index(kl.argmax(), kl.shape)
print(f"Worst cell: {worst}, KL={kl[worst]:.4f}")
print(f"  GT: {gt[worst]}")
print(f"  Pred: {pred[worst]}")

# Check our predictions with confidence
preds = api_client.get_my_predictions(round_id)
```
