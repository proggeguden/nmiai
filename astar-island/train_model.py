"""Offline training script for ML predictor.

Usage:
    python3 train_model.py                    # Train on all GT data, export weights
    python3 train_model.py --cv               # Leave-one-round-out cross-validation
    python3 train_model.py --rebuild-data     # Rebuild training_data.npz from API
    python3 train_model.py --augmentations 5  # Control noisy rate augmentation count
"""

import argparse
import os
import sys
import time

import numpy as np

import api_client
from ml_predictor import extract_features, numpy_forward, save_model, NUM_FEATURES, RATE_KEYS
from predictor import (
    terrain_code_to_class,
    estimate_survival_rate,
    estimate_expansion_rate,
    estimate_port_formation_rate,
    estimate_all_rates,
    score_predictions,
    STATIC_CODES,
    TERRAIN_TO_CLASS,
    NUM_CLASSES,
)


# ---------------------------------------------------------------------------
# GT rate computation
# ---------------------------------------------------------------------------

def compute_gt_rates(gt, initial_grid):
    """Compute ground-truth round-level rates from GT probability tensor.

    Args:
        gt: H×W×6 probability array (ground truth)
        initial_grid: H×W terrain code list

    Returns:
        dict with survival, expansion, port_formation, forest_reclamation, ruin rates
    """
    H, W = len(initial_grid), len(initial_grid[0])
    sett_alive, sett_total = 0.0, 0.0
    new_sett, non_sett = 0.0, 0.0
    port_formed, coastal_non_port = 0.0, 0.0
    forest_reclaimed, non_forest_near = 0.0, 0.0
    ruin_count = 0.0

    for r in range(H):
        for c in range(W):
            code = initial_grid[r][c]
            if code in STATIC_CODES:
                continue
            gt_dist = gt[r, c]

            if code in (1, 2):  # Initial settlement/port
                sett_total += 1.0
                sett_alive += gt_dist[1] + gt_dist[2]  # P(Settlement) + P(Port)
                ruin_count += gt_dist[3]  # P(Ruin)

            if code in (0, 11, 4):  # Non-settlement
                non_sett += 1.0
                new_sett += gt_dist[1]  # P(Settlement)

            # Coastal non-port for port formation
            is_coastal = any(
                0 <= r + dr < H and 0 <= c + dc < W and initial_grid[r + dr][c + dc] == 10
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
            )
            if is_coastal and code != 2:
                coastal_non_port += 1.0
                port_formed += gt_dist[2]

            # Forest reclamation: non-forest cells near forest
            has_adj_forest = any(
                0 <= r + dr < H and 0 <= c + dc < W and initial_grid[r + dr][c + dc] == 4
                for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0)
            )
            if has_adj_forest and code != 4:
                non_forest_near += 1.0
                forest_reclaimed += gt_dist[4]

    # Forest clearing rate: P(non-forest | initially forest)
    forest_total, forest_cleared = 0.0, 0.0
    for r in range(H):
        for c in range(W):
            if initial_grid[r][c] == 4:
                forest_total += 1.0
                forest_cleared += (1.0 - gt[r, c, 4])  # 1 - P(stays forest)

    return {
        "survival": sett_alive / max(sett_total, 1),
        "expansion": min(new_sett / max(non_sett, 1), 0.50),
        "port_formation": min(port_formed / max(coastal_non_port, 1), 0.15),
        "forest_reclamation": min(forest_reclaimed / max(non_forest_near, 1), 0.40),
        "ruin": min(ruin_count / max(sett_total, 1), 0.95),
        "forest_clearing": min(forest_cleared / max(forest_total, 1), 0.60),
    }


# ---------------------------------------------------------------------------
# Noisy rate simulation (matches production noise)
# ---------------------------------------------------------------------------

CLASS_TO_CODE = {0: 11, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}  # Empty class → Plains code


def _api_retry(func, *args, max_retries=5, base_wait=3.0):
    """Call an API function with retry on 429 rate limit errors."""
    for attempt in range(max_retries):
        try:
            return func(*args)
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = base_wait * (attempt + 1)
                print(f"  Rate limited, waiting {wait:.0f}s... (attempt {attempt + 1})")
                time.sleep(wait)
            else:
                raise


