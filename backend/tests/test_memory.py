"""Tests for caller memory.

The Health Access rules make two of these hard failures rather than bugs: saving
anything without consent, and storing a written-out medical note. Both are
enforced in `memory.py` rather than in the prompt, and both are pinned here.

    uv run pytest tests/test_memory.py -q      # offline, fast
"""

import sqlite3

import pytest

from memory import (
    ConsentRequiredError,
    DoNotCallError,
    FactNotAllowedError,
    InvalidPhoneError,
    MemoryStore,
    clean_name,
    normalise_fact,
    normalise_phone,
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


class TestBeingCalled:
    """Permission to telephone someone, which is not permission to remember them."""

    def test_a_number_needs_its_own_consent(self, store):
        """Agreeing to be remembered is not agreeing to be rung."""
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")

        assert store.get("caller-1").callback_consent is False
        assert store.get("caller-1").phone == ""

    def test_storing_a_number(self, store):
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")
        store.record_call_consent("caller-1", agreed=True, phone="+91 98765 43210")

        record = store.get("caller-1")
        assert record.phone == "+919876543210"
        assert record.callback_consent is True

    def test_a_number_cannot_be_stored_without_being_remembered_first(self, store):
        with pytest.raises(ConsentRequiredError):
            store.record_call_consent("caller-1", agreed=True, phone="+919876543210")

    @pytest.mark.parametrize(
        "bad",
        [
            # No country code, so it is ambiguous rather than dialable. It must
            # not be mistaken for a SIP username either.
            "9876543210",
            "+91",
            "not a number",
            "",
            "+0123456789",
            "12345",
            "sip:@sip.linphone.org",
            "sip:nobody",
        ],
    )
    def test_unreachable_destinations_are_refused(self, bad):
        with pytest.raises(InvalidPhoneError):
            normalise_phone(bad)

    @pytest.mark.parametrize(
        "given,expected",
        [
            ("+919876543210", "+919876543210"),
            ("+91 98765-43210", "+919876543210"),
            # Twilio's free tier stopped allowing trial numbers, so demos run
            # over Linphone. A bare username is completed to a full SIP address.
            ("nilesh123", "sip:nilesh123@sip.linphone.org"),
            ("sip:nilesh123@sip.linphone.org", "sip:nilesh123@sip.linphone.org"),
            ("SIP:Bob@sip.linphone.org", "sip:Bob@sip.linphone.org"),
        ],
    )
    def test_both_phone_numbers_and_sip_addresses_are_accepted(self, given, expected):
        assert normalise_phone(given) == expected

    def test_a_sip_address_gets_the_same_consent_and_suppression(self, store):
        """Reaching someone over SIP is still reaching them.

        The consent gate and the do-not-call list must not care which kind of
        address it is, or the softphone path would quietly be the unprotected
        one.
        """
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")
        store.record_call_consent("caller-1", agreed=True, phone="nilesh123")

        assert store.get("caller-1").phone == "sip:nilesh123@sip.linphone.org"

        store.stop_calling("nilesh123")
        assert store.is_do_not_call("sip:nilesh123@sip.linphone.org") is True

    def test_a_phone_number_is_still_not_a_storable_fact(self):
        """Day 4's rule stands: the model cannot write a number as a fact.

        The only way one gets stored is the explicit consent path above.
        """
        with pytest.raises(FactNotAllowedError):
            normalise_fact("phone", "+919876543210")


class TestDoNotCall:
    """ "How do I make it stop" has to have an answer that actually stops it."""

    def test_opting_out_suppresses_the_number(self, store):
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")
        store.record_call_consent("caller-1", agreed=True, phone="+919876543210")

        store.stop_calling("+919876543210")

        assert store.is_do_not_call("+919876543210") is True
        assert store.get("caller-1").phone == ""
        assert store.get("caller-1").callback_consent is False

    def test_an_opt_out_cannot_be_undone_by_consenting_again(self, store):
        """The whole point. A suppression a later chat could reverse is not one."""
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")
        store.stop_calling("+919876543210")

        with pytest.raises(DoNotCallError):
            store.record_call_consent("caller-1", agreed=True, phone="+919876543210")

    def test_being_forgotten_also_stops_the_calls(self, store):
        """Forgotten and then rung the next morning is failing someone twice."""
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")
        store.record_call_consent("caller-1", agreed=True, phone="+919876543210")

        store.forget("caller-1")

        assert store.get("caller-1") is None
        assert store.is_do_not_call("+919876543210") is True

    def test_the_suppression_list_does_not_keep_the_number(self, store):
        """It holds a fingerprint, so "we deleted your data" stays true.

        Honouring an opt-out means recognising the number again; storing it in
        readable form is more than that requires.
        """
        store.stop_calling("+919876543210")

        with sqlite3.connect(store._path) as raw:
            blob = " ".join(str(r) for r in raw.execute("SELECT * FROM do_not_call"))

        assert "9876543210" not in blob
        assert store.is_do_not_call("+919876543210") is True

    def test_declining_a_callback_erases_any_number_held(self, store):
        store.record_consent("caller-1", agreed=True)
        store.remember("caller-1", name="Ramesh")
        store.record_call_consent("caller-1", agreed=True, phone="+919876543210")

        store.record_call_consent("caller-1", agreed=False)

        assert store.get("caller-1").phone == ""
        assert store.is_do_not_call("+919876543210") is True

    def test_an_unusable_destination_reads_as_suppressed(self, store):
        """Failing towards not calling is the safe direction.

        Note "garbage" would now be a perfectly valid Linphone username, so the
        example has to be something no address form accepts.
        """
        assert store.is_do_not_call("not a valid destination!") is True


class TestWhoGetsRung:
    def _consented_caller(self, store, user_id, phone):
        store.record_consent(user_id, agreed=True)
        store.remember(user_id, name="Ramesh")
        store.record_call_consent(user_id, agreed=True, phone=phone)

    def test_only_callers_who_agreed_are_listed(self, store):
        self._consented_caller(store, "yes", "+919876543210")
        store.record_consent("no-phone", agreed=True)
        store.remember("no-phone", name="Someone")

        due = store.callers_to_ring(reason="follow_up", max_attempts=2)

        assert [c.user_id for c in due] == ["yes"]

    def test_the_attempt_cap_removes_someone_from_the_list(self, store):
        self._consented_caller(store, "caller-1", "+919876543210")

        assert (
            store.record_call_attempt(
                "caller-1", reason="follow_up", outcome="no_answer"
            )
            == 1
        )
        assert len(store.callers_to_ring(reason="follow_up", max_attempts=2)) == 1

        store.record_call_attempt("caller-1", reason="follow_up", outcome="no_answer")
        assert store.callers_to_ring(reason="follow_up", max_attempts=2) == []

    def test_attempts_are_counted_per_reason(self, store):
        self._consented_caller(store, "caller-1", "+919876543210")
        store.record_call_attempt("caller-1", reason="follow_up", outcome="busy")
        store.record_call_attempt("caller-1", reason="follow_up", outcome="busy")

        assert store.callers_to_ring(reason="follow_up", max_attempts=2) == []
        assert len(store.callers_to_ring(reason="reminder", max_attempts=2)) == 1

    def test_a_suppressed_caller_is_never_listed(self, store):
        self._consented_caller(store, "caller-1", "+919876543210")
        store.stop_calling("+919876543210")

        assert store.callers_to_ring(reason="follow_up", max_attempts=2) == []

    def test_saving_a_fact_does_not_wipe_the_number(self, store):
        """A later remember() must not look like it revoked permission."""
        self._consented_caller(store, "caller-1", "+919876543210")
        store.remember("caller-1", facts={"age_band": "senior"})

        record = store.get("caller-1")
        assert record.phone == "+919876543210"
        assert record.callback_consent is True
