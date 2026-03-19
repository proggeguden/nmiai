"""
Local test script for the /solve endpoint.

Usage:
    python3 test_local.py

Requires:
    - Server running: python3 -m uvicorn main:app --reload --port 8080
    - Sandbox credentials in .env or set as env vars:
        SANDBOX_BASE_URL=https://kkpqfuj-amager.tripletex.dev/v2
        SANDBOX_SESSION_TOKEN=your-sandbox-token
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8080"
SANDBOX_API_URL = os.environ.get("SANDBOX_BASE_URL", "https://kkpqfuj-amager.tripletex.dev/v2")
SANDBOX_TOKEN = os.environ.get("SANDBOX_SESSION_TOKEN", "")

if not SANDBOX_TOKEN:
    print("ERROR: Set SANDBOX_SESSION_TOKEN in your .env file")
    exit(1)


def call_solve(prompt: str, label: str = ""):
    print(f"\n{'='*60}")
    print(f"TEST: {label or prompt[:60]}")
    print(f"{'='*60}")

    payload = {
        "prompt": prompt,
        "files": [],
        "tripletex_credentials": {
            "base_url": SANDBOX_API_URL,
            "session_token": SANDBOX_TOKEN,
        },
    }

    resp = requests.post(f"{BASE_URL}/solve", json=payload, timeout=310)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    return resp


def check_health():
    print("Checking /health ...")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"Status: {resp.status_code} — {resp.json()}")
    assert resp.status_code == 200, "Health check failed"


# --- Test cases ---

TESTS = [
    {
        "label": "Create employee (Norwegian)",
        "prompt": "Opprett en ansatt med navn Test Person, test.person@example.com. Han skal være kontoadministrator.",
    },
    {
        "label": "Create customer (Norwegian)",
        "prompt": "Opprett en kunde med navn Testfirma AS og e-post post@testfirma.no.",
    },
    {
        "label": "Create employee (English)",
        "prompt": "Create an employee named Jane Doe with email jane.doe@example.com.",
    },
]


if __name__ == "__main__":
    check_health()

    import sys
    # Run a specific test by index: python3 test_local.py 0
    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
        t = TESTS[idx]
        call_solve(t["prompt"], t["label"])
    else:
        # Run all tests
        for t in TESTS:
            call_solve(t["prompt"], t["label"])

    print("\nDone.")
