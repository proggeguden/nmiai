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

### Competitive Position
- R6 score: 78.5 (rank 28/186). Top teams: 80-87+ per round.
- Leaderboard = **best round score × round weight**. Weights compound 5%/round.
- R8 weight ≈ 1.48. Scoring **85 on R8 → weighted 125.8 → #1 on leaderboard**.
- Even **80 on R8 → weighted 118.2 → top 3**.
- So a 5-7 point improvement wins the whole thing.

### Round 6 Error Analysis (where we actually lose points)
| Source | Share of total KL loss | What goes wrong |
|--------|----------------------|-----------------|
| **Plains** (code 11) | **55.7%** | Misjudge Empty/Settlement/Forest balance near settlements |
| **Forest** (code 4) | **30.1%** | Underestimate Port creation on coast, miss expansion |
| Settlement (code 1) | 3.6% | Per-cell KL high (0.14) but few cells |
| Port (code 2) | 0.7% | Extremely high per-cell KL (0.83!) but only ~5 cells |

**97.7% of weighted KL comes from medium+high entropy cells** (settlements, nearby plains/forest).
Static cells are essentially free points.

**Key systematic error: Port probability is under-predicted everywhere.**
GT shows 17-29% Port probability at many coastal cells, but our model assigns near-zero.

### What we tried in Round 7 and what we learned:
- **Graduated forest adjacency (0/1/2/3+)**: Tiny improvement
- **Forest adjacency on empty/ruin cells**: **Big win** for harsh winters (R3: 0.075→0.067)
- **4-level distance buckets**: **Consistently hurts** — fragments data, don't try again
- **Bayesian bucket smoothing (K=5)**: Small but consistent wins. K=20 too aggressive.

---

### 4a. Fix viewport position bug (FREE POINTS — implement first)
**Bug**: Current viewport positions `[0, 15, 30]` for a 40-wide grid waste capacity.
Viewport at x=30 only covers 10 cells (30-39) despite having capacity for 15.

**Fix**: Use positions `[0, 15, 25]` instead. Last viewport covers 25-39 (full 15 cells).
Overlap at x=25-29 gives those cells double observations for free.

**Impact**: +425 cell-observations per coverage pass (+26%). Every cell in the
overlap band gets observed twice instead of once. Zero cost.

### 4b. Continuous distance blending in prediction (HIGH IMPACT)
**Problem**: 3 discrete distance buckets lose info. 4 buckets fragment. Interpolation
captures both benefits.

**Approach**: At prediction time (not training), for each cell with distance d:
1. Look up bucket distributions for the two adjacent distance brackets
2. Linearly interpolate based on actual distance
3. E.g., d=4 is midway between bracket-1 (≤4) and bracket-2 (5+) → blend 50/50

This is done in `build_prediction`, NOT in bucket training. Buckets stay at 3 levels,
no fragmentation. But predictions get smooth distance curves.

### 4c. Estimate winter severity → global calibration (HIGH IMPACT)
**Key insight**: Winter severity is the single biggest source of round-to-round variance.
It's a hidden parameter shared across all cells AND all seeds. If we estimate it, we
can calibrate ALL predictions at once.

**Implementation**:
1. From initial grids (free): count initial settlements across all 5 seeds (~200+)
2. From observations: check how many initial-settlement positions are still settlements
3. `survival_rate = still_settlement / observed_initial_settlements`
4. This is a precise estimate (200+ samples)
5. Use survival_rate to scale settlement probability in predictions:
   - If our bucket says P(Settlement)=0.40 but survival_rate=0.15 (harsh)
     → scale down: `P_adj = P * (survival_rate / bucket_survival_rate)`
   - Redistribute mass to Empty/Forest/Ruin proportionally

This is NOT about building a simulator. It's a one-number global calibration that fixes
the biggest variance source.

### 4d. Port probability fix (TARGETED — fixes systematic error)
The error analysis shows Port is catastrophically under-predicted (per-cell KL=0.83).

**Root cause**: Ports are rare in initial grid (~5 per seed). Our bucket model sees
few port creations. Bayesian smoothing pulls the already-low Port mass towards zero.

**Fix options**:
1. Add explicit Port-formation features: `(is_coastal AND dist_to_settlement ≤ 2)` → boost Port prior
2. In bucket smoothing, use terrain-specific priors that include Port probability for
   coastal cells (not the global prior, which has ~0% Port)
3. When blending, set a minimum Port probability (e.g., 0.03) for any coastal cell
   near a settlement

### 4e. Settlement cluster features (MEDIUM IMPACT)
Count settlements within Manhattan distance 5 in initial grid. Discretize: isolated (0-1),
small (2-3), dense (4+). Dense clusters survive more (trade) but also collapse more (raids).

Use as feature in plains/forest/settlement bucket keys.

### 4f. Settlement stats from query responses (MEDIUM IMPACT — unused data)
The simulate endpoint returns settlement stats (food, population, defense, wealth)
that we currently **completely ignore**. The observation dict has a `settlements` key.

**Use**: Average food level of observed settlements → signal for settlement survival.
Settlements with avg food < threshold → predict collapse. Could help per-cell blending
for settlement cells specifically.

### 4g. Lightweight forward model (HIGH EFFORT, TRANSFORMATIVE)
Not a full simulator — just calibrate 3-4 key rates from observations:
1. **Settlement survival rate** (from 4c above)
2. **Expansion rate**: how many new settlements formed / initial settlements
3. **Port formation rate**: new ports / coastal settlements
4. **Forest reclamation rate**: forest cells gained / ruin+empty cells near forest

Then for each cell, compute:
- P(Settlement) = f(initial_code, distance, survival_rate, expansion_rate)
- P(Port) = f(is_coastal, distance, port_formation_rate)
- P(Forest) = f(adj_forest, distance, reclamation_rate)
- P(Empty) = 1 - sum(above) - P(Ruin) - P(Mountain)

This would be a parametric model calibrated per-round instead of a nonparametric bucket model.

### 4h. Deploy to Cloud Run (DO WHEN MODEL IS GOOD)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

---

### Priority for Round 8 (ordered by expected impact / effort)
| # | Change | Expected gain | Effort |
|---|--------|---------------|--------|
| 1 | **Fix viewport positions** (4a) | ~2 pts (more observations) | 10 min |
| 2 | **Winter severity calibration** (4c) | ~3-5 pts (fixes biggest variance source) | 1 hr |
| 3 | **Port probability fix** (4d) | ~2-3 pts (fixes systematic error) | 30 min |
| 4 | **Continuous distance blend** (4b) | ~2-3 pts (smooth distance effects) | 1 hr |
| 5 | **Settlement cluster features** (4e) | ~1-2 pts | 30 min |
| 6 | **Parse settlement stats** (4f) | ~1 pt | 30 min |

Items 1-4 together could yield ~10 points → score ~88 → **#1 on leaderboard**.

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
