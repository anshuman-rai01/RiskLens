"""
Regression tests for the "AI assistant is temporarily unavailable" bug on tool questions.

Root cause: Gemini 3 attaches a thought_signature to function-call parts and returns
HTTP 400 if the NEXT request does not echo the model's turn back unmodified. The client
used to rebuild that turn from (name, args), which drops the signature.
"""

from __future__ import annotations

import types as pytypes
from datetime import date
from typing import Any, List

import pytest

from app.schemas.assistant import AssistantChatRequest, ChatMessage
from app.services.assistant import llm as llm_module
from app.services.assistant.agent import run_assistant_agent
from app.services.assistant.llm import (
    AssistantMessage,
    GeminiClient,
    LLMQuotaError,
    LLMTurn,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

SIGNATURE = b"opaque-gemini-3-thought-signature"


def _install_fake_genai(monkeypatch, responses: List[Any], captured: List[Any]) -> None:
    """Replace genai.Client so no network is used; capture the `contents` of every request."""
    import google.genai as genai

    class _Models:
        async def generate_content(self, model, contents, config):
            captured.append(list(contents))
            return responses[len(captured) - 1]

    class _Client:
        def __init__(self, api_key=None):
            self.aio = pytypes.SimpleNamespace(models=_Models())

    monkeypatch.setattr(genai, "Client", _Client)


@pytest.mark.asyncio
async def test_gemini_client_returns_thought_signature_unchanged(monkeypatch):
    from google.genai import types as T

    model_turn = T.Content(
        role="model",
        parts=[
            T.Part(
                function_call=T.FunctionCall(name="build_report", args={"period": "custom"}),
                thought_signature=SIGNATURE,
            )
        ],
    )
    final = T.Content(role="model", parts=[T.Part(text="Here is your report.")])
    captured: List[Any] = []
    _install_fake_genai(
        monkeypatch,
        [
            T.GenerateContentResponse(candidates=[T.Candidate(content=model_turn)]),
            T.GenerateContentResponse(candidates=[T.Candidate(content=final)]),
        ],
        captured,
    )

    client = GeminiClient(api_key="fake", model="gemini-3.6-flash", timeout_seconds=5)
    user = UserMessage("list all expenses of 4th October")
    turn = await client.generate("sys", [user], [])
    assert turn.tool_calls and turn.raw is model_turn

    history = [
        user,
        AssistantMessage(text=turn.text, tool_calls=turn.tool_calls, raw=turn.raw),
        ToolResultMessage(results=[llm_module.ToolResult(name="build_report", data={"status": "ok"})]),
    ]
    await client.generate("sys", history, [])

    resent_model_turn = captured[1][1]
    assert resent_model_turn is model_turn, "model turn must be replayed verbatim"
    assert resent_model_turn.parts[0].thought_signature == SIGNATURE


@pytest.mark.asyncio
async def test_plain_text_history_is_still_rebuilt_without_raw(monkeypatch):
    """Earlier-turn assistant text (sent by the browser) has no raw content and must still work."""
    from google.genai import types as T

    captured: List[Any] = []
    _install_fake_genai(
        monkeypatch,
        [T.GenerateContentResponse(candidates=[T.Candidate(content=T.Content(role="model", parts=[T.Part(text="ok")]))])],
        captured,
    )
    client = GeminiClient(api_key="fake", timeout_seconds=5)
    await client.generate(
        "sys",
        [UserMessage("hi"), AssistantMessage(text="Hello!"), UserMessage("and now?")],
        [],
    )
    roles = [c.role for c in captured[0]]
    assert roles == ["user", "model", "user"]
    assert captured[0][1].parts[0].text == "Hello!"


class _RecordingLLM:
    def __init__(self, turns: List[LLMTurn]):
        self.turns = list(turns)
        self.received: List[List[Any]] = []

    async def generate(self, system_instruction, messages, tools):
        self.received.append(list(messages))
        return self.turns.pop(0)


@pytest.mark.asyncio
async def test_agent_passes_raw_model_turn_into_next_round():
    raw_sentinel = object()
    llm = _RecordingLLM(
        [
            LLMTurn(
                tool_calls=[ToolCall(name="build_report", args={"period": "last_7_days"})],
                raw=raw_sentinel,
            ),
            LLMTurn(text="Done."),
        ]
    )
    req = AssistantChatRequest(messages=[ChatMessage(role="user", text="report")])
    res = await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000099",  # no such user: tool returns no_data
        client_date=date(2026, 10, 5),
        llm_client=llm,
    )
    assert res.outcome == "ok"
    second_round = llm.received[1]
    tool_call_turn = [m for m in second_round if isinstance(m, AssistantMessage) and m.tool_calls][0]
    assert tool_call_turn.raw is raw_sentinel


@pytest.mark.asyncio
async def test_duplicate_calls_still_get_one_response_each_in_order():
    """Gemini needs one function response per function call; duplicates must not be dropped."""
    same = {"period": "last_7_days"}
    other = {"period": "last_30_days"}
    llm = _RecordingLLM(
        [
            LLMTurn(
                tool_calls=[
                    ToolCall(name="build_report", args=same),
                    ToolCall(name="build_report", args=same),  # exact duplicate
                    ToolCall(name="build_report", args=other),
                ]
            ),
            LLMTurn(text="Done."),
        ]
    )
    req = AssistantChatRequest(messages=[ChatMessage(role="user", text="report")])
    await run_assistant_agent(
        request=req,
        user_id="00000000-0000-0000-0000-000000000099",
        client_date=date(2026, 10, 5),
        llm_client=llm,
    )
    results_msg = [m for m in llm.received[1] if isinstance(m, ToolResultMessage)][0]
    assert [r.name for r in results_msg.results] == ["build_report"] * 3
    assert results_msg.results[0].data == results_msg.results[1].data


@pytest.mark.asyncio
async def test_gemini_client_raises_quota_error_on_429(monkeypatch):
    """GeminiClient retries 429 errors up to max_attempts then raises LLMQuotaError."""
    import asyncio
    import google.genai as genai

    attempts = 0

    class _FailingModels:
        async def generate_content(self, model, contents, config):
            nonlocal attempts
            attempts += 1
            raise Exception("429 RESOURCE_EXHAUSTED: quota exceeded for model")

    class _Client:
        def __init__(self, api_key=None):
            self.aio = pytypes.SimpleNamespace(models=_FailingModels())

    monkeypatch.setattr(genai, "Client", _Client)
    monkeypatch.setattr(llm_module.settings, "GEMINI_API_KEY", "fake-key")

    async def _noop_sleep(_):
        pass

    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    client = GeminiClient(api_key="fake-key", model="gemini-test")
    with pytest.raises(LLMQuotaError) as exc_info:
        await client.generate("system prompt", [UserMessage(text="add entry")], [])

    assert "quota exceeded" in str(exc_info.value).lower()
    assert attempts == 3
