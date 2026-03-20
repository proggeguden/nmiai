"""FastAPI app for the Astar Island /solve endpoint.

Strategy: hidden parameters are shared across all 5 seeds in a round.
So we observe heavily on 1 seed to learn transition probabilities,
then apply that model to predict all 5 seeds.
"""

import time
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

load_dotenv()

import api_client
from predictor import (
    build_prediction, predictions_to_list, validate_predictions,
    learn_spatial_transition_model,
)

app = FastAPI()


class SolveRequest(BaseModel):
    round_id: str
    access_token: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/solve")
async def solve(request: Request, body: SolveRequest):
    t_start = time.monotonic()
    print(f"=== /solve request: round_id={body.round_id} ===")

    if body.access_token:
        api_client.ACCESS_TOKEN = body.access_token

    try:
        result = run_pipeline(body.round_id)
        elapsed_ms = round((time.monotonic() - t_start) * 1000)
        print(f"=== Completed in {elapsed_ms}ms ===")
        return JSONResponse({"status": "completed", **result})
    except Exception as e:
        elapsed_ms = round((time.monotonic() - t_start) * 1000)
        print(f"=== Error after {elapsed_ms}ms: {e} ===")
        traceback.print_exc()
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


def run_pipeline(round_id):
    """Full pipeline: observe seed 0 → learn transitions → predict all seeds.

    Query budget (50) is SHARED across all seeds. Strategy:
    - Spend all 50 queries on seed 0 to learn transition probabilities
    - 9 tiles for full coverage × ~5 repeats each = good statistics
    - Apply learned model to all 5 seeds using their initial grids
    """

    # 1. Get round details
    print(f"Fetching round detail for {round_id}...")
    detail = api_client.get_round_detail(round_id)
    print(f"Round status: {detail.get('status')}")

    seeds_count = detail.get("seeds_count", len(detail.get("initial_states", [])))
    initial_states = detail.get("initial_states", [])
    queries_max = detail.get("queries_max", 50)

    if not initial_states:
        raise ValueError("No initial states found in round detail")

    height = detail.get("map_height", len(initial_states[0]["grid"]))
    width = detail.get("map_width", len(initial_states[0]["grid"][0]))
    print(f"Grid: {width}x{height}, Seeds: {seeds_count}, Max queries: {queries_max}")

    # 2. Observe seed 0 with all queries to learn transition model
    print(f"\n--- Learning phase: observing seed 0 with {queries_max} queries ---")
    observations = observe_seed(round_id, seed_index=0,
                                height=height, width=width,
                                max_queries=queries_max)
    print(f"Collected {len(observations)} observations")

    # Tag observations with seed index for the transition model
    for obs in observations:
        obs["seed_index"] = 0

    # 3. Learn spatial transition model from observations
    global_model, spatial_model = learn_spatial_transition_model(
        [initial_states[0]["grid"]],
        observations
    )
    from predictor import CLASS_NAMES
    print(f"Learned: {len(global_model)} terrain codes, {len(spatial_model)} spatial buckets")
    for bucket, probs in sorted(spatial_model.items(), key=str):
        top = sorted(enumerate(probs), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{CLASS_NAMES[i]}={p:.2f}" for i, p in top if p > 0.01)
        print(f"  {bucket}: {top_str}")

    # 4. Predict and submit for all seeds
    results = []
    for seed_idx in range(seeds_count):
        print(f"\n--- Predicting seed {seed_idx} ---")
        initial_grid = initial_states[seed_idx]["grid"]

        # For seed 0, also pass direct observations for per-cell blending
        seed_obs = observations if seed_idx == 0 else []

        pred = build_prediction(height, width, initial_grid, seed_obs,
                                transition_model=global_model,
                                spatial_model=spatial_model)
        pred_list = predictions_to_list(pred)
        validate_predictions(pred_list, height, width)

        print(f"  Submitting prediction...")
        try:
            resp = api_client.submit_prediction(round_id, seed_idx, pred_list)
            print(f"  Submit response: {resp}")
            results.append({"seed_index": seed_idx, "submitted": True, "response": resp})
        except Exception as e:
            print(f"  Submit error: {e}")
            results.append({"seed_index": seed_idx, "submitted": False, "error": str(e)})

    return {"seeds_submitted": len(results), "results": results}


def observe_seed(round_id, seed_index, height, width, max_queries):
    """Query viewports to observe the map for a given seed.

    Strategy: tile the map with 15×15 viewports for full coverage,
    then repeat tiles round-robin for more statistical samples.
    """
    observations = []
    vp_w, vp_h = 15, 15

    # Compute tile positions for full coverage
    positions = []
    y = 0
    while y < height:
        x = 0
        while x < width:
            positions.append((x, y))
            x += vp_w
        y += vp_h
    # For 40×40 map: 9 tiles (3×3 grid)

    # Phase 1: Full coverage (9 queries)
    for x, y in positions[:max_queries]:
        try:
            result = api_client.query_seed(round_id, seed_index,
                                           viewport_x=x, viewport_y=y,
                                           viewport_w=vp_w, viewport_h=vp_h)
            observations.append(result)
        except Exception as e:
            print(f"  Query error at ({x},{y}): {e}")
            break

    # Phase 2: Repeat tiles round-robin for more samples
    remaining = max_queries - len(observations)
    for i in range(remaining):
        x, y = positions[i % len(positions)]
        try:
            result = api_client.query_seed(round_id, seed_index,
                                           viewport_x=x, viewport_y=y,
                                           viewport_w=vp_w, viewport_h=vp_h)
            observations.append(result)
        except Exception as e:
            print(f"  Query error repeat ({x},{y}): {e}")
            break

    return observations
