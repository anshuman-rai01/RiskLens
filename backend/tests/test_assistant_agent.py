"""
Unit tests for the assistant agent loop and FakeLLM.
Tests:
- No-tool direct prose answer
- Single tool call with blocks returned
- Two parallel tool calls
- Invalid tool args then recovery
- Unknown tool name
- Loop cap gives degraded with blocks kept
- LLM exception and missing key give unavailable with HTTP 200
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional
import pytest

from app.schemas.assistant import AssistantChatRequest, ChatMessage
from app.services.assistant.agent import run_assistant_agent
from app.services.assistant.llm import (
    LLMClient,
    LLMError,
    LLMMissingKeyError,
    LLMQuotaError,
    LLMTimeoutError,
    LLMTurn,
    NeutralMessage,
    ToolCall,
    ToolDeclaration,
)


class ScriptedFakeLLM(LLMClient):
    """A mock LLMClient that yields scripted LLMTurns or raises configured exceptions."""

    def __init__(self, turns: Optional[List[Any]] = None):
        self.turns: List[Any] = list(turns) if turns else []
        self.call_count: int = 0
        self.received_messages: List[List[NeutralMessage]] = []

    async def generate(
        self,
        system_instruction: str,
        messages: List[NeutralMessage],
        tools: List[ToolDeclaration],
    ) -> LLMTurn:
        self.call_count += 1
        self.received_messages.append(list(messages))

        if not self.turns:
            return LLMTurn(text="Default fallback reply")

        next_action = self.turns.pop(0)
        if isinstance(next_action, Exception):
            raise next_action
        return next_action


@pytest.mark.asyncio
async def test_agent_no_tool_chat():
    """When the user asks general chat, LLM produces text with no tool calls."""
    fake_llm = ScriptedFakeLLM([
        LLMTurn(text="Hello! How can I help you today?", tool_calls=[])
    ])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Hello")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000001",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "ok"
    assert res.text == "Hello! How can I help you today?"
    assert len(res.blocks) == 0
    assert fake_llm.call_count == 1


@pytest.mark.asyncio
async def test_agent_single_tool_call():
    """Agent calls get_forecast, executes it, then generates prose referencing it."""
    fake_llm = ScriptedFakeLLM([
        # Round 1: Call get_forecast
        LLMTurn(
            text=None,
            tool_calls=[ToolCall(name="get_forecast", args={"series": "expenses", "horizon_days": 30})],
        ),
        # Round 2: Provide final reply
        LLMTurn(
            text="Based on your tracked history, your estimated 30-day expenses are shown below.",
            tool_calls=[],
        ),
    ])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Predict my expenses")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000002",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "ok"
    assert "estimated 30-day expenses" in res.text
    assert fake_llm.call_count == 2
    # Since user has 0 entries, get_forecast emits an insufficient_data notice block
    assert len(res.blocks) >= 1
    assert res.blocks[0].type == "notice"


@pytest.mark.asyncio
async def test_agent_two_parallel_tool_calls():
    """Agent calls get_forecast and build_report concurrently in round 1."""
    fake_llm = ScriptedFakeLLM([
        # Round 1: Two tool calls concurrently
        LLMTurn(
            text="Let me check both your report and forecast.",
            tool_calls=[
                ToolCall(name="get_forecast", args={"series": "savings", "horizon_days": 14}),
                ToolCall(name="build_report", args={"period": "last_7_days"}),
            ],
        ),
        # Round 2: Final reply
        LLMTurn(
            text="Here is your past week summary and savings projection.",
            tool_calls=[],
        ),
    ])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="How did I do and what is coming?")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000003",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "ok"
    assert "past week summary" in res.text
    assert fake_llm.call_count == 2
    # Both tools emitted blocks
    assert len(res.blocks) >= 2


@pytest.mark.asyncio
async def test_agent_invalid_tool_args_recovery():
    """If model supplies invalid args, agent feeds back error and model recovers."""
    fake_llm = ScriptedFakeLLM([
        # Round 1: Invalid series arg
        LLMTurn(
            tool_calls=[ToolCall(name="get_forecast", args={"series": "invalid_series"})],
        ),
        # Round 2: Model recovers with valid arg
        LLMTurn(
            tool_calls=[ToolCall(name="get_forecast", args={"series": "expenses"})],
        ),
        # Round 3: Final answer
        LLMTurn(
            text="Corrected forecast generated.",
            tool_calls=[],
        ),
    ])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Forecast please")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000004",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "ok"
    assert res.text == "Corrected forecast generated."
    assert fake_llm.call_count == 3


@pytest.mark.asyncio
async def test_agent_unknown_tool_recovery():
    """If model calls an unknown tool, agent feeds back error and model recovers."""
    fake_llm = ScriptedFakeLLM([
        # Round 1: Non-existent tool
        LLMTurn(
            tool_calls=[ToolCall(name="delete_account", args={})],
        ),
        # Round 2: Model acknowledges and answers in prose
        LLMTurn(
            text="I cannot do that.",
            tool_calls=[],
        ),
    ])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Delete everything")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000005",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "ok"
    assert res.text == "I cannot do that."
    assert fake_llm.call_count == 2


@pytest.mark.asyncio
async def test_agent_loop_cap_degraded():
    """When tool calls keep repeating and exceed ASSISTANT_MAX_TOOL_ROUNDS, returns outcome: degraded with collected blocks."""
    infinite_tool_turns = [
        LLMTurn(tool_calls=[ToolCall(name="build_report", args={"period": "last_7_days"})])
        for _ in range(5)
    ]
    fake_llm = ScriptedFakeLLM(infinite_tool_turns)

    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Run loop forever")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000006",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "degraded"
    assert "limit of tool operations" in res.text
    assert len(res.blocks) > 0


@pytest.mark.asyncio
async def test_agent_missing_key_unavailable():
    """Missing API key returns HTTP 200 with outcome: unavailable and friendly text."""
    fake_llm = ScriptedFakeLLM([LLMMissingKeyError("API key not configured")])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Hello")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000007",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "unavailable"
    assert "temporarily unavailable" in res.text
    assert len(res.blocks) == 0


@pytest.mark.asyncio
async def test_agent_llm_timeout_unavailable():
    """LLM timeout returns outcome: unavailable and friendly message."""
    fake_llm = ScriptedFakeLLM([LLMTimeoutError("Timed out")])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Hello")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000008",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "unavailable"
    assert "timed out" in res.text
    assert len(res.blocks) == 0


@pytest.mark.asyncio
async def test_agent_llm_exception_unavailable():
    """Generic LLM exception returns outcome: unavailable and never leaks raw exception string."""
    fake_llm = ScriptedFakeLLM([LLMError("Internal 500 secret API stack trace")])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Hello")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000009",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "unavailable"
    assert "secret API stack trace" not in res.text
    assert len(res.blocks) == 0


@pytest.mark.asyncio
async def test_agent_llm_quota_unavailable():
    """LLM quota error (429/RESOURCE_EXHAUSTED) returns friendly busy message."""
    fake_llm = ScriptedFakeLLM([LLMQuotaError("429 ResourceExhausted")])
    req = AssistantChatRequest(
        messages=[ChatMessage(role="user", text="Hello")]
    )
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000010",
        client_date=date(2026, 10, 4),
        llm_client=fake_llm,
    )
    assert res.outcome == "unavailable"
    assert res.text == "The assistant is busy right now. Please try again in a minute."
    assert len(res.blocks) == 0
