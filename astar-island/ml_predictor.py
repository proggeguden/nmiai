"""ML feature extraction for Astar Island terrain prediction.

Extracts a fixed-length feature vector for each cell in the initial grid.
These features are used to train an ML model that replaces the bucket-based
spatial transition model in predictor.py.

Feature layout (25 features total):
  [0..5]   One-hot terrain class (Empty, Settlement, Port, Ruin, Forest, Mountain)
  [6]      Distance to nearest settlement (BFS, capped at 20)
  [7]      Is coastal (has adjacent ocean cell, 8-connected)
  [8]      Adjacent forest count (8-connected, 0-8)
  [9]      Adjacent settlement count (8-connected, 0-8)
  [10]     Adjacent ocean count (8-connected, 0-8)
  [11]     Is clustered (≥2 settlements within Manhattan distance 5)
  [12]     Is interior forest (forest cell with ≥4 adjacent forest cells)
  [13]     survival_rate
  [14]     expansion_rate
  [15]     port_formation_rate
  [16]     forest_reclamation_rate
  [17]     ruin_rate
  [18]     dist_to_coast (BFS from ocean cells, capped at 20)
  [19]     adj_mountain_count (8-connected, 0-8)
  [20]     settlement_count_r3 (count of settlement cells within Manhattan distance 3)
  [21]     forest_density_r2 (count of forest cells within Manhattan distance 2, max 13)
  [22]     dist_to_forest (BFS distance to nearest forest cell, capped at 10)
  [23]     settlement_count_r5 (count of settlement cells within Manhattan distance 5)
  [24]     adj_ruin_count (count of adjacent ruin cells, 8-connected, 0-8)
"""

import numpy as np
from predictor import (
    _precompute_settlement_distances,
    _precompute_cluster_density,
    terrain_code_to_class,
    TERRAIN_TO_CLASS,
    STATIC_CODES,
    NUM_CLASSES,
)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

FEATURE_NAMES = [
    "is_empty",
    "is_settlement",
    "is_port",
    "is_ruin",
    "is_forest",
    "is_mountain",
    "dist_to_settlement",
    "is_coastal",
    "adj_forest_count",
    "adj_settlement_count",
    "adj_ocean_count",
    "is_clustered",
    "is_interior_forest",
    "survival_rate",
    "expansion_rate",
    "port_formation_rate",
    "forest_reclamation_rate",
    "ruin_rate",
    "dist_to_coast",
    "adj_mountain_count",
    "settlement_count_r3",
    "forest_density_r2",
    "dist_to_forest",
    "settlement_count_r5",
    "adj_ruin_count",
]

NUM_FEATURES = 25

RATE_KEYS = ["survival", "expansion", "port_formation", "forest_reclamation", "ruin"]

RATE_DEFAULT = 0.5

