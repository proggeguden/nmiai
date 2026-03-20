"""API client for the Astar Island competition endpoints."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.ainm.no")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")


def _headers():
    return {"Authorization": f"Bearer {ACCESS_TOKEN}"}


def _get(path):
    url = f"{API_BASE_URL}{path}"
    resp = requests.get(url, headers=_headers())
    resp.raise_for_status()
    return resp.json()


def _post(path, json_data=None):
    url = f"{API_BASE_URL}{path}"
    resp = requests.post(url, headers=_headers(), json=json_data)
    resp.raise_for_status()
    return resp.json()


def get_rounds():
    """List all rounds."""
    return _get("/astar-island/rounds")


def get_round_detail(round_id):
    """Get round details including initial states for all seeds."""
    return _get(f"/astar-island/rounds/{round_id}")


def query_seed(round_id, seed_index, viewport_x=0, viewport_y=0,
               viewport_w=15, viewport_h=15):
    """Run one stochastic simulation and observe a viewport window.

    Each call costs 1 query from the shared budget (50 per round).
    Rate limit: max 5 req/sec.

    Returns grid (viewport_h × viewport_w), settlements in viewport,
    viewport bounds, full map dimensions, and query usage.
    """
    return _post("/astar-island/simulate", {
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": viewport_x,
        "viewport_y": viewport_y,
        "viewport_w": viewport_w,
        "viewport_h": viewport_h,
    })


def submit_prediction(round_id, seed_index, prediction):
    """Submit a W×H×6 probability tensor for a specific seed.

    prediction: list of lists of lists (H x W x 6), each cell sums to 1.0
    """
    return _post("/astar-island/submit", {
        "round_id": round_id,
        "seed_index": seed_index,
        "prediction": prediction,
    })


def get_my_rounds():
    """Get all rounds with team scores, ranks, query usage, and seeds_submitted.

    Returns list of round dicts with: round_score, seed_scores, seeds_submitted,
    rank, total_teams, queries_used, queries_max, initial_grid.
    """
    return _get("/astar-island/my-rounds")


def get_my_predictions(round_id):
    """Get submitted predictions for a round with argmax/confidence grids.

    Returns list of dicts with: seed_index, argmax_grid (H×W class indices),
    confidence_grid (H×W max probabilities), score, submitted_at.
    """
    return _get(f"/astar-island/my-predictions/{round_id}")


def get_analysis(round_id, seed_index):
    """Get prediction vs ground truth for a completed/scoring round.

    Returns: prediction (H×W×6), ground_truth (H×W×6), score, width, height,
    initial_grid.
    """
    return _get(f"/astar-island/analysis/{round_id}/{seed_index}")


def get_leaderboard():
    """Get public leaderboard.

    Returns list of teams with: weighted_score (best round_score × round_weight),
    rounds_participated, hot_streak_score (avg last 3), rank.
    """
    return _get("/astar-island/leaderboard")
