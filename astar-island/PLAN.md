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

## Phase 3: Improve Transition Model (HIGH PRIORITY — next)
- [ ] Per-cell predictions instead of per-terrain-code: cells near settlements behave differently
- [ ] Use settlement features (population, food, wealth, defense) as spatial features
- [ ] Spatial context: a plains cell adjacent to 3 forests behaves differently than one in open field
- [ ] Variable blending weight k: tune for optimal per-cell vs global balance
- [ ] Test whether observing 2 seeds (25 queries each) beats 1 seed (50 queries)
  - More diverse terrain samples vs more observations per cell
- [ ] Learn from Port (code 2) settlements specifically — they only appear after simulation

## Phase 4: Smarter Query Strategy (MEDIUM)
- [ ] After first pass of 9 tiles, focus remaining 41 queries on dynamic regions
- [ ] Skip mostly-ocean tiles (static, no scoring impact)
- [ ] Use smaller viewports (5×5) for targeted high-entropy sampling
- [ ] Track which cells changed vs initial to identify dynamic zones

## Phase 5: Cross-Round Learning (MEDIUM)
- [ ] Analyze how hidden parameters vary across rounds
- [ ] Build prior distributions from historical rounds
- [ ] Detect round "type" early (high-settlement vs low-settlement) and adapt

## Phase 6: Deploy to Cloud Run (when predictions are good)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

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
