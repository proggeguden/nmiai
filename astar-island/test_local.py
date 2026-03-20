"""Local testing script for the Astar Island pipeline.

Usage:
    python3 test_local.py                  # full pipeline test (observe + predict + validate)
    python3 test_local.py --submit         # also submit predictions
    python3 test_local.py --round ROUND_ID # test specific round
    python3 test_local.py --server         # test against local /solve endpoint
    python3 test_local.py --list-rounds    # list available rounds
"""

import argparse
import json
import sys

import numpy as np

import api_client
from predictor import (
    build_prediction,
    predictions_to_list,
    validate_predictions,
    NUM_CLASSES,
    terrain_code_to_class,
)


def list_rounds():
    """List all available rounds."""
    print("Fetching rounds...")
    rounds = api_client.get_rounds()
    print(json.dumps(rounds, indent=2))
    return rounds


def test_pipeline(round_id, submit=False):
    """Test the full pipeline for a given round."""
    print(f"\n{'='*60}")
    print(f"Testing pipeline for round: {round_id}")
    print(f"{'='*60}")

    # 1. Get round detail
    print("\n[1] Fetching round detail...")
    detail = api_client.get_round_detail(round_id)
    print(f"  Status: {detail.get('status')}")
    seeds_count = detail.get("seeds_count", len(detail.get("initial_states", [])))
    initial_states = detail.get("initial_states", [])
    queries_max = detail.get("queries_max", 50)

    if not initial_states:
        print("  ERROR: No initial states found!")
        return False

    height = len(initial_states[0]["grid"])
    width = len(initial_states[0]["grid"][0])
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
    for i, name in enumerate(["Empty", "Settlement", "Port", "Ruin", "Forest", "Mountain"]):
        pct = class_counts[i] / total * 100
        print(f"    {name}: {class_counts[i]} ({pct:.1f}%)")

    # 2. Query a few viewports for seed 0
    print(f"\n[2] Querying viewports for seed 0...")
    queries_per_seed = queries_max // seeds_count
    observations = []

    # Query a few positions (tile the map)
    test_positions = [(0, 0), (15, 0), (30, 0), (0, 15), (15, 15), (30, 15), (0, 30), (15, 30), (30, 30)]
    for x, y in test_positions[:queries_per_seed]:
        try:
            result = api_client.query_seed(round_id, 0, viewport_x=x, viewport_y=y)
            vp = result.get("viewport", {})
            grid_obs = result.get("grid", [])
            settlements = result.get("settlements", [])
            print(f"  Query ({x},{y}): viewport={vp}, grid={len(grid_obs)}x{len(grid_obs[0]) if grid_obs else 0}, settlements={len(settlements)}")
            observations.append(result)
        except Exception as e:
            print(f"  Query ({x},{y}) error: {e}")

    # 3. Build prediction
    print(f"\n[3] Building prediction for seed 0...")
    pred = build_prediction(height, width, initial_states[0]["grid"], observations)
    print(f"  Shape: {pred.shape}")
    print(f"  Sum range: [{pred.sum(axis=2).min():.4f}, {pred.sum(axis=2).max():.4f}]")
    print(f"  Min prob: {pred.min():.6f}")
    print(f"  Max prob: {pred.max():.6f}")

    # Show predicted distribution
    avg_probs = pred.mean(axis=(0, 1))
    print(f"\n  Average predicted probabilities:")
    for i, name in enumerate(["Empty", "Settlement", "Port", "Ruin", "Forest", "Mountain"]):
        print(f"    {name}: {avg_probs[i]:.4f}")

    # 4. Validate
    print(f"\n[4] Validating predictions...")
    pred_list = predictions_to_list(pred)
    try:
        validate_predictions(pred_list, height, width)
        print("  PASSED: Valid prediction format")
    except AssertionError as e:
        print(f"  FAILED: {e}")
        return False

    # 5. Submit if requested
    if submit:
        print(f"\n[5] Submitting prediction for seed 0...")
        try:
            resp = api_client.submit_prediction(round_id, 0, pred_list)
            print(f"  Response: {json.dumps(resp, indent=2)}")
        except Exception as e:
            print(f"  Submit error: {e}")
    else:
        print(f"\n[5] Skipping submit (use --submit to submit)")

    print(f"\n{'='*60}")
    print("Pipeline test completed successfully!")
    return True


def test_server(round_id, server_url="http://localhost:8080"):
    """Test the /solve endpoint on a local server."""
    import requests

    print(f"Testing /solve endpoint at {server_url}...")

    # Health check
    try:
        resp = requests.get(f"{server_url}/health")
        print(f"Health: {resp.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

    # Solve
    payload = {"round_id": round_id}
    if api_client.ACCESS_TOKEN:
        payload["access_token"] = api_client.ACCESS_TOKEN

    print(f"Sending /solve with round_id={round_id}...")
    resp = requests.post(f"{server_url}/solve", json=payload, timeout=300)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    return resp.status_code == 200


def main():
    parser = argparse.ArgumentParser(description="Astar Island local test")
    parser.add_argument("--round", type=str, help="Specific round ID to test")
    parser.add_argument("--submit", action="store_true", help="Submit predictions")
    parser.add_argument("--server", action="store_true", help="Test local /solve endpoint")
    parser.add_argument("--server-url", default="http://localhost:8080", help="Server URL")
    parser.add_argument("--list-rounds", action="store_true", help="List available rounds")
    args = parser.parse_args()

    if args.list_rounds:
        list_rounds()
        return

    # Find a round to test
    round_id = args.round
    if not round_id:
        print("Fetching active rounds...")
        rounds = api_client.get_rounds()
        # Find an active round
        active = [r for r in rounds if r.get("status") == "active"] if isinstance(rounds, list) else []
        if not active and isinstance(rounds, list) and rounds:
            active = rounds  # use whatever is available
        elif isinstance(rounds, dict):
            # Handle dict response format
            active = rounds.get("rounds", rounds.get("data", []))

        if not active:
            print("No rounds found! Response:")
            print(json.dumps(rounds, indent=2))
            return

        if isinstance(active[0], dict):
            round_id = active[0].get("id", active[0].get("round_id"))
        else:
            round_id = active[0]
        print(f"Using round: {round_id}")

    if args.server:
        test_server(round_id, args.server_url)
    else:
        test_pipeline(round_id, submit=args.submit)


if __name__ == "__main__":
    main()
