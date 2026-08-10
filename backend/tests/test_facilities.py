"""Tests for the nearest-facility lookup.

Two of these matter more than the rest. The lookup must never answer for a
district it does not hold — sending someone to the wrong town is worse than
admitting ignorance — and a missing data file must degrade to "no coverage"
rather than raising, because losing a directory should not take a health line
down with it.

    uv run pytest tests/test_facilities.py -q     # offline, fast
"""

import json

import pytest

import facilities
from facilities import Facility, find_nearby, haversine_km

# A miniature stand-in for the real extract. Coordinates are real enough for the
# distance ordering to be meaningful: Wardha centre, with facilities at
# increasing distance, plus a second district to prove they never mix.
FIXTURE = {
    "source": "OpenStreetMap via Overpass API",
    "as_of": "2026-05-31T22:37:44Z",
    "district_centres": {
        "wardha": {"lat": 20.8256, "lon": 78.6131},
        "nagpur": {"lat": 21.1458, "lon": 79.0882},
    },
    "facilities": [
        {
            "name": "Sahu Hospital",
            "kind": "hospital",
            "lat": 20.8280,
            "lon": 78.6150,
            "district": "Wardha",
            "address": "Main Road",
            "phone": "",
        },
        {
            "name": "Wardha Health Centre",
            "kind": "centre",
            "lat": 20.8600,
            "lon": 78.6400,
            "district": "Wardha",
            "address": "",
            "phone": "",
        },
        {
            "name": "Pawade Nursing Home",
            "kind": "clinic",
            "lat": 20.9100,
            "lon": 78.7000,
            "district": "Wardha",
            "address": "",
            "phone": "",
        },
        {
            "name": "Sakshi Medicals",
            "kind": "pharmacy",
            "lat": 20.9500,
            "lon": 78.7500,
            "district": "Wardha",
            "address": "",
            "phone": "",
        },
        {
            "name": "Nagpur General Hospital",
            "kind": "hospital",
            "lat": 21.1500,
            "lon": 79.0900,
            "district": "Nagpur",
            "address": "",
            "phone": "",
        },
    ],
}


@pytest.fixture(autouse=True)
def extract(tmp_path, monkeypatch):
    """Point the module at a fixture file for every test in this module."""
    path = tmp_path / "facilities.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    monkeypatch.setattr(facilities, "DATA_PATH", path)
    facilities.reload_data()
    yield path
    facilities.reload_data()


class TestFindingFacilities:
    def test_returns_nearest_first(self):
        found = find_nearby("Wardha", limit=3)

        assert [f.name for f in found] == [
            "Sahu Hospital",
            "Wardha Health Centre",
            "Pawade Nursing Home",
        ]
        assert found[0].distance_km < found[1].distance_km < found[2].distance_km

    def test_limit_is_respected(self):
        assert len(find_nearby("Wardha", limit=2)) == 2

    def test_districts_never_mix(self):
        """A Wardha caller must never be sent to a Nagpur hospital."""
        names = [f.name for f in find_nearby("Wardha", limit=10)]
        assert "Nagpur General Hospital" not in names

    @pytest.mark.parametrize(
        "spoken",
        ["Wardha", "wardha", "  WARDHA  ", "Wardha district", "Wardha, Maharashtra"],
    )
    def test_place_names_are_matched_forgivingly(self, spoken):
        assert find_nearby(spoken), f"{spoken!r} should resolve to Wardha"

    def test_kind_filter(self):
        found = find_nearby("Wardha", kind="pharmacy", limit=5)
        assert [f.name for f in found] == ["Sakshi Medicals"]


class TestHonestFailure:
    """The lookup must say nothing rather than say something wrong."""

    @pytest.mark.parametrize("place", ["Chennai", "Kolkata", "somewhere else", ""])
    def test_uncovered_districts_return_nothing(self, place):
        assert find_nearby(place) == []

    def test_a_missing_file_degrades_instead_of_raising(self, tmp_path, monkeypatch):
        """Deleting the data must not take the agent down.

        This is the Day 5 "kill the data source" case: the tool has to be able to
        say it has no directory, which it cannot do if the import raised.
        """
        monkeypatch.setattr(facilities, "DATA_PATH", tmp_path / "gone.json")
        facilities.reload_data()

        assert find_nearby("Wardha") == []
        assert facilities.covered_districts() == ()
        assert facilities.data_as_of() == ""

    def test_corrupt_file_degrades_too(self, tmp_path, monkeypatch):
        broken = tmp_path / "broken.json"
        broken.write_text("{ this is not json", encoding="utf-8")
        monkeypatch.setattr(facilities, "DATA_PATH", broken)
        facilities.reload_data()

        assert find_nearby("Wardha") == []


class TestProvenanceAndSpeech:
    def test_as_of_is_a_plain_date(self):
        """Spoken to the caller, so it must be a date and not a timestamp."""
        assert facilities.data_as_of() == "2026-05-31"

    def test_covered_districts_are_lowercased_and_sorted(self):
        assert facilities.covered_districts() == ("nagpur", "wardha")

    def test_spoken_form_has_no_json_in_it(self):
        spoken = find_nearby("Wardha", limit=1)[0].spoken()

        assert "Sahu Hospital" in spoken
        assert "hospital" in spoken
        assert not any(ch in spoken for ch in '{}[]"')

    def test_very_close_facilities_avoid_zero_kilometres(self):
        """ "Zero kilometres away" is not a thing anyone says."""
        near = Facility(
            name="X",
            kind="clinic",
            lat=0.0,
            lon=0.0,
            district="d",
            address="",
            phone="",
            distance_km=0.3,
        )
        assert "under a kilometre" in near.spoken()

    def test_osm_tag_values_become_speakable_words(self):
        """`centre` is the OSM tag for a PHC, and is not a spoken word."""
        found = find_nearby("Wardha", kind="centre", limit=1)
        assert found[0].kind_word == "health centre"


def test_haversine_matches_a_known_distance():
    """Wardha to Nagpur is about 61 km in a straight line.

    Not the ~75 km you get from a road router — that gap is the whole reason the
    agent says "about" and never gives a precise figure. Someone told "two
    kilometres" who then walks three has been misled by us, not by the map.
    """
    km = haversine_km(20.8256, 78.6131, 21.1458, 79.0882)
    assert 58 < km < 64
