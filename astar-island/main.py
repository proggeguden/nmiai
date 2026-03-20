"""FastAPI app for the Astar Island /solve endpoint.

Strategy: hidden parameters are shared across all 5 seeds in a round.
Spread 10 queries per seed across all 5 seeds for diverse terrain coverage,
then learn a spatial transition model from all observations combined.
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
    learn_spatial_transition_model, estimate_survival_rate, estimate_all_rates,
    extract_settlement_stats,
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
    """Full pipeline: observe all seeds → learn transitions → predict all seeds.

    Query budget (50) is SHARED across all seeds. Strategy:
    - Spread 10 queries per seed across all 5 seeds for diverse terrain coverage
    - Hidden parameters are shared, so observations from any seed teach us
    - More seeds → better spatial bucket coverage → better model
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

    # 2. Observe all seeds (allocate queries proportional to settlement density)
    # Score each seed by number of dynamic cells (settlements count extra)
    seed_scores = []
    for seed_idx in range(seeds_count):
        grid = initial_states[seed_idx]["grid"]
        settlements = sum(1 for row in grid for code in row if code in (1, 2, 3))
        dynamic = sum(1 for row in grid for code in row if code not in (10, 5))
        # Settlements are most valuable; also count total dynamic cells
        seed_scores.append(dynamic + settlements * 5)

    total_score = sum(seed_scores) or 1
    seed_query_alloc = [max(5, round(queries_max * s / total_score)) for s in seed_scores]
    # Adjust to exactly hit budget
    while sum(seed_query_alloc) > queries_max:
        seed_query_alloc[seed_query_alloc.index(max(seed_query_alloc))] -= 1
    while sum(seed_query_alloc) < queries_max:
        seed_query_alloc[seed_query_alloc.index(min(seed_query_alloc))] += 1

    print(f"Query allocation: {seed_query_alloc} (scores: {seed_scores})")

    all_observations = []
    seed_observations = {}  # seed_idx → list of observations

    for seed_idx in range(seeds_count):
        n_queries = seed_query_alloc[seed_idx]

        print(f"\n--- Learning phase: observing seed {seed_idx} with {n_queries} queries ---")
        obs = observe_seed(round_id, seed_index=seed_idx,
                           height=height, width=width,
                           max_queries=n_queries,
                           initial_grid=initial_states[seed_idx]["grid"])
        print(f"Collected {len(obs)} observations from seed {seed_idx}")

        # Tag observations with seed index
        for o in obs:
            o["seed_index"] = seed_idx

        seed_observations[seed_idx] = obs
        all_observations.extend(obs)

    # 3. Learn spatial transition model from all observations
    initial_grids = [s["grid"] for s in initial_states]
    global_model, spatial_model = learn_spatial_transition_model(
        initial_grids, all_observations
    )

    # Estimate winter severity and all forward model rates
    survival_rate = estimate_survival_rate(initial_grids, all_observations)
    forward_rates = estimate_all_rates(initial_grids, all_observations)
    print(f"Estimated survival rate: {survival_rate}")
    print(f"Forward model rates: {forward_rates}")

    # Extract settlement stats from observations
    settlement_stats = extract_settlement_stats(all_observations)
    if settlement_stats:
        print(f"Settlement stats: avg_food={settlement_stats['avg_food']:.1f}, "
              f"median_food={settlement_stats['median_food']:.1f}, "
              f"avg_pop={settlement_stats['avg_population']:.1f}, "
              f"positions={settlement_stats['unique_positions']}, "
              f"obs={settlement_stats['total_observations']}")
    else:
        print("Settlement stats: insufficient data")

    from predictor import CLASS_NAMES
    print(f"\nLearned: {len(global_model)} terrain codes, {len(spatial_model)} spatial buckets")
    for bucket, probs in sorted(spatial_model.items(), key=str):
        top = sorted(enumerate(probs), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{CLASS_NAMES[i]}={p:.2f}" for i, p in top if p > 0.01)
        print(f"  {bucket}: {top_str}")

    # 4. Predict and submit for all seeds
    results = []
    for seed_idx in range(seeds_count):
        print(f"\n--- Predicting seed {seed_idx} ---")
        initial_grid = initial_states[seed_idx]["grid"]

        # Pass this seed's observations for per-cell blending
        seed_obs = seed_observations.get(seed_idx, [])

        pred = build_prediction(height, width, initial_grid, seed_obs,
                                transition_model=global_model,
                                spatial_model=spatial_model,
                                survival_rate=survival_rate,
                                settlement_stats=settlement_stats)
        pred_list = predictions_to_list(pred)
        validate_predictions(pred_list, height, width)

        print(f"  Submitting prediction...")
        for attempt in range(3):
            try:
                resp = api_client.submit_prediction(round_id, seed_idx, pred_list)
                print(f"  Submit response: {resp}")
                results.append({"seed_index": seed_idx, "submitted": True, "response": resp})
                time.sleep(0.3)  # avoid rate limiting
                break
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    print(f"  Rate limited, retrying in 2s...")
                    time.sleep(2)
                else:
                    print(f"  Submit error: {e}")
                    results.append({"seed_index": seed_idx, "submitted": False, "error": str(e)})
                    break

    return {"seeds_submitted": len(results), "results": results}


def observe_seed(round_id, seed_index, height, width, max_queries,
                 initial_grid=None):
    """Query viewports to observe the map for a given seed.

    Strategy:
    1. Score each tile by dynamic cell count (non-ocean, non-mountain)
    2. Skip tiles that are mostly static (ocean/mountain)
    3. Full coverage of dynamic tiles first
    4. Repeat queries on most dynamic tiles (settlement-heavy areas)
    """
    from predictor import STATIC_CODES

    observations = []
    vp_w, vp_h = 15, 15

    # Compute tile positions for full coverage
    # Use overlapping positions so the last tile uses full viewport capacity.
    # E.g., for a 40-wide grid with 15-wide viewports: [0, 15, 25] not [0, 15, 30].
    # Position 25 covers cells 25-39 (full 15), while 30 would only cover 30-39 (10).
    # Overlap cells (25-29) get double-observed for free.
    def _tile_starts(grid_size, vp_size):
        starts = []
        pos = 0
        while pos < grid_size:
            starts.append(pos)
            pos += vp_size
        # Pull last position back so viewport doesn't extend past grid edge
        if starts and starts[-1] + vp_size > grid_size:
            starts[-1] = max(grid_size - vp_size, 0)
        # Deduplicate (in case grid_size <= vp_size)
        return list(dict.fromkeys(starts))

    x_starts = _tile_starts(width, vp_w)
    y_starts = _tile_starts(height, vp_h)
    positions = [(x, y) for y in y_starts for x in x_starts]

    # Score tiles by dynamic cell count if we have the initial grid
    if initial_grid:
        tile_scores = []
        for tx, ty in positions:
            dynamic = 0
            settlements = 0
            for r in range(ty, min(ty + vp_h, height)):
                for c in range(tx, min(tx + vp_w, width)):
                    code = initial_grid[r][c]
                    if code not in STATIC_CODES:
                        dynamic += 1
                    if code in (1, 2):  # settlement or port
                        settlements += 1
            # Score: settlements count 3x (most valuable to observe)
            tile_scores.append(dynamic + settlements * 3)

        # Sort tiles by score descending
        scored_tiles = sorted(zip(tile_scores, positions), reverse=True)

        # Phase 1: Cover all tiles with dynamic cells (skip pure ocean/mountain)
        coverage_tiles = [(s, pos) for s, pos in scored_tiles if s > 0]
        repeat_tiles = [(s, pos) for s, pos in scored_tiles if s > 10]

        print(f"  Tiles: {len(coverage_tiles)} dynamic (of {len(positions)}), "
              f"{len(repeat_tiles)} high-value for repeats")
    else:
        coverage_tiles = [(1, pos) for pos in positions]
        repeat_tiles = coverage_tiles

    # Phase 1: Full coverage of dynamic tiles
    for _, (x, y) in coverage_tiles[:max_queries]:
        try:
            result = api_client.query_seed(round_id, seed_index,
                                           viewport_x=x, viewport_y=y,
                                           viewport_w=vp_w, viewport_h=vp_h)
            observations.append(result)
        except Exception as e:
            print(f"  Query error at ({x},{y}): {e}")
            break

    # Phase 2: Repeat queries on high-value tiles (settlement-heavy areas)
    remaining = max_queries - len(observations)
    if repeat_tiles:
        for i in range(remaining):
            _, (x, y) = repeat_tiles[i % len(repeat_tiles)]
            try:
                result = api_client.query_seed(round_id, seed_index,
                                               viewport_x=x, viewport_y=y,
                                               viewport_w=vp_w, viewport_h=vp_h)
                observations.append(result)
            except Exception as e:
                print(f"  Query error repeat ({x},{y}): {e}")
                break

    return observations
