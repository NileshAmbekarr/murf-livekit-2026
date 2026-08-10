"""Download health facilities from OpenStreetMap into a local file.

Run by hand, never during a call:

    uv run python scripts/build_facilities.py
    uv run python scripts/build_facilities.py --districts "Wardha, Maharashtra"

Why a downloaded file rather than a live lookup: Overpass was measured at 21 to
37 seconds against these districts, and its main instance returned 504. A caller
waiting through that is a caller who hangs up — the agent's whole latency budget
to first audio is under eight seconds. So the slow part happens here, once, and
the agent reads a file in about a millisecond.

The cost is that coverage is limited to whatever was downloaded, and the data
ages. Both are stated out loud by the agent and in the README rather than hidden.

Data © OpenStreetMap contributors, ODbL. Both APIs used here are free and
community-run, so the script is deliberately unhurried: one request at a time,
with a pause between, per their usage policies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Nominatim and Overpass both ask for a real User-Agent identifying the app.
USER_AGENT = "SehatSathi/1.0 (health-access voice agent; +https://github.com/NileshAmbekarr/murf-livekit-2026)"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# The main instance returns 504 under load and one popular mirror does not
# resolve from here, so the list is tried in order rather than trusted.
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

DEFAULT_DISTRICTS = (
    "Wardha, Maharashtra, India",
    "Nagpur, Maharashtra, India",
    "Varanasi, Uttar Pradesh, India",
    "Patna, Bihar, India",
)

#: How far around the district centre to collect facilities.
RADIUS_M = 20_000

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "facilities.json"


def _get(url: str, *, data: bytes | None = None, timeout: int = 90) -> str:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode()


def geocode(place: str) -> tuple[float, float] | None:
    """Turn a district name into coordinates. About a second per call."""
    query = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    try:
        results = json.loads(_get(f"{NOMINATIM_URL}?{query}", timeout=30))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  ! geocode failed for {place}: {exc}", file=sys.stderr)
        return None

    if not results:
        print(f"  ! no match for {place}", file=sys.stderr)
        return None

    return float(results[0]["lat"]), float(results[0]["lon"])


def fetch_facilities(lat: float, lon: float) -> tuple[list[dict[str, Any]], str | None]:
    """Collect health facilities around a point, trying each mirror in turn.

    Queries `healthcare` as well as `amenity`, because Indian primary health
    centres are usually tagged `healthcare=centre` and a query on `amenity`
    alone silently misses exactly the facilities this agent most wants to name.
    """
    query = f"""[out:json][timeout:60];
(
  nwr[amenity~"^(clinic|hospital|doctors|pharmacy)$"](around:{RADIUS_M},{lat},{lon});
  nwr[healthcare](around:{RADIUS_M},{lat},{lon});
);
out center 200;"""
    payload = urllib.parse.urlencode({"data": query}).encode()

    for mirror in OVERPASS_MIRRORS:
        host = urllib.parse.urlparse(mirror).netloc
        started = time.perf_counter()
        try:
            body = _get(mirror, data=payload, timeout=120)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  ! {host}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        elapsed = time.perf_counter() - started
        parsed = json.loads(body)
        print(f"  · {host} responded in {elapsed:.0f}s")
        return parsed.get("elements", []), parsed.get("osm3s", {}).get(
            "timestamp_osm_base"
        )

    return [], None


def to_record(element: dict[str, Any], district: str) -> dict[str, Any] | None:
    """Reduce an OSM element to the few fields worth speaking aloud.

    Unnamed entries are dropped: "there is a clinic nine hundred metres away"
    with no name is not something a caller can act on.
    """
    tags = element.get("tags", {})
    name = (tags.get("name") or "").strip()
    if not name:
        return None

    centre = element.get("center") or element
    lat, lon = centre.get("lat"), centre.get("lon")
    if lat is None or lon is None:
        return None

    address = ", ".join(
        part
        for part in (
            tags.get("addr:street"),
            tags.get("addr:village")
            or tags.get("addr:city")
            or tags.get("addr:suburb"),
        )
        if part
    )

    return {
        "name": name,
        # `healthcare` is the more specific tag where both are present.
        "kind": tags.get("healthcare") or tags.get("amenity") or "clinic",
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "district": district,
        "address": address,
        # Rarely present in Indian OSM data — 0 of 60 in the first sample — so
        # the frontend must not assume a facility can be phoned.
        "phone": tags.get("phone") or tags.get("contact:phone") or "",
    }


def build(districts: tuple[str, ...]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    centres: dict[str, dict[str, float]] = {}
    as_of: str | None = None

    for place in districts:
        short = place.split(",")[0].strip()
        print(f"{short}…")

        point = geocode(place)
        if point is None:
            continue
        lat, lon = point
        time.sleep(1.1)  # Nominatim asks for at most one request a second.

        elements, timestamp = fetch_facilities(lat, lon)
        as_of = as_of or timestamp

        found = [record for record in (to_record(e, short) for e in elements) if record]
        # The same hospital is often mapped as both a node and a way.
        unique = {
            (r["name"].lower(), round(r["lat"], 3), round(r["lon"], 3)): r
            for r in found
        }

        # A district is only "covered" if facilities actually came back. Every
        # mirror was down for two districts on the first run, and recording their
        # centres anyway would have had the agent claim coverage it did not have
        # — and offered them as storable districts in caller memory.
        if not unique:
            print("  · nothing returned; leaving this district uncovered")
            time.sleep(2)
            continue

        centres[short.lower()] = {"lat": lat, "lon": lon}
        records.extend(unique.values())

        print(f"  · kept {len(unique)} named facilities")
        time.sleep(2)  # Be gentle with a free, community-run endpoint.

    return {
        "source": "OpenStreetMap via Overpass API",
        "licence": "© OpenStreetMap contributors, ODbL",
        "as_of": as_of or "",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "radius_m": RADIUS_M,
        "district_centres": centres,
        "facilities": sorted(records, key=lambda r: (r["district"], r["name"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--districts",
        nargs="*",
        default=list(DEFAULT_DISTRICTS),
        help='Districts to download, e.g. "Wardha, Maharashtra, India"',
    )
    args = parser.parse_args()

    data = build(tuple(args.districts))

    if not data["facilities"]:
        print("Nothing downloaded — leaving the existing file alone.", file=sys.stderr)
        return 1

    # Merge rather than replace. Overpass fails a district at a time, so building
    # the file usually takes several runs, and a run for one district must not
    # throw away the districts that already succeeded.
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

        fresh = {d.lower() for d in data["district_centres"]}
        kept = [
            f
            for f in existing.get("facilities", [])
            if f["district"].lower() not in fresh
        ]

        data["facilities"] = sorted(
            kept + data["facilities"], key=lambda r: (r["district"], r["name"])
        )
        data["district_centres"] = {
            **existing.get("district_centres", {}),
            **data["district_centres"],
        }
        print(f"Merged with {len(kept)} facilities already on file.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"\nWrote {len(data['facilities'])} facilities across "
        f"{len(data['district_centres'])} districts to {OUTPUT}"
        f"\nOSM data as of {data['as_of'] or 'unknown'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
