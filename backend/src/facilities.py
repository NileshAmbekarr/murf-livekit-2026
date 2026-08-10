"""Nearest health facility lookup, from a local OpenStreetMap extract.

The agent ends nearly every non-emergency call telling someone to visit their
nearest PHC, and until now it had no idea where that was. This is the lookup
that makes that sentence actionable.

**No network at call time.** `scripts/build_facilities.py` downloads the data
ahead of time into `data/facilities.json`; this module reads it. That is not
laziness about "using a real API" — Overpass was measured at 21 to 37 seconds
against these districts, with its main instance returning 504, and the agent's
entire budget from button press to first audio is under eight seconds. The slow
part belongs in a script that runs once, not in a conversational turn.

Two consequences, both stated aloud by the agent rather than hidden:

* Coverage is only the districts that were downloaded. Anywhere else, the honest
  answer is "I do not have that area" plus the 104 helpline — never a guess.
* The data ages, and it is community-maintained, so it can be wrong. Callers are
  told to phone ahead before travelling.

No LiveKit imports, so this tests offline in milliseconds like
`health_resources.py` and `memory.py`. Everything the agent needs goes through
here, so swapping the local file for a live nationwide source later means
writing one more loader, not touching the agent.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("sehat-sathi")

DATA_PATH = Path(
    os.getenv(
        "FACILITIES_PATH",
        Path(__file__).resolve().parent.parent / "data" / "facilities.json",
    )
)

#: Spoken kinds, mapped from the OSM tag values the extract stores. Anything not
#: listed is described with the neutral word rather than the raw tag, because
#: "healthcare centre" is speakable and "centre" on its own is not.
KIND_WORDS: dict[str, str] = {
    "hospital": "hospital",
    "clinic": "clinic",
    "centre": "health centre",
    "doctors": "doctor's clinic",
    "pharmacy": "medical store",
    "dentist": "dental clinic",
    "laboratory": "test laboratory",
}


@dataclass(frozen=True)
class Facility:
    """One health facility, with the distance from wherever we searched."""

    name: str
    kind: str
    lat: float
    lon: float
    district: str
    address: str
    phone: str
    distance_km: float

    @property
    def kind_word(self) -> str:
        return KIND_WORDS.get(self.kind, "health centre")

    def spoken(self) -> str:
        """One clause a TTS voice can read without stumbling."""
        distance = (
            "under a kilometre away"
            if self.distance_km < 1
            else f"about {round(self.distance_km)} kilometres away"
        )
        return f"{self.name}, a {self.kind_word}, {distance}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres. Plenty accurate at district scale."""
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _dataset() -> dict[str, Any]:
    """Read the extract once, and survive its absence.

    A missing or corrupt file must degrade to "no coverage" rather than raising:
    the agent still has helplines, schemes and the emergency path, and losing a
    directory should not take a health line down.
    """
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning(
            "no facility data at %s; lookups will report no coverage", DATA_PATH
        )
    except (OSError, json.JSONDecodeError):
        logger.exception("facility data at %s could not be read", DATA_PATH)
    return {"facilities": [], "district_centres": {}, "as_of": ""}


def reload_data() -> None:
    """Drop the cached extract. For tests, and after re-running the script."""
    _dataset.cache_clear()


def data_as_of() -> str:
    """The date the OpenStreetMap data was current, as `YYYY-MM-DD`, or empty.

    Spoken to the caller. "Yesterday's data" and "three months old" are different
    decisions for someone deciding whether to travel.
    """
    stamp = _dataset().get("as_of") or ""
    return stamp[:10]


def covered_districts() -> tuple[str, ...]:
    """Districts the extract holds, lowercased.

    Doubles as the allow-list for the `district` fact in `memory.py`: a district
    we cannot serve must not be storable as though we could.
    """
    return tuple(sorted(_dataset().get("district_centres", {})))


def _resolve_district(place: str) -> str | None:
    """Match a spoken place name to a covered district, or None.

    Deliberately forgiving at the edges — a caller may say "Wardha district" or
    "wardha, maharashtra" — but never guesses across districts. Returning None
    is what produces an honest "I don't have that area" instead of directions to
    the wrong town.
    """
    spoken = " ".join((place or "").lower().split())
    if not spoken:
        return None

    districts = covered_districts()
    if spoken in districts:
        return spoken

    for district in districts:
        # "wardha district", "wardha, maharashtra", "I'm in wardha"
        if district in spoken.split(",")[0] or spoken.split(",")[0].strip() == district:
            return district
        if district in spoken:
            return district

    return None


def find_nearby(
    place: str, *, kind: str | None = None, limit: int = 3
) -> list[Facility]:
    """Facilities near a district, nearest first.

    Returns an empty list when the district is not covered, which the caller of
    this function must treat as "say so" rather than "try something else".
    """
    district = _resolve_district(place)
    if district is None:
        return []

    data = _dataset()
    centre = data.get("district_centres", {}).get(district)
    if not centre:
        return []

    wanted = (kind or "").strip().lower() or None
    results: list[Facility] = []

    for row in data.get("facilities", []):
        if row.get("district", "").lower() != district:
            continue
        if wanted and wanted not in (
            row.get("kind", ""),
            KIND_WORDS.get(row.get("kind", ""), ""),
        ):
            continue

        results.append(
            Facility(
                name=row["name"],
                kind=row.get("kind", "clinic"),
                lat=row["lat"],
                lon=row["lon"],
                district=row.get("district", district),
                address=row.get("address", ""),
                phone=row.get("phone", ""),
                distance_km=haversine_km(
                    centre["lat"], centre["lon"], row["lat"], row["lon"]
                ),
            )
        )

    results.sort(key=lambda f: f.distance_km)
    return results[:limit]
