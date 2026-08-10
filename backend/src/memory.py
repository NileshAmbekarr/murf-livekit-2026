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

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

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


class ConsentRequiredError(Exception):
    """Raised when something tried to write without the caller having agreed."""


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

    @property
    def language_preference(self) -> str:
        return self.facts.get("language_preference", "")

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

        return CallerRecord(
            user_id=row["user_id"],
            name=row["name"],
            facts=json.loads(row["facts"]),
            created_at=row["created_at"],
            last_interaction=row["last_interaction"],
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
        """
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM callers WHERE user_id = ?", (user_id,)
            )
            return cursor.rowcount > 0
