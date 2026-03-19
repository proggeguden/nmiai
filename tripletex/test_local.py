"""
Local test script for the /solve endpoint.

Usage:
    python3 test_local.py            # run all tests
    python3 test_local.py 3          # run test by index
    python3 test_local.py employees  # run a group
    python3 test_local.py list       # list all tests

Requires:
    - Server running: python3 -m uvicorn main:app --reload --port 8080
    - Sandbox credentials in .env:
        SANDBOX_BASE_URL=https://kkpqfuj-amager.tripletex.dev/v2
        SANDBOX_SESSION_TOKEN=your-sandbox-token
"""

import os
import sys
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

SANDBOX_AUTH = ("0", SANDBOX_TOKEN)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def call_solve(prompt: str, label: str = "") -> requests.Response:
    print(f"\n{'='*60}")
    print(f"TEST: {label or prompt[:60]}")
    print(f"{'='*60}")
    print(f"Prompt: {prompt}")

    payload = {
        "prompt": prompt,
        "files": [],
        "tripletex_credentials": {
            "base_url": SANDBOX_API_URL,
            "session_token": SANDBOX_TOKEN,
        },
    }

    resp = requests.post(f"{BASE_URL}/solve", json=payload, timeout=310)
    print(f"→ HTTP {resp.status_code}", end="  ")
    try:
        print(f"{resp.json()}")
    except Exception:
        print(f"(raw) {resp.text}")
    return resp


def tx_get(endpoint: str, params: dict = None):
    """Query the sandbox directly to verify results."""
    resp = requests.get(
        f"{SANDBOX_API_URL}{endpoint}",
        auth=SANDBOX_AUTH,
        params=params or {},
    )
    return resp.json()


def verify(label: str, endpoint: str, params: dict = None, check=None):
    """Query sandbox and print verification result."""
    data = tx_get(endpoint, params)
    values = data.get("values", [data.get("value", data)])
    if not isinstance(values, list):
        values = [values]

    print(f"\n  ✔ VERIFY [{label}]: {len(values)} result(s) found")
    for v in values[:3]:  # show up to 3
        print(f"    {json.dumps(v, ensure_ascii=False)}")

    if check:
        result = check(values)
        status = "PASS ✓" if result else "FAIL ✗"
        print(f"  → Check: {status}")
        return result
    return bool(values)


def check_health():
    print("Checking /health ...")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"  {resp.status_code} — {resp.json()}")
    assert resp.status_code == 200, "Health check failed"


# ---------------------------------------------------------------------------
# Test definitions
# Each test has: label, group, prompt, and optionally a verify_fn
# ---------------------------------------------------------------------------

def make_test(label, group, prompt, verify_fn=None):
    return {"label": label, "group": group, "prompt": prompt, "verify_fn": verify_fn}


