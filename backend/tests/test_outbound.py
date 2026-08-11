"""Tests for the outbound calling rules.

The ones that matter are the ones that stop the agent behaving badly towards
someone who did not ask to be called: the attempt cap, treating a decline as an
answer, the calling window, and never following up on an emergency.

    uv run pytest tests/test_outbound.py -q     # offline, fast
"""

from datetime import datetime, timedelta

import pytest

from outbound import (
    IST,
    MAX_ATTEMPTS,
    Outcome,
    deserves_follow_up,
    is_soft_opt_out,
    next_attempt,
    next_window_opens,
    outcome_from_sip_status,
    within_calling_window,
)


class TestSipStatusMapping:
    @pytest.mark.parametrize(
        "status,expected",
        [
            (486, Outcome.BUSY),
            (600, Outcome.BUSY),
            (487, Outcome.NO_ANSWER),
            (480, Outcome.NO_ANSWER),
            (603, Outcome.DECLINED),
            (607, Outcome.DECLINED),
            (608, Outcome.DECLINED),
        ],
    )
    def test_known_codes(self, status, expected):
        assert outcome_from_sip_status(status) == expected

    @pytest.mark.parametrize("status", [500, 503, 404, None, 0])
    def test_unknown_codes_are_failures_not_guesses(self, status):
        """An unrecognised code must not be read as a decline.

        Treating a server error as "they rejected us" would silently stop
        following up on someone for a reason that had nothing to do with them.
        """
        assert outcome_from_sip_status(status) == Outcome.FAILED


class TestRetryRules:
    def test_a_decline_is_never_retried(self):
        """Rejecting the call is an answer, and we heard it."""
        assert next_attempt(Outcome.DECLINED, 0).retry is False

    def test_hanging_up_is_never_retried(self):
        assert next_attempt(Outcome.HUNG_UP, 0).retry is False

    def test_an_answered_call_is_not_repeated(self):
        assert next_attempt(Outcome.ANSWERED, 0).retry is False

    @pytest.mark.parametrize(
        "outcome", [Outcome.BUSY, Outcome.NO_ANSWER, Outcome.NO_HUMAN, Outcome.FAILED]
    )
    def test_transient_outcomes_retry_once(self, outcome):
        assert next_attempt(outcome, 0).retry is True

    def test_busy_waits_less_than_no_answer(self):
        """Someone on another call is reachable sooner than someone who is out."""
        assert (
            next_attempt(Outcome.BUSY, 0).wait < next_attempt(Outcome.NO_ANSWER, 0).wait
        )

    @pytest.mark.parametrize(
        "outcome", [Outcome.BUSY, Outcome.NO_ANSWER, Outcome.NO_HUMAN, Outcome.FAILED]
    )
    def test_the_cap_beats_every_rule(self, outcome):
        """The worst bug here would be ringing a sick person repeatedly.

        Whatever the network says, the cap wins.
        """
        assert next_attempt(outcome, MAX_ATTEMPTS).retry is False
        assert next_attempt(outcome, MAX_ATTEMPTS + 5).retry is False

    def test_every_outcome_has_a_stated_reason(self):
        """The reason is logged, so a retry decision is never unexplained."""
        for outcome in Outcome:
            assert next_attempt(outcome, 0).why


class TestSoftOptOut:
    @pytest.mark.parametrize("outcome", [Outcome.DECLINED, Outcome.HUNG_UP])
    def test_rejection_and_hangup_are_heard_as_stop(self, outcome):
        assert is_soft_opt_out(outcome) is True

    @pytest.mark.parametrize(
        "outcome", [Outcome.ANSWERED, Outcome.BUSY, Outcome.NO_ANSWER, Outcome.NO_HUMAN]
    )
    def test_not_reaching_someone_is_not_a_refusal(self, outcome):
        """A missed call is not consent withdrawn — it is just a missed call."""
        assert is_soft_opt_out(outcome) is False


class TestCallingWindow:
    @pytest.mark.parametrize("hour", [9, 12, 17, 20])
    def test_daytime_is_allowed(self, hour):
        assert within_calling_window(datetime(2026, 8, 11, hour, 0, tzinfo=IST))

    @pytest.mark.parametrize("hour", [0, 5, 8, 21, 22, 23])
    def test_nights_and_early_mornings_are_refused(self, hour):
        assert not within_calling_window(datetime(2026, 8, 11, hour, 0, tzinfo=IST))

    def test_the_boundaries(self):
        assert within_calling_window(datetime(2026, 8, 11, 9, 0, tzinfo=IST))
        assert within_calling_window(datetime(2026, 8, 11, 20, 59, tzinfo=IST))
        # 21:00 is the end, not the last allowed minute.
        assert not within_calling_window(datetime(2026, 8, 11, 21, 0, tzinfo=IST))

    def test_the_window_is_ist_regardless_of_server_timezone(self):
        """A server in UTC must not ring Indian phones at 3am local.

        03:30 UTC is 09:00 IST, so this is inside the window; 20:00 UTC is
        01:30 IST the next day, so it is not.
        """
        from datetime import timezone as tz

        assert within_calling_window(datetime(2026, 8, 11, 3, 30, tzinfo=tz.utc))
        assert not within_calling_window(datetime(2026, 8, 11, 20, 0, tzinfo=tz.utc))

    def test_next_opening_is_in_the_future_and_at_nine(self):
        late = datetime(2026, 8, 11, 23, 30, tzinfo=IST)
        opens = next_window_opens(late)

        assert opens > late
        assert opens.hour == 9
        assert opens - late < timedelta(days=1)

    def test_before_nine_opens_the_same_morning(self):
        early = datetime(2026, 8, 11, 6, 0, tzinfo=IST)
        opens = next_window_opens(early)

        assert opens.day == early.day
        assert opens.hour == 9


class TestWhoDeservesAFollowUp:
    @pytest.mark.parametrize(
        "outcome",
        ["advised clinic visit", "advised asha worker", "ADVISED CLINIC VISIT"],
    )
    def test_clinic_advice_earns_a_follow_up(self, outcome):
        assert deserves_follow_up(outcome) is True

    def test_an_emergency_referral_never_earns_one(self):
        """The most important rule in this module.

        Someone told to call an ambulance needed help then. A call the next day
        must never be, or resemble, the safety net for that — offering one
        implies a promise the service cannot keep.
        """
        assert deserves_follow_up("emergency referral") is False

    @pytest.mark.parametrize(
        "outcome", ["information only", "scheme guidance", "", "   "]
    )
    def test_ordinary_calls_are_left_alone(self, outcome):
        assert deserves_follow_up(outcome) is False
