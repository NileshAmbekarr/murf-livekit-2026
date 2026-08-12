"""Consent-gated human-help requests for Sehat Sathi.

This is deliberately separate from ``memory.py``. Caller memory is a very
narrow, long-lived record that must never hold today's symptoms. A human-help
request is a short, caller-approved hand-off for a specific unresolved issue.
It is still private health information, so it has an allow-list, redacts common
secrets, contains no transcript, and is never created without an explicit
per-call consent gate in the agent.

SQLite is the source of truth. Email is only a best-effort notification: a
temporary SMTP failure must not silently lose a request.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("sehat-sathi")

REASONS: tuple[str, ...] = ("clinical_decision", "human_follow_up")
URGENCY_LEVELS: tuple[str, ...] = ("low", "medium", "high")
REQUEST_STATUSES: tuple[str, ...] = ("open", "in_progress", "resolved")
FOLLOW_UP_METHODS: tuple[str, ...] = ("same_app", "phone", "none")
LANGUAGES: tuple[str, ...] = ("hindi", "english", "mixed")

MAX_SUMMARY_LENGTH = 280
MAX_CHECKED_LENGTH = 180
MAX_NAME_LENGTH = 40

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\+?\d[\s-]?){8,16}(?!\d)")
_SECRET = re.compile(
    r"\b(?:otp|one[- ]?time password|password|pin)\b"
    r"\s*(?:is|number|code|:)?\s*[A-Za-z0-9]{4,}\b",
    re.IGNORECASE,
)
_ACCOUNT = re.compile(
    r"\b(?:account|a/c|card)\s*(?:number|no\.?|#)?\s*[:=-]?\s*"
    r"(?:\d[\s-]?){6,20}",
    re.IGNORECASE,
)

# These are intentionally narrow, phrase-level triggers. They are a backstop
# for a caller plainly asking the agent to make a clinical decision or connect
# them to a person, not a classifier for every health question. The emergency
# detector in ``health_resources`` runs first and always takes precedence.
_CLINICAL_DECISION_TRIGGERS: tuple[str, ...] = (
    "diagnose",
    "diagnosis",
    "prescribe",
    "prescription",
    "which medicine",
    "what medicine should i take",
    "medicine should i take",
    "give me medicine",
    "dawa bata",
    "dawai bata",
    "dava bata",
    "kaunsi dawa",
    "kaun si dawa",
    "कौन सी दवा",
    "दवा बताइ",
    "दवाई बताइ",
    "निदान",
    "डायग्नोस",
)
_HUMAN_FOLLOW_UP_TRIGGERS: tuple[str, ...] = (
    "speak to a human",
    "talk to a human",
    "human helper",
    "speak to doctor",
    "talk to doctor",
    "speak to a nurse",
    "talk to a nurse",
    "asha worker se baat",
    "doctor se baat",
    "किसी इंसान से बात",
    "डॉक्टर से बात",
    "नर्स से बात",
    "आशा कार्यकर्ता से बात",
    "आशा वर्कर से बात",
)


class HumanHelpValidationError(ValueError):
    """Raised when an escalation field is not one of the safe allowed values."""


def detect_human_help_reason(text: str) -> str:
    """Return the narrow human-help reason in an explicit caller request.

    An empty return value means this is a normal conversation. A request for a
    diagnosis wins over an overlapping request to speak to someone because it
    needs the stronger clinical-decision hand-off language.
    """
    haystack = " ".join((text or "").lower().split())
    if any(trigger in haystack for trigger in _CLINICAL_DECISION_TRIGGERS):
        return "clinical_decision"
    if any(trigger in haystack for trigger in _HUMAN_FOLLOW_UP_TRIGGERS):
        return "human_follow_up"
    return ""


@dataclass(frozen=True)
class HumanHelpRequest:
    """The bounded record a human needs to act on an escalation."""

    reference_id: str
    caller_id: str
    caller_name: str
    reason: str
    summary: str
    checked: str
    urgency: str
    language: str
    follow_up_method: str
    status: str
    notification_status: str
    notification_error: str
    created_at: float
    updated_at: float
    last_requested_at: float

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> HumanHelpRequest:
        return cls(
            reference_id=row["reference_id"],
            caller_id=row["caller_id"],
            caller_name=row["caller_name"],
            reason=row["reason"],
            summary=row["summary"],
            checked=row["checked"],
            urgency=row["urgency"],
            language=row["language"],
            follow_up_method=row["follow_up_method"],
            status=row["status"],
            notification_status=row["notification_status"],
            notification_error=row["notification_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_requested_at=row["last_requested_at"],
        )


@dataclass(frozen=True)
class CreateRequestResult:
    """Result of creating a request, including whether it was a duplicate."""

    request: HumanHelpRequest
    created: bool


@dataclass(frozen=True)
class NotificationResult:
    """The delivery result, expressed safely for the agent's next response."""

    delivered: bool
    message: str


