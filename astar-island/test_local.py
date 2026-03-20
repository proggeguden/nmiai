"""Local testing script for the Astar Island pipeline.

Usage:
    python3 test_local.py                      # full pipeline test on active round
    python3 test_local.py --submit             # also submit predictions
    python3 test_local.py --round ROUND_ID     # test specific round
    python3 test_local.py --server             # test against local /solve endpoint
    python3 test_local.py --list-rounds        # list available rounds
    python3 test_local.py --my-rounds          # show scores and ranks
    python3 test_local.py --leaderboard        # show leaderboard
    python3 test_local.py --backtest ROUND_ID  # backtest against ground truth
    python3 test_local.py --backtest all       # backtest all completed rounds
"""

import argparse
import json
import sys

import numpy as np

import api_client
from predictor import (
    build_prediction, learn_transition_model, learn_spatial_transition_model,
    compute_feature_map, predictions_to_list,
    validate_predictions, terrain_code_to_class, score_predictions,
    NUM_CLASSES, CLASS_NAMES, STATIC_CODES,
    estimate_survival_rate as _est_survival,
)


def list_rounds():
    print("Fetching rounds...")
    rounds = api_client.get_rounds()
    for r in rounds:
        print(f"  Round {r['round_number']} ({r['status']}): {r['id']}")
        print(f"    {r['started_at']} → {r['closes_at']}")


def show_my_rounds():
    print("Fetching team rounds...")
    rounds = api_client.get_my_rounds()
    for r in rounds:
        score = r.get("round_score")
        rank = r.get("rank")
        total = r.get("total_teams")
        print(f"  Round {r['round_number']} ({r['status']}): "
              f"score={score}, rank={rank}/{total}, "
              f"seeds={r['seeds_submitted']}/5, "
              f"queries={r['queries_used']}/{r['queries_max']}")
        if r.get("seed_scores"):
            print(f"    seed_scores: {r['seed_scores']}")


def show_leaderboard():
    print("Leaderboard:")
    lb = api_client.get_leaderboard()
    for t in lb[:15]:
        print(f"  #{t['rank']} {t['team_name']}: "
              f"weighted={t['weighted_score']:.1f}, "
              f"streak={t['hot_streak_score']:.1f}, "
              f"rounds={t['rounds_participated']}")


def _score_predictions(pred, gt):
    """Compute entropy-weighted KL divergence. Delegates to predictor.score_predictions."""
    return score_predictions(pred, gt)


