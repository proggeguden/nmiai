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

# Adaptive smoothing: k controls how much we trust the bucket model vs per-cell observations
# High k → trust bucket model more; Low k → trust empirical observations more
# Settlements/ports are highly variable (trust model), plains/forest are predictable (trust data)
K_PER_CODE = {
    1: 8.0,   # Settlement — high variance, trust model
    2: 8.0,   # Port — high variance, trust model
    3: 5.0,   # Ruin — moderate
    0: 3.0,   # Empty — predictable
    11: 3.0,  # Plains — predictable
    4: 3.0,   # Forest — predictable
    10: 5.0,  # Ocean — static anyway
    5: 5.0,   # Mountain — static anyway
}
K_DEFAULT = 5.0

# Minimum observations per spatial bucket before we trust it
MIN_BUCKET_OBS = 5


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
    adj_mountain = 0
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
                elif n == 5:
                    adj_mountain += 1

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

    if code == 1:    # Settlement — binary forest (was graduated adj_forest_level)
        return (1, has_adj_forest, has_adj_settlement, is_coastal)
    elif code == 2:  # Port — simplified to coastal only
        return (2, is_coastal)
    elif code == 11: # Plains
        return (11, dist_bucket, is_coastal, has_adj_forest)
    elif code == 0:  # Empty
        return (0, dist_bucket, has_adj_forest)
    elif code == 4:  # Forest
        return (4, dist_bucket, has_adj_settlement)
    elif code == 3:  # Ruin — dropped has_adj_forest
        return (3, dist_bucket, has_adj_settlement)
    else:
        return (code,)


def compute_feature_map(initial_grid):
    """Compute spatial bucket keys for all cells in the grid.

    Returns (fmap, settlement_dists):
        fmap: list of lists of bucket key tuples (H×W)
        settlement_dists: H×W grid of Manhattan distances to nearest settlement
    """
    H = len(initial_grid)
    W = len(initial_grid[0])
    settlement_dists = _precompute_settlement_distances(initial_grid)
    fmap = [[compute_bucket_key(initial_grid, r, c, settlement_dists) for c in range(W)]
            for r in range(H)]
    return fmap, settlement_dists


# Distance bracket midpoints for interpolation
# Bucket 0=[0,2] → mid 1.0, bucket 1=[3,4] → mid 3.5, bucket 2=[5+] → mid 7.0
DIST_MIDPOINTS = [1.0, 3.5, 7.0]


def _interpolate_dist(d, key, dist_idx, spatial_model):
    """Interpolate between adjacent distance bracket distributions.

    Smooths the hard bucket boundaries by blending with the neighboring bracket
    based on the cell's raw distance from the bucket midpoint.
    """
    current_bucket = key[dist_idx]
    current_mid = DIST_MIDPOINTS[current_bucket]

    if d < current_mid and current_bucket > 0:
        neighbor_bucket = current_bucket - 1
    elif d > current_mid and current_bucket < 2:
        neighbor_bucket = current_bucket + 1
    else:
        return spatial_model.get(key)  # at edge, no interpolation

    neighbor_key = key[:dist_idx] + (neighbor_bucket,) + key[dist_idx + 1:]

    if neighbor_key not in spatial_model or key not in spatial_model:
        return spatial_model.get(key)

    # Linear interpolation based on distance from midpoint
    neighbor_mid = DIST_MIDPOINTS[neighbor_bucket]
    t = abs(d - current_mid) / abs(neighbor_mid - current_mid)
    t = min(t, 1.0)
    return (1 - t) * spatial_model[key] + t * spatial_model[neighbor_key]


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
            feature_maps[seed_idx], _ = compute_feature_map(initial_grids[seed_idx])

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

    # Normalize spatial model with Bayesian smoothing towards global prior
    # Instead of hard threshold, blend bucket evidence with global model
    BUCKET_SMOOTH_K = 5.0  # pseudo-count for global prior
    spatial_model = {}
    for bucket, counts in spatial_counts.items():
        n = spatial_obs[bucket]
        if n < 3:  # absolute minimum — too few to even blend
            continue
        total = counts.sum()
        if total > 0:
            bucket_prob = counts / total
            # Get global prior for this terrain code
            terrain_code = bucket[0]
            if terrain_code in global_model:
                global_prior = global_model[terrain_code]
                weight = n / (n + BUCKET_SMOOTH_K)
                spatial_model[bucket] = weight * bucket_prob + (1 - weight) * global_prior
            else:
                spatial_model[bucket] = bucket_prob

    return global_model, spatial_model


# ---------------------------------------------------------------------------
# Winter severity estimation
# ---------------------------------------------------------------------------

