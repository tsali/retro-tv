#!/usr/bin/env python3
"""Geocode a ZIP code to lat/lon using Nominatim (OpenStreetMap)."""

import json
import sys
import urllib.request


def geocode_zip(zip_code):
    """Convert a US ZIP code to (latitude, longitude) using Nominatim."""
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?postalcode={zip_code}&country=US&format=json&limit=1"
    )

    req = urllib.request.Request(url, headers={
        "User-Agent": "RetroTV-EAS/1.0 (retro-tv@local)"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    if not data:
        raise ValueError(f"No geocoding results for ZIP code: {zip_code}")

    return float(data[0]["lat"]), float(data[0]["lon"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <zip_code>", file=sys.stderr)
        sys.exit(1)

    try:
        lat, lon = geocode_zip(sys.argv[1])
        print(json.dumps({"latitude": lat, "longitude": lon}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
