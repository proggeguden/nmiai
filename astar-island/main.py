"""FastAPI app for the Astar Island /solve endpoint."""

import os
import time
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

load_dotenv()

import api_client
from predictor import build_prediction, predictions_to_list, validate_predictions

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

    # Override token if provided in request
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
    """Full pipeline: observe → predict → submit for all seeds.

    Query budget is SHARED across all seeds (not per-seed).
    Strategy: distribute queries evenly across seeds.
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

    # 2. Distribute queries evenly across seeds (budget is shared!)
    queries_per_seed = queries_max // seeds_count

    # 3. For each seed: observe and predict
    results = []
    queries_used = 0
    for seed_idx in range(seeds_count):
        print(f"\n--- Seed {seed_idx} ---")
        initial_grid = initial_states[seed_idx]["grid"]

        # Observe with our budget slice
        remaining = queries_max - queries_used
        budget = min(queries_per_seed, remaining)
        observations = observe_seed(round_id, seed_idx, height, width, budget)
        queries_used += len(observations)
        print(f"  Collected {len(observations)} observations (total used: {queries_used}/{queries_max})")

        # Build prediction
        pred = build_prediction(height, width, initial_grid, observations)
        pred_list = predictions_to_list(pred)

        # Validate
        validate_predictions(pred_list, height, width)

        # Submit
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

    Strategy: tile the map with 15×15 viewports first to get full coverage,
    then use remaining budget for repeat observations on dynamic areas.
    """
    observations = []
    vp_w, vp_h = 15, 15

    # Phase 1: Tile the map for full coverage
    positions = []
    y = 0
    while y < height:
        x = 0
        while x < width:
            positions.append((x, y))
            x += vp_w
        y += vp_h

    # For a 40×40 map with 15×15 viewports: ceil(40/15)^2 = 9 tiles
    # With 50 queries / 5 seeds = 10 per seed, that's 9 tiles + 1 repeat
    for x, y in positions[:max_queries]:
        try:
            result = api_client.query_seed(round_id, seed_index,
                                           viewport_x=x, viewport_y=y,
                                           viewport_w=vp_w, viewport_h=vp_h)
            observations.append(result)
        except Exception as e:
            print(f"  Query error at ({x},{y}): {e}")
            break

    # Phase 2: Use remaining budget for repeat observations (more samples = better stats)
    remaining = max_queries - len(observations)
    for i in range(remaining):
        # Re-observe tiles in round-robin to build statistics
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