def estimate_survival_rate(initial_grids, observations):
    """Estimate settlement survival rate from observations.

    Compares initial settlement/port cells to their observed final state.
    Returns the fraction that survived, or None if insufficient data.
    """
    alive_count = 0
    observed_count = 0
    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx >= len(initial_grids):
            continue
        init_grid = initial_grids[seed_idx]
        vp = obs["viewport"]
        grid = obs["grid"]
        vp_x, vp_y = vp["x"], vp["y"]
        for dr in range(len(grid)):
            for dc in range(len(grid[0]) if grid else 0):
                r, c = vp_y + dr, vp_x + dc
                if 0 <= r < len(init_grid) and 0 <= c < len(init_grid[0]):
                    if init_grid[r][c] in (1, 2):  # initial settlement/port
                        observed_count += 1
                        final_cls = terrain_code_to_class(grid[dr][dc])
                        if final_cls in (1, 2):  # still settlement or port
                            alive_count += 1
    if observed_count < 20:
        return None  # not enough data
    return alive_count / observed_count


# ---------------------------------------------------------------------------
# Prediction building
# ---------------------------------------------------------------------------

def build_prediction(height, width, initial_grid, observations,
                     transition_model=None, spatial_model=None,
                     survival_rate=None):
    """Build a H×W×6 probability tensor.

    Uses spatial_model (per-bucket) when available, falls back to
    transition_model (per-code), then to initial-grid class.
    Per-cell observation counts are blended in for directly observed cells.
    Distance interpolation smooths bucket boundaries for distance-dependent codes.
    """
    # Codes that use distance as a bucket feature (dist_idx=1 in the key tuple)
    DIST_DEPENDENT_CODES = {0, 3, 4, 11}

    predictions = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    # Precompute feature map if we have a spatial model
    fmap = None
    settlement_dists = None
    if spatial_model:
        fmap, settlement_dists = compute_feature_map(initial_grid)

    # Step 1: Apply model to all cells (with distance interpolation)
    for r in range(height):
        for c in range(width):
            code = initial_grid[r][c]

            if code in STATIC_CODES:
                predictions[r, c, terrain_code_to_class(code)] = 1.0
            elif fmap and fmap[r][c] in spatial_model:
                key = fmap[r][c]
                # Distance interpolation for distance-dependent terrain codes
                if settlement_dists is not None and code in DIST_DEPENDENT_CODES:
                    d = settlement_dists[r][c]
                    interp = _interpolate_dist(d, key, 1, spatial_model)
                    if interp is not None:
                        predictions[r, c] = interp
                    else:
                        predictions[r, c] = spatial_model[key]
                else:
                    predictions[r, c] = spatial_model[key]
            elif transition_model and code in transition_model:
                predictions[r, c] = transition_model[code]
            else:
                predictions[r, c, terrain_code_to_class(code)] = 1.0

    # Step 1.5: Port probability boost for coastal cells near settlements
    if fmap and settlement_dists:
        for r in range(height):
            for c in range(width):
                code = initial_grid[r][c]
                if code in STATIC_CODES:
                    continue
                d = settlement_dists[r][c]
                is_coastal = any(
                    0 <= r + dr < height and 0 <= c + dc < width
                    and initial_grid[r + dr][c + dc] == 10
                    for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)
                )
                if is_coastal and d <= 3:
                    min_port = 0.05 if d <= 1 else 0.03
                    if predictions[r, c, 2] < min_port:
                        deficit = min_port - predictions[r, c, 2]
                        predictions[r, c, 2] = min_port
                        # Remove deficit from the dominant non-Port class
                        dominant = max(
                            (i for i in range(NUM_CLASSES) if i != 2),
                            key=lambda i: predictions[r, c, i]
                        )
                        predictions[r, c, dominant] -= deficit
                        predictions[r, c] = np.maximum(predictions[r, c], 0.001)
                        predictions[r, c] /= predictions[r, c].sum()

    # Step 1.6: Winter severity calibration
    if survival_rate is not None:
        model_survival = 0
        model_count = 0
        for r in range(height):
            for c in range(width):
                if initial_grid[r][c] in (1, 2):
                    model_survival += predictions[r, c, 1] + predictions[r, c, 2]
                    model_count += 1
        if model_count > 0:
            model_rate = model_survival / model_count
            if model_rate > 0.01:
                scale = survival_rate / model_rate
                scale = max(0.3, min(scale, 3.0))  # clamp to avoid wild swings
                for r in range(height):
                    for c in range(width):
                        if initial_grid[r][c] in (1, 2):
                            predictions[r, c, 1] *= scale  # Settlement
                            predictions[r, c, 2] *= scale  # Port
                            predictions[r, c] = np.maximum(predictions[r, c], 0.001)
                            predictions[r, c] /= predictions[r, c].sum()

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

            # Adaptive k per terrain type
            k_grid = np.full((height, width), K_DEFAULT)
            for r in range(height):
                for c in range(width):
                    k_grid[r, c] = K_PER_CODE.get(initial_grid[r][c], K_DEFAULT)

            alpha = cell_obs_count / (cell_obs_count + k_grid)
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
