"""Rules for calling someone who did not ask to be called.

Every previous day, the caller started the conversation. Outbound reverses that,
and for a health line an unwanted call is worse than no call: it is intrusive at
best, and at worst it says something private out loud to whoever picked up.

So the rules live here, in one place, as plain functions rather than scattered
through the dialler. No LiveKit imports, so they test offline in milliseconds
like `health_resources.py`, `memory.py` and `facilities.py`.

Three of them are worth stating up front.

**Attempts are capped and recorded, never recomputed.** The worst bug this
project could ship is a retry loop that rings a sick person over and over. Two
attempts per reason, counted on the caller's row.

**A decline is an answer.** Someone who rejects the call has told us something;
dialling again would be refusing to hear it.

**Calls only run 09:00-21:00 IST.** TRAI requires it. It is also simply how you
treat people.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from enum import Enum

#: India Standard Time. Fixed offset — India has no daylight saving.
IST = timezone(timedelta(hours=5, minutes=30))

#: TRAI restricts commercial calling to these hours, and it is decent practice
#: regardless. Enforced in the dialler rather than left to whoever runs it.
CALL_WINDOW_START = time(9, 0)
CALL_WINDOW_END = time(21, 0)

#: Hard ceiling per reason. Not a tuning knob — see the module docstring.
MAX_ATTEMPTS = 2


class Reason(str, Enum):
    """Why we are calling. Chosen by the trigger, passed as job metadata."""

    FOLLOW_UP = "follow_up"
    REMINDER = "reminder"


class Outcome(str, Enum):
    """How a call ended. Recorded so a misbehaving retry rule is visible."""

    ANSWERED = "answered"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    DECLINED = "declined"
    #: Picked up, but nobody spoke. Most likely an answering machine.
    NO_HUMAN = "no_human"
    #: Hung up within seconds of us starting to speak.
    HUNG_UP = "hung_up"
    FAILED = "failed"


# SIP status codes that carry a meaning we act on. Anything else is FAILED,
# which retries like a transient fault because that is what it usually is.
_SIP_OUTCOMES: dict[int, Outcome] = {
    486: Outcome.BUSY,  # Busy Here
    600: Outcome.BUSY,  # Global Busy Everywhere
    487: Outcome.NO_ANSWER,  # Request Terminated — rang out
    480: Outcome.NO_ANSWER,  # Temporarily Unavailable
    603: Outcome.DECLINED,  # Decline — they pressed reject
    607: Outcome.DECLINED,  # Unwanted — they marked us as spam
    608: Outcome.DECLINED,  # Rejected
}


def outcome_from_sip_status(status: int | None) -> Outcome:
    """Map a SIP response code to something we can make a decision about."""
    if status is None:
        return Outcome.FAILED
    return _SIP_OUTCOMES.get(int(status), Outcome.FAILED)


@dataclass(frozen=True)
class RetryRule:
    """Whether to try again, and how long to wait."""

    retry: bool
    wait: timedelta
    why: str


#: What each outcome earns. Declines and hang-ups earn nothing, deliberately.
_RETRIES: dict[Outcome, RetryRule] = {
    Outcome.ANSWERED: RetryRule(False, timedelta(0), "the call happened"),
    Outcome.BUSY: RetryRule(True, timedelta(hours=1), "they were on another call"),
    Outcome.NO_ANSWER: RetryRule(True, timedelta(days=1), "nobody picked up"),
    Outcome.DECLINED: RetryRule(
        False, timedelta(0), "they rejected the call, which is an answer"
    ),
    Outcome.NO_HUMAN: RetryRule(
        True, timedelta(days=1), "probably an answering machine, so nothing was said"
    ),
    Outcome.HUNG_UP: RetryRule(
        False, timedelta(0), "hanging up on us is a request to stop"
    ),
    Outcome.FAILED: RetryRule(True, timedelta(hours=1), "the network, most likely"),
}


def next_attempt(outcome: Outcome, attempts_so_far: int) -> RetryRule:
    """Whether to dial again after `outcome`, having already tried this often.

    The attempt cap wins over any per-outcome rule. A caller is never rung more
    than `MAX_ATTEMPTS` times for one reason, whatever the network did.
    """
    if attempts_so_far >= MAX_ATTEMPTS:
        return RetryRule(False, timedelta(0), f"already tried {attempts_so_far} times")

    return _RETRIES.get(outcome, _RETRIES[Outcome.FAILED])


def is_soft_opt_out(outcome: Outcome) -> bool:
    """Whether this outcome should be read as "stop calling me".

    Rejecting a call and hanging up immediately are both people telling us
    something without using words. Treating them as neutral would be choosing not
    to hear it.
    """
    return outcome in (Outcome.DECLINED, Outcome.HUNG_UP)


def within_calling_window(now: datetime | None = None) -> bool:
    """Whether it is an acceptable hour to ring an Indian phone."""
    moment = (now or datetime.now(IST)).astimezone(IST)
    return CALL_WINDOW_START <= moment.time() < CALL_WINDOW_END


def next_window_opens(now: datetime | None = None) -> datetime:
    """When calling next becomes allowed. Used to explain a refusal."""
    moment = (now or datetime.now(IST)).astimezone(IST)
    today = moment.replace(
        hour=CALL_WINDOW_START.hour,
        minute=CALL_WINDOW_START.minute,
        second=0,
        microsecond=0,
    )
    return today if moment.time() < CALL_WINDOW_START else today + timedelta(days=1)


#: Triage outcomes worth following up on.
#:
#: `emergency referral` is deliberately absent. Someone told to call an ambulance
#: needed help at that moment, and a call the next day must never look like the
#: safety net for it. If the escalation failed, a follow-up is far too late to be
#: the answer — and offering one implies a promise the service cannot keep.
FOLLOW_UP_OUTCOMES: frozenset[str] = frozenset(
    {
        "advised clinic visit",
        "advised asha worker",
    }
)


def deserves_follow_up(last_triage_outcome: str) -> bool:
    """Whether a previous call's ending warrants ringing someone back."""
    return (last_triage_outcome or "").strip().lower() in FOLLOW_UP_OUTCOMES