def simulate_noisy_rates(gt, initial_grid, rng, n_queries=50):
    """Simulate production rate estimation from n_queries viewport observations.

    Samples discrete terrain from GT, creates viewport-like observations,
    then runs existing rate estimators on them. Matches production noise profile
    by simulating actual viewport strategy (15×15 tiles sorted by settlement density).
    """
    H, W = len(initial_grid), len(initial_grid[0])

    # Create viewport-like observations (15×15 tiles, sorted by settlement density)
    vp_size = 15
    tiles = []
    for y in range(0, H, vp_size):
        for x in range(0, W, vp_size):
            h = min(vp_size, H - y)
            w = min(vp_size, W - x)
            sett_count = sum(1 for dr in range(h) for dc in range(w)
                             if initial_grid[y + dr][x + dc] in (1, 2))
            dynamic = sum(1 for dr in range(h) for dc in range(w)
                          if initial_grid[y + dr][x + dc] not in STATIC_CODES)
            tiles.append((dynamic + sett_count * 3, x, y, w, h))
    tiles.sort(reverse=True)

    # Select up to n_queries tiles (unique first, then repeat top tiles)
    unique_tiles = tiles[:n_queries]
    remaining = n_queries - len(unique_tiles)
    if remaining > 0 and tiles:
        repeat_pool = tiles[:max(1, len(tiles) // 3)]
        all_tiles = unique_tiles + [repeat_pool[i % len(repeat_pool)]
                                     for i in range(remaining)]
    else:
        all_tiles = unique_tiles

    observations = []
    for _, vp_x, vp_y, vp_w, vp_h in all_tiles[:n_queries]:
        # Sample discrete terrain for each observation (different stochastic outcome)
        grid_obs = []
        for dr in range(vp_h):
            row = []
            for dc in range(vp_w):
                r, c = vp_y + dr, vp_x + dc
                if 0 <= r < H and 0 <= c < W:
                    cls = rng.choice(6, p=gt[r, c])
                    row.append(CLASS_TO_CODE[cls])
                else:
                    row.append(11)  # Out of bounds → Plains (Empty class)
            grid_obs.append(row)

        observations.append({
            "viewport": {"x": vp_x, "y": vp_y, "w": vp_w, "h": vp_h},
            "grid": grid_obs,
            "seed_index": 0,
        })

    # Estimate rates using existing production functions
    initial_grids = [initial_grid]
    rates = estimate_all_rates(initial_grids, observations)
    return rates


# ---------------------------------------------------------------------------
# Training data construction
# ---------------------------------------------------------------------------

def build_training_data(n_augmentations=10, cache_path="training_data.npz"):
    """Fetch GT from all completed rounds and build training dataset.

    Returns:
        X: (N, 18) feature array
        Y: (N, 6) target probability array
        round_ids: (N,) round index per example (for CV)
    """
    if os.path.exists(cache_path):
        print(f"Loading cached training data from {cache_path}")
        data = np.load(cache_path)
        return data["X"], data["Y"], data["round_ids"]

    rounds = _api_retry(api_client.get_rounds)
    completed = [r for r in rounds if r["status"] == "completed"]
    print(f"Found {len(completed)} completed rounds")

    all_X, all_Y, all_round_ids = [], [], []
    valid_round_idx = 0

    for round_info in completed:
        round_id = round_info["id"]
        round_num = round_info.get("round_number", "?")
        detail = _api_retry(api_client.get_round_detail, round_id)
        initial_states = detail["initial_states"]
        seeds_count = len(initial_states)

        print(f"\nRound {round_num} ({round_id[:8]}): {seeds_count} seeds")

        # Fetch GT for all seeds
        all_gt = {}
        skip_round = False
        for seed_idx in range(seeds_count):
            try:
                analysis = _api_retry(api_client.get_analysis, round_id, seed_idx)
                all_gt[seed_idx] = np.array(analysis["ground_truth"])
            except Exception as e:
                if "404" in str(e) or "400" in str(e):
                    print(f"  No analysis for R{round_num} seed {seed_idx}, skipping round")
                else:
                    print(f"  Error fetching R{round_num} seed {seed_idx}: {e}")
                skip_round = True
                break
            time.sleep(0.5)  # Rate limit courtesy

        if skip_round or len(all_gt) < seeds_count:
            print(f"  Skipping round {round_num} (incomplete GT data)")
            continue

        round_idx = valid_round_idx
        valid_round_idx += 1

        time.sleep(0.5)  # Extra delay between rounds
        rng = np.random.default_rng(seed=42 + round_idx)

        for aug_idx in range(n_augmentations):
            # Generate noisy rates for this augmentation
            rate_seed = rng.integers(0, seeds_count)
            noisy_rates = simulate_noisy_rates(
                all_gt[rate_seed], initial_states[rate_seed]["grid"], rng
            )

            for seed_idx in range(seeds_count):
                gt = all_gt[seed_idx]
                init_grid = initial_states[seed_idx]["grid"]
                H, W = gt.shape[0], gt.shape[1]

                # Extract features with noisy rates
                features = extract_features(init_grid, noisy_rates)

                # Collect dynamic cells only
                for r in range(H):
                    for c in range(W):
                        if init_grid[r][c] in STATIC_CODES:
                            continue
                        if gt[r, c].max() >= 1.0:
                            continue  # Static cell (deterministic outcome)
                        all_X.append(features[r, c])
                        all_Y.append(gt[r, c].astype(np.float32))
                        all_round_ids.append(round_idx)

            if (aug_idx + 1) % 5 == 0:
                print(f"  Aug {aug_idx + 1}/{n_augmentations}, "
                      f"samples so far: {len(all_X)}")

    X = np.array(all_X, dtype=np.float32)
    Y = np.array(all_Y, dtype=np.float32)
    round_ids = np.array(all_round_ids, dtype=np.int32)

    print(f"\nTotal training examples: {len(X)}")
    print(f"Feature shape: {X.shape}, Target shape: {Y.shape}")

    np.savez(cache_path, X=X, Y=Y, round_ids=round_ids)
    print(f"Saved to {cache_path}")

    return X, Y, round_ids


# ---------------------------------------------------------------------------
# PyTorch training
# ---------------------------------------------------------------------------

def train_model(X, Y, round_ids=None, exclude_round=None,
                epochs=80, batch_size=4096, lr=1e-3, verbose=True):
    """Train MLP on feature/target data.

    Args:
        X: (N, 18) features
        Y: (N, 6) target distributions
        round_ids: (N,) round index per sample (for CV filtering)
        exclude_round: round index to exclude (for LOOCV)

    Returns:
        dict of numpy weight arrays + normalization stats
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import TensorDataset, DataLoader

    class TerrainMLP(nn.Module):
        def __init__(self, n_features=NUM_FEATURES, n_classes=6):
            super().__init__()
            self.fc1 = nn.Linear(n_features, 256)
            self.fc2 = nn.Linear(256, 128)
            self.fc3 = nn.Linear(128, 64)
            self.fc4 = nn.Linear(64, n_classes)
            self.dropout = nn.Dropout(0.1)

        def forward(self, x):
            x = self.dropout(F.relu(self.fc1(x)))
            x = self.dropout(F.relu(self.fc2(x)))
            x = F.relu(self.fc3(x))
            x = F.softmax(self.fc4(x), dim=-1)
            return x

    # Filter for CV
    if exclude_round is not None and round_ids is not None:
        mask = round_ids != exclude_round
        X_train = X[mask]
        Y_train = Y[mask]
        if verbose:
            print(f"  Training on {mask.sum()} samples "
                  f"(excluded round {exclude_round}: {(~mask).sum()} samples)")
    else:
        X_train = X
        Y_train = Y

    # Compute normalization stats
    feat_mean = X_train.mean(axis=0).astype(np.float32)
    feat_std = X_train.std(axis=0).astype(np.float32)
    feat_std[feat_std < 1e-6] = 1.0

    # Normalize
    X_norm = (X_train - feat_mean) / feat_std

    # Convert to tensors
    X_t = torch.tensor(X_norm, dtype=torch.float32)
    Y_t = torch.tensor(Y_train, dtype=torch.float32)

    dataset = TensorDataset(X_t, Y_t)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True,
                        num_workers=0, pin_memory=False)

    model = TerrainMLP()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_loss = float("inf")
    patience = 10
    patience_counter = 0
    best_state = None

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        n_batches = 0
        for X_batch, Y_batch in loader:
            pred = model(X_batch)
            # KL divergence: F.kl_div expects log(pred) as first arg
            log_pred = torch.log(pred + 1e-8)
            loss = F.kl_div(log_pred, Y_batch, reduction="batchmean")

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_loss = total_loss / n_batches

        if avg_loss < best_loss - 1e-6:
            best_loss = avg_loss
            patience_counter = 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1

        if verbose and (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch + 1}/{epochs}: loss={avg_loss:.6f} "
                  f"best={best_loss:.6f} lr={scheduler.get_last_lr()[0]:.6f}")

        if patience_counter >= patience:
            if verbose:
                print(f"  Early stopping at epoch {epoch + 1}")
            break

    # Load best state
    if best_state:
        model.load_state_dict(best_state)
    model.eval()

    # Export weights as numpy
    weights = {
        "fc1_w": model.fc1.weight.detach().numpy().astype(np.float32),
        "fc1_b": model.fc1.bias.detach().numpy().astype(np.float32),
        "fc2_w": model.fc2.weight.detach().numpy().astype(np.float32),
        "fc2_b": model.fc2.bias.detach().numpy().astype(np.float32),
        "fc3_w": model.fc3.weight.detach().numpy().astype(np.float32),
        "fc3_b": model.fc3.bias.detach().numpy().astype(np.float32),
        "fc4_w": model.fc4.weight.detach().numpy().astype(np.float32),
        "fc4_b": model.fc4.bias.detach().numpy().astype(np.float32),
        "feat_mean": feat_mean,
        "feat_std": feat_std,
    }
    return weights


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------

def cross_validate(X, Y, round_ids, verbose=True):
    """Leave-one-round-out cross-validation.

    Returns:
        dict mapping round_index → avg KL divergence
    """
    unique_rounds = sorted(set(round_ids))
    results = {}

    print(f"\nCross-validation: {len(unique_rounds)} folds")

    for fold_idx, round_idx in enumerate(unique_rounds):
        if verbose:
            print(f"\n--- Fold {fold_idx + 1}/{len(unique_rounds)}: "
                  f"exclude round {round_idx} ---")

        weights = train_model(X, Y, round_ids, exclude_round=round_idx,
                              verbose=verbose)

        # Evaluate on held-out round
        mask = round_ids == round_idx
        X_test = X[mask]
        Y_test = Y[mask]

        # Forward pass using numpy (production path)
        N = X_test.shape[0]
        # Reshape to use numpy_forward (expects H×W×F)
        preds = numpy_forward(X_test.reshape(1, N, NUM_FEATURES), weights)
        preds = preds.reshape(N, NUM_CLASSES)

        # Compute KL per cell
        kl_per_cell = np.sum(
            Y_test * np.log((Y_test + 1e-10) / (preds + 1e-10)), axis=1
        )
        avg_kl = float(kl_per_cell.mean())
        results[int(round_idx)] = avg_kl

        if verbose:
            print(f"  Round {round_idx}: avg cell KL = {avg_kl:.6f} "
                  f"({mask.sum()} cells)")

    overall = float(np.mean(list(results.values())))
    if verbose:
        print(f"\n{'='*50}")
        print(f"CV Overall: avg cell KL = {overall:.6f}")
        print(f"Per-round: {', '.join(f'R{k}={v:.4f}' for k, v in sorted(results.items()))}")

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train ML predictor for Astar Island")
    parser.add_argument("--cv", action="store_true",
                        help="Run leave-one-round-out cross-validation")
    parser.add_argument("--rebuild-data", action="store_true",
                        help="Rebuild training data from API (ignore cache)")
    parser.add_argument("--augmentations", type=int, default=10,
                        help="Number of noisy rate augmentations per round")
    parser.add_argument("--output", default="model_weights.npz",
                        help="Output path for trained weights")
    parser.add_argument("--epochs", type=int, default=80,
                        help="Training epochs")
    parser.add_argument("--lr", type=float, default=1e-3,
                        help="Learning rate")
    parser.add_argument("--n-snapshots", type=int, default=1,
                        help="Number of ensemble snapshots to train (different seeds)")
    args = parser.parse_args()

    cache = "training_data.npz"
    if args.rebuild_data and os.path.exists(cache):
        os.remove(cache)
        print("Removed cached training data, will rebuild from API")

    X, Y, round_ids = build_training_data(
        n_augmentations=args.augmentations, cache_path=cache
    )

    if args.cv:
        cross_validate(X, Y, round_ids)
    else:
        n_snap = args.n_snapshots
        if n_snap > 1:
            print(f"\nTraining {n_snap}-snapshot ensemble on {len(X)} samples...")
            from ml_predictor import save_ensemble
            snapshots = []
            for snap_idx in range(n_snap):
                print(f"\n--- Snapshot {snap_idx + 1}/{n_snap} (seed offset={snap_idx * 7}) ---")
                import torch
                torch.manual_seed(42 + snap_idx * 7)
                weights = train_model(X, Y, epochs=args.epochs, lr=args.lr, verbose=True)
                snapshots.append(weights)
            save_ensemble(snapshots, args.output)
            print(f"\nEnsemble ({n_snap} snapshots) saved to {args.output}")
        else:
            print(f"\nTraining final model on all {len(X)} samples...")
            weights = train_model(X, Y, epochs=args.epochs, lr=args.lr, verbose=True)
            save_model(weights, args.output)
            print(f"\nModel saved to {args.output}")
        print(f"Weights file size: {os.path.getsize(args.output) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
