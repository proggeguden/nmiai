# Astar Island — Roadmap

## Phase 1: MVP Pipeline (DONE)
- [x] Project scaffold (FastAPI, api_client, predictor, test_local)
- [x] Correct API endpoints (simulate, submit, my-rounds, my-predictions, analysis, leaderboard)
- [x] Submitted predictions for round 5 (basic approach)

## Phase 2: Transition Model Predictor (DONE)
- [x] Key insight: hidden params are same for all 5 seeds → learn from 1, predict all
- [x] learn_transition_model(): P(final_class | initial_terrain_code) from observations
- [x] Spend all 50 queries on seed 0 → learn transitions → apply to all 5 seeds
- [x] Per-cell blending: observed cells mix local counts with global model
- [x] Backtested on rounds 1–4: ~0.05–0.14 weighted KL (8x better than naive)
- [x] test_local.py: --backtest, --my-rounds, --leaderboard modes

## Phase 3: Spatial Feature Model (DONE)
- [x] Spatial bucketing: P(class | terrain_code, spatial_features)
- [x] Features: adj_forest, adj_settlement, near_settlement, is_coastal
- [x] 16 buckets with fallback to global model if <10 observations
- [x] Backtested improvement: 13-48% reduction in weighted KL across all rounds

## Round 5 Post-Mortem
- Score: 13.1/100, rank 130/144 (submitted before model was ready)
- Our submitted predictions were naive: 95% Settlement for settlement cells
- GT shows settlements only survive ~34%, become Empty ~43%, Forest ~20%
- Current spatial model would have scored ~0.08 weighted_KL (much better)
- Top teams score 60-80+ (weighted_score ~110+ on leaderboard)

## Critical Insight: Hidden Parameters Are New Every Round

Tested Bayesian priors from historical rounds — they DON'T help and sometimes hurt.
Each round has unique hidden params (winter severity, expansion rate, etc.) that
create wildly different transition rates (settlements survive 2–44% depending on round).

**Historical rounds are useful for understanding STRUCTURE (which spatial features
matter) but NOT for predicting specific transition rates.** The rates must be
learned fresh each round from the 50 observation queries.

### Data budget analysis
- 50 queries, 9 tiles for full coverage → ~5.5 observations per cell
- Per-cell estimates are noisy (SE ~0.15–0.22 for main classes with N=5)
- BUT: pooling across cells with same bucket gives 100–500 samples → reliable estimates
- The spatial model works well with noisy data because of this pooling

## Phase 4: Remaining Improvements (NEXT)

### 4a. Smarter query allocation (HIGH)
50 queries, 9 tiles for full coverage, 41 remaining for repeats.
- Skip ocean-dominated tiles entirely (static, use initial grid)
- Identify which tiles have settlements from initial_states
- Focus repeats on settlement-heavy tiles for more samples
- This gives ~10+ observations per dynamic cell instead of ~5

### 4b. Finer spatial features (HIGH)
The spatial model uses binary features. Finer features can help:
- adj_forest count: 0, 1, 2, 3+ (not just 0 vs 1+) — more food = more survival
- Number of settlements within radius 3 (not just adjacent)
- BUT: keep bucket sizes >50 observations or noise dominates

### 4c. Use settlement stats from observations (MEDIUM)
Simulate endpoint returns population, food, wealth, defense.
- Could group settlements by stats (high food vs low food)
- Only available for seed 0 but transition rates transfer
- Risk: stats vary across observations (stochastic), may not help much

### 4d. Cross-round regime detection (LOW — tested, minimal benefit)
- Historical priors don't improve predictions (-0.4% to +0.7% change)
- Each round is too unique for priors to help
- Focus efforts on better observation strategy instead

## Phase 5: Deploy to Cloud Run (when predictions are good)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

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

## How to Iterate

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
