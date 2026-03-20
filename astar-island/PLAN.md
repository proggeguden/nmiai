# Astar Island — Roadmap

## Phase 1: MVP Pipeline (DONE)
- [x] Project scaffold (FastAPI, api_client, predictor, test_local)
- [x] Correct API endpoints (simulate, submit, my-rounds, my-predictions, analysis, leaderboard)
- [x] Basic predictor: count terrain frequencies from initial grid + observations, probability floor 0.01
- [x] Viewport tiling strategy: 9 tiles (ceil(40/15)^2) per seed for full map coverage
- [x] Submitted predictions for round 5

## Phase 2: Improve Predictions (HIGH PRIORITY)
- [ ] Analyze ground truth from completed rounds via `/analysis` to understand scoring
- [ ] Compare our predictions vs ground truth to identify systematic errors
- [ ] Better query budget allocation: 50 queries / 5 seeds = 10 per seed
  - 9 tiles for full coverage → only 1 repeat observation per seed
  - Consider: fewer seeds with more observations vs all seeds with minimal coverage
- [ ] Separate static vs dynamic cell handling:
  - Ocean (10) and Mountain (5) are permanent → predict with high confidence
  - Plains (11) near settlements are dynamic → need more observation samples
- [ ] Use settlement data (population, food, wealth, defense, alive) to inform predictions
- [ ] Track which cells change across observations to estimate entropy

## Phase 3: Smart Query Strategy (MEDIUM)
- [ ] Prioritize viewport positions that cover dynamic areas (near settlements)
- [ ] Skip tiles that are mostly ocean/mountain (static, low entropy, low scoring impact)
- [ ] Use smaller viewports (5×5) focused on high-entropy regions for more targeted sampling
- [ ] Adaptive: first pass with full coverage, then re-observe dynamic areas

## Phase 4: Model Improvements (MEDIUM)
- [ ] Learn hidden parameter patterns across rounds
- [ ] Use settlement proximity as a feature for terrain prediction
- [ ] Model terrain transition probabilities (e.g., plains near settlement → settlement/ruin)
- [ ] Spatial smoothing of predictions

## Phase 5: Deploy to Cloud Run (LOW — when ready)
- [ ] Deploy Dockerfile to Cloud Run
- [ ] Register endpoint at app.ainm.no
- [ ] Automated round handling via /solve endpoint

## Debugging Tools
- `python3 test_local.py --list-rounds` — see available rounds
- `python3 test_local.py --round ROUND_ID` — test pipeline
- `python3 test_local.py --submit` — submit predictions
- Use `api_client.get_my_rounds()` to check scores and ranks
- Use `api_client.get_my_predictions(round_id)` to see argmax/confidence grids
- Use `api_client.get_analysis(round_id, seed_index)` to compare vs ground truth
- Use `api_client.get_leaderboard()` to check standings
