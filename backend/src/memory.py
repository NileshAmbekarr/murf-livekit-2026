"""Caller memory for Sehat Sathi — what the agent is allowed to remember.

A health line that makes you repeat your age and your conditions on every call
is a health line people stop using. So the agent remembers. But this is health
information about identifiable people, and the rules it is held to are stricter
than "put it in a database":

  1. **Nothing is stored without the caller agreeing first.** Consent is a
     precondition enforced here, in code — not a line in the prompt that a small
     model may or may not honour.
  2. **Only a fixed set of facts can be stored, with validated values.** The
     model cannot invent a key or write free text. This is the important one: a
     tool shaped `save(key: str, value: str)` would have the model writing
     "caller has chest pain, worried about a heart attack" the first time
     somebody described a symptom, and a written-out medical note is exactly
     what a health service must not keep.
  3. **Forgetting is real.** `forget` deletes the row. There is no soft-delete
     flag, no archive table, and the file is local — so "I have forgotten you"
     is true rather than nearly true.

SQLite on purpose. The lookup happens mid-conversation, and a local file read
costs microseconds where a hosted database costs a network round-trip inside a
turn the caller is waiting through. Everything here goes through `MemoryStore`,
so swapping in Postgres later means writing one more class, not a rewrite.

No LiveKit imports, so the tests run offline in milliseconds.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("sehat-sathi")

# --- What may be remembered ---------------------------------------------------
#
# The Health Access rules allow an age band, ongoing conditions and the last
# triage outcome — and explicitly forbid written-out medical notes. That line is
# the difference between a service people trust and one that quietly builds a
# medical record nobody consented to, so the allow-list is narrow and every value
# is checked against it.

#: Coarse enough to be useful for guidance, too coarse to identify anyone.
AGE_BANDS: tuple[str, ...] = (
    "child",
    "teen",
    "adult",
    "senior",
)

#: Long-term conditions that change what general guidance is appropriate. Named
#: conditions only — never a description of how the caller is feeling today.
CONDITIONS: tuple[str, ...] = (
    "diabetes",
    "high blood pressure",
    "asthma",
    "heart condition",
    "thyroid",
    "tuberculosis",
    "pregnancy",
    "arthritis",
    "kidney problem",
    "anaemia",
)

#: What the last call concluded. Not why — the reason would be a medical note.
TRIAGE_OUTCOMES: tuple[str, ...] = (
    "emergency referral",
    "advised clinic visit",
    "advised asha worker",
    "information only",
    "scheme guidance",
)

LANGUAGES: tuple[str, ...] = ("hindi", "english", "mixed")


def _storable_districts() -> tuple[str, ...]:
    """Districts a caller may be recorded as living in.

    Deliberately not "any district in India". The allowed values are exactly the
    districts the facility extract covers, which keeps two promises at once: the
    Day 4 rule that every stored value comes from a closed set rather than free
    text, and the Day 5 rule that we never imply coverage we do not have. A
    district we cannot look up is a district we have no reason to remember.

    Imported lazily so `memory.py` keeps working — with no districts storable —
    if the facility data is missing entirely.
    """
    try:
        import facilities

        return facilities.covered_districts()
    except Exception:  # pragma: no cover - defensive
        return ()


#: key -> the closed set of values it accepts.
ALLOWED_FACTS: dict[str, tuple[str, ...]] = {
    "age_band": AGE_BANDS,
    "ongoing_condition": CONDITIONS,
    "last_triage_outcome": TRIAGE_OUTCOMES,
    "language_preference": LANGUAGES,
    # Coarse — an Indian district averages around two million people, so this is
    # closer to an age band than to an address. It exists so a returning caller
    # is not asked where they live on every single call.
    "district": _storable_districts(),
}


#: E.164 — a plus and eight to fifteen digits. Shape only; whether the number
#: rings is the telephony provider's business, not ours.
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

#: A SIP address, for reaching a softphone rather than the telephone network.
#:
#: This exists because Twilio's free tier stopped allowing trial accounts to buy
#: a number, so development and demos run over Linphone instead: the agent dials
#: `sip:someone@sip.linphone.org` and the app rings. It is a real call over a
#: real SIP trunk — just not over the PSTN — and it sidesteps the Indian
#: telemarketing rules entirely, because no telephone network is involved.
_SIP_URI = re.compile(r"^sip:[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{3,253}$")

#: A bare Linphone username, which is how the dialler is usually invoked.
_SIP_USER = re.compile(r"^[A-Za-z0-9._-]{2,64}$")

#: Domain used when only a username is given.
SIP_DOMAIN = os.getenv("SIP_DOMAIN", "sip.linphone.org")

#: Salts the suppression hashes. A default is fine — the hash exists so a
#: forgotten number is not stored in readable form, not to withstand an attacker
#: who already has the database and a list of every Indian mobile number. Set
#: `MEMORY_PHONE_SALT` to make the list non-portable between deployments.
_PHONE_SALT = os.getenv("MEMORY_PHONE_SALT", "sehat-sathi")


def normalise_phone(contact: str) -> str:
    """Validate somewhere we can call, and return it canonically, or raise.

    Two forms are accepted, and both are checked strictly:

    * a phone number in E.164 — `+919876543210`;
    * a SIP address — `sip:someone@sip.linphone.org`, or a bare username which is
      completed with `SIP_DOMAIN`.

    Spaces, dashes and brackets are stripped from numbers, because a number read
    aloud and transcribed arrives in every imaginable format.

    The name is a slight lie now that it takes SIP addresses too, and is kept
    because everything downstream — the suppression list, the consent gate — is
    identical either way. What matters is that it is a place we can reach
    somebody, and that they said we may.
    """
    raw = (contact or "").strip()

    if raw.lower().startswith("sip:"):
        candidate = "sip:" + raw[4:]
        if not _SIP_URI.match(candidate):
            raise InvalidPhoneError(
                f"'{contact}' is not a usable SIP address. It should look like "
                "sip:someone@sip.linphone.org."
            )
        return candidate

    # Spaces and dashes are stripped only for the number path, where people
    # genuinely write "+91 98765-43210". Doing it before the username check
    # would turn "not a number" into the perfectly valid username
    # "notanumber", which is how a transcription error becomes a call to a
    # stranger.
    cleaned = re.sub(r"[\s\-()]", "", raw)
    if _E164.match(cleaned):
        return cleaned

    # A bare Linphone username, matched against the raw text so it must already
    # be a single well-formed token.
    if _SIP_USER.match(raw) and not raw.isdigit():
        return f"sip:{raw}@{SIP_DOMAIN}"

    raise InvalidPhoneError(
        f"'{contact}' is not somewhere we can call. Use a phone number in "
        "international form like +919876543210, or a SIP address like "
        "sip:someone@sip.linphone.org."
    )


def _phone_fingerprint(phone: str) -> str:
    """A one-way fingerprint of a number, for the suppression list."""
    return hashlib.sha256(f"{_PHONE_SALT}:{phone}".encode()).hexdigest()


class ConsentRequiredError(Exception):
    """Raised when something tried to write without the caller having agreed."""


class CallConsentRequiredError(Exception):
    """Raised when something tried to store a number without permission to call.

    Separate from `ConsentRequiredError` on purpose. Agreeing to be remembered
    is not agreeing to be telephoned, and collapsing the two would make the
    second consent meaningless.
    """


class DoNotCallError(Exception):
    """Raised when something tried to store a number that has opted out."""


class InvalidPhoneError(Exception):
    """Raised for anything that is not a usable E.164 number."""


class FactNotAllowedError(Exception):
    """Raised for an unknown key or a value outside its allow-list."""


def normalise_fact(key: str, value: str) -> tuple[str, str]:
    """Validate a single fact, returning it in canonical form.

    Raises `FactNotAllowedError` rather than silently dropping, so a model that tries
    to store something it should not gets told, and the attempt shows up in the
    logs instead of vanishing.
    """
    clean_key = (key or "").strip().lower().replace(" ", "_")
    if clean_key not in ALLOWED_FACTS:
        raise FactNotAllowedError(
            f"'{key}' is not a storable fact. Allowed: {', '.join(sorted(ALLOWED_FACTS))}."
        )

    clean_value = " ".join((value or "").strip().lower().split())
    permitted = ALLOWED_FACTS[clean_key]
    if clean_value not in permitted:
        raise FactNotAllowedError(
            f"'{value}' is not an accepted {clean_key}. Allowed: {', '.join(permitted)}."
        )

    return clean_key, clean_value


#: A name is stored to greet people by. Cap it so a model cannot smuggle a
#: sentence of medical detail into the one free-text field there is.
MAX_NAME_LENGTH = 40


def clean_name(name: str) -> str:
    """Trim a spoken name down to something safe to store and say back."""
    collapsed = " ".join((name or "").strip().split())
    return collapsed[:MAX_NAME_LENGTH]


@dataclass
class CallerRecord:
    """What the agent knows about one caller."""

    user_id: str
    name: str = ""
    facts: dict[str, str] = field(default_factory=dict)
    last_interaction: float = 0.0
    created_at: float = 0.0
    #: E.164, and only ever set through `record_call_consent`. Never a fact.
    phone: str = ""
    callback_consent: bool = False
    #: reason -> how many times we have rung them for it.
    call_attempts: dict[str, int] = field(default_factory=dict)
    last_call_at: float = 0.0

    @property
    def language_preference(self) -> str:
        return self.facts.get("language_preference", "")

    @property
    def district(self) -> str:
        return self.facts.get("district", "")

    def summary_for_agent(self) -> str:
        """A short, speakable description of what is already known.

        Returned to the model as tool output, so it reads as instructions rather
        than as a record dump — the model should weave this into a greeting, not
        recite it.
        """
        if not self.name and not self.facts:
            return "No record for this caller. Treat them as new."

        known: list[str] = []
        if self.name:
            known.append(f"name: {self.name}")
        for key, value in sorted(self.facts.items()):
            known.append(f"{key.replace('_', ' ')}: {value}")

        return (
            "This caller has spoken to you before. Known: "
            + "; ".join(known)
            + ". Greet them by name, mention briefly what you remember, and ask "
            "how that has been since. Do not read the list out like a form."
        )


class MemoryStore:
    """SQLite-backed caller memory.

    One row per caller. Facts live in a JSON column because they are a small,
    validated key-value bag, and a column per fact would mean a migration every
    time the allow-list grows.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS callers (
                    user_id          TEXT PRIMARY KEY,
                    name             TEXT NOT NULL DEFAULT '',
                    facts            TEXT NOT NULL DEFAULT '{}',
                    consented        INTEGER NOT NULL DEFAULT 0,
                    created_at       REAL NOT NULL,
                    last_interaction REAL NOT NULL
                )
                """
            )

            # Added for outbound calling. Existing databases already have rows,
            # so these are applied as migrations rather than baked into the
            # CREATE above — a caller who used the service yesterday should not
            # have to be forgotten to be callable.
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(callers)")
            }
            for column, ddl in (
                ("phone", "TEXT NOT NULL DEFAULT ''"),
                ("callback_consent", "INTEGER NOT NULL DEFAULT 0"),
                ("call_attempts", "TEXT NOT NULL DEFAULT '{}'"),
                ("last_call_at", "REAL NOT NULL DEFAULT 0"),
            ):
                if column not in existing:
                    connection.execute(f"ALTER TABLE callers ADD COLUMN {column} {ddl}")

            # Suppression list, deliberately a separate table so that it
            # outlives `forget()`.
            #
            # There is a real tension here: honouring "never call me again"
            # requires remembering something about a person who asked to be
            # erased. It is resolved by storing only a salted hash of the number
            # — enough to answer "is this number suppressed?", not enough to
            # recover it or to call it. Deleting a record therefore stays true in
            # substance, and the promise not to ring them stays keepable.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS do_not_call (
                    phone_hash TEXT PRIMARY KEY,
                    added_at   REAL NOT NULL
                )
                """
            )

    # --- Reading -------------------------------------------------------------

    def get(self, user_id: str) -> CallerRecord | None:
        """Return what is known about a caller, or None if they are new."""
        if not user_id:
            return None

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM callers WHERE user_id = ?", (user_id,)
            ).fetchone()

        if row is None:
            return None

        return self._to_record(row)

    @staticmethod
    def _to_record(row: sqlite3.Row) -> CallerRecord:
        """One place that turns a row into a record, so the two readers agree."""
        keys = row.keys()
        return CallerRecord(
            user_id=row["user_id"],
            name=row["name"],
            facts=json.loads(row["facts"]),
            created_at=row["created_at"],
            last_interaction=row["last_interaction"],
            phone=row["phone"] if "phone" in keys else "",
            callback_consent=bool(row["callback_consent"])
            if "callback_consent" in keys
            else False,
            call_attempts=json.loads(row["call_attempts"])
            if "call_attempts" in keys
            else {},
            last_call_at=row["last_call_at"] if "last_call_at" in keys else 0.0,
        )

    def has_consent(self, user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT consented FROM callers WHERE user_id = ?", (user_id,)
            ).fetchone()
        return bool(row and row["consented"])

    # --- Writing -------------------------------------------------------------

    def record_consent(self, user_id: str, *, agreed: bool) -> None:
        """Record the caller's answer to "may I remember this?".

        A refusal is stored too, and stored as a *deletion*: someone who says no
        should not be left with a row that merely has a flag turned off.
        """
        now = time.time()

        if not agreed:
            self.forget(user_id)
            return

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO callers (user_id, consented, created_at, last_interaction)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    consented = 1,
                    last_interaction = excluded.last_interaction
                """,
                (user_id, now, now),
            )

    def remember(
        self,
        user_id: str,
        *,
        name: str | None = None,
        facts: dict[str, str] | None = None,
    ) -> CallerRecord:
        """Store a name and/or facts about a caller.

        Refuses outright unless consent has been recorded, and validates every
        fact before anything touches the database. Both checks happen before the
        write, so a partially-valid batch stores nothing rather than half of
        itself.
        """
        if not user_id:
            raise ValueError("user_id is required")

        if not self.has_consent(user_id):
            raise ConsentRequiredError(
                "The caller has not agreed to be remembered. Ask first, then call "
                "record_consent, and only then save anything."
            )

        validated = dict(
            normalise_fact(key, value) for key, value in (facts or {}).items()
        )

        existing = self.get(user_id) or CallerRecord(user_id=user_id)
        merged = {**existing.facts, **validated}
        new_name = clean_name(name) if name else existing.name
        now = time.time()

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE callers
                SET name = ?, facts = ?, last_interaction = ?
                WHERE user_id = ?
                """,
                (new_name, json.dumps(merged, ensure_ascii=False), now, user_id),
            )

        return CallerRecord(
            user_id=user_id,
            name=new_name,
            facts=merged,
            created_at=existing.created_at or now,
            last_interaction=now,
            # Carried through so saving a fact never looks like it wiped a
            # number or revoked permission to call.
            phone=existing.phone,
            callback_consent=existing.callback_consent,
            call_attempts=existing.call_attempts,
            last_call_at=existing.last_call_at,
        )

    def touch(self, user_id: str) -> None:
        """Update last_interaction without storing anything new."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE callers SET last_interaction = ? WHERE user_id = ?",
                (time.time(), user_id),
            )

    def forget(self, user_id: str) -> bool:
        """Delete everything held about a caller. Returns whether a row existed.

        A real delete, not a flag. If someone asks to be forgotten by a health
        service, the only honest implementation is that the data is gone.

        One thing deliberately outlives it: if we held a number for them, its
        fingerprint goes on the suppression list. Being forgotten and then rung
        the following morning would be failing the same person twice, and the
        only way to prevent it is to be able to recognise the number. A hash is
        the least we can keep and still keep the promise.
        """
        record = self.get(user_id)

        with self._connect() as connection:
            if record and record.phone:
                connection.execute(
                    "INSERT OR IGNORE INTO do_not_call (phone_hash, added_at) VALUES (?, ?)",
                    (_phone_fingerprint(record.phone), time.time()),
                )

            cursor = connection.execute(
                "DELETE FROM callers WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount > 0

    # --- Being called --------------------------------------------------------

    def is_do_not_call(self, phone: str) -> bool:
        """Whether this number has opted out. Checked before every dial."""
        try:
            number = normalise_phone(phone)
        except InvalidPhoneError:
            # An unusable number is not callable anyway, and treating it as
            # suppressed fails in the safe direction.
            return True

        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM do_not_call WHERE phone_hash = ?",
                (_phone_fingerprint(number),),
            ).fetchone()
        return row is not None

    def stop_calling(self, phone: str) -> None:
        """Never ring this number again. Irreversible, by design.

        There is no matching `start_calling`. "How do I make it stop" has to have
        an answer that actually stops it, and a suppression a later conversation
        could quietly undo is not that.
        """
        number = normalise_phone(phone)

        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO do_not_call (phone_hash, added_at) VALUES (?, ?)",
                (_phone_fingerprint(number), time.time()),
            )
            # Clear the stored number too: once suppressed, holding it serves no
            # purpose the hash does not already serve.
            connection.execute(
                "UPDATE callers SET phone = '', callback_consent = 0 WHERE phone = ?",
                (number,),
            )

    def record_call_consent(
        self, user_id: str, *, agreed: bool, phone: str = ""
    ) -> None:
        """Record whether the caller agreed to be telephoned, and on what number.

        Its own method rather than a flag on `record_consent`, because the two
        questions are genuinely different: one asks to remember somebody, the
        other asks to interrupt their day.

        Refuses a suppressed number outright — an opt-out cannot be talked back.
        """
        if not agreed:
            existing = self.get(user_id)
            if existing and existing.phone:
                self.stop_calling(existing.phone)
            with self._connect() as connection:
                connection.execute(
                    "UPDATE callers SET phone = '', callback_consent = 0 WHERE user_id = ?",
                    (user_id,),
                )
            return

        number = normalise_phone(phone)
        if self.is_do_not_call(number):
            raise DoNotCallError(
                "This number has asked never to be called again, and that cannot "
                "be undone here."
            )

        if not self.has_consent(user_id):
            raise ConsentRequiredError(
                "The caller has not agreed to be remembered at all yet, so there "
                "is nowhere to keep a number."
            )

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE callers
                SET phone = ?, callback_consent = 1, last_interaction = ?
                WHERE user_id = ?
                """,
                (number, time.time(), user_id),
            )

    def record_call_attempt(self, user_id: str, *, reason: str, outcome: str) -> int:
        """Note that we rang someone, and how it went. Returns attempts so far.

        Counted and stored rather than derived, so a retry rule that misbehaves
        shows up as a number on a row instead of as somebody's phone ringing for
        the fifth time.
        """
        record = self.get(user_id)
        attempts = dict(record.call_attempts) if record else {}
        attempts[reason] = attempts.get(reason, 0) + 1

        with self._connect() as connection:
            connection.execute(
                "UPDATE callers SET call_attempts = ?, last_call_at = ? WHERE user_id = ?",
                (json.dumps(attempts), time.time(), user_id),
            )

        logger.info(
            "outbound call attempt recorded",
            extra={"reason": reason, "outcome": outcome, "attempt": attempts[reason]},
        )
        return attempts[reason]

    def callers_to_ring(self, *, reason: str, max_attempts: int) -> list[CallerRecord]:
        """Everyone eligible for an outbound call, for this reason.

        Eligibility is deliberately narrow: they agreed to be remembered, agreed
        separately to be called, gave us a number, are not suppressed, and have
        not already been rung the maximum number of times for this reason.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM callers
                WHERE consented = 1 AND callback_consent = 1 AND phone != ''
                ORDER BY last_interaction DESC
                """
            ).fetchall()

        due: list[CallerRecord] = []
        for row in rows:
            record = self._to_record(row)
            if record.call_attempts.get(reason, 0) >= max_attempts:
                continue
            if self.is_do_not_call(record.phone):
                continue
            due.append(record)

        return due