# Maximum distance value (raw BFS distances beyond this are clamped)
_DIST_CAP = 20


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_features(initial_grid, rates=None):
    """Extract a 25-feature vector for every cell in initial_grid.

    Parameters
    ----------
    initial_grid : list[list[int]]
        H×W grid of terrain codes.
    rates : dict | None
        Round-level rate estimates keyed by RATE_KEYS strings.
        Missing or None values default to RATE_DEFAULT (0.5).

    Returns
    -------
    np.ndarray, shape (H, W, 25), dtype float32
    """
    H = len(initial_grid)
    W = len(initial_grid[0])

    # Pre-compute BFS settlement distances, cluster density, and coast distances
    settlement_dists = _precompute_settlement_distances(initial_grid)
    cluster_density = _precompute_cluster_density(initial_grid)
    coast_dists = _precompute_coast_distances(initial_grid)
    forest_dists = _precompute_forest_distances(initial_grid)

    # Collect all settlement positions for radius counts (features 20, 23)
    settlement_positions = [
        (r, c)
        for r in range(H)
        for c in range(W)
        if initial_grid[r][c] in (1, 2)
    ]

    # Resolve rate values (default 0.5 for missing/None)
    rate_values = _resolve_rates(rates)

    out = np.zeros((H, W, NUM_FEATURES), dtype=np.float32)

    for r in range(H):
        row = initial_grid[r]
        for c in range(W):
            code = row[c]
            out[r, c] = _compute_cell_features(
                initial_grid, r, c, code, H, W,
                settlement_dists, cluster_density, rate_values, coast_dists,
                forest_dists, settlement_positions,
            )

    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _precompute_coast_distances(initial_grid):
    """Precompute BFS distance to nearest ocean cell for all cells.

    Seeds BFS from all ocean cells (code=10), identical pattern to
    _precompute_settlement_distances but for ocean cells.

    Returns H×W list of lists with distances (999 if no ocean exists).
    """
    from collections import deque
    H = len(initial_grid)
    W = len(initial_grid[0])
    dist = [[999] * W for _ in range(H)]
    q = deque()
    for r in range(H):
        for c in range(W):
            if initial_grid[r][c] == 10:
                dist[r][c] = 0
                q.append((r, c))

    if not q:
        return dist

    while q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and dist[nr][nc] > dist[r][c] + 1:
                dist[nr][nc] = dist[r][c] + 1
                q.append((nr, nc))

    return dist


def _precompute_forest_distances(initial_grid):
    """Precompute BFS distance to nearest forest cell for all cells.

    Seeds BFS from all forest cells (code=4), identical pattern to
    _precompute_coast_distances but for forest cells.
    Distances beyond _FOREST_DIST_CAP (10) are clamped at inference time.

    Returns H×W list of lists with distances (999 if no forest exists).
    """
    from collections import deque
    H = len(initial_grid)
    W = len(initial_grid[0])
    dist = [[999] * W for _ in range(H)]
    q = deque()
    for r in range(H):
        for c in range(W):
            if initial_grid[r][c] == 4:
                dist[r][c] = 0
                q.append((r, c))

    if not q:
        return dist

    while q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and dist[nr][nc] > dist[r][c] + 1:
                dist[nr][nc] = dist[r][c] + 1
                q.append((nr, nc))

    return dist


_FOREST_DIST_CAP = 10


def _count_settlements_in_radius(r, c, settlement_positions, radius):
    """Count settlement positions within Manhattan distance <= radius from (r, c)."""
    count = 0
    for sr, sc in settlement_positions:
        if abs(sr - r) + abs(sc - c) <= radius:
            count += 1
    return count


def _count_forest_density_r2(initial_grid, r, c, H, W):
    """Count forest cells (code 4) within Manhattan distance <= 2 from (r, c).

    The Manhattan diamond of radius 2 has at most 13 cells (including the center).
    """
    count = 0
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            if abs(dr) + abs(dc) > 2:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and initial_grid[nr][nc] == 4:
                count += 1
    return count


def _resolve_rates(rates):
    """Return a list of 5 floats in RATE_KEYS order, defaulting to RATE_DEFAULT."""
    if rates is None:
        return [RATE_DEFAULT] * len(RATE_KEYS)
    return [
        float(rates[k]) if (k in rates and rates[k] is not None) else RATE_DEFAULT
        for k in RATE_KEYS
    ]


