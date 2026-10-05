"""
Agent loop for the RiskLens AI Assistant.
Orchestrates multi-turn conversation and function-calling rounds up to ASSISTANT_MAX_TOOL_ROUNDS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import ValidationError

from app.config import settings
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    Block,
)
from app.services.assistant.llm import (
    AssistantMessage,
    LLMClient,
    LLMError,
    LLMMissingKeyError,
    LLMQuotaError,
    LLMTimeoutError,
    NeutralMessage,
    ToolCall,
    ToolResult,
    ToolResultMessage,
    UserMessage,
)
from app.services.assistant.prompts import build_system_prompt
from app.services.assistant.tools import (
    ToolContext,
    ToolExecutionResult,
    get_tool_registry,
)

logger = logging.getLogger(__name__)


async def _execute_single_tool(
    tool_call: ToolCall,
    context: ToolContext,
) -> Tuple[ToolResult, List[Block]]:
    """
    Execute a single tool call within a 30s timeout and return (ToolResult, blocks).
    Logs tool name, duration, and outcome code only (never raw text/data at INFO).
    """
    registry = get_tool_registry()
    start_time = time.monotonic()
    tool_name = tool_call.name
    call_id = tool_call.id or tool_name

    if tool_name not in registry:
        duration = time.monotonic() - start_time
        logger.info("Tool executed: name=%s duration=%.3fs outcome=unknown_tool", tool_name, duration)
        return (
            ToolResult(
                name=tool_name,
                call_id=call_id,
                data={"status": "error", "error": "unknown_tool", "tool": tool_name},
            ),
            [],
        )

    registered_tool = registry[tool_name]

    # Validate arguments against Pydantic args model
    try:
        validated_args = registered_tool.args_model.model_validate(tool_call.args)
    except ValidationError as val_err:
        duration = time.monotonic() - start_time
        fields = [str(err["loc"][-1]) for err in val_err.errors() if err.get("loc")]
        logger.info("Tool executed: name=%s duration=%.3fs outcome=invalid_args", tool_name, duration)
        return (
            ToolResult(
                name=tool_name,
                call_id=call_id,
                data={"status": "error", "error": "invalid_arguments", "fields": fields},
            ),
            [],
        )

    # Execute with 30s timeout
    try:
        exec_res: ToolExecutionResult = await asyncio.wait_for(
            registered_tool.handler(validated_args, context),
            timeout=30.0,
        )
        duration = time.monotonic() - start_time
        outcome = "ok" if exec_res.data.get("status") != "error" else "error"
        logger.info("Tool executed: name=%s duration=%.3fs outcome=%s", tool_name, duration, outcome)
        return (
            ToolResult(
                name=tool_name,
                call_id=call_id,
                data=exec_res.data,
            ),
            exec_res.blocks,
        )
    except asyncio.TimeoutError:
        duration = time.monotonic() - start_time
        logger.info("Tool executed: name=%s duration=%.3fs outcome=timeout", tool_name, duration)
        return (
            ToolResult(
                name=tool_name,
                call_id=call_id,
                data={"status": "error", "error": "timeout"},
            ),
            [],
        )
    except Exception as exc:
        duration = time.monotonic() - start_time
        logger.warning(
            "Tool execution failed: name=%s duration=%.3fs outcome=exception exc=%s",
            tool_name,
            duration,
            exc,
        )
        return (
            ToolResult(
                name=tool_name,
                call_id=call_id,
                data={"status": "error", "error": "execution_failed"},
            ),
            [],
        )


async def run_assistant_agent(
    request: AssistantChatRequest,
    user_id: str,
    client_date: date,
    llm_client: LLMClient,
) -> AssistantChatResponse:
    """
    Run the assistant agent loop.
    Enforces overall request deadline, max rounds, tool de-duplication,
    blocks collection, and graceful error outcomes.
    """
    response_id = f"resp_{uuid.uuid4().hex}"
    overall_deadline = time.monotonic() + settings.ASSISTANT_REQUEST_DEADLINE_S
    system_prompt = build_system_prompt(client_date)
    context = ToolContext(user_id=user_id, client_date=client_date)

    registry = get_tool_registry()
    tool_declarations = [rt.declaration for rt in registry.values()]

    # Convert request messages to neutral messages
    history_messages: List[NeutralMessage] = []
    for msg in request.messages:
        if msg.role == "user":
            history_messages.append(UserMessage(text=msg.text))
        elif msg.role == "assistant":
            history_messages.append(AssistantMessage(text=msg.text))

    collected_blocks: List[Block] = []

    try:
        for round_idx in range(settings.ASSISTANT_MAX_TOOL_ROUNDS):
            remaining_time = overall_deadline - time.monotonic()
            if remaining_time <= 0:
                logger.warning("Assistant agent request deadline exceeded before round %d", round_idx)
                return AssistantChatResponse(
                    id=response_id,
                    text="I reached the time limit while processing your request. Here is what was gathered so far.",
                    blocks=collected_blocks[:6],
                    outcome="degraded",
                )

            # Call LLM
            turn = await llm_client.generate(
                system_instruction=system_prompt,
                messages=history_messages,
                tools=tool_declarations,
            )

            # If no tool calls, model provided the final text answer
            if not turn.tool_calls:
                reply_text = (turn.text or "").strip()
                if not reply_text and collected_blocks:
                    reply_text = "Here is the summary based on your tracked data:"
                return AssistantChatResponse(
                    id=response_id,
                    text=reply_text,
                    blocks=collected_blocks[:6],
                    outcome="ok",
                )

            # Process tool calls
            history_messages.append(
                AssistantMessage(text=turn.text, tool_calls=turn.tool_calls, raw=turn.raw)
            )

            # Execute identical (tool_name, serialized args) calls only once...
            unique_calls: List[ToolCall] = []
            index_by_signature: Dict[str, int] = {}
            call_signatures: List[str] = []
            for tc in turn.tool_calls:
                sig = f"{tc.name}:{json.dumps(tc.args, sort_keys=True)}"
                call_signatures.append(sig)
                if sig not in index_by_signature:
                    index_by_signature[sig] = len(unique_calls)
                    unique_calls.append(tc)

            # Concurrently execute all unique tool calls in this round
            results = await asyncio.gather(
                *[_execute_single_tool(tc, context) for tc in unique_calls]
            )
            for _, blocks in results:  # blocks are collected once per executed call
                collected_blocks.extend(blocks)

            # ...but Gemini requires exactly one function response per function call,
            # in the same order, so duplicates reuse the executed result.
            round_tool_results: List[ToolResult] = []
            for tc, sig in zip(turn.tool_calls, call_signatures):
                shared, _ = results[index_by_signature[sig]]
                round_tool_results.append(
                    ToolResult(name=tc.name, call_id=shared.call_id, data=shared.data)
                )

            history_messages.append(ToolResultMessage(results=round_tool_results))

        # If loop exited after MAX_ROUNDS without final text
        logger.info("Agent exceeded max tool rounds (%d)", settings.ASSISTANT_MAX_TOOL_ROUNDS)
        return AssistantChatResponse(
            id=response_id,
            text="I reached the limit of tool operations while analyzing your request. Here is the data collected so far:",
            blocks=collected_blocks[:6],
            outcome="degraded",
        )

    except LLMMissingKeyError:
        logger.warning("Assistant request failed: missing Gemini API key")
        return AssistantChatResponse(
            id=response_id,
            text="The AI assistant is temporarily unavailable because the service is not configured.",
            blocks=[],
            outcome="unavailable",
        )
    except LLMTimeoutError:
        logger.warning("Assistant request failed: LLM timeout")
        return AssistantChatResponse(
            id=response_id,
            text="The AI assistant timed out while processing your request. Please try again shortly.",
            blocks=[],
            outcome="unavailable",
        )
    except LLMQuotaError:
        logger.warning("Assistant request failed: LLM quota exceeded")
        return AssistantChatResponse(
            id=response_id,
            text="The assistant is busy right now. Please try again in a minute.",
            blocks=[],
            outcome="unavailable",
        )
    except Exception as exc:
        logger.warning(
            "Assistant request failed: type=%s status=%s",
            type(exc).__name__,
            getattr(exc, "code", None) or getattr(getattr(exc, "__cause__", None), "code", None),
            exc_info=True,
        )
        return AssistantChatResponse(
            id=response_id,
            text="The AI assistant is temporarily unavailable. Please try again later.",
            blocks=[],
            outcome="unavailable",
        )
