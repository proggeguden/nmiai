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
PROB_FLOOR = 0.0005

# Adaptive smoothing: k controls how much we trust the bucket model vs per-cell observations
# High k → trust bucket model more; Low k → trust empirical observations more
# Settlements/ports are highly variable (trust model), plains/forest are predictable (trust data)
K_PER_CODE = {
    1: 8.0,   # Settlement — high variance, trust model
    2: 15.0,  # Port — few observations per cell, trust model more
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


def _precompute_cluster_density(initial_grid):
    """Count settlements within Manhattan distance 5 of each cell.

    Returns H×W list of lists: True if ≥2 settlements within d≤5, else False.
    """
    H = len(initial_grid)
    W = len(initial_grid[0])
    settlements = []
    for r in range(H):
        for c in range(W):
            if initial_grid[r][c] in (1, 2):
                settlements.append((r, c))

    cluster = [[False] * W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            count = 0
            for sr, sc in settlements:
                if abs(r - sr) + abs(c - sc) <= 5:
                    count += 1
                    if count >= 2:
                        cluster[r][c] = True
                        break
    return cluster


def compute_bucket_key(initial_grid, r, c, settlement_dists=None, cluster_density=None):
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

    is_clustered = cluster_density[r][c] if cluster_density else False

    if code == 1:    # Settlement — binary forest + cluster density
        return (1, has_adj_forest, has_adj_settlement, is_coastal, is_clustered)
    elif code == 2:  # Port — simplified to coastal only
        return (2, is_coastal)
    elif code == 11: # Plains — 3-level forest adjacency + cluster density
        forest_level = 0 if adj_forest == 0 else (1 if adj_forest <= 2 else 2)
        return (11, dist_bucket, is_coastal, forest_level, is_clustered)
    elif code == 0:  # Empty
        return (0, dist_bucket, has_adj_forest)
    elif code == 4:  # Forest — 3-level settlement adjacency + interior flag
        adj_sett_level = 0 if adj_settlement == 0 else (1 if adj_settlement == 1 else 2)
        is_interior = adj_forest >= 4  # surrounded by 4+ forest neighbors = stable interior
        return (4, dist_bucket, adj_sett_level, is_coastal, is_interior)
    elif code == 3:  # Ruin — dropped has_adj_forest
        return (3, dist_bucket, has_adj_settlement)
    else:
        return (code,)


def compute_feature_map(initial_grid):
    """Compute spatial bucket keys for all cells in the grid.

    Returns (fmap, settlement_dists, cluster_density):
        fmap: list of lists of bucket key tuples (H×W)
        settlement_dists: H×W grid of Manhattan distances to nearest settlement
        cluster_density: H×W grid of booleans (True if ≥2 settlements within d≤5)
    """
    H = len(initial_grid)
    W = len(initial_grid[0])
    settlement_dists = _precompute_settlement_distances(initial_grid)
    cluster_density = _precompute_cluster_density(initial_grid)
    fmap = [[compute_bucket_key(initial_grid, r, c, settlement_dists, cluster_density) for c in range(W)]
            for r in range(H)]
    return fmap, settlement_dists, cluster_density


# Distance bracket midpoints for interpolation
# Bucket 0=[0,2] → mid 1.0, bucket 1=[3,4] → mid 3.5, bucket 2=[5+] → mid 7.0
DIST_MIDPOINTS = [1.0, 3.5, 7.0]

# Forest level midpoints: level 0=0 neighbors, level 1=1-2 neighbors (mid 1.5), level 2=3+ (mid 4.0)
FOREST_LEVEL_MIDPOINTS = [0.0, 1.5, 4.0]


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


def _interpolate_forest(adj_forest_count, probs, key, forest_idx, spatial_model):
    """Interpolate between adjacent forest level brackets for Plains cells.

    Similar to _interpolate_dist but operates on the forest_level dimension.
    `probs` is the base probability vector (possibly already distance-interpolated).
    """
    current_level = key[forest_idx]
    current_mid = FOREST_LEVEL_MIDPOINTS[current_level]

    if adj_forest_count < current_mid and current_level > 0:
        neighbor_level = current_level - 1
    elif adj_forest_count > current_mid and current_level < 2:
        neighbor_level = current_level + 1
    else:
        return probs  # at edge, no interpolation

    neighbor_key = key[:forest_idx] + (neighbor_level,) + key[forest_idx + 1:]

    if neighbor_key not in spatial_model:
        return probs

    neighbor_mid = FOREST_LEVEL_MIDPOINTS[neighbor_level]
    t = abs(adj_forest_count - current_mid) / abs(neighbor_mid - current_mid)
    t = min(t, 0.5)  # cap blending at 50% to avoid over-smoothing
    return (1 - t) * probs + t * spatial_model[neighbor_key]


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
            feature_maps[seed_idx], _, _ = compute_feature_map(initial_grids[seed_idx])

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
    # Per-terrain K: more data → less smoothing, sparse terrain → more smoothing
    BUCKET_SMOOTH_K_PER_CODE = {
        11: 3.0,   # Plains: abundant data
        4:  4.0,   # Forest
        0:  4.0,   # Empty
        1:  8.0,   # Settlement: sparse
        2: 10.0,   # Port: very sparse
        3:  6.0,   # Ruin
    }
    BUCKET_SMOOTH_K_DEFAULT = 5.0
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
                k = BUCKET_SMOOTH_K_PER_CODE.get(terrain_code, BUCKET_SMOOTH_K_DEFAULT)
                weight = n / (n + k)
                spatial_model[bucket] = weight * bucket_prob + (1 - weight) * global_prior
            else:
                spatial_model[bucket] = bucket_prob

    return global_model, spatial_model, spatial_obs


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


def estimate_expansion_rate(initial_grids, observations):
    """Estimate rate of new settlement formation from observations.

    Counts cells that were Empty/Plains/Forest initially but became Settlement.
    Returns new_settlements / initial_settlement_count, or None if insufficient data.
    """
    new_settlements = 0
    initial_settlement_count = 0
    observed_non_settlement = 0

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
                    init_code = init_grid[r][c]
                    final_cls = terrain_code_to_class(grid[dr][dc])
                    if init_code in (0, 11, 4):  # was empty/plains/forest
                        observed_non_settlement += 1
                        if final_cls == 1:  # became settlement
                            new_settlements += 1

    # Count initial settlements (once per seed observed)
    seen_seeds = set()
    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx < len(initial_grids) and seed_idx not in seen_seeds:
            seen_seeds.add(seed_idx)
            for row in initial_grids[seed_idx]:
                for code in row:
                    if code in (1, 2):
                        initial_settlement_count += 1

    if initial_settlement_count < 10 or observed_non_settlement < 30:
        return None
    # Rate = new settlements per observation / initial settlements per seed
    obs_count = len(observations) if observations else 1
    rate = new_settlements / obs_count
    # Normalize by initial settlements per seed
    seeds_observed = max(len(seen_seeds), 1)
    avg_initial = initial_settlement_count / seeds_observed
    if avg_initial > 0:
        rate = rate / avg_initial
    return max(0.0, min(rate, 0.5))


def estimate_port_formation_rate(initial_grids, observations):
    """Estimate rate at which coastal non-port cells become ports.

    Returns port_formations / coastal_non_port_observed, or None.
    """
    port_formed = 0
    coastal_non_port = 0

    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx >= len(initial_grids):
            continue
        init_grid = initial_grids[seed_idx]
        H, W = len(init_grid), len(init_grid[0])
        vp = obs["viewport"]
        grid = obs["grid"]
        vp_x, vp_y = vp["x"], vp["y"]
        for dr in range(len(grid)):
            for dc in range(len(grid[0]) if grid else 0):
                r, c = vp_y + dr, vp_x + dc
                if 0 <= r < H and 0 <= c < W:
                    init_code = init_grid[r][c]
                    if init_code == 2:  # already a port
                        continue
                    # Check if coastal
                    is_coastal = False
                    for nr, nc in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                        if 0 <= nr < H and 0 <= nc < W and init_grid[nr][nc] == 10:
                            is_coastal = True
                            break
                    if is_coastal and init_code not in STATIC_CODES:
                        coastal_non_port += 1
                        if terrain_code_to_class(grid[dr][dc]) == 2:
                            port_formed += 1

    if coastal_non_port < 30:
        return None
    return max(0.0, min(port_formed / coastal_non_port, 0.15))


def estimate_forest_reclamation_rate(initial_grids, observations):
    """Estimate rate at which non-forest cells near forest become forest.

    Returns forest_reclaimed / non_forest_near_forest_observed, or None.
    """
    reclaimed = 0
    eligible = 0

    for obs in observations:
        seed_idx = obs.get("seed_index", 0)
        if seed_idx >= len(initial_grids):
            continue
        init_grid = initial_grids[seed_idx]
        H, W = len(init_grid), len(init_grid[0])
        vp = obs["viewport"]
        grid = obs["grid"]
        vp_x, vp_y = vp["x"], vp["y"]
        for dr in range(len(grid)):
            for dc in range(len(grid[0]) if grid else 0):
                r, c = vp_y + dr, vp_x + dc
                if 0 <= r < H and 0 <= c < W:
                    init_code = init_grid[r][c]
                    if init_code in STATIC_CODES or init_code == 4:
                        continue
                    # Check if near forest
                    adj_forest = 0
                    for ar in range(max(0, r-1), min(H, r+2)):
                        for ac in range(max(0, c-1), min(W, c+2)):
                            if (ar, ac) != (r, c) and init_grid[ar][ac] == 4:
                                adj_forest += 1
                    if adj_forest > 0:
                        eligible += 1
                        if terrain_code_to_class(grid[dr][dc]) == 4:
                            reclaimed += 1

    if eligible < 30:
        return None
    return max(0.0, min(reclaimed / eligible, 0.40))


def estimate_ruin_rate(initial_grids, observations):
    """Estimate rate at which initial settlements become ruins.

    Returns ruined / initial_settlements_observed, or None.
    """
    ruined = 0
    observed = 0

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
                    if init_grid[r][c] in (1, 2):
                        observed += 1
                        if terrain_code_to_class(grid[dr][dc]) == 3:
                            ruined += 1

    if observed < 30:
        return None
    return max(0.0, min(ruined / observed, 0.95))


def estimate_all_rates(initial_grids, observations):
    """Estimate all forward model rates from observations.

    Returns dict with all rates, or None values for insufficient data.
    """
    return {
        "survival": estimate_survival_rate(initial_grids, observations),
        "expansion": estimate_expansion_rate(initial_grids, observations),
        "port_formation": estimate_port_formation_rate(initial_grids, observations),
        "forest_reclamation": estimate_forest_reclamation_rate(initial_grids, observations),
        "ruin": estimate_ruin_rate(initial_grids, observations),
    }


# ---------------------------------------------------------------------------
# Monte Carlo forward simulation
# ---------------------------------------------------------------------------

def monte_carlo_predict(initial_grid, rates, n_runs=100, n_years=50):
    """Run Monte Carlo simulations of the Norse world and return probability tensor.

    Simplified simulation of the 5-phase yearly cycle:
    1. Growth: settlements produce food from adjacent forests
    2. Expansion: prosperous settlements found new settlements nearby
    3. Port formation: coastal settlements develop ports
    4. Winter: settlements lose food, weak ones collapse to ruins
    5. Environment: ruins decay to empty/forest, forest reclaims land

    Args:
        initial_grid: H×W list of lists with terrain codes
        rates: dict with estimated rates from observations
        n_runs: number of Monte Carlo simulation runs
        n_years: number of years to simulate (game uses 50)

    Returns:
        H×W×6 numpy probability tensor
    """
    import random

    H = len(initial_grid)
    W = len(initial_grid[0])

    # Extract rates with defaults
    survival_50y = rates.get("survival") or 0.4
    expansion_50y = rates.get("expansion") or 0.1
    port_50y = rates.get("port_formation") or 0.03
    forest_reclaim_50y = rates.get("forest_reclamation") or 0.15

    # Calibrate per-year rates from 50-year outcome rates.
    # expansion_50y = avg P(Settlement | initial Plains/Empty) across all cells.
    # This includes far cells (~0%) and near cells (~30-60%), averaging to ~14%.
    # To reproduce this, per-settlement-per-year expansion must be high enough
    # that the cumulative effect over 50 years matches.

    import math

    # Death rate: 1 - survival^(1/years), adjusted for food protection (~0.25 avg)
    if 0.001 < survival_50y < 0.999:
        annual_survive = survival_50y ** (1.0 / n_years)
        base_annual_death = (1.0 - annual_survive) / 0.75
        base_annual_death = max(0.003, min(base_annual_death, 0.12))
    else:
        base_annual_death = 0.10 if survival_50y < 0.05 else 0.003

    # Expansion: each settlement tries to expand with this prob per year.
    # Empirically calibrated: expansion_50y * 20/n_years gives correct magnitude.
    # The factor 20 accounts for: most eligible cells are far from settlements
    # and never get expanded into, so the per-settlement rate must be much higher
    # than the per-cell outcome rate.
    annual_expansion = max(0.005, min(expansion_50y * 20.0 / n_years, 0.12))

    # Port: annual probability for coastal settlement to develop port
    annual_port = max(0.002, min(port_50y * 15.0 / n_years, 0.06))

    # Forest reclamation: annual probability per ruin/empty cell near forest
    annual_forest = max(0.005, min(forest_reclaim_50y * 5.0 / n_years, 0.04))

    # Ruin decay: ruins become empty or forest, not stay as ruin forever
    # Low value — most ruins transition to forest, not empty
    annual_ruin_decay = 0.015

    # Precompute static masks
    impassable = set()
    coastal_cells = set()
    for r in range(H):
        for c in range(W):
            if initial_grid[r][c] in (5, 10):
                impassable.add((r, c))
            # Precompute coastal adjacency (using initial grid for ocean)
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W and initial_grid[nr][nc] == 10:
                    coastal_cells.add((r, c))

    # Neighbor offsets (8-connected)
    NEIGHBORS_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    # Expansion range (Manhattan ≤ 3)
    EXPAND_OFFSETS = [(dr, dc) for dr in range(-3, 4) for dc in range(-3, 4)
                      if (dr, dc) != (0, 0) and abs(dr) + abs(dc) <= 3]

    # Count outcomes across runs
    outcome_counts = np.zeros((H, W, NUM_CLASSES), dtype=np.float64)

    for run in range(n_runs):
        # Initialize grid (class indices)
        grid = [[terrain_code_to_class(initial_grid[r][c]) for c in range(W)] for r in range(H)]

        for year in range(n_years):
            # --- Phase 1: Growth (compute food) ---
            food = {}
            settlements = []
            for r in range(H):
                for c in range(W):
                    if grid[r][c] in (1, 2):
                        f = 0
                        for dr, dc in NEIGHBORS_8:
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < H and 0 <= nc < W and grid[nr][nc] == 4:
                                f += 1
                        food[(r, c)] = f
                        settlements.append((r, c))

            # --- Phase 2: Expansion ---
            new_cells = []
            for r, c in settlements:
                f = food.get((r, c), 0)
                prob = annual_expansion * (1.0 + 0.4 * min(f, 3))
                if random.random() < prob:
                    candidates = []
                    for dr, dc in EXPAND_OFFSETS:
                        nr, nc = r + dr, c + dc
                        if (0 <= nr < H and 0 <= nc < W
                                and (nr, nc) not in impassable
                                and grid[nr][nc] in (0, 4)):
                            # Prefer empty over forest (lower cost)
                            weight = 2 if grid[nr][nc] == 0 else 1
                            candidates.extend([(nr, nc)] * weight)
                    if candidates:
                        nr, nc = random.choice(candidates)
                        # Coastal expansion → port; inland → settlement
                        if (nr, nc) in coastal_cells and random.random() < 0.3:
                            new_cells.append((nr, nc, 2))
                        else:
                            new_cells.append((nr, nc, 1))

            for nr, nc, cell_type in new_cells:
                grid[nr][nc] = cell_type

            # --- Phase 3: Port formation (existing settlements) ---
            for r, c in settlements:
                if grid[r][c] != 1:
                    continue
                if (r, c) in coastal_cells:
                    f = food.get((r, c), 0)
                    prob = annual_port * (1.0 + 0.5 * min(f, 3))
                    if random.random() < prob:
                        grid[r][c] = 2

            # --- Phase 4: Winter ---
            winter_severity = random.uniform(0.6, 1.4)
            for r, c in settlements:
                if grid[r][c] not in (1, 2):
                    continue  # already dead from raids or expansion overwrite
                f = food.get((r, c), 0)
                food_prot = min(f / 3.0, 1.0)
                death = base_annual_death * winter_severity * (1.0 - 0.5 * food_prot)
                if grid[r][c] == 2:
                    death *= 0.75  # ports more resilient (trade)
                if random.random() < death:
                    grid[r][c] = 3  # ruin

            # --- Phase 5: Environment ---
            changes = []
            for r in range(H):
                for c in range(W):
                    if (r, c) in impassable:
                        continue
                    cell = grid[r][c]

                    if cell == 3:  # Ruin
                        adj_forest = 0
                        adj_sett = 0
                        for dr, dc in NEIGHBORS_8:
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < H and 0 <= nc < W:
                                if grid[nr][nc] == 4:
                                    adj_forest += 1
                                elif grid[nr][nc] in (1, 2):
                                    adj_sett += 1

                        # Settlement reclaims ruin
                        if adj_sett > 0 and random.random() < 0.02 * adj_sett:
                            if (r, c) in coastal_cells and random.random() < 0.4:
                                changes.append((r, c, 2))
                            else:
                                changes.append((r, c, 1))
                        # Forest reclaims ruin
                        elif adj_forest > 0 and random.random() < annual_forest * min(adj_forest, 3):
                            changes.append((r, c, 4))
                        # Ruin decays to empty
                        elif random.random() < annual_ruin_decay:
                            changes.append((r, c, 0))

            for r, c, new_type in changes:
                grid[r][c] = new_type

        # Record final state
        for r in range(H):
            for c in range(W):
                outcome_counts[r, c, grid[r][c]] += 1

    # Normalize to probabilities
    predictions = outcome_counts / n_runs
    return predictions


def extract_settlement_stats(observations):
    """Extract settlement statistics from query responses.

    Parses the 'settlements' list that comes back from simulate queries.
    Returns dict with avg_food, median_food, etc. or None if no data.
    """
    all_food = []
    all_population = []
    all_wealth = []
    settlement_positions = set()

    for obs in observations:
        settlements = obs.get("settlements", [])
        for s in settlements:
            food = s.get("food")
            pop = s.get("population")
            wealth = s.get("wealth")
            pos = s.get("position")
            if food is not None:
                all_food.append(food)
            if pop is not None:
                all_population.append(pop)
            if wealth is not None:
                all_wealth.append(wealth)
            if pos is not None:
                # Track unique positions (x,y) to detect expansion
                if isinstance(pos, dict):
                    settlement_positions.add((pos.get("x", 0), pos.get("y", 0)))
                elif isinstance(pos, (list, tuple)) and len(pos) >= 2:
                    settlement_positions.add((pos[0], pos[1]))

    if len(all_food) < 10:
        return None

    all_food.sort()
    all_population.sort()
    stats = {
        "avg_food": sum(all_food) / len(all_food),
        "median_food": all_food[len(all_food) // 2],
        "avg_population": sum(all_population) / len(all_population) if all_population else 0,
        "avg_wealth": sum(all_wealth) / len(all_wealth) if all_wealth else 0,
        "unique_positions": len(settlement_positions),
        "total_observations": len(all_food),
    }
    return stats


import math


def _compute_forward_probs(initial_grid, r, c, settlement_dists, rates):
    """Compute forward model probability vector for a single cell.

    Uses physics-inspired rates + spatial context to predict terrain outcome.
    Returns np.array(NUM_CLASSES) or None if forward model doesn't apply.
    """
    code = initial_grid[r][c]
    if code in STATIC_CODES:
        return None

    H = len(initial_grid)
    W = len(initial_grid[0])
    d = settlement_dists[r][c] if settlement_dists else 999

    # Count adjacencies
    adj_forest = 0
    adj_settlement = 0
    adj_ocean = 0
    for dr_ in range(-1, 2):
        for dc_ in range(-1, 2):
            if dr_ == 0 and dc_ == 0:
                continue
            nr, nc = r + dr_, c + dc_
            if 0 <= nr < H and 0 <= nc < W:
                n = initial_grid[nr][nc]
                if n == 4:
                    adj_forest += 1
                elif n in (1, 2):
                    adj_settlement += 1
                elif n == 10:
                    adj_ocean += 1

    is_coastal = adj_ocean > 0
    probs = np.zeros(NUM_CLASSES, dtype=np.float64)

    expansion_rate = rates.get("expansion") or 0.1
    port_rate = rates.get("port_formation") or 0.02
    reclamation_rate = rates.get("forest_reclamation") or 0.15
    survival_rate = rates.get("survival") or 0.5
    ruin_rate = rates.get("ruin") or 0.3

    if code in (1, 2):
        # Initial settlement/port cell
        p_survive = survival_rate * (1.0 + 0.1 * min(adj_forest, 3) + 0.05 * min(adj_settlement, 2))
        p_survive = min(p_survive, 0.99)
        p_ruin = ruin_rate * max(0.3, 1.0 - 0.15 * adj_forest - 0.1 * adj_settlement)
        p_ruin = min(p_ruin, 0.95)

        # Normalize survival vs ruin
        total_sr = p_survive + p_ruin
        if total_sr > 0:
            p_survive = p_survive / total_sr
            p_ruin = p_ruin / total_sr

        if code == 2:  # Port
            probs[2] = p_survive * 0.85  # stays port
            probs[1] = p_survive * 0.15  # becomes settlement
        else:  # Settlement
            probs[1] = p_survive * (0.7 if not is_coastal else 0.5)
            probs[2] = p_survive * (0.3 if is_coastal else 0.05) if is_coastal else p_survive * 0.02
            probs[1] += p_survive - probs[1] - probs[2]  # remainder
            probs[1] = max(probs[1], 0)

        probs[3] = p_ruin  # ruin
        probs[0] = max(0.01, 1.0 - probs.sum())  # empty/plains
        probs[4] = 0.01  # small forest chance

    elif code in (0, 11):
        # Empty or Plains — may get settled, stay empty, or become forest
        p_expand = expansion_rate * math.exp(-0.5 * d) * (1.0 + 0.3 * min(adj_forest, 3))
        p_expand = min(p_expand, 0.4)

        p_port = 0.0
        if is_coastal:
            prox = 1.0 if d <= 2 else (0.5 if d <= 4 else 0.0)
            p_port = port_rate * prox
            p_port = min(p_port, 0.15)

        p_forest = 0.0
        if adj_forest > 0:
            p_forest = reclamation_rate * min(adj_forest / 3.0, 1.0) * (1.0 + 0.2 * max(0, d - 3))
            p_forest = min(p_forest, 0.5)

        probs[1] = p_expand
        probs[2] = p_port
        probs[4] = p_forest
        probs[3] = 0.01  # tiny ruin chance
        probs[0] = max(0.01, 1.0 - probs.sum())

    elif code == 4:
        # Forest — may be cleared for settlement or stay
        p_cleared = 0.0
        if d <= 4:
            p_cleared = expansion_rate * 0.3 * math.exp(-0.3 * d)
            p_cleared = min(p_cleared, 0.2)

        probs[4] = max(0.5, 1.0 - p_cleared - 0.02)  # forest stays
        probs[1] = p_cleared  # becomes settlement
        probs[0] = max(0.01, 1.0 - probs[4] - probs[1] - 0.01)
        probs[3] = 0.005
        probs[2] = 0.005

    elif code == 3:
        # Ruin — may be reclaimed, become forest, or stay
        p_reclaim = 0.0
        if d <= 4:
            p_reclaim = 0.15 * math.exp(-0.3 * d) * (1.0 + 0.2 * adj_settlement)
            p_reclaim = min(p_reclaim, 0.3)
        p_forest = reclamation_rate * min(adj_forest / 3.0, 1.0) * 0.5
        p_forest = min(p_forest, 0.3)

        probs[3] = max(0.1, 1.0 - p_reclaim - p_forest - 0.05)  # stays ruin
        probs[1] = p_reclaim
        probs[4] = p_forest
        probs[0] = max(0.01, 1.0 - probs.sum())

    else:
        return None

    # Ensure valid distribution
    probs = np.maximum(probs, 0.001)
    probs /= probs.sum()
    return probs


def _apply_forward_calibration(predictions, initial_grid, settlement_dists, rates):
    """Apply forward model corrections to predictions (step 1.7).

    Blends forward model predictions with bucket model using context-dependent weights.
    Modifies predictions in-place.
    """
    if rates is None:
        return

    # Check minimum data quality — need at least survival and one other rate
    available = sum(1 for v in rates.values() if v is not None)
    if available < 2:
        return

    # Consistency check: if survival + ruin > 1.1, rates are unreliable
    sr = rates.get("survival") or 0.5
    rr = rates.get("ruin") or 0.3
    if sr + rr > 1.1:
        # Reduce all weights dramatically
        weight_scale = 0.15
    else:
        weight_scale = 1.0

    H = len(initial_grid)
    W = len(initial_grid[0])

    for r in range(H):
        for c in range(W):
            code = initial_grid[r][c]
            if code in STATIC_CODES:
                continue

            forward = _compute_forward_probs(initial_grid, r, c, settlement_dists, rates)
            if forward is None:
                continue

            d = settlement_dists[r][c] if settlement_dists else 999

            # Context-dependent blending weight (conservative — bucket model is primary)
            if code in (0, 11) and d <= 4:  # Plains/empty near settlements
                w = 0.10
            elif code == 4 and d <= 3:  # Forest near settlements
                w = 0.08
            elif code in (1, 2):  # Settlement/port
                w = 0.08
            elif d > 6:  # Far from settlements
                w = 0.03
            else:
                w = 0.05

            w *= weight_scale

            predictions[r, c] = (1 - w) * predictions[r, c] + w * forward
            predictions[r, c] = np.maximum(predictions[r, c], 0)
            predictions[r, c] /= predictions[r, c].sum()


# ---------------------------------------------------------------------------
# Prediction building
# ---------------------------------------------------------------------------

def build_prediction(height, width, initial_grid, observations,
                     transition_model=None, spatial_model=None,
                     survival_rate=None, forward_rates=None,
                     settlement_stats=None, spatial_obs=None,
                     expansion_rate=None, port_formation_rate=None,
                     mc_rates=None):
    """Build a H×W×6 probability tensor.

    Uses spatial_model (per-bucket) when available, falls back to
    transition_model (per-code), then to initial-grid class.
    Per-cell observation counts are blended in for directly observed cells.
    Distance interpolation smooths bucket boundaries for distance-dependent codes.
    Forward model (step 1.7) applies rate-based corrections if forward_rates provided.
    """
    # Codes that use distance as a bucket feature (dist_idx=1 in the key tuple)
    DIST_DEPENDENT_CODES = {0, 3, 4, 11}

    predictions = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    # Precompute feature map if we have a spatial model
    fmap = None
    settlement_dists = None
    if spatial_model:
        fmap, settlement_dists, _ = compute_feature_map(initial_grid)

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
                # Forest-level interpolation for Plains cells (forest_level is at index 3)
                if code == 11:
                    adj_f = sum(1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                                if (dr, dc) != (0, 0)
                                and 0 <= r + dr < height and 0 <= c + dc < width
                                and initial_grid[r + dr][c + dc] == 4)
                    predictions[r, c] = _interpolate_forest(
                        adj_f, predictions[r, c], key, 3, spatial_model)
            elif transition_model and code in transition_model:
                predictions[r, c] = transition_model[code]
            else:
                predictions[r, c, terrain_code_to_class(code)] = 1.0

    # Step 1.5: Rate-adaptive port calibration for coastal cells near settlements
    # Use observed port_formation_rate to set minimum port probability,
    # scaling by distance to settlement. On high-port rounds this can be 15-30%+.
    if fmap and settlement_dists:
        # Determine minimum port probability based on observed rate
        if port_formation_rate is not None and port_formation_rate > 0.005:
            # Scale observed rate by distance: d≤1 gets full rate, d≤3 gets half
            base_port_near = min(port_formation_rate * 1.0, 0.25)  # d≤1
            base_port_mid = min(port_formation_rate * 0.5, 0.15)   # d=2-3
            base_port_far = min(port_formation_rate * 0.3, 0.10)   # d=4-5
        else:
            # Fallback: conservative fixed minimums
            base_port_near = 0.05
            base_port_mid = 0.03
            base_port_far = 0.0

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
                if is_coastal and d <= 5:
                    if d <= 1:
                        min_port = base_port_near
                    elif d <= 3:
                        min_port = base_port_mid
                    else:
                        min_port = base_port_far
                    if min_port > 0 and predictions[r, c, 2] < min_port:
                        deficit = min_port - predictions[r, c, 2]
                        predictions[r, c, 2] = min_port
                        # Distribute deficit proportionally across non-port classes
                        non_port_mass = sum(predictions[r, c, i] for i in range(NUM_CLASSES) if i != 2)
                        if non_port_mass > 0:
                            for i in range(NUM_CLASSES):
                                if i != 2:
                                    predictions[r, c, i] -= deficit * (predictions[r, c, i] / non_port_mass)
                        predictions[r, c] = np.maximum(predictions[r, c], 0)
                        predictions[r, c] /= predictions[r, c].sum()

    # Step 1.6: Winter severity calibration (with optional food modulation)
    if survival_rate is not None:
        # Modulate scale based on settlement food levels if available
        food_modifier = 1.0
        FOOD_BASELINE = 50.0  # conservative default, calibrate from live data
        if settlement_stats and settlement_stats.get("avg_food") is not None:
            food_modifier = max(0.8, min(settlement_stats["avg_food"] / FOOD_BASELINE, 1.2))

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
                scale *= food_modifier
                scale = max(0.3, min(scale, 3.0))  # clamp to avoid wild swings
                for r in range(height):
                    for c in range(width):
                        if initial_grid[r][c] in (1, 2):
                            predictions[r, c, 1] *= scale  # Settlement
                            predictions[r, c, 2] *= scale  # Port
                            predictions[r, c] = np.maximum(predictions[r, c], 0.001)
                            predictions[r, c] /= predictions[r, c].sum()

                # Harsh winter: boost Ruin and Forest for settlement/port cells
                if scale < 0.8:
                    ruin_boost = (1.0 - scale) * 0.3
                    for r in range(height):
                        for c in range(width):
                            if initial_grid[r][c] in (1, 2):
                                predictions[r, c, 3] *= (1.0 + ruin_boost)
                                predictions[r, c, 4] *= (1.0 + ruin_boost * 0.3)
                                predictions[r, c] = np.maximum(predictions[r, c], 0.001)
                                predictions[r, c] /= predictions[r, c].sum()

    # Step 1.7: Forward model calibration
    if forward_rates is not None:
        # Ensure we have settlement_dists even without spatial model
        if settlement_dists is None:
            settlement_dists = _precompute_settlement_distances(initial_grid)
        _apply_forward_calibration(predictions, initial_grid, settlement_dists, forward_rates)

    # Step 1.75: Expansion rate modulation — scale settlement predictions for nearby cells
    if expansion_rate is not None:
        if settlement_dists is None:
            settlement_dists = _precompute_settlement_distances(initial_grid)
    if expansion_rate is not None and settlement_dists is not None:
        # Compute model's implicit expansion rate for Plains/Forest cells near settlements
        model_exp = 0.0
        exp_count = 0
        for r in range(height):
            for c in range(width):
                code = initial_grid[r][c]
                if code in (11, 4) and settlement_dists[r][c] <= 8:
                    model_exp += predictions[r, c, 1]
                    exp_count += 1
        if exp_count > 0:
            model_avg = model_exp / exp_count
            if model_avg > 0.005:
                raw_scale = expansion_rate / model_avg
                # Dampen: 30% correction, not full override. The spatial bucket model
                # already encodes expansion rates from the same observations.
                scale = 1.0 + 0.3 * (raw_scale - 1.0)
                scale = max(0.7, min(scale, 1.5))
                if abs(scale - 1.0) > 0.05:  # only adjust if meaningful difference
                    for r in range(height):
                        for c in range(width):
                            code = initial_grid[r][c]
                            d = settlement_dists[r][c]
                            if code in (11, 4) and d <= 8:
                                # Decay effect for d=5-8
                                effective_scale = 1.0 + (scale - 1.0) * max(0.0, 1.0 - max(0, d - 4) / 5.0)
                                predictions[r, c, 1] *= effective_scale
                                # Also scale Port for coastal cells
                                is_coastal = any(
                                    0 <= r + dr < height and 0 <= c + dc < width
                                    and initial_grid[r + dr][c + dc] == 10
                                    for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                                    if (dr, dc) != (0, 0)
                                )
                                if is_coastal:
                                    port_scale = 1.0 + (effective_scale - 1.0) * 0.5
                                    predictions[r, c, 2] *= port_scale
                                predictions[r, c] = np.maximum(predictions[r, c], 0.001)
                                predictions[r, c] /= predictions[r, c].sum()

    # Step 1.85: Forest-specific entropy injection
    # Forest bucket model over-predicts Forest=0.86-0.91 when GT is 0.73-0.80
    # Shrink Forest mass and redistribute to other classes using global prior
    if transition_model and transition_model.get(4) is not None:
        forest_prior = transition_model[4]
        forest_retention = forest_prior[4]  # P(Forest→Forest) from observations
        if settlement_dists is None:
            settlement_dists = _precompute_settlement_distances(initial_grid)
        # Only shrink when observed forest retention is clearly low
        # retention > 0.85 = forest mostly stays, don't interfere
        if forest_retention < 0.85:
            clearing_signal = max(0.0, 0.85 - forest_retention)  # 0 to ~0.20
            base_shrink = min(0.15, clearing_signal * 0.6)
        else:
            base_shrink = 0.0  # forest mostly stays, skip
        for r in range(height):
            for c in range(width):
                if initial_grid[r][c] != 4:
                    continue
                forest_p = predictions[r, c, 4]
                if forest_p < 0.60:
                    continue
                d = settlement_dists[r][c]
                if d <= 2:
                    shrink = base_shrink * 1.5
                elif d <= 4:
                    shrink = base_shrink
                else:
                    shrink = base_shrink * 0.4
                deficit = forest_p * shrink
                predictions[r, c, 4] -= deficit
                # Redistribute to non-Forest classes using global prior
                non_forest_prior = forest_prior.copy()
                non_forest_prior[4] = 0
                if non_forest_prior.sum() > 0:
                    non_forest_prior /= non_forest_prior.sum()
                predictions[r, c] += deficit * non_forest_prior
                predictions[r, c] = np.maximum(predictions[r, c], 0.001)
                predictions[r, c] /= predictions[r, c].sum()

    # Step 1.8: Distance-based temperature scaling
    # Near settlements: outcomes are stochastic (expansion/conflict/winter) → T>1 spreads mass
    # Far from settlements: outcomes are deterministic (cells stay same) → T<1 sharpens
    # This replaces the prior-blending approach which had a bias toward the global average
    if settlement_dists is None:
        settlement_dists = _precompute_settlement_distances(initial_grid)
    for r in range(height):
        for c in range(width):
            code = initial_grid[r][c]
            if code in STATIC_CODES:
                continue
            d = settlement_dists[r][c]
            if d <= 2:
                T = 1.10   # spread: near settlements, high uncertainty
            elif d <= 4:
                T = 1.03   # slight spread
            else:
                T = 0.92   # sharpen: far from settlements, low uncertainty
            if abs(T - 1.0) > 0.005:
                inv_T = 1.0 / T
                scaled = np.power(np.maximum(predictions[r, c], 1e-10), inv_T)
                predictions[r, c] = scaled / scaled.sum()

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

            # Adaptive k per terrain type, scaled by spatial model confidence
            k_grid = np.full((height, width), K_DEFAULT)
            for r in range(height):
                for c in range(width):
                    base_k = K_PER_CODE.get(initial_grid[r][c], K_DEFAULT)
                    # Scale k up when spatial model has many observations (trust model more)
                    if spatial_obs and fmap and fmap[r][c] in spatial_obs:
                        bucket_n = spatial_obs[fmap[r][c]]
                        confidence_scale = 1.0 + 0.5 * min(bucket_n / 100.0, 3.0)
                        base_k *= confidence_scale
                    k_grid[r, c] = base_k

            alpha = cell_obs_count / (cell_obs_count + k_grid)
            alpha = alpha[..., np.newaxis]

            for r in range(height):
                for c in range(width):
                    if observed_mask[r, c] and initial_grid[r][c] not in STATIC_CODES:
                        predictions[r, c] = (
                            alpha[r, c, 0] * cell_probs[r, c]
                            + (1 - alpha[r, c, 0]) * predictions[r, c]
                        )

    # Step 2.5: Monte Carlo blending — DISABLED
    # Simulated-production testing shows MC hurts by +1.1% avg (+3.7% on R12).
    # The uncalibrated per-year rates add noise rather than correcting errors.
    # Kept as dead code for potential future calibration improvement.
    # if mc_rates is not None:
    #     sr = mc_rates.get("survival") or 0.0
    #     if sr > 0.50:
    #         mc_weight = 0.05
    #         mc_pred = monte_carlo_predict(initial_grid, mc_rates,
    #                                       n_runs=80, n_years=50)
    #         mc_pred = apply_floor(mc_pred, floor=0.001)
    #         predictions = (1 - mc_weight) * predictions + mc_weight * mc_pred
    #         sums = predictions.sum(axis=2, keepdims=True)
    #         predictions = predictions / sums

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


def score_predictions(pred, gt):
    """Compute entropy-weighted KL divergence.

    Args:
        pred: H×W×6 numpy array of predicted probabilities
        gt: H×W×6 numpy array of ground truth probabilities

    Returns:
        (weighted_kl, dynamic_cell_count) tuple
    """
    kl = np.sum(gt * np.log((gt + 1e-10) / (pred + 1e-10)), axis=2)
    entropy = -np.sum(gt * np.log(gt + 1e-10), axis=2)
    dynamic = entropy > 0.01
    if dynamic.any():
        weighted_kl = (kl[dynamic] * entropy[dynamic]).sum() / entropy[dynamic].sum()
    else:
        weighted_kl = 0
    return weighted_kl, dynamic.sum()


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
