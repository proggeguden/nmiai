# Astar Island — Norse World Prediction

## Task Summary
Observe a black-box Norse civilisation simulator through limited viewport queries,
then predict the probability distribution of terrain types across the full map.
Scored on entropy-weighted KL divergence — only dynamic cells matter.

## How It Works
1. A round starts with 5 seeds (different terrain layouts, same hidden parameters)
2. Each seed has an initial 40×40 grid + settlements
3. You get max 50 queries total — each returns a 15×15 viewport after simulation
4. The simulation runs 50 years with random sim seed (different each query)
5. Submit a W×H×6 probability tensor per seed predicting terrain distributions
6. Your score is based on how well your predictions match ground truth

## Terrain Types
| Internal Code | Terrain    | Class Index | Description                              |
|--------------|-----------|-------------|------------------------------------------|
| 10           | Ocean     | 0 (Empty)   | Impassable water, borders the map        |
| 11           | Plains    | 0 (Empty)   | Open land, can become forest/settlement  |
| 4            | Forest    | 4 (Forest)  | Grows on plains, can be cleared          |
| 5            | Mountain  | 5 (Mountain)| Impassable, permanent                    |
| 1            | Settlement| 1 (Settlement)| Active village/town                    |
| 2            | Port      | 2 (Port)    | Coastal settlement with trade            |
| 3            | Ruin      | 3 (Ruin)    | Destroyed settlement                     |

**6 Prediction Classes**: Empty(0), Settlement(1), Port(2), Ruin(3), Forest(4), Mountain(5)

## Key Concepts
- **Map seed**: Determines terrain layout (fixed per seed, visible)
- **Sim seed**: Random seed for each simulation run (different every query)
- **Hidden parameters**: Values controlling world behavior (same for all seeds in a round)
- **Entropy weighting**: Static cells (ocean, mountain) have near-zero entropy → excluded from scoring
- **Probability floor**: NEVER assign 0.0 — use floor (0.01) and renormalize
- **Query budget is SHARED** across all seeds (not per-seed!) — 50 total for all 5 seeds
- **Viewport is controllable**: set viewport_x, viewport_y, viewport_w (5–15), viewport_h (5–15)
- **Rate limit**: max 5 requests/sec
- For 40×40 map with 15×15 viewport: 9 tiles for full coverage (ceil(40/15)^2)

## API
- **Base URL**: `https://api.ainm.no`
- **Auth**: Bearer token (JWT from app.ainm.no cookies)
- **Endpoints**:
  - `GET /astar-island/rounds` — list all rounds (public)
  - `GET /astar-island/rounds/{round_id}` — detail with initial states for all seeds
  - `POST /astar-island/simulate` — run simulation, observe viewport (1 query, max 5 req/sec)
    - Body: `{round_id, seed_index, viewport_x, viewport_y, viewport_w (5–15), viewport_h (5–15)}`
    - Returns: grid (viewport region), settlements, viewport bounds, queries_used/max
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
python3 -m uvicorn main:app --port 8080  # run server
```

## Scoring
- Entropy-weighted KL divergence
- Only dynamic cells (those that change between sim runs) count
- Higher entropy cells count more
- Score is normalized: 1.0 = perfect, 0.0 = worst
- Critical: probability floor of 0.01, or KL divergence → infinity