def _normalise_choice(value: str, allowed: tuple[str, ...], field: str) -> str:
    clean = " ".join((value or "").strip().lower().split())
    if clean not in allowed:
        raise HumanHelpValidationError(
            f"'{value}' is not a valid {field}. Allowed: {', '.join(allowed)}."
        )
    return clean


def _clean_short_text(value: str, maximum: int) -> str:
    """Collapse text and redact details a hand-off must not carry."""
    text = " ".join((value or "").strip().split())
    text = _SECRET.sub("[secret removed]", text)
    text = _ACCOUNT.sub("[account details removed]", text)
    text = _EMAIL.sub("[email removed]", text)
    text = _LONG_NUMBER.sub("[number removed]", text)
    return text[:maximum]


def sanitise_summary(value: str) -> str:
    """Return a short, redacted human-help summary or reject an empty one."""
    clean = _clean_short_text(value, MAX_SUMMARY_LENGTH)
    if len(clean) < 8:
        raise HumanHelpValidationError(
            "The summary must be a short useful description, at least eight characters."
        )
    return clean


def sanitise_checked(value: str) -> str:
    """Return the small list of things the agent already checked."""
    clean = _clean_short_text(value, MAX_CHECKED_LENGTH)
    return clean or "No lookup completed."


def clean_caller_name(value: str) -> str:
    """Keep a first name useful without making a free-text data channel."""
    return " ".join((value or "").strip().split())[:MAX_NAME_LENGTH]


