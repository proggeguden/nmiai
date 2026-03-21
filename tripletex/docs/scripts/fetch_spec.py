#!/usr/bin/env python3
"""Fetch the Tripletex OpenAPI spec."""
import os
import urllib.request

SPEC_URL = "https://kkpqfuj-amager.tripletex.dev/v2/openapi.json"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.json")

if __name__ == "__main__":
    print(f"Fetching {SPEC_URL}...")
    urllib.request.urlretrieve(SPEC_URL, OUT)
    print(f"Saved to {OUT} ({os.path.getsize(OUT)} bytes)")
