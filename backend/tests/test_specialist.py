"""Unit tests for the Yojana Sathi specialist agent and handoff mechanism."""

from unittest.mock import MagicMock
import pytest
from livekit.agents import llm

from agent import SehatSathi
from specialist import YojanaSathi, YOJANA_PROMPT


def _mock_run_context() -> MagicMock:
    return MagicMock()


def test_yojana_sathi_initialization() -> None:
    """Yojana Sathi initializes with correct prompt and Khyati voice."""
    chat_ctx = llm.ChatContext()
    chat_ctx.add_message(role="user", content="Namaste")

    agent = YojanaSathi(caller_id="test-caller-123", chat_ctx=chat_ctx)
    assert agent._caller_id == "test-caller-123"
    assert agent._instructions == YOJANA_PROMPT
    assert len(agent.chat_ctx.messages()) == 1
    assert agent.chat_ctx.messages()[0].text_content == "Namaste"
    assert agent._tts._opts.voice == "Khyati"


@pytest.mark.asyncio
async def test_sehat_to_yojana_handoff_tool() -> None:
    """SehatSathi.transfer_to_yojana_sathi returns a YojanaSathi instance with context."""
    chat_ctx = llm.ChatContext()
    chat_ctx.add_message(role="user", content="Ayushman card kaise banaye?")
    sehat = SehatSathi(caller_id="test-caller-456", chat_ctx=chat_ctx)

    context = _mock_run_context()
    target_agent, transfer_message = await sehat.transfer_to_yojana_sathi(context)

    assert isinstance(target_agent, YojanaSathi)
    assert target_agent._caller_id == "test-caller-456"
    assert "योजना" in transfer_message
    assert sehat.success_reason == "scheme_specialist_handoff"

    # Context was copied without instructions
    assert len(target_agent.chat_ctx.messages()) == 1
    assert target_agent.chat_ctx.messages()[0].text_content == "Ayushman card kaise banaye?"


@pytest.mark.asyncio
async def test_yojana_to_sehat_handback_tool() -> None:
    """YojanaSathi.transfer_back_to_sehat_sathi returns a SehatSathi instance with is_transfer=True."""
    chat_ctx = llm.ChatContext()
    chat_ctx.add_message(role="user", content="Mujhe hospital dhundna hai")
    yojana = YojanaSathi(caller_id="test-caller-789", chat_ctx=chat_ctx)

    context = _mock_run_context()
    target_agent, transfer_message = await yojana.transfer_back_to_sehat_sathi(context)

    assert isinstance(target_agent, SehatSathi)
    assert target_agent._caller_id == "test-caller-789"
    assert target_agent._is_transfer is True
    assert "सेहत साथी" in transfer_message
    assert len(target_agent.chat_ctx.messages()) == 1
    assert target_agent.chat_ctx.messages()[0].text_content == "Mujhe hospital dhundna hai"


@pytest.mark.asyncio
async def test_yojana_find_health_service_tool() -> None:
    """YojanaSathi.find_health_service looks up scheme details correctly."""
    yojana = YojanaSathi(caller_id="test-caller-123")
    context = _mock_run_context()

    result = await yojana.find_health_service(context, "PM-JAY")
    assert "Ayushman Bharat PM-JAY" in result
    assert "14555" in result
