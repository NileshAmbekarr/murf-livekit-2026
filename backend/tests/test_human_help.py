"""Offline tests for Day 7 human-help requests.

These pin the parts that must not depend on the LLM doing the right thing:
limited values, privacy redaction, no duplicate open work, durable statuses, and
email delivery never being the only copy of a request.

    uv run pytest tests/test_human_help.py -q
"""

from unittest.mock import MagicMock, patch

import pytest
from livekit.agents import llm

from agent import SehatSathi
from human_help import (
    EmailNotifier,
    HumanHelpStore,
    HumanHelpValidationError,
    detect_human_help_reason,
)


@pytest.fixture
def store(tmp_path):
    return HumanHelpStore(tmp_path / "human-help.db")


def create_request(store, **overrides):
    values = {
        "caller_id": "sehat-caller-test-123",
        "caller_name": "Ramesh",
        "reason": "clinical_decision",
        "summary": "Caller asked whether their ongoing cough needs a prescription.",
        "checked": "Explained that Sehat Sathi cannot prescribe medicine.",
        "urgency": "medium",
        "language": "mixed",
        "follow_up_method": "same_app",
    }
    values.update(overrides)
    return store.create_request(**values)


async def injected_instruction(utterance: str) -> str | None:
    """Run the real voice turn hook that `session.run()` intentionally skips."""
    agent = SehatSathi()
    turn_ctx = llm.ChatContext.empty()
    message = llm.ChatMessage(role="user", content=[utterance])

    before = len(turn_ctx.items)
    await agent.on_user_turn_completed(turn_ctx, message)
    added = turn_ctx.items[before:]
    return added[0].text_content if added else None


class TestHumanHelpTrigger:
    @pytest.mark.parametrize(
        ("utterance", "reason"),
        [
            ("Can you diagnose my cough and prescribe medicine?", "clinical_decision"),
            ("Mujhe kaunsi dawa leni chahiye?", "clinical_decision"),
            ("क्या आप मुझे निदान बता सकती हैं?", "clinical_decision"),
            ("I want to speak to a human helper.", "human_follow_up"),
            ("Mujhe doctor se baat karni hai.", "human_follow_up"),
            ("मुझे आशा कार्यकर्ता से बात करनी है।", "human_follow_up"),
        ],
    )
    def test_explicit_human_help_requests_are_classified(self, utterance, reason):
        assert detect_human_help_reason(utterance) == reason

    @pytest.mark.asyncio
    async def test_trigger_injects_permission_first_instructions(self):
        injected = await injected_instruction(
            "Can you diagnose my cough and tell me which medicine to take?"
        )

        assert injected is not None
        assert "HUMAN HELP TRIGGER DETECTED" in injected
        assert "record_human_help_consent" in injected
        assert "Do NOT create a request yet" in injected

    @pytest.mark.asyncio
    async def test_ordinary_question_injects_no_human_help_instruction(self):
        assert (
            await injected_instruction("What does fasting before a blood test mean?")
            is None
        )

    @pytest.mark.asyncio
    async def test_emergency_always_wins_over_human_help(self):
        injected = await injected_instruction(
            "Can you diagnose this chest pain and prescribe medicine?"
        )

        assert injected is not None
        assert "DANGER SIGN DETECTED" in injected
        assert "HUMAN HELP TRIGGER DETECTED" not in injected


class TestHumanHelpStore:
    def test_request_persists_with_a_human_reference(self, store):
        result = create_request(store)

        assert result.created is True
        assert result.request.reference_id.startswith("SS-")
        saved = store.get(result.request.reference_id)
        assert saved is not None
        assert saved.status == "open"
        assert saved.notification_status == "pending"
        assert saved.caller_name == "Ramesh"

    def test_only_the_safe_choice_values_are_accepted(self, store):
        with pytest.raises(HumanHelpValidationError, match="reason"):
            create_request(store, reason="anything else")

        with pytest.raises(HumanHelpValidationError, match="urgency"):
            create_request(store, urgency="emergency")

        with pytest.raises(HumanHelpValidationError, match="follow-up method"):
            create_request(store, follow_up_method="whatsapp")

    def test_summary_redacts_common_secrets_and_contact_details(self, store):
        result = create_request(
            store,
            summary=(
                "Caller gave OTP is 123456, card number 4111 1111 1111 1111, "
                "phone +91 98765 43210 and name@example.com."
            ),
            checked="No private number was needed.",
        )

        assert "123456" not in result.request.summary
        assert "4111" not in result.request.summary
        assert "98765" not in result.request.summary
        assert "name@example.com" not in result.request.summary
        assert "[secret removed]" in result.request.summary
        assert "[account details removed]" in result.request.summary
        assert "[number removed]" in result.request.summary
        assert "[email removed]" in result.request.summary

    def test_duplicate_open_request_reuses_the_reference(self, store):
        first = create_request(store)
        repeated = create_request(store)

        assert repeated.created is False
        assert repeated.request.reference_id == first.request.reference_id
        assert len(store.list_requests()) == 1

    def test_resolved_request_does_not_block_a_new_request(self, store):
        first = create_request(store)
        resolved = store.update_status(first.request.reference_id, "resolved")

        assert resolved is not None
        assert resolved.status == "resolved"

        later = create_request(store)
        assert later.created is True
        assert later.request.reference_id != first.request.reference_id

    def test_statuses_are_limited_and_listable(self, store):
        result = create_request(store)
        updated = store.update_status(result.request.reference_id, "in_progress")

        assert updated is not None
        assert updated.status == "in_progress"
        assert [item.reference_id for item in store.list_requests("in_progress")] == [
            result.request.reference_id
        ]

        with pytest.raises(HumanHelpValidationError, match="status"):
            store.update_status(result.request.reference_id, "waiting")


class TestEmailNotifier:
    def test_unconfigured_email_leaves_delivery_pending(self, store):
        request = create_request(store).request
        result = EmailNotifier().send_request(request)

        assert result.delivered is False
        assert result.message == "Email delivery is not configured yet."

    def test_email_contains_only_the_bounded_request_summary(self, store):
        request = create_request(store).request
        notifier = EmailNotifier(
            recipient="care@example.com",
            sender="sehat@example.com",
            password="app-password",
        )
        client = MagicMock()

        with patch("human_help.smtplib.SMTP_SSL") as smtp_ssl:
            smtp_ssl.return_value.__enter__.return_value = client
            result = notifier.send_request(request)

        assert result.delivered is True
        client.login.assert_called_once_with("sehat@example.com", "app-password")
        message = client.send_message.call_args.args[0]
        body = message.get_content()
        assert request.reference_id in message["Subject"]
        assert "Caller: Ramesh" in body
        assert request.summary in body
        assert request.caller_id not in body
