"""
Local test script using real prompts from md/test_prompts.json.

Usage:
    python3 test_local.py            # run all tests
    python3 test_local.py 5          # run test by ID
    python3 test_local.py payment    # run by category
    python3 test_local.py list       # list all tests
    python3 test_local.py --plan 5   # show planner output only (no execution)

Requires:
    - Server running: python3 -m uvicorn main:app --reload --port 8080
    - Sandbox credentials in .env:
        SANDBOX_BASE_URL=https://kkpqfuj-amager.tripletex.dev/v2
        SANDBOX_SESSION_TOKEN=your-sandbox-token
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("TEST_SERVER_URL", "http://localhost:8080")
SANDBOX_API_URL = os.environ.get("SANDBOX_BASE_URL", "https://kkpqfuj-amager.tripletex.dev/v2")
SANDBOX_TOKEN = os.environ.get("SANDBOX_SESSION_TOKEN", "")
PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "md", "test_prompts.json")

SANDBOX_AUTH = ("0", SANDBOX_TOKEN) if SANDBOX_TOKEN else None


# ---------------------------------------------------------------------------
# Load prompts from JSON
# ---------------------------------------------------------------------------

def load_prompts() -> list[dict]:
    with open(PROMPTS_FILE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def call_solve(prompt: str, label: str = "") -> dict:
    """Send a prompt to the /solve endpoint and return the response.

    Output is buffered to prevent interleaving when run in parallel.
    """
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"TEST: {label}")
    lines.append(f"{'='*70}")
    lines.append(f"Prompt: {prompt[:120]}{'...' if len(prompt) > 120 else ''}")
    lines.append("")

    payload = {
        "prompt": prompt,
        "files": [],
        "tripletex_credentials": {
            "base_url": SANDBOX_API_URL,
            "session_token": SANDBOX_TOKEN,
        },
    }

    t0 = time.monotonic()
    try:
        resp = requests.post(f"{BASE_URL}/solve", json=payload, timeout=310)
    except requests.exceptions.ConnectionError:
        print("  ERROR: Cannot connect to server. Is it running?")
        print(f"  Start with: python3 -m uvicorn main:app --reload --port 8080")
        sys.exit(1)

    elapsed = time.monotonic() - t0
    status = resp.status_code

    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}

    lines.append(f"  HTTP {status} — {elapsed:.1f}s")
    lines.append(f"  Response: {json.dumps(body, ensure_ascii=False)[:200]}")

    # Print atomically to avoid interleaving
    print("\n".join(lines))

    return {"status": status, "body": body, "elapsed": elapsed}


def tx_get(endpoint: str, params: dict = None) -> dict:
    """Query the sandbox Tripletex API directly."""
    resp = requests.get(
        f"{SANDBOX_API_URL}{endpoint}",
        auth=SANDBOX_AUTH,
        params=params or {},
    )
    return resp.json()


def check_health():
    """Verify the server is running."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        assert resp.status_code == 200
        print(f"Server OK: {BASE_URL}")
    except Exception:
        print(f"ERROR: Server not reachable at {BASE_URL}")
        print(f"Start with: python3 -m uvicorn main:app --reload --port 8080")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_test(test: dict) -> dict:
    """Run a single test and return results."""
    label = f"[{test['id']}] {test['description']} ({test['language']})"
    result = call_solve(test["prompt"], label)
    result["test_id"] = test["id"]
    result["category"] = test["category"]
    return result


def print_summary(results: list[dict]):
    """Print a summary table of all test results."""
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'ID':<4} {'STATUS':<8} {'TIME':<8} {'CATEGORY':<12} DESCRIPTION")
    print("-" * 70)

    prompts = {p["id"]: p for p in load_prompts()}
    ok_count = 0
    for r in results:
        test = prompts.get(r["test_id"], {})
        status = "OK" if r["status"] == 200 else f"ERR {r['status']}"
        if r["status"] == 200:
            ok_count += 1
        print(f"{r['test_id']:<4} {status:<8} {r['elapsed']:>5.1f}s  {r.get('category', ''):<12} {test.get('description', '')}")

    print(f"\n{ok_count}/{len(results)} passed")


def main():
    prompts = load_prompts()
    categories = sorted(set(p["category"] for p in prompts))

    arg = sys.argv[1] if len(sys.argv) > 1 else None
    arg2 = sys.argv[2] if len(sys.argv) > 2 else None

    # List tests
    if arg == "list":
        print(f"\n{'ID':<4} {'LANG':<5} {'CATEGORY':<12} DESCRIPTION")
        print("-" * 70)
        for p in prompts:
            print(f"{p['id']:<4} {p['language']:<5} {p['category']:<12} {p['description']}")
        print(f"\nCategories: {', '.join(categories)}")
        print(f"Total: {len(prompts)} tests")
        sys.exit(0)

    # Plan-only mode
    if arg == "--plan":
        test_id = int(arg2) if arg2 else None
        if test_id is None:
            print("Usage: python3 test_local.py --plan <test_id>")
            sys.exit(1)
        test = next((p for p in prompts if p["id"] == test_id), None)
        if not test:
            print(f"Test ID {test_id} not found")
            sys.exit(1)
        # Run with plan-only (just call solve and show output)
        check_health()
        run_test(test)
        sys.exit(0)

    if not SANDBOX_TOKEN:
        print("ERROR: Set SANDBOX_SESSION_TOKEN in your .env file")
        sys.exit(1)

    check_health()

    # Run by ID
    if arg and arg.isdigit():
        test_id = int(arg)
        test = next((p for p in prompts if p["id"] == test_id), None)
        if not test:
            print(f"Test ID {test_id} not found. Use 'list' to see available tests.")
            sys.exit(1)
        result = run_test(test)
        print_summary([result])
        sys.exit(0)

    # Run by category
    if arg in categories:
        tests_to_run = [p for p in prompts if p["category"] == arg]
        with ThreadPoolExecutor(max_workers=min(len(tests_to_run), 8)) as pool:
            futures = {pool.submit(run_test, t): t for t in tests_to_run}
            results = []
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda r: r["test_id"])
        print_summary(results)
        sys.exit(0)

    # Unknown arg
    if arg:
        print(f"Unknown argument '{arg}'.")
        print(f"Usage: python3 test_local.py [list | <id> | <category> | --plan <id>]")
        print(f"Categories: {', '.join(categories)}")
        sys.exit(1)

    # Run all
    with ThreadPoolExecutor(max_workers=min(len(prompts), 8)) as pool:
        futures = {pool.submit(run_test, p): p for p in prompts}
        results = []
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda r: r["test_id"])
    print_summary(results)


if __name__ == "__main__":
    main()
