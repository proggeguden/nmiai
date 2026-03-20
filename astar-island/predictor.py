"""Prediction logic for Astar Island.

Core insight: hidden parameters are the SAME for all 5 seeds in a round.
So observations from any seed teach us the terrain transition probabilities.

Strategy:
1. Observe heavily on 1-2 seeds to learn transition rates
2. Build a spatial transition model: P(final_class | initial_code, spatial_features)
3. Apply that model to all 5 seeds using their initial grids
4. For directly observed cells, blend per-cell counts with the model
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

# Minimum observations per spatial bucket before we trust it
MIN_BUCKET_OBS = 10


def terrain_code_to_class(code):
    """Convert internal terrain code to prediction class index."""
    return TERRAIN_TO_CLASS.get(code, 0)


# ---------------------------------------------------------------------------
# Spatial feature computation
# ---------------------------------------------------------------------------

def _precompute_settlement_distances(initial_grid):
    """Precompute Manhattan distance to nearest settlement for all cells.

    Returns H×W list of lists with distances (999 if no settlements exist).
    """
    H = len(initial_grid)
    W = len(initial_grid[0])
    settlements = []
    for r in range(H):
        for c in range(W):
            if initial_grid[r][c] in (1, 2):
                settlements.append((r, c))

    if not settlements:
        return [[999] * W for _ in range(H)]

    # BFS from all settlements simultaneously for efficiency
    dist = [[999] * W for _ in range(H)]
    from collections import deque
    q = deque()
    for sr, sc in settlements:
        dist[sr][sc] = 0
        q.append((sr, sc))

    while q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and dist[nr][nc] > dist[r][c] + 1:
                dist[nr][nc] = dist[r][c] + 1
                q.append((nr, nc))

    return dist


def compute_bucket_key(initial_grid, r, c, settlement_dists=None):
    """Compute spatial bucket key for a cell based on its neighbors.

    Features are computed from the initial grid (fully visible, no queries needed).
    Returns a tuple used as dict key for the spatial transition model.

    settlement_dists: precomputed Manhattan distance grid (optional, for efficiency).
    """
    code = initial_grid[r][c]
    H = len(initial_grid)
    W = len(initial_grid[0])

    if code in STATIC_CODES:
        return (code,)

    # Count 8-connected neighbors by type
    adj_forest = 0
    adj_ocean = 0
    adj_settlement = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W:
                n = initial_grid[nr][nc]
                if n == 4:
                    adj_forest += 1
                elif n == 10:
                    adj_ocean += 1
                elif n in (1, 2):
                    adj_settlement += 1

    # Compute distance bucket to nearest settlement
    if settlement_dists is not None:
        d = settlement_dists[r][c]
    else:
        # Fallback: compute distance manually (slower)
        d = 999
        for sr in range(H):
            for sc in range(W):
                if initial_grid[sr][sc] in (1, 2):
                    d = min(d, abs(r - sr) + abs(c - sc))

    # 3-level distance bucket: 0=near(≤2), 1=mid(3-4), 2=far(5+)
    dist_bucket = 0 if d <= 2 else (1 if d <= 4 else 2)

    is_coastal = adj_ocean > 0
    has_adj_forest = adj_forest > 0
    has_adj_settlement = adj_settlement > 0

    if code == 1:    # Settlement
        return (1, has_adj_forest, has_adj_settlement)
    elif code == 2:  # Port
        return (2, has_adj_forest)
    elif code == 11: # Plains
        return (11, dist_bucket, is_coastal)
    elif code == 0:  # Empty
        return (0, dist_bucket)
    elif code == 4:  # Forest
        return (4, dist_bucket)
    elif code == 3:  # Ruin
        return (3, dist_bucket)
    else:
        return (code,)


def compute_feature_map(initial_grid):
    """Compute spatial bucket keys for all cells in the grid.

    Returns list of lists of bucket key tuples (H×W).
    """
    H = len(initial_grid)
    W = len(initial_grid[0])
    settlement_dists = _precompute_settlement_distances(initial_grid)
    return [[compute_bucket_key(initial_grid, r, c, settlement_dists) for c in range(W)]
            for r in range(H)]


# ---------------------------------------------------------------------------
# Transition model learning
# ---------------------------------------------------------------------------

def learn_transition_model(initial_grids, observations):
    """Learn P(final_class | initial_terrain_code) from observations.

    Returns dict mapping initial_terrain_code → np.array(NUM_CLASSES).
    """
    transition_counts = {}

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

    transition_model = {}
    for code, counts in transition_counts.items():
        total = counts.sum()
        if total > 0:
            transition_model[code] = counts / total
        else:
            probs = np.zeros(NUM_CLASSES)
            probs[terrain_code_to_class(code)] = 1.0
            transition_model[code] = probs

    return transition_model


def learn_spatial_transition_model(initial_grids, observations):
    """Learn P(final_class | bucket_key) from observations.

    Returns:
        global_model: dict mapping terrain_code → probability vector (fallback)
        spatial_model: dict mapping bucket_key → probability vector
    """
    global_counts = {}   # code → counts
    spatial_counts = {}  # bucket_key → counts
    spatial_obs = {}     # bucket_key → total observations

    # Precompute feature maps for observed seeds
    feature_maps = {}
    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx not in feature_maps and seed_idx < len(initial_grids):
            feature_maps[seed_idx] = compute_feature_map(initial_grids[seed_idx])

    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx >= len(initial_grids):
            continue
        initial_grid = initial_grids[seed_idx]
        fmap = feature_maps[seed_idx]

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
                    bucket = fmap[r][c]

                    # Global counts
                    if init_code not in global_counts:
                        global_counts[init_code] = np.zeros(NUM_CLASSES, dtype=np.float64)
                    global_counts[init_code][final_cls] += 1

                    # Spatial counts
                    if bucket not in spatial_counts:
                        spatial_counts[bucket] = np.zeros(NUM_CLASSES, dtype=np.float64)
                        spatial_obs[bucket] = 0
                    spatial_counts[bucket][final_cls] += 1
                    spatial_obs[bucket] += 1

    # Normalize global model
    global_model = {}
    for code, counts in global_counts.items():
        total = counts.sum()
        if total > 0:
            global_model[code] = counts / total
        else:
            probs = np.zeros(NUM_CLASSES)
            probs[terrain_code_to_class(code)] = 1.0
            global_model[code] = probs

    # Normalize spatial model (with minimum observation threshold)
    spatial_model = {}
    for bucket, counts in spatial_counts.items():
        if spatial_obs[bucket] >= MIN_BUCKET_OBS:
            total = counts.sum()
            if total > 0:
                spatial_model[bucket] = counts / total

    return global_model, spatial_model


# ---------------------------------------------------------------------------
# Prediction building
# ---------------------------------------------------------------------------

def build_prediction(height, width, initial_grid, observations,
                     transition_model=None, spatial_model=None):
    """Build a H×W×6 probability tensor.

    Uses spatial_model (per-bucket) when available, falls back to
    transition_model (per-code), then to initial-grid class.
    Per-cell observation counts are blended in for directly observed cells.
    """
    predictions = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    # Precompute feature map if we have a spatial model
    fmap = None
    if spatial_model:
        fmap = compute_feature_map(initial_grid)

    # Step 1: Apply model to all cells
    for r in range(height):
        for c in range(width):
            code = initial_grid[r][c]

            if code in STATIC_CODES:
                predictions[r, c, terrain_code_to_class(code)] = 1.0
            elif fmap and fmap[r][c] in spatial_model:
                predictions[r, c] = spatial_model[fmap[r][c]]
            elif transition_model and code in transition_model:
                predictions[r, c] = transition_model[code]
            else:
                predictions[r, c, terrain_code_to_class(code)] = 1.0

    # Step 2: Blend per-cell observations (for directly observed cells)
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

        observed_mask = cell_obs_count > 0
        if observed_mask.any():
            cell_totals = cell_obs_count[..., np.newaxis]
            cell_probs = np.zeros_like(cell_counts)
            np.divide(cell_counts, cell_totals, out=cell_probs,
                      where=(cell_totals > 0))

            k = 5.0
            alpha = cell_obs_count / (cell_obs_count + k)
            alpha = alpha[..., np.newaxis]

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