TESTS = [
    # --- EMPLOYEES ---
    make_test(
        label="Create employee (Norwegian)",
        group="employees",
        prompt="Opprett en ansatt med fornavn Erik og etternavn Hansen, e-post erik.hansen@example.com. Han skal være kontoadministrator.",
        verify_fn=lambda: verify(
            "employee Erik Hansen",
            "/employee",
            {"fields": "id,firstName,lastName,email"},
            check=lambda vs: any(v.get("firstName") == "Erik" and v.get("lastName") == "Hansen" for v in vs),
        ),
    ),
    make_test(
        label="Create employee (English)",
        group="employees",
        prompt="Create an employee named Sofia Berg with email sofia.berg@example.com.",
        verify_fn=lambda: verify(
            "employee Sofia Berg",
            "/employee",
            {"fields": "id,firstName,lastName,email"},
            check=lambda vs: any(v.get("firstName") == "Sofia" for v in vs),
        ),
    ),
    make_test(
        label="Create employee (German)",
        group="employees",
        prompt="Erstelle einen Mitarbeiter mit dem Namen Klaus Müller und der E-Mail-Adresse k.mueller@example.com.",
        verify_fn=lambda: verify(
            "employee Klaus Müller",
            "/employee",
            {"fields": "id,firstName,lastName,email"},
            check=lambda vs: any(v.get("firstName") == "Klaus" for v in vs),
        ),
    ),

    # --- CUSTOMERS ---
    make_test(
        label="Create customer (Norwegian)",
        group="customers",
        prompt="Opprett en kunde med navn Solberg Consulting AS og e-post kontakt@solberg.no.",
        verify_fn=lambda: verify(
            "customer Solberg Consulting",
            "/customer",
            {"name": "Solberg", "fields": "id,name,email"},
            check=lambda vs: any("Solberg" in v.get("name", "") for v in vs),
        ),
    ),
    make_test(
        label="Create customer (Spanish)",
        group="customers",
        prompt="Crea un cliente con el nombre Empresa Global S.A. y correo info@empresa.es.",
        verify_fn=lambda: verify(
            "customer Empresa Global",
            "/customer",
            {"name": "Empresa", "fields": "id,name,email"},
        ),
    ),
    make_test(
        label="Create customer (French)",
        group="customers",
        prompt="Créez un client avec le nom Société Dupont et l'email contact@dupont.fr.",
        verify_fn=lambda: verify(
            "customer Dupont",
            "/customer",
            {"name": "Dupont", "fields": "id,name,email"},
        ),
    ),

    # --- PRODUCTS ---
    make_test(
        label="Create product (Norwegian)",
        group="products",
        prompt="Opprett et produkt med navn Konsulenttime, pris 1500 kr og varenummer KT-001.",
        verify_fn=lambda: verify(
            "product Konsulenttime",
            "/product",
            {"name": "Konsulenttime", "fields": "id,name,costExcludingVatCurrency,number"},
        ),
    ),

    # --- INVOICING ---
    make_test(
        label="Create invoice for existing customer (Norwegian)",
        group="invoicing",
        prompt=(
            "Opprett en faktura for kunden Solberg Consulting AS. "
            "Fakturaen skal ha forfallsdato om 14 dager og én fakturalinje: "
            "Konsulenttime, antall 2, enhetspris 1500 kr."
        ),
        verify_fn=lambda: verify(
            "invoice",
            "/invoice",
            {"fields": "id,invoiceDate,invoiceDueDate,customer,amount"},
        ),
    ),

    # --- TRAVEL EXPENSES ---
    make_test(
        label="Create travel expense (Norwegian)",
        group="travel",
        prompt=(
            "Registrer en reiseregning for ansatt Erik Hansen. "
            "Reisen var fra Oslo til Bergen, dato 2026-03-15, formål: Kundemøte."
        ),
        verify_fn=lambda: verify(
            "travel expense",
            "/travelExpense",
            {"fields": "id,title,employee,departureDate"},
        ),
    ),

    # --- PROJECTS ---
    make_test(
        label="Create project (Norwegian)",
        group="projects",
        prompt=(
            "Opprett et prosjekt med navn 'Digitaliseringsprosjekt 2026' "
            "koblet til kunden Solberg Consulting AS. Startdato er 2026-04-01."
        ),
        verify_fn=lambda: verify(
            "project",
            "/project",
            {"name": "Digitaliseringsprosjekt", "fields": "id,name,startDate,customer"},
        ),
    ),

    # --- DEPARTMENTS ---
    make_test(
        label="Create department (Norwegian)",
        group="departments",
        prompt="Opprett en avdeling med navn Salgsavdelingen.",
        verify_fn=lambda: verify(
            "department",
            "/department",
            {"fields": "id,name"},
            check=lambda vs: any("Salg" in v.get("name", "") for v in vs),
        ),
    ),

    # --- CORRECTIONS ---
    make_test(
        label="List and delete latest travel expense (Norwegian)",
        group="corrections",
        prompt=(
            "Finn den siste reiseregningen i systemet og slett den."
        ),
        verify_fn=lambda: verify(
            "travel expenses after delete",
            "/travelExpense",
            {"fields": "id,title"},
        ),
    ),

    # --- NYNORSK ---
    make_test(
        label="Create employee (Nynorsk)",
        group="employees",
        prompt="Opprett ein tilsett med namn Ingrid Dahl og e-post ingrid.dahl@example.com.",
        verify_fn=lambda: verify(
            "employee Ingrid Dahl",
            "/employee",
            {"fields": "id,firstName,lastName,email"},
            check=lambda vs: any(v.get("firstName") == "Ingrid" for v in vs),
        ),
    ),

    # --- PORTUGUESE ---
    make_test(
        label="Create customer (Portuguese)",
        group="customers",
        prompt="Crie um cliente com o nome Empresa Portuguesa Ltda e email geral@empresa.pt.",
        verify_fn=lambda: verify(
            "customer Portuguesa",
            "/customer",
            {"name": "Portuguesa", "fields": "id,name,email"},
        ),
    ),
]

GROUPS = sorted(set(t["group"] for t in TESTS))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_test(t: dict):
    call_solve(t["prompt"], t["label"])
    if t.get("verify_fn"):
        try:
            t["verify_fn"]()
        except Exception as e:
            print(f"  ✗ Verify error: {e}")


if __name__ == "__main__":
    check_health()

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "list":
        print(f"\n{'IDX':<4} {'GROUP':<14} LABEL")
        print("-" * 60)
        for i, t in enumerate(TESTS):
            print(f"{i:<4} {t['group']:<14} {t['label']}")
        sys.exit(0)

    elif arg and arg.isdigit():
        run_test(TESTS[int(arg)])

    elif arg in GROUPS:
        for t in TESTS:
            if t["group"] == arg:
                run_test(t)

    else:
        if arg and arg not in GROUPS:
            print(f"Unknown argument '{arg}'. Use an index, a group name, or 'list'.")
            print(f"Groups: {', '.join(GROUPS)}")
            sys.exit(1)
        for t in TESTS:
            run_test(t)

    print("\nDone.")
