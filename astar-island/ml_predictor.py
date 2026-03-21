"""ML feature extraction for Astar Island terrain prediction.

Extracts a fixed-length feature vector for each cell in the initial grid.
These features are used to train an ML model that replaces the bucket-based
spatial transition model in predictor.py.

Feature layout (18 features total):
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
]

NUM_FEATURES = 18

RATE_KEYS = ["survival", "expansion", "port_formation", "forest_reclamation", "ruin"]

RATE_DEFAULT = 0.5

# Maximum distance value (raw BFS distances beyond this are clamped)
_DIST_CAP = 20


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_features(initial_grid, rates=None):
    """Extract an 18-feature vector for every cell in initial_grid.

    Parameters
    ----------
    initial_grid : list[list[int]]
        H×W grid of terrain codes.
    rates : dict | None
        Round-level rate estimates keyed by RATE_KEYS strings.
        Missing or None values default to RATE_DEFAULT (0.5).

    Returns
    -------
    np.ndarray, shape (H, W, 18), dtype float32
    """
    H = len(initial_grid)
    W = len(initial_grid[0])

    # Pre-compute BFS settlement distances and cluster density
    settlement_dists = _precompute_settlement_distances(initial_grid)
    cluster_density = _precompute_cluster_density(initial_grid)

    # Resolve rate values (default 0.5 for missing/None)
    rate_values = _resolve_rates(rates)

    out = np.zeros((H, W, NUM_FEATURES), dtype=np.float32)

    for r in range(H):
        row = initial_grid[r]
        for c in range(W):
            code = row[c]
            out[r, c] = _compute_cell_features(
                initial_grid, r, c, code, H, W,
                settlement_dists, cluster_density, rate_values,
            )

    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_rates(rates):
    """Return a list of 5 floats in RATE_KEYS order, defaulting to RATE_DEFAULT."""
    if rates is None:
        return [RATE_DEFAULT] * len(RATE_KEYS)
    return [
        float(rates[k]) if (k in rates and rates[k] is not None) else RATE_DEFAULT
        for k in RATE_KEYS
    ]


def _compute_cell_features(initial_grid, r, c, code, H, W,
                            settlement_dists, cluster_density, rate_values):
    """Compute the 18-feature vector for a single cell."""
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

    return vec