def backtest_round(round_id):
    """Backtest our predictor against ground truth from a completed round.

    Compares global model (per-code) vs spatial model (per-bucket).
    Uses GT from all seeds (simulating multi-seed observation strategy).
    """
    print(f"\n{'='*60}")
    print(f"Backtesting round: {round_id}")
    print(f"{'='*60}")

    detail = api_client.get_round_detail(round_id)
    height, width = detail["map_height"], detail["map_width"]
    seeds_count = detail["seeds_count"]
    initial_states = detail["initial_states"]

    # Load ground truth for all seeds
    all_gt = {}
    for seed_idx in range(seeds_count):
        all_gt[seed_idx] = np.array(api_client.get_analysis(round_id, seed_idx)["ground_truth"])

    # Build models from ALL seeds' GT (simulates multi-seed observation)
    global_probs = {}
    spatial_probs = {}
    spatial_obs = {}

    for seed_idx in range(seeds_count):
        gt = all_gt[seed_idx]
        init_grid = initial_states[seed_idx]["grid"]
        fmap, _, _ = compute_feature_map(init_grid)

        for r in range(height):
            for c in range(width):
                code = init_grid[r][c]
                bucket = fmap[r][c]

                # Global counts
                if code not in global_probs:
                    global_probs[code] = np.zeros(NUM_CLASSES)
                global_probs[code] += gt[r, c]

                # Spatial counts
                if bucket not in spatial_probs:
                    spatial_probs[bucket] = np.zeros(NUM_CLASSES)
                    spatial_obs[bucket] = 0
                spatial_probs[bucket] += gt[r, c]
                spatial_obs[bucket] += 1

    global_model = {}
    for code, probs in global_probs.items():
        total = probs.sum()
        if total > 0:
            global_model[code] = probs / total

    BUCKET_SMOOTH_K = 5.0
    spatial_model = {}
    for bucket, probs in spatial_probs.items():
        n = spatial_obs[bucket]
        if n < 3:
            continue
        total = probs.sum()
        if total > 0:
            bucket_prob = probs / total
            terrain_code = bucket[0]
            if terrain_code in global_model:
                weight = n / (n + BUCKET_SMOOTH_K)
                spatial_model[bucket] = weight * bucket_prob + (1 - weight) * global_model[terrain_code]
            else:
                spatial_model[bucket] = bucket_prob

    # Also build single-seed models for comparison
    gt0 = all_gt[0]
    init_grid_0 = initial_states[0]["grid"]
    fmap_0, _, _ = compute_feature_map(init_grid_0)

    single_global_probs = {}
    single_spatial_probs = {}
    single_spatial_obs = {}
    for r in range(height):
        for c in range(width):
            code = init_grid_0[r][c]
            bucket = fmap_0[r][c]
            if code not in single_global_probs:
                single_global_probs[code] = np.zeros(NUM_CLASSES)
            single_global_probs[code] += gt0[r, c]
            if bucket not in single_spatial_probs:
                single_spatial_probs[bucket] = np.zeros(NUM_CLASSES)
                single_spatial_obs[bucket] = 0
            single_spatial_probs[bucket] += gt0[r, c]
            single_spatial_obs[bucket] += 1

    single_global = {code: p / p.sum() for code, p in single_global_probs.items() if p.sum() > 0}
    single_spatial = {}
    for b, p in single_spatial_probs.items():
        n = single_spatial_obs[b]
        if n < 3 or p.sum() == 0:
            continue
        bucket_prob = p / p.sum()
        terrain_code = b[0]
        if terrain_code in single_global:
            weight = n / (n + BUCKET_SMOOTH_K)
            single_spatial[b] = weight * bucket_prob + (1 - weight) * single_global[terrain_code]
        else:
            single_spatial[b] = bucket_prob

    print(f"\nModels: {len(global_model)} terrain codes, {len(spatial_model)} spatial buckets (multi-seed)")
    print(f"Single-seed: {len(single_global)} terrain codes, {len(single_spatial)} spatial buckets")
    for bucket in sorted(spatial_model.keys(), key=str):
        probs = spatial_model[bucket]
        n = spatial_obs[bucket]
        top = sorted(enumerate(probs), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{CLASS_NAMES[i]}={p:.3f}" for i, p in top if p > 0.005)
        print(f"  {bucket} (n={n}): {top_str}")

    # Compute forward model rates directly from GT probability distributions
    # Use expected values from GT probabilities (not argmax) for accurate rates
    initial_grids = [s["grid"] for s in initial_states]
    survival_total = 0.0
    survival_count = 0
    expansion_new = 0.0
    expansion_eligible = 0
    port_formed = 0.0
    coastal_nonport = 0
    forest_reclaimed = 0.0
    forest_eligible = 0
    ruin_total = 0.0
    ruin_count = 0

    for seed_idx in range(seeds_count):
        gt = all_gt[seed_idx]  # H×W×6 probability
        init_grid = initial_states[seed_idx]["grid"]
        for r in range(height):
            for c in range(width):
                code = init_grid[r][c]
                if code in STATIC_CODES:
                    continue
                gt_probs = gt[r, c]  # 6-class probability vector

                if code in (1, 2):
                    # Settlement/port survival and ruin rates
                    survival_total += gt_probs[1] + gt_probs[2]
                    ruin_total += gt_probs[3]
                    survival_count += 1
                    ruin_count += 1

                elif code in (0, 11):
                    # Expansion: non-settlement becoming settlement
                    expansion_new += gt_probs[1]
                    expansion_eligible += 1

                    # Port formation for coastal cells
                    is_coastal = False
                    for nr, nc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                        if 0 <= nr < height and 0 <= nc < width and init_grid[nr][nc] == 10:
                            is_coastal = True
                            break
                    if is_coastal:
                        port_formed += gt_probs[2]
                        coastal_nonport += 1

                # Forest reclamation (non-forest near forest)
                if code != 4 and code not in STATIC_CODES:
                    adj_forest = 0
                    for ar in range(max(0, r-1), min(height, r+2)):
                        for ac in range(max(0, c-1), min(width, c+2)):
                            if (ar, ac) != (r, c) and init_grid[ar][ac] == 4:
                                adj_forest += 1
                    if adj_forest > 0:
                        forest_reclaimed += gt_probs[4]
                        forest_eligible += 1

    forward_rates = {
        "survival": survival_total / survival_count if survival_count > 0 else None,
        "expansion": expansion_new / expansion_eligible if expansion_eligible > 0 else None,
        "port_formation": port_formed / coastal_nonport if coastal_nonport > 0 else None,
        "forest_reclamation": forest_reclaimed / forest_eligible if forest_eligible > 0 else None,
        "ruin": ruin_total / ruin_count if ruin_count > 0 else None,
    }
    print(f"\nForward model rates (from GT): { {k: f'{v:.4f}' if v else v for k, v in forward_rates.items()} }")

    # Score all seeds with all model variants
    print(f"\n{'Model':<20} | {'Seed 0':>8} {'Seed 1':>8} {'Seed 2':>8} {'Seed 3':>8} {'Seed 4':>8} | {'Avg':>8}")
    print("-" * 87)

    best_scores = None
    for model_name, gm, sm, fr in [
        ("1seed-Global", single_global, None, None),
        ("1seed-Spatial", single_global, single_spatial, None),
        ("5seed-Global", global_model, None, None),
        ("5seed-Spatial", global_model, spatial_model, None),
        ("5seed-Sp+Forward", global_model, spatial_model, forward_rates),
    ]:
        kl_scores = []
        for seed_idx in range(seeds_count):
            gt = all_gt[seed_idx]
            init_grid_s = initial_states[seed_idx]["grid"]
            pred = build_prediction(height, width, init_grid_s, [],
                                    transition_model=gm, spatial_model=sm,
                                    forward_rates=fr)
            wkl, _ = _score_predictions(pred, gt)
            kl_scores.append(wkl)

        avg = np.mean(kl_scores)
        scores_str = " ".join(f"{s:.4f}" for s in kl_scores)
        print(f"{model_name:<20} | {scores_str} | {avg:.4f}")
        if model_name == "5seed-Spatial":
            best_scores = kl_scores

    return np.mean(best_scores)  # return primary model score (5seed-Spatial)


def test_pipeline(round_id, submit=False):
    """Test the full pipeline for a given round."""
    print(f"\n{'='*60}")
    print(f"Testing pipeline for round: {round_id}")
    print(f"{'='*60}")

    detail = api_client.get_round_detail(round_id)
    print(f"  Status: {detail.get('status')}")
    seeds_count = detail.get("seeds_count", len(detail.get("initial_states", [])))
    initial_states = detail.get("initial_states", [])
    queries_max = detail.get("queries_max", 50)
    height = detail.get("map_height", len(initial_states[0]["grid"]))
    width = detail.get("map_width", len(initial_states[0]["grid"][0]))
    print(f"  Grid: {width}x{height}, Seeds: {seeds_count}, Max queries: {queries_max}")

    # Show initial terrain distribution for seed 0
    grid = initial_states[0]["grid"]
    print(f"\n  Initial terrain distribution (seed 0):")
    class_counts = [0] * NUM_CLASSES
    for row in grid:
        for code in row:
            cls = terrain_code_to_class(code)
            class_counts[cls] += 1
    total = sum(class_counts)
    for i, name in enumerate(CLASS_NAMES):
        pct = class_counts[i] / total * 100
        print(f"    {name}: {class_counts[i]} ({pct:.1f}%)")

    if detail.get("status") != "active":
        print("\n  Round is not active — skipping queries. Use --backtest instead.")
        return True

    if submit:
        # Full pipeline: use all queries for maximum accuracy
        from main import run_pipeline
        print(f"\n  Running full pipeline (all {queries_max} queries)...")
        result = run_pipeline(round_id)
        print(f"\n  Result: {result['seeds_submitted']} seeds submitted")
    else:
        # Quick test: use 4 queries to check things work
        print(f"\n  Querying seed 0 (4 tiles for quick test)...")
        observations = []
        test_positions = [(0, 0), (15, 0), (0, 15), (15, 15)]
        for x, y in test_positions:
            try:
                result = api_client.query_seed(round_id, 0, viewport_x=x, viewport_y=y)
                vp = result.get("viewport", {})
                print(f"    ({x},{y}): viewport={vp}, queries={result['queries_used']}/{result['queries_max']}")
                result["seed_index"] = 0
                observations.append(result)
            except Exception as e:
                print(f"    ({x},{y}) error: {e}")
                break

        global_model, spatial_model = learn_spatial_transition_model(
            [initial_states[0]["grid"]], observations
        )
        print(f"\n  Models: {len(global_model)} codes, {len(spatial_model)} spatial buckets")

        pred = build_prediction(height, width, initial_states[0]["grid"],
                                observations, transition_model=global_model,
                                spatial_model=spatial_model)
        pred_list = predictions_to_list(pred)
        validate_predictions(pred_list, height, width)
        print(f"\n  Prediction valid: shape={pred.shape}, "
              f"sum=[{pred.sum(axis=2).min():.4f}, {pred.sum(axis=2).max():.4f}], "
              f"min_prob={pred.min():.6f}")

    print(f"\n{'='*60}")
    print("Pipeline test completed!")
    return True


def test_server(round_id, server_url="http://localhost:8080"):
    import requests
    print(f"Testing /solve at {server_url}...")

    try:
        resp = requests.get(f"{server_url}/health")
        print(f"Health: {resp.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

    payload = {"round_id": round_id}
    if api_client.ACCESS_TOKEN:
        payload["access_token"] = api_client.ACCESS_TOKEN

    resp = requests.post(f"{server_url}/solve", json=payload, timeout=300)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    return resp.status_code == 200


def main():
    parser = argparse.ArgumentParser(description="Astar Island local test")
    parser.add_argument("--round", type=str, help="Specific round ID")
    parser.add_argument("--submit", action="store_true", help="Submit predictions")
    parser.add_argument("--server", action="store_true", help="Test local /solve")
    parser.add_argument("--server-url", default="http://localhost:8080")
    parser.add_argument("--list-rounds", action="store_true")
    parser.add_argument("--my-rounds", action="store_true")
    parser.add_argument("--leaderboard", action="store_true")
    parser.add_argument("--backtest", type=str,
                        help="Backtest against ground truth (round ID or 'all')")
    args = parser.parse_args()

    if args.list_rounds:
        list_rounds()
        return
    if args.my_rounds:
        show_my_rounds()
        return
    if args.leaderboard:
        show_leaderboard()
        return

    if args.backtest:
        if args.backtest == "all":
            rounds = api_client.get_rounds()
            completed = [r for r in rounds if r["status"] == "completed"]
            scores = []
            for r in completed:
                s = backtest_round(r["id"])
                scores.append((r["round_number"], s))
            print(f"\n{'='*60}")
            print("Summary:")
            for rnum, s in scores:
                print(f"  Round {rnum}: avg weighted_KL = {s:.4f}")
        else:
            backtest_round(args.backtest)
        return

    # Find a round to test
    round_id = args.round
    if not round_id:
        rounds = api_client.get_rounds()
        active = [r for r in rounds if r.get("status") == "active"]
        if active:
            round_id = active[0]["id"]
            print(f"Using active round: {round_id}")
        elif rounds:
            round_id = rounds[0]["id"]
            print(f"No active round, using latest: {round_id}")
        else:
            print("No rounds found!")
            return

    if args.server:
        test_server(round_id, args.server_url)
    else:
        test_pipeline(round_id, submit=args.submit)


if __name__ == "__main__":
    main()
