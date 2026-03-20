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

## Phase 4: Remaining Improvements (NEXT)

### 4a. Per-cell prediction within buckets (HIGH)
The spatial model gives the same probability to ALL settlements with forest adjacency.
But GT shows individual settlement cells vary: one has 44% survival, another 20%.
- Use MORE spatial features to create finer buckets (e.g., adj_forest count: 0, 1, 2, 3+)
- Count adj_forest as integer not binary for settlements
- Add settlement distance features (dist to nearest other settlement)

### 4b. Smarter query allocation (HIGH)
50 queries, 9 tiles for full coverage, 41 remaining for repeats.
- Skip ocean-dominated tiles entirely (they're static, use initial grid)
- Focus on settlement-heavy tiles for more observations
- Settlement positions are known from initial_states — target viewports accordingly

### 4c. Use settlement stats from observations (MEDIUM)
Simulate endpoint returns population, food, wealth, defense for each settlement.
- Average these across observations to identify strong vs weak settlements
- Strong settlements (high food, high defense) more likely to survive
- Only available for seed 0 (observed) but transition rates transfer to all seeds

### 4d. Cross-round learning (MEDIUM)
- Round 3: 2% settlement survival, Round 1/2/4/5: 22-44% survival
- Learn to detect "regime" from first few observations
- Build priors from historical rounds for each regime type

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