def _compute_cell_features(initial_grid, r, c, code, H, W,
                            settlement_dists, cluster_density, rate_values, coast_dists,
                            forest_dists, settlement_positions):
    """Compute the 25-feature vector for a single cell."""
    vec = np.zeros(NUM_FEATURES, dtype=np.float32)

    # --- Features 0-5: one-hot terrain class ---
    cls = terrain_code_to_class(code)
    vec[cls] = 1.0

    # --- Feature 6: distance to nearest settlement, capped at 20 ---
    raw_dist = settlement_dists[r][c]
    vec[6] = float(min(raw_dist, _DIST_CAP))

    # --- 8-connected neighbor counts ---
    adj_forest = 0
    adj_settlement = 0
    adj_ocean = 0
    adj_mountain = 0
    adj_ruin = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W:
                n = initial_grid[nr][nc]
                if n == 4:
                    adj_forest += 1
                elif n in (1, 2):
                    adj_settlement += 1
                elif n == 10:
                    adj_ocean += 1
                elif n == 5:
                    adj_mountain += 1
                elif n == 3:
                    adj_ruin += 1

    # --- Feature 7: is_coastal ---
    vec[7] = 1.0 if adj_ocean > 0 else 0.0

    # --- Feature 8: adj_forest_count ---
    vec[8] = float(adj_forest)

    # --- Feature 9: adj_settlement_count ---
    vec[9] = float(adj_settlement)

    # --- Feature 10: adj_ocean_count ---
    vec[10] = float(adj_ocean)

    # --- Feature 11: is_clustered ---
    vec[11] = 1.0 if cluster_density[r][c] else 0.0

    # --- Feature 12: is_interior_forest (forest with ≥4 adjacent forest cells) ---
    vec[12] = 1.0 if (code == 4 and adj_forest >= 4) else 0.0

    # --- Features 13-17: round-level rates ---
    vec[13:18] = rate_values

    # --- Feature 18: dist_to_coast (BFS from ocean cells, capped at 20) ---
    vec[18] = float(min(coast_dists[r][c], _DIST_CAP))

    # --- Feature 19: adj_mountain_count ---
    vec[19] = float(adj_mountain)

    # --- Feature 20: settlement_count_r3 ---
    vec[20] = float(_count_settlements_in_radius(r, c, settlement_positions, 3))

    # --- Feature 21: forest_density_r2 ---
    vec[21] = float(_count_forest_density_r2(initial_grid, r, c, H, W))

    # --- Feature 22: dist_to_forest (BFS from forest cells, capped at 10) ---
    vec[22] = float(min(forest_dists[r][c], _FOREST_DIST_CAP))

    # --- Feature 23: settlement_count_r5 ---
    vec[23] = float(_count_settlements_in_radius(r, c, settlement_positions, 5))

    # --- Feature 24: adj_ruin_count ---
    vec[24] = float(adj_ruin)

    return vec


# ---------------------------------------------------------------------------
# Numpy inference: forward pass, save, load
# ---------------------------------------------------------------------------

def numpy_forward(features, weights):
    """Numpy-only MLP forward pass: Input(25) → 128 → 64 → 32 → Softmax(6).

    Args:
        features: H×W×25 float32 array
        weights: dict with fc*_w, fc*_b, feat_mean, feat_std
    Returns:
        H×W×6 float64 probability array
    """
    H, W, F = features.shape
    x = features.reshape(-1, F).astype(np.float64)

    # Z-score normalize
    x = (x - weights["feat_mean"].astype(np.float64)) / (weights["feat_std"].astype(np.float64) + 1e-8)

    # Layer 1-3: Linear + ReLU
    x = x @ weights["fc1_w"].astype(np.float64).T + weights["fc1_b"].astype(np.float64)
    x = np.maximum(x, 0)
    x = x @ weights["fc2_w"].astype(np.float64).T + weights["fc2_b"].astype(np.float64)
    x = np.maximum(x, 0)
    x = x @ weights["fc3_w"].astype(np.float64).T + weights["fc3_b"].astype(np.float64)
    x = np.maximum(x, 0)

    # Layer 4: Linear + Temperature-scaled Softmax
    x = x @ weights["fc4_w"].astype(np.float64).T + weights["fc4_b"].astype(np.float64)
    T = float(weights.get("temperature", np.array([1.0])).flat[0])
    if T != 1.0:
        x = x / T
    x_max = x.max(axis=1, keepdims=True)
    exp_x = np.exp(x - x_max)
    x = exp_x / exp_x.sum(axis=1, keepdims=True)

    return x.reshape(H, W, 6)


def save_model(weights, path):
    np.savez(path, **weights)


def load_model(path):
    data = np.load(path)
    return {key: data[key] for key in data.files}
