"""Prediction logic for Astar Island.

Takes initial grid + observation results and builds a W×H×6 probability tensor.
"""

import numpy as np

# 6 prediction classes
NUM_CLASSES = 6
CLASS_NAMES = ["Empty", "Settlement", "Port", "Ruin", "Forest", "Mountain"]

# Map internal terrain codes to prediction class indices
TERRAIN_TO_CLASS = {
    10: 0,  # Ocean → Empty
    11: 0,  # Plains → Empty
    4: 4,   # Forest → Forest
    5: 5,   # Mountain → Mountain
    1: 1,   # Settlement → Settlement
    2: 2,   # Port → Port
    3: 3,   # Ruin → Ruin
}

# Probability floor to avoid KL divergence → infinity
PROB_FLOOR = 0.01


def terrain_code_to_class(code):
    """Convert internal terrain code to prediction class index."""
    return TERRAIN_TO_CLASS.get(code, 0)


def build_prediction(height, width, initial_grid, observations):
    """Build a H×W×6 probability tensor from initial grid + observations.

    Args:
        height: Grid height
        width: Grid width
        initial_grid: H×W grid of terrain codes (initial state)
        observations: List of observation dicts, each with:
            - viewport: {x, y, w, h}
            - grid: 2D terrain codes (after simulation)

    Returns:
        H×W×6 numpy array of probabilities (each cell sums to 1.0)
    """
    # Count terrain class occurrences per cell across observations
    counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    # Start with initial grid as a single "observation"
    for r in range(height):
        for c in range(width):
            cls = terrain_code_to_class(initial_grid[r][c])
            counts[r, c, cls] += 1

    # Add observations from viewport queries
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
                    counts[r, c, cls] += 1

    # Convert counts to probabilities
    predictions = _counts_to_probs(counts)
    return predictions


def _counts_to_probs(counts):
    """Convert observation counts to probability distributions with floor enforcement."""
    total = counts.sum(axis=2, keepdims=True)

    # Start with uniform distribution as default
    predictions = np.full_like(counts, 1.0 / NUM_CLASSES)

    # Normalize where we have observations
    mask = (total > 0)  # shape: (H, W, 1)
    np.divide(counts, total, out=predictions, where=mask)

    # Enforce probability floor
    predictions = apply_floor(predictions)

    return predictions


def apply_floor(predictions, floor=PROB_FLOOR):
    """Enforce minimum probability floor and renormalize.

    Uses iterative clipping to guarantee no value falls below floor.
    """
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
