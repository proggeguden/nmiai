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

### Backtest Results (5-seed spatial, weighted KL — lower is better)
| Round | Weighted KL | Notes |
|-------|------------|-------|
| 1     | 0.067      | |
| 2     | 0.050      | |
| 3     | 0.075      | Harsh winter, everything collapses |
| 4     | 0.040      | Best performance |
| 5     | 0.072      | |

### Key Insights
- **Hidden params are unique per round** — historical priors don't help, must learn fresh
- **Multi-seed observation beats single-seed** on 4/5 rounds (more diverse terrain coverage)
- **Distance-to-settlement is the strongest spatial feature** — settlement proximity drives expansion, food, and survival
- **Settlement survival ranges 2–44%** across rounds depending on hidden params

### Scoring Context
- Our round 5 score: 13.1/100 (naive predictor, submitted before model was ready)
- Round 6: submitted with spatial model (score pending)
- Top teams: ~113 weighted score → ~80+ raw on best rounds
- Gap to close: ~65+ points. Current model is ~0.06 avg KL; top teams are likely ~0.01-0.02

---

## Phase 4: Close the Gap to Top Teams (NEXT)

The gap from ~0.06 to ~0.01 weighted KL requires fundamentally better modeling,
not just incremental feature tweaks. Here are the highest-leverage improvements,
ordered by expected impact.

### 4a. Per-cell model with smoothing (HIGHEST IMPACT)
**Problem**: Current bucket model pools all cells with same features into one distribution.
But cells at (5,10) and (20,30) may have very different outcomes even with the same bucket key
because they have different local contexts (specific neighbor configurations, faction proximity).

**Approach**: Build a per-cell prediction by combining:
1. **Per-cell empirical counts** from the ~2 observations of that specific cell (noisy but unbiased)
2. **Bucket model** as prior (pooled, smooth)
3. **Bayesian blending** with adaptive weight based on observation count

Current blending uses k=5.0 fixed. Tune this per-bucket or per-terrain-type.
- Settlements need higher k (more variable, bucket prior is valuable)
- Plains far from settlements need lower k (very predictable, empirical is good enough)

**How to test**: Backtest with varying k values per terrain type. Measure KL improvement.

### 4b. Richer spatial features without bucket explosion (HIGH IMPACT)
**Problem**: 14 buckets is too coarse. Top teams likely model continuous spatial effects.

**Approaches to try** (pick one, backtest, iterate):

1. **Graduated forest adjacency**: For settlements, count adj_forest 0/1/2/3+ instead of binary.
   More forest → more food → higher survival. This is a core simulation mechanic.

2. **Settlement cluster density**: Count settlements within radius 3-5. Dense clusters have
   more conflict (raids) but also more trade. This affects survival probability.

3. **Continuous distance interpolation**: Instead of 3 discrete distance buckets,
   interpolate between adjacent bucket distributions using actual distance.
   E.g., distance=2.5 → 50% near-bucket + 50% mid-bucket.

4. **Interaction features**: distance × coastal, distance × forest_count.
   But watch bucket sizes — need ≥30 observations per bucket.

**How to test**: Add one feature at a time. Run `--backtest all`. Keep only if it improves
avg KL without hurting any round by >5%.

### 4c. Observation-aware confidence calibration (HIGH IMPACT)
**Problem**: With only 10 queries per seed (2 per cell on avg), our per-cell counts
are very noisy. But the model doesn't know which cells it's confident about.

**Approach**:
- Track how many unique observations each cell got
- For cells with 0 observations: use bucket model only (no blending)
- For cells with 5+ observations: trust empirical more heavily
- For intermediate: smooth interpolation

Also: **viewport placement optimization** — instead of fixed 15×15 grid,
compute which viewport positions maximize information gain:
- Avoid ocean-dominated areas (no information)
- Overlap viewports on settlement-heavy areas for more samples
- Consider smaller viewports (e.g., 10×10) centered on dynamic areas to get
  more total observations from 10 queries

### 4d. Ensemble across query replays (MEDIUM IMPACT)
**Problem**: Each query gives one stochastic simulation outcome. Pooling counts
across queries works but doesn't capture the shape of the distribution well.

**Approach**: Instead of just counting classes, compute per-cell distributions
from each individual observation, then average them. This naturally handles
the case where a cell is Settlement 60% of the time and Ruin 40%.

Currently we already do this via counting. But we could:
- Weight more recent queries higher (if there's temporal variation)
- Detect bimodal distributions (cell is either Settlement OR Forest, rarely Empty)
  and model them explicitly

### 4e. Exploit settlement stats from simulate responses (MEDIUM IMPACT)
**Problem**: The simulate endpoint returns rich settlement data (population, food,
wealth, defense, tech_level, faction) that we currently ignore.

**Approach**:
- Group settlements by food level → high-food settlements survive more
- Group by faction → large factions may dominate, small ones collapse
- Group by defense level → well-defended settlements survive raids
- Use these as additional bucket features for settlement cells specifically

**Risk**: Stats are stochastic (vary per query), so need multiple observations
to estimate reliably. With only ~2 observations per cell, this may be noisy.

### 4f. Simulation-informed priors (LOW-MEDIUM IMPACT)
**Problem**: We treat the simulator as a pure black box. But we know the mechanics:
forests feed settlements, settlements expand, harsh winters kill, etc.

**Approach**: Build a lightweight forward model:
1. From initial grid, estimate food supply per settlement (count adj forests)
2. Estimate expansion targets (nearby empty/plains cells)
3. Use observation data to calibrate the forward model's parameters
4. Run the forward model to generate predictions

This is high-effort but could be transformative if done well. Top teams may
be doing something like this.

### 4g. Deploy to Cloud Run (DO WHEN MODEL IS GOOD)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

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
