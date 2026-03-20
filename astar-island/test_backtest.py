"""Enhanced backtest with JSON output, regression detection, and per-terrain breakdown.

Usage:
    python3 test_backtest.py                            # backtest all, human-readable
    python3 test_backtest.py --round ROUND_ID           # single round
    python3 test_backtest.py --output results.json      # write JSON results
    python3 test_backtest.py --baseline baseline.json   # compare to baseline
    python3 test_backtest.py --threshold 0.10            # regression threshold (10% relative)

Exit codes:
    0 = no regressions
    1 = regression detected
    2 = error
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

import api_client
from predictor import (
    build_prediction,
    compute_feature_map,
    score_predictions,
    terrain_code_to_class,
    NUM_CLASSES,
    CLASS_NAMES,
    STATIC_CODES,
)


def get_git_commit():
    """Get short git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def per_terrain_kl(pred, gt, initial_grid, height, width):
    """Compute per-terrain-type KL breakdown.

    Returns dict: terrain_name → {weighted_kl, cell_count, share_of_loss}
    """
    kl = np.sum(gt * np.log((gt + 1e-10) / (pred + 1e-10)), axis=2)
    entropy = -np.sum(gt * np.log(gt + 1e-10), axis=2)

    # Group cells by initial terrain code
    terrain_groups = {}  # code → list of (r, c)
    for r in range(height):
        for c in range(width):
            code = initial_grid[r][c]
            if code not in terrain_groups:
                terrain_groups[code] = []
            terrain_groups[code].append((r, c))

    # Map internal codes to display names
    CODE_NAMES = {
        0: "Empty", 10: "Ocean", 11: "Plains", 1: "Settlement",
        2: "Port", 3: "Ruin", 4: "Forest", 5: "Mountain",
    }

    total_weighted_loss = 0
    results = {}
    for code, cells in terrain_groups.items():
        group_kl = 0
        group_entropy = 0
        for r, c in cells:
            if entropy[r, c] > 0.01:
                group_kl += kl[r, c] * entropy[r, c]
                group_entropy += entropy[r, c]
        if group_entropy > 0:
            weighted = group_kl / group_entropy
        else:
            weighted = 0
        total_weighted_loss += group_kl
        name = CODE_NAMES.get(code, f"Code{code}")
        results[name] = {
            "weighted_kl": float(weighted),
            "cell_count": len(cells),
            "total_loss": float(group_kl),
        }

    # Compute share of loss
    if total_weighted_loss > 0:
        for name in results:
            results[name]["share_of_loss"] = float(
                results[name]["total_loss"] / total_weighted_loss
            )
    else:
        for name in results:
            results[name]["share_of_loss"] = 0.0

    # Remove internal total_loss field
    for name in results:
        del results[name]["total_loss"]

    return results


def worst_cells(pred, gt, initial_grid, height, width, seed_idx, top_n=10):
    """Find worst-predicted cells for diagnosis."""
    kl = np.sum(gt * np.log((gt + 1e-10) / (pred + 1e-10)), axis=2)
    fmap, _, _ = compute_feature_map(initial_grid)

    cells = []
    for r in range(height):
        for c in range(width):
            if initial_grid[r][c] in STATIC_CODES:
                continue
            cells.append((kl[r, c], r, c))

    cells.sort(reverse=True)
    result = []
    for cell_kl, r, c in cells[:top_n]:
        gt_top_idx = int(np.argmax(gt[r, c]))
        pred_top_idx = int(np.argmax(pred[r, c]))
        result.append({
            "r": r, "c": c,
            "kl": float(cell_kl),
            "seed": seed_idx,
            "init_code": initial_grid[r][c],
            "bucket_key": str(fmap[r][c]),
            "gt_top": f"{CLASS_NAMES[gt_top_idx]}={gt[r, c, gt_top_idx]:.3f}",
            "pred_top": f"{CLASS_NAMES[pred_top_idx]}={pred[r, c, pred_top_idx]:.3f}",
        })
    return result


