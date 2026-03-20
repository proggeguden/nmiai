"""Prediction logic for Astar Island.

Core insight: hidden parameters are the SAME for all 5 seeds in a round.
So observations from any seed teach us the terrain transition probabilities.

Strategy:
1. Observe heavily on 1-2 seeds to learn transition rates
2. Build a transition model: P(final_class | initial_terrain_code)
3. Apply that model to all 5 seeds using their initial grids
4. For directly observed cells, blend per-cell counts with the global model
"""

import numpy as np

# 6 prediction classes
NUM_CLASSES = 6
CLASS_NAMES = ["Empty", "Settlement", "Port", "Ruin", "Forest", "Mountain"]

# Map internal terrain codes to prediction class indices
TERRAIN_TO_CLASS = {
    0: 0,   # Empty → Empty
    10: 0,  # Ocean → Empty
    11: 0,  # Plains → Empty
    4: 4,   # Forest → Forest
    5: 5,   # Mountain → Mountain
    1: 1,   # Settlement → Settlement
    2: 2,   # Port → Port
    3: 3,   # Ruin → Ruin
}

# Terrain codes that are static (never change in simulation)
STATIC_CODES = {10, 5}  # Ocean → always Empty, Mountain → always Mountain

# Probability floor to avoid KL divergence → infinity
PROB_FLOOR = 0.01


def terrain_code_to_class(code):
    """Convert internal terrain code to prediction class index."""
    return TERRAIN_TO_CLASS.get(code, 0)


def learn_transition_model(initial_grids, observations):
    """Learn P(final_class | initial_terrain_code) from observations.

    Args:
        initial_grids: list of H×W grids (one per seed that was observed)
        observations: list of observation dicts from those seeds, each with:
            - seed_index: which seed this observation is from
            - viewport: {x, y, w, h}
            - grid: 2D terrain codes (after simulation)

    Returns:
        dict mapping initial_terrain_code → np.array of shape (NUM_CLASSES,)
    """
    # Count transitions: for each initial terrain code, how often does it
    # become each class after simulation?
    transition_counts = {}  # code → np.array(NUM_CLASSES)

    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx >= len(initial_grids):
            continue
        initial_grid = initial_grids[seed_idx]

        vp = obs["viewport"]
        grid = obs["grid"]
        vp_x, vp_y = vp["x"], vp["y"]
        vp_h = len(grid)
        vp_w = len(grid[0]) if vp_h > 0 else 0

        for dr in range(vp_h):
            for dc in range(vp_w):
                r = vp_y + dr
                c = vp_x + dc
                if 0 <= r < len(initial_grid) and 0 <= c < len(initial_grid[0]):
                    init_code = initial_grid[r][c]
                    final_cls = terrain_code_to_class(grid[dr][dc])

                    if init_code not in transition_counts:
                        transition_counts[init_code] = np.zeros(NUM_CLASSES, dtype=np.float64)
                    transition_counts[init_code][final_cls] += 1

    # Normalize to probabilities
    transition_model = {}
    for code, counts in transition_counts.items():
        total = counts.sum()
        if total > 0:
            transition_model[code] = counts / total
        else:
            # Fallback: predict the class the code maps to
            probs = np.zeros(NUM_CLASSES)
            probs[terrain_code_to_class(code)] = 1.0
            transition_model[code] = probs

    return transition_model


def build_prediction(height, width, initial_grid, observations,
                     transition_model=None):
    """Build a H×W×6 probability tensor.

    If transition_model is provided, uses it for all cells (learned from
    observations across seeds). Per-cell observation counts are blended in
    for directly observed cells.

    If no transition_model, falls back to per-cell frequency counting.
    """
    predictions = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    # Step 1: Apply transition model (or initial-grid fallback) to all cells
    for r in range(height):
        for c in range(width):
            code = initial_grid[r][c]

            if code in STATIC_CODES:
                # Static: 100% one class
                predictions[r, c, terrain_code_to_class(code)] = 1.0
            elif transition_model and code in transition_model:
                predictions[r, c] = transition_model[code]
            else:
                # Fallback: predict the initial class
                predictions[r, c, terrain_code_to_class(code)] = 1.0

    # Step 2: For directly observed cells, blend per-cell counts with model
    if observations:
        cell_counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)
        cell_obs_count = np.zeros((height, width), dtype=np.float64)

        for obs in observations:
            vp = obs["viewport"]
            grid = obs["grid"]
            vp_x, vp_y = vp["x"], vp["y"]
            vp_h = len(grid)
            vp_w = len(grid[0]) if vp_h > 0 else 0

            for dr in range(vp_h):
                for dc in range(vp_w):
                    r = vp_y + dr
                    c = vp_x + dc
                    if 0 <= r < height and 0 <= c < width:
                        cls = terrain_code_to_class(grid[dr][dc])
                        cell_counts[r, c, cls] += 1
                        cell_obs_count[r, c] += 1

        # Blend: where we have direct observations, mix per-cell data with model
        # Weight: more observations → trust per-cell more
        observed_mask = cell_obs_count > 0
        if observed_mask.any():
            # Normalize per-cell counts
            cell_totals = cell_obs_count[..., np.newaxis]  # (H, W, 1)
            cell_probs = np.zeros_like(cell_counts)
            np.divide(cell_counts, cell_totals, out=cell_probs,
                      where=(cell_totals > 0))

            # Blend weight: alpha = n_obs / (n_obs + k), where k controls
            # how much we trust the global model vs local observations
            k = 5.0  # with 5+ observations, trust local data ~50%
            alpha = cell_obs_count / (cell_obs_count + k)
            alpha = alpha[..., np.newaxis]  # (H, W, 1)

            # Only blend non-static cells
            for r in range(height):
                for c in range(width):
                    if observed_mask[r, c] and initial_grid[r][c] not in STATIC_CODES:
                        predictions[r, c] = (
                            alpha[r, c, 0] * cell_probs[r, c]
                            + (1 - alpha[r, c, 0]) * predictions[r, c]
                        )

    # Step 3: Apply probability floor
    predictions = apply_floor(predictions)
    return predictions


def apply_floor(predictions, floor=PROB_FLOOR):
    """Enforce minimum probability floor and renormalize."""
    for _ in range(5):
        predictions = np.maximum(predictions, floor)
        sums = predictions.sum(axis=2, keepdims=True)
        predictions = predictions / sums
        if (predictions >= floor - 1e-9).all():
            break
    return predictions


def predictions_to_list(predictions):
    """Convert numpy predictions to nested list for JSON serialization."""
    return predictions.tolist()


def validate_predictions(predictions, height, width):
    """Validate prediction tensor format."""
    arr = np.array(predictions)
    assert arr.shape == (height, width, NUM_CLASSES), \
        f"Shape mismatch: expected ({height}, {width}, {NUM_CLASSES}), got {arr.shape}"

    sums = arr.sum(axis=2)
    assert np.allclose(sums, 1.0, atol=1e-4), \
        f"Probabilities don't sum to 1.0: min={sums.min():.4f}, max={sums.max():.4f}"

    assert (arr >= PROB_FLOOR - 1e-6).all(), \
        f"Probabilities below floor {PROB_FLOOR}: min={arr.min():.6f}"

    return True