class HumanHelpStore:
    """SQLite-backed request queue, with duplicate protection for open work."""

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
                CREATE TABLE IF NOT EXISTS human_help_requests (
                    reference_id TEXT PRIMARY KEY,
                    caller_id TEXT NOT NULL,
                    caller_name TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    checked TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    language TEXT NOT NULL,
                    follow_up_method TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    notification_status TEXT NOT NULL DEFAULT 'pending',
                    notification_error TEXT NOT NULL DEFAULT '',
                    dedupe_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_requested_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_human_help_open_dedupe
                ON human_help_requests (caller_id, dedupe_hash, status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_human_help_status_updated
                ON human_help_requests (status, updated_at DESC)
                """
            )

    @staticmethod
    def _dedupe_hash(caller_id: str, reason: str, summary: str) -> str:
        canonical = "|".join((caller_id, reason, summary.lower()))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _new_reference_id(self, connection: sqlite3.Connection) -> str:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        for _ in range(10):
            reference_id = f"SS-{date}-{secrets.token_hex(3).upper()}"
            existing = connection.execute(
                "SELECT 1 FROM human_help_requests WHERE reference_id = ?",
                (reference_id,),
            ).fetchone()
            if existing is None:
                return reference_id
        raise RuntimeError("Could not create a unique human-help reference id.")

    def create_request(
        self,
        *,
        caller_id: str,
        caller_name: str,
        reason: str,
        summary: str,
        checked: str,
        urgency: str,
        language: str,
        follow_up_method: str,
    ) -> CreateRequestResult:
        """Create an open request, or return an equivalent open request.

        An identical unresolved issue never creates a second ticket. It only
        refreshes ``last_requested_at`` so an operator can see that the caller
        asked again.
        """
        clean_caller_id = (caller_id or "").strip()
        if not clean_caller_id:
            raise HumanHelpValidationError(
                "A caller id is required to create a request."
            )

        clean_reason = _normalise_choice(reason, REASONS, "reason")
        clean_urgency = _normalise_choice(urgency, URGENCY_LEVELS, "urgency")
        clean_language = _normalise_choice(language, LANGUAGES, "language")
        clean_follow_up = _normalise_choice(
            follow_up_method, FOLLOW_UP_METHODS, "follow-up method"
        )
        clean_summary = sanitise_summary(summary)
        clean_checked = sanitise_checked(checked)
        clean_name = clean_caller_name(caller_name)
        dedupe_hash = self._dedupe_hash(clean_caller_id, clean_reason, clean_summary)
        now = time.time()

        with self._connect() as connection:
            duplicate = connection.execute(
                """
                SELECT * FROM human_help_requests
                WHERE caller_id = ? AND dedupe_hash = ?
                  AND status IN ('open', 'in_progress')
                ORDER BY updated_at DESC LIMIT 1
                """,
                (clean_caller_id, dedupe_hash),
            ).fetchone()
            if duplicate is not None:
                connection.execute(
                    """
                    UPDATE human_help_requests
                    SET last_requested_at = ?, updated_at = ?
                    WHERE reference_id = ?
                    """,
                    (now, now, duplicate["reference_id"]),
                )
                refreshed = connection.execute(
                    "SELECT * FROM human_help_requests WHERE reference_id = ?",
                    (duplicate["reference_id"],),
                ).fetchone()
                assert refreshed is not None
                return CreateRequestResult(
                    request=HumanHelpRequest.from_row(refreshed), created=False
                )

            reference_id = self._new_reference_id(connection)
            connection.execute(
                """
                INSERT INTO human_help_requests (
                    reference_id, caller_id, caller_name, reason, summary,
                    checked, urgency, language, follow_up_method, status,
                    notification_status, notification_error, dedupe_hash,
                    created_at, updated_at, last_requested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', 'pending', '', ?, ?, ?, ?)
                """,
                (
                    reference_id,
                    clean_caller_id,
                    clean_name,
                    clean_reason,
                    clean_summary,
                    clean_checked,
                    clean_urgency,
                    clean_language,
                    clean_follow_up,
                    dedupe_hash,
                    now,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM human_help_requests WHERE reference_id = ?",
                (reference_id,),
            ).fetchone()
            assert row is not None
            return CreateRequestResult(
                request=HumanHelpRequest.from_row(row), created=True
            )

    def get(self, reference_id: str) -> HumanHelpRequest | None:
        """Return a request by its human-readable reference id."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM human_help_requests WHERE reference_id = ?",
                ((reference_id or "").strip(),),
            ).fetchone()
        return HumanHelpRequest.from_row(row) if row is not None else None

    def list_requests(self, status: str = "") -> list[HumanHelpRequest]:
        """List current requests, optionally filtered by a validated status."""
        with self._connect() as connection:
            if status:
                clean_status = _normalise_choice(status, REQUEST_STATUSES, "status")
                rows = connection.execute(
                    """
                    SELECT * FROM human_help_requests WHERE status = ?
                    ORDER BY updated_at DESC
                    """,
                    (clean_status,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM human_help_requests ORDER BY updated_at DESC"
                ).fetchall()
        return [HumanHelpRequest.from_row(row) for row in rows]

    def update_status(self, reference_id: str, status: str) -> HumanHelpRequest | None:
        """Move a request through open, in progress, and resolved."""
        clean_status = _normalise_choice(status, REQUEST_STATUSES, "status")
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE human_help_requests SET status = ?, updated_at = ?
                WHERE reference_id = ?
                """,
                (clean_status, now, (reference_id or "").strip()),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM human_help_requests WHERE reference_id = ?",
                ((reference_id or "").strip(),),
            ).fetchone()
        assert row is not None
        return HumanHelpRequest.from_row(row)

    def record_notification(
        self, reference_id: str, result: NotificationResult
    ) -> HumanHelpRequest | None:
        """Record whether the non-essential email notification made it out."""
        now = time.time()
        status = "sent" if result.delivered else "pending"
        error = "" if result.delivered else result.message[:180]
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE human_help_requests
                SET notification_status = ?, notification_error = ?, updated_at = ?
                WHERE reference_id = ?
                """,
                (status, error, now, (reference_id or "").strip()),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM human_help_requests WHERE reference_id = ?",
                ((reference_id or "").strip(),),
            ).fetchone()
        assert row is not None
        return HumanHelpRequest.from_row(row)


class EmailNotifier:
    """Best-effort SMTP notification, configured only through environment vars."""

    def __init__(
        self,
        *,
        recipient: str = "",
        sender: str = "",
        password: str = "",
        host: str = "smtp.gmail.com",
        port: int = 465,
    ) -> None:
        self._recipient = recipient.strip()
        self._sender = sender.strip()
        self._password = password
        self._host = host.strip()
        self._port = port

    @classmethod
    def from_environment(cls) -> EmailNotifier:
        """Build the notifier without exposing secrets in source control."""
        port_text = os.getenv("HUMAN_HELP_SMTP_PORT", "465")
        try:
            port = int(port_text)
        except ValueError:
            port = 465
        return cls(
            recipient=os.getenv("HUMAN_HELP_EMAIL_TO", ""),
            sender=os.getenv("HUMAN_HELP_EMAIL_FROM", ""),
            password=os.getenv("HUMAN_HELP_SMTP_PASSWORD", ""),
            host=os.getenv("HUMAN_HELP_SMTP_HOST", "smtp.gmail.com"),
            port=port,
        )

    @property
    def configured(self) -> bool:
        return bool(self._recipient and self._sender and self._password and self._host)

    @staticmethod
    def _reason_label(reason: str) -> str:
        return {
            "clinical_decision": "Clinical decision requested",
            "human_follow_up": "Human or ASHA follow-up requested",
        }[reason]

    def _message_for(self, request: HumanHelpRequest) -> EmailMessage:
        caller = request.caller_name or "Caller chose not to share a name"
        message = EmailMessage()
        message["Subject"] = (
            f"[Sehat Sathi] {request.urgency.upper()} human-help request "
            f"{request.reference_id}"
        )
        message["From"] = self._sender
        message["To"] = self._recipient
        message.set_content(
            "A caller approved this limited hand-off.\n\n"
            f"Reference: {request.reference_id}\n"
            f"Urgency: {request.urgency}\n"
            f"Reason: {self._reason_label(request.reason)}\n"
            f"Caller: {caller}\n"
            f"Language: {request.language}\n"
            f"Preferred follow-up: {request.follow_up_method}\n\n"
            f"What happened:\n{request.summary}\n\n"
            f"What Sehat Sathi checked:\n{request.checked}\n\n"
            "This is a short, consented summary. It is not a diagnosis and does "
            "not include the full conversation."
        )
        return message

    def send_request(self, request: HumanHelpRequest) -> NotificationResult:
        """Send an email without turning a delivery problem into a lost request."""
        if not self.configured:
            return NotificationResult(
                delivered=False,
                message="Email delivery is not configured yet.",
            )

        try:
            message = self._message_for(request)
            context = ssl.create_default_context()
            if self._port == 465:
                with smtplib.SMTP_SSL(
                    self._host, self._port, timeout=10, context=context
                ) as client:
                    client.login(self._sender, self._password)
                    client.send_message(message)
            else:
                with smtplib.SMTP(self._host, self._port, timeout=10) as client:
                    client.starttls(context=context)
                    client.login(self._sender, self._password)
                    client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning(
                "human-help email notification failed",
                extra={"reference_id": request.reference_id, "error": str(exc)},
            )
            return NotificationResult(
                delivered=False,
                message="Email notification could not be sent yet.",
            )

        logger.info(
            "human-help email notification sent",
            extra={"reference_id": request.reference_id},
        )
        return NotificationResult(delivered=True, message="Email notification sent.")