def backtest_round_enhanced(round_id, verbose=True):
    """Backtest a single round with enhanced diagnostics.

    Returns dict with per-round results.
    """
    detail = api_client.get_round_detail(round_id)
    height, width = detail["map_height"], detail["map_width"]
    seeds_count = detail["seeds_count"]
    initial_states = detail["initial_states"]
    round_number = detail.get("round_number", 0)

    # Load GT for all seeds
    all_gt = {}
    for seed_idx in range(seeds_count):
        all_gt[seed_idx] = np.array(api_client.get_analysis(round_id, seed_idx)["ground_truth"])

    # Build multi-seed models from GT (same as backtest_round in test_local.py)
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
                if code not in global_probs:
                    global_probs[code] = np.zeros(NUM_CLASSES)
                global_probs[code] += gt[r, c]
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

    # Compute forward rates from GT
    forward_rates = _compute_forward_rates(initial_states, all_gt, height, width, seeds_count)

    # Score all seeds with model variants
    model_variants = {}
    for model_name, gm, sm, fr in [
        ("5seed-Spatial", global_model, spatial_model, None),
        ("5seed-Sp+Forward", global_model, spatial_model, forward_rates),
    ]:
        kl_scores = []
        for seed_idx in range(seeds_count):
            gt = all_gt[seed_idx]
            init_grid = initial_states[seed_idx]["grid"]
            pred = build_prediction(height, width, init_grid, [],
                                    transition_model=gm, spatial_model=sm,
                                    forward_rates=fr)
            wkl, _ = score_predictions(pred, gt)
            kl_scores.append(float(wkl))
        model_variants[model_name] = float(np.mean(kl_scores))

    # Primary model: 5seed-Spatial — get detailed per-seed results
    per_seed_kl = []
    all_terrain_kl = {}
    all_worst = []
    for seed_idx in range(seeds_count):
        gt = all_gt[seed_idx]
        init_grid = initial_states[seed_idx]["grid"]
        pred = build_prediction(height, width, init_grid, [],
                                transition_model=global_model,
                                spatial_model=spatial_model)
        wkl, _ = score_predictions(pred, gt)
        per_seed_kl.append(float(wkl))

        # Per-terrain breakdown (aggregate across seeds)
        terrain = per_terrain_kl(pred, gt, init_grid, height, width)
        for name, data in terrain.items():
            if name not in all_terrain_kl:
                all_terrain_kl[name] = {"weighted_kl_sum": 0, "cell_count": 0, "loss_sum": 0}
            all_terrain_kl[name]["weighted_kl_sum"] += data["weighted_kl"]
            all_terrain_kl[name]["cell_count"] += data["cell_count"]
            all_terrain_kl[name]["loss_sum"] += data["share_of_loss"]

        # Worst cells (from first seed only to keep output manageable)
        if seed_idx == 0:
            all_worst = worst_cells(pred, gt, init_grid, height, width, seed_idx)

    # Average per-terrain across seeds
    per_terrain = {}
    for name, data in all_terrain_kl.items():
        per_terrain[name] = {
            "weighted_kl": float(data["weighted_kl_sum"] / seeds_count),
            "cell_count": data["cell_count"],
            "share_of_loss": float(data["loss_sum"] / seeds_count),
        }

    avg_kl = float(np.mean(per_seed_kl))

    if verbose:
        print(f"\n  Round {round_number}: avg_weighted_kl = {avg_kl:.4f}")
        print(f"    Per seed: {', '.join(f'{s:.4f}' for s in per_seed_kl)}")
        print(f"    Variants: {', '.join(f'{k}={v:.4f}' for k, v in model_variants.items())}")
        print(f"    Forward rates: { {k: f'{v:.4f}' if v else 'None' for k, v in forward_rates.items()} }")
        print(f"    Per-terrain KL:")
        for name, data in sorted(per_terrain.items(), key=lambda x: -x[1]["share_of_loss"]):
            print(f"      {name:12s}: wkl={data['weighted_kl']:.4f}, "
                  f"cells={data['cell_count']:>5d}, share={data['share_of_loss']:.2%}")

    return {
        "round_id": round_id,
        "round_number": round_number,
        "avg_weighted_kl": avg_kl,
        "per_seed": per_seed_kl,
        "forward_rates": {k: float(v) if v is not None else None for k, v in forward_rates.items()},
        "per_terrain_kl": per_terrain,
        "worst_cells": all_worst,
        "model_variants": model_variants,
    }


def _compute_forward_rates(initial_states, all_gt, height, width, seeds_count):
    """Compute forward model rates from GT probability distributions."""
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
        gt = all_gt[seed_idx]
        init_grid = initial_states[seed_idx]["grid"]
        for r in range(height):
            for c in range(width):
                code = init_grid[r][c]
                if code in STATIC_CODES:
                    continue
                gt_probs = gt[r, c]

                if code in (1, 2):
                    survival_total += gt_probs[1] + gt_probs[2]
                    ruin_total += gt_probs[3]
                    survival_count += 1
                    ruin_count += 1
                elif code in (0, 11):
                    expansion_new += gt_probs[1]
                    expansion_eligible += 1
                    is_coastal = False
                    for nr, nc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                        if 0 <= nr < height and 0 <= nc < width and init_grid[nr][nc] == 10:
                            is_coastal = True
                            break
                    if is_coastal:
                        port_formed += gt_probs[2]
                        coastal_nonport += 1

                if code != 4 and code not in STATIC_CODES:
                    adj_forest = 0
                    for ar in range(max(0, r-1), min(height, r+2)):
                        for ac in range(max(0, c-1), min(width, c+2)):
                            if (ar, ac) != (r, c) and init_grid[ar][ac] == 4:
                                adj_forest += 1
                    if adj_forest > 0:
                        forest_reclaimed += gt_probs[4]
                        forest_eligible += 1

    return {
        "survival": survival_total / survival_count if survival_count > 0 else None,
        "expansion": expansion_new / expansion_eligible if expansion_eligible > 0 else None,
        "port_formation": port_formed / coastal_nonport if coastal_nonport > 0 else None,
        "forest_reclamation": forest_reclaimed / forest_eligible if forest_eligible > 0 else None,
        "ruin": ruin_total / ruin_count if ruin_count > 0 else None,
    }


