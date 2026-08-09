"""Tests for caller memory.

The Health Access rules make two of these hard failures rather than bugs: saving
anything without consent, and storing a written-out medical note. Both are
enforced in `memory.py` rather than in the prompt, and both are pinned here.

    uv run pytest tests/test_memory.py -q      # offline, fast
"""

import pytest

from memory import (
    ConsentRequiredError,
    FactNotAllowedError,
    MemoryStore,
    clean_name,
    normalise_fact,
)


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "callers.db")


class TestConsent:
    """Nothing is stored unless the caller agreed. This is a hard rule."""

    def test_saving_without_consent_is_refused(self, store):
        with pytest.raises(ConsentRequiredError):
            store.remember("caller-1", name="Ramesh")

        assert store.get("caller-1") is None

    def test_saving_works_once_consent_is_recorded(self, store):
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh", facts={"age_band": "adult"})

        record = store.get("caller-1")
        assert record is not None
        assert record.name == "Ramesh"
        assert record.facts["age_band"] == "adult"

    def test_refusing_consent_leaves_nothing_behind(self, store):
        """A "no" deletes the record rather than flagging it.

        Someone who declines should not be left as a row in a health database
        with a boolean turned off.
        """
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")

        store.record_consent("caller-1", agreed=False)

        assert store.get("caller-1") is None
        assert store.has_consent("caller-1") is False

    def test_consent_does_not_leak_between_callers(self, store):
        store.record_consent("caller-1", agreed=True)

        with pytest.raises(ConsentRequiredError):
            store.remember("caller-2", name="Someone else")


class TestFactAllowList:
    """The model cannot invent a key or write free text into the store."""

    @pytest.mark.parametrize(
        "key,value",
        [
            ("age_band", "adult"),
            ("ongoing_condition", "diabetes"),
            ("last_triage_outcome", "advised clinic visit"),
            ("language_preference", "hindi"),
            # Case and spacing are normalised rather than rejected.
            ("Age_Band", "  Senior "),
        ],
    )
    def test_allowed_facts_are_accepted(self, key, value):
        assert normalise_fact(key, value)

    @pytest.mark.parametrize(
        "key,value",
        [
            # The one that matters: a written-out medical note. A tool taking
            # free-text values would have stored this happily.
            ("symptoms", "caller has chest pain and is worried about a heart attack"),
            ("notes", "complained of breathlessness for two days"),
            ("address", "12 Gandhi Road, Pune"),
            ("aadhaar", "1234 5678 9012"),
            ("phone", "9876543210"),
            # Known key, value outside its allow-list — still free text.
            ("ongoing_condition", "sharp pain in the left side since Tuesday"),
            ("age_band", "34 years old"),
        ],
    )
    def test_disallowed_facts_are_rejected(self, key, value):
        with pytest.raises(FactNotAllowedError):
            normalise_fact(key, value)

    def test_a_rejected_fact_stores_nothing_at_all(self, store):
        """A batch with one bad fact must not half-write.

        Validation happens before the database is touched, so the good fact in
        this batch should not survive either.
        """
        store.record_consent("caller-1", agreed=True)

        with pytest.raises(FactNotAllowedError):
            store.remember(
                "caller-1",
                facts={"age_band": "adult", "symptoms": "chest pain since morning"},
            )

        record = store.get("caller-1")
        assert record is not None
        assert record.facts == {}

    def test_name_is_capped_so_it_cannot_carry_a_note(self):
        smuggled = (
            "Ramesh who has been having chest pain and breathlessness for two days"
        )
        assert len(clean_name(smuggled)) <= 40


class TestPersistenceAndForgetting:
    def test_data_survives_a_new_store_on_the_same_file(self, tmp_path):
        """The Day 4 pass condition: still there after a full restart."""
        path = tmp_path / "callers.db"

        first = MemoryStore(path)
        first.record_consent("caller-1", agreed=True)
        first.remember("caller-1", name="Ramesh", facts={"age_band": "senior"})

        reopened = MemoryStore(path)
        record = reopened.get("caller-1")

        assert record is not None
        assert record.name == "Ramesh"
        assert record.facts["age_band"] == "senior"

    def test_facts_merge_across_calls(self, store):
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh", facts={"age_band": "senior"})
        store.remember("caller-1", facts={"ongoing_condition": "diabetes"})

        record = store.get("caller-1")
        assert record.name == "Ramesh"
        assert record.facts == {"age_band": "senior", "ongoing_condition": "diabetes"}

    def test_forget_really_deletes(self, store):
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh", facts={"age_band": "adult"})

        assert store.forget("caller-1") is True
        assert store.get("caller-1") is None
        # And a later save is refused again, because consent went with the row.
        with pytest.raises(ConsentRequiredError):
            store.remember("caller-1", name="Ramesh")

    def test_forgetting_an_unknown_caller_is_harmless(self, store):
        assert store.forget("never-existed") is False

    def test_unknown_caller_reads_as_new(self, store):
        assert store.get("nobody") is None


class TestAgentSummary:
    def test_new_caller_summary_says_so(self):
        from memory import CallerRecord

        assert "new" in CallerRecord(user_id="x").summary_for_agent().lower()

    def test_returning_caller_summary_carries_the_name(self, store):
        store.record_consent("caller-1", agreed=True)
        record = store.remember(
            "caller-1", name="Ramesh", facts={"ongoing_condition": "diabetes"}
        )

        summary = record.summary_for_agent()
        assert "Ramesh" in summary
        assert "diabetes" in summary
