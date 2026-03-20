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

## Phase 3: Spatial Feature Model (HIGH PRIORITY — next)

The simulation has 5 phases per year over 50 years. Our predictions should model
the spatial factors that drive outcomes:

### 3a. Adjacent-terrain features
A cell's fate depends heavily on its neighbors, not just its own initial type:
- **Forest adjacency** → more food for settlements → higher survival probability
- **Ocean adjacency** → port potential (settlements on coast become ports)
- **Settlement density** → more conflict (raids), but also more trade between ports
- **Mountain adjacency** → impassable, limits expansion directions
- Instead of P(class | terrain_code), model P(class | terrain_code, neighbor_features)

### 3b. Settlement proximity features
- Distance to nearest settlement → expansion targets (new settlements on nearby land)
- Number of settlements in radius → conflict intensity
- Settlement cluster vs isolated → different survival dynamics
- Faction (owner_id) distribution → war likelihood

### 3c. Settlement stat features (from observations)
The simulate endpoint returns full settlement stats: population, food, wealth, defense.
- High food → likely to survive winter, expand
- Low food → desperate raiding, collapse risk
- High wealth → trade activity
- Has longship → extended raid/trade range
- These are observable for cells within our viewport queries

### 3d. Implementation approach
- Compute feature vectors per cell: [initial_code, n_forest_adj, n_ocean_adj, n_settlement_adj, n_mountain_adj, dist_nearest_settlement, ...]
- Bucket cells by feature vector → learn transition probabilities per bucket
- Backtest to verify improvement over global per-code model

## Phase 4: Smarter Query Strategy (MEDIUM)
- [ ] After first 9 tiles (full coverage), identify dynamic zones
- [ ] Focus remaining 41 queries on high-entropy areas (near settlements)
- [ ] Skip ocean-dominated tiles (static, zero scoring impact)
- [ ] Consider observing 2 seeds (25 each) for more diverse terrain samples
- [ ] Use settlement positions from initial_states to plan viewport placement

## Phase 5: Cross-Round Learning (MEDIUM)
- [ ] Hidden parameters vary per round: winter severity, expansion rate, conflict intensity, trade range
- [ ] Backtest reveals: Round 3 had ~2% settlement survival vs Round 1–2 at ~40%
  - Likely controlled by winter severity or food scarcity parameters
- [ ] Build priors from historical rounds for faster convergence
- [ ] Detect round "regime" from first few observations and pick best prior

## Phase 6: Deploy to Cloud Run (when predictions are good)
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