def compare_baseline(results, baseline_path, threshold):
    """Compare results against a baseline. Returns regression info or None."""
    try:
        with open(baseline_path, "r") as f:
            baseline = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"error": str(e)}

    baseline_avg = baseline["overall"]["avg_weighted_kl"]
    current_avg = results["overall"]["avg_weighted_kl"]
    overall_delta = (current_avg - baseline_avg) / max(baseline_avg, 1e-6)

    per_round_regressions = []
    baseline_rounds = {r["round_id"]: r for r in baseline.get("per_round", [])}

    for r in results["per_round"]:
        rid = r["round_id"]
        if rid in baseline_rounds:
            base_kl = baseline_rounds[rid]["avg_weighted_kl"]
            curr_kl = r["avg_weighted_kl"]
            delta = (curr_kl - base_kl) / max(base_kl, 1e-6)
            if delta > threshold:
                per_round_regressions.append({
                    "round_id": rid,
                    "round_number": r["round_number"],
                    "baseline_kl": base_kl,
                    "current_kl": curr_kl,
                    "delta_pct": float(delta),
                })

    regression = None
    if overall_delta > 0.05:  # overall 5% regression
        regression = {
            "type": "overall",
            "baseline_avg": float(baseline_avg),
            "current_avg": float(current_avg),
            "delta_pct": float(overall_delta),
            "per_round_regressions": per_round_regressions,
        }
    elif per_round_regressions:
        regression = {
            "type": "per_round",
            "per_round_regressions": per_round_regressions,
        }

    return regression


def main():
    parser = argparse.ArgumentParser(description="Enhanced Astar Island backtest")
    parser.add_argument("--round", type=str, help="Specific round ID")
    parser.add_argument("--output", type=str, help="Write JSON results to file")
    parser.add_argument("--baseline", type=str, help="Compare to baseline JSON")
    parser.add_argument("--threshold", type=float, default=0.10,
                        help="Regression threshold (relative, default 0.10)")
    args = parser.parse_args()

    try:
        rounds = api_client.get_rounds()
        completed = [r for r in rounds if r["status"] == "completed"]

        if args.round:
            round_ids = [args.round]
        else:
            round_ids = [r["id"] for r in completed]

        if not round_ids:
            print("No completed rounds to backtest.")
            sys.exit(2)

        print(f"Backtesting {len(round_ids)} round(s)...")
        per_round = []
        for rid in round_ids:
            result = backtest_round_enhanced(rid)
            per_round.append(result)

        # Compute overall stats
        all_kls = [r["avg_weighted_kl"] for r in per_round]
        avg_kl = float(np.mean(all_kls))

        # Rounds 1-6 avg (if available)
        r1_r6 = [r for r in per_round if r["round_number"] <= 6]
        avg_r1_r6 = float(np.mean([r["avg_weighted_kl"] for r in r1_r6])) if r1_r6 else None

        # Model variant averages
        variant_avgs = {}
        for name in per_round[0]["model_variants"]:
            vals = [r["model_variants"].get(name) for r in per_round if r["model_variants"].get(name) is not None]
            if vals:
                variant_avgs[name] = float(np.mean(vals))

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": get_git_commit(),
            "overall": {
                "avg_weighted_kl": avg_kl,
                "avg_weighted_kl_r1_r6": avg_r1_r6,
                "rounds_tested": len(per_round),
                "model_variants": variant_avgs,
            },
            "per_round": per_round,
            "regression": None,
        }

        # Summary
        print(f"\n{'='*60}")
        print(f"Overall: avg_weighted_kl = {avg_kl:.4f}")
        if avg_r1_r6 is not None:
            print(f"  R1-R6 avg: {avg_r1_r6:.4f}")
        for name, val in variant_avgs.items():
            print(f"  {name}: {val:.4f}")

        # Baseline comparison
        if args.baseline:
            regression = compare_baseline(results, args.baseline, args.threshold)
            results["regression"] = regression
            if regression:
                if "error" in regression:
                    print(f"\nBaseline error: {regression['error']}")
                elif regression["type"] == "overall":
                    print(f"\nREGRESSION DETECTED (overall): "
                          f"{regression['baseline_avg']:.4f} → {regression['current_avg']:.4f} "
                          f"({regression['delta_pct']:+.1%})")
                elif regression["type"] == "per_round":
                    print(f"\nREGRESSION DETECTED ({len(regression['per_round_regressions'])} round(s)):")
                    for rr in regression["per_round_regressions"]:
                        print(f"  Round {rr['round_number']}: "
                              f"{rr['baseline_kl']:.4f} → {rr['current_kl']:.4f} "
                              f"({rr['delta_pct']:+.1%})")
            else:
                print("\nNo regression detected.")

        # Write output
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults written to {args.output}")

        # Exit code
        if results["regression"] and "error" not in (results["regression"] or {}):
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
