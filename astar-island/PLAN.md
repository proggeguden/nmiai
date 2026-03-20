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
| Round | Phase 3 (R6) | Phase 3.5 (R7) | Phase 4 (R8) | Phase 4f+g (cluster+stats) | Notes |
|-------|-------------|---------------|-------------|---------------------------|-------|
| 1     | 0.0671      | 0.0664        | 0.0632      | 0.0620                    | |
| 2     | 0.0500      | 0.0495        | 0.0468      | 0.0456                    | |
| 3     | 0.0747      | 0.0666        | 0.0690      | 0.0690                    | Harsh winter |
| 4     | 0.0396      | 0.0392        | 0.0384      | 0.0380                    | Best round |
| 5     | 0.0715      | 0.0706        | 0.0718      | 0.0700                    | |
| 6     | 0.0643      | 0.0641        | 0.0615      | 0.0608                    | |
| 7     | —           | 0.1506        | 0.1468      | 0.1416                    | Very harsh winter |
| **Avg** | **0.0612** | **0.0594**  | **0.0568** (R1-6) | **0.0576** (R1-6)   | |

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
- Round 7 score: **60.36** (rank 83/199) — 18-point drop, very harsh winter round (7% survival)
- Round 8: submitted with Phase 4 improvements (score pending)
- Top teams: ~115-119 weighted score → ~80-87+ raw per round
- Gap to close: ~5-10 raw points per round

---

## Phase 4: Close the Gap to Top Teams

### Competitive Position
- R6 score: 78.5 (rank 28/186). R7 score: 60.36 (rank 83/199).
- Leaderboard = **best round score × round weight**. Weights compound 5%/round.
- R7 regression caused by harsh winter (7% survival) and observation sparsity.
- Phase 4 targets both issues with calibration and fewer buckets.

### Round 6 Error Analysis (where we actually lose points)
| Source | Share of total KL loss | What goes wrong |
|--------|----------------------|-----------------|
| **Plains** (code 11) | **55.7%** | Misjudge Empty/Settlement/Forest balance near settlements |
| **Forest** (code 4) | **30.1%** | Underestimate Port creation on coast, miss expansion |
| Settlement (code 1) | 3.6% | Per-cell KL high (0.14) but few cells |
| Port (code 2) | 0.7% | Extremely high per-cell KL (0.83!) but only ~5 cells |

### What we tried and learned across rounds:
- **Graduated forest adjacency (0/1/2/3+)**: Tiny improvement → reverted to binary in Phase 4
- **Forest adjacency on empty/ruin cells**: **Big win** for harsh winters (R3: 0.075→0.067)
- **4-level distance buckets**: **Consistently hurts** — fragments data, don't try again
- **Bayesian bucket smoothing (K=5)**: Small but consistent wins. K=20 too aggressive.

---

### 4a. Fix viewport position bug ✅ (committed before R8)
+425 cell-observations per coverage pass (+26%).

### 4b. Continuous distance interpolation ✅ (R8 submission)
Blends between adjacent distance brackets based on raw Manhattan distance.
Uses midpoints [1.0, 3.5, 7.0] for linear interpolation. Applied at prediction
time only — bucket training unchanged.

### 4c. Winter severity calibration ✅ (R8 submission)
`estimate_survival_rate()` counts how many initial settlement/port cells survived
in observations. Scales model's settlement/port predictions to match observed rate.
Clamped to [0.3, 3.0] to avoid wild swings. R8 saw 7.1% survival → correctly
scaled down from model's average.

### 4d. Port probability fix ✅ (R8 submission)
Coastal cells within d≤3 of settlements get minimum Port probability (5% if d≤1,
3% if d≤3). Deficit taken from dominant non-Port class.

### 4e. Simplified bucket keys ✅ (R8 submission)
Reduced from ~30 to ~20 buckets:
- Settlement: binary `has_adj_forest` (was graduated 0/1/2/3+)
- Port: `is_coastal` only (was `adj_forest_level`)
- Ruin: dropped `has_adj_forest`
- Plains, Empty, Forest: unchanged

### 4f. Settlement cluster density ✅ (committed)
Binary `is_clustered` (≥2 settlements within Manhattan d≤5) added to Settlement and Plains
bucket keys. Tested 3 variants: both (best), settlement-only, none.
- R7 improved 0.1468→0.1416 (biggest gain — clustered vs isolated settlements behave differently in harsh winters)
- R1-6 avg 0.0568→0.0576 (slight regression — more buckets = less data per bucket)
- R1-7 avg improved overall due to R7 gain

### 4g. Settlement stats extraction ✅ (committed, pending live validation)
`extract_settlement_stats()` parses food/population/wealth from simulate query responses.
- Level 1: avg_food modulates winter calibration scale (±20%, clamped)
- Level 2 (per-cell food z-score) and Level 3 (expansion signal) not yet implemented
- Schema discovery blocked by rate limit — wired but safe no-op until live data confirms fields
- Cannot backtest (GT has no settlement stats)

### 4h. Forward model ✅ (implemented but DISABLED in production)
Rate estimation functions: expansion, port_formation, forest_reclamation, ruin.
Physics-based forward probabilities with context-dependent blending weights.

**Result: consistently hurts in backtesting.** Even at very low weights (3-10%), the
parametric formulas can't match the data-driven bucket model. Reasons:
- Bucket model already captures actual transition dynamics from observations
- Physics formulas use simplified exponential/linear approximations
- The bucket model has access to the same spatial features the forward model uses
- Forward model adds noise rather than correcting errors

**Kept for future use** — rate estimation functions may be useful for settlement stats
integration or as diagnostic tools.

### 4i. Deploy to Cloud Run (DO WHEN MODEL IS GOOD)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

---

### R8 submission summary
All 4 priority items implemented and submitted:
- 4a viewport fix ✅, 4b distance interpolation ✅, 4c winter calibration ✅, 4d port fix ✅, 4e bucket simplification ✅
- R8 round had 7.1% settlement survival (very harsh winter)
- Backtest: R1-6 avg 0.0568 (was 0.0594), R7 0.1468 (was 0.1506)

### Priority for Round 9+ (remaining items)
| # | Change | Status | Notes |
|---|--------|--------|-------|
| 1 | **Settlement cluster features** (4f) | ✅ Done | +3.5% on R7, slight regression R1-6 |
| 2 | **Parse settlement stats** (4g) | ✅ Wired, needs live validation | Food modulation of winter calibration |
| 3 | **Lightweight forward model** (4h) | ❌ Disabled | Consistently hurts in backtest |
| 4 | **Deploy to Cloud Run** (4i) | Not started | Automation |

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
