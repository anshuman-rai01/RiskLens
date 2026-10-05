"""
LLM abstraction layer for the RiskLens AI Assistant.
Provides a provider-neutral protocol (LLMClient) and a concrete GeminiClient
using the google-genai SDK, along with a FakeLLM for testing.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable

from app.config import settings

logger = logging.getLogger(__name__)


# ── Provider-neutral Message Types ───────────────────────────────

@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    id: str = ""


@dataclass
class ToolResult:
    name: str
    data: Dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class LLMTurn:
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    # Opaque provider-native model turn (for Gemini: the SDK Content object). It must be
    # sent back UNMODIFIED when returning tool results: Gemini 3 attaches a thought
    # signature to function-call parts and rejects the next request (HTTP 400) if it is lost.
    raw: Any = None


@dataclass
class UserMessage:
    text: str


@dataclass
class AssistantMessage:
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw: Any = None  # see LLMTurn.raw; only set for tool-call turns of the CURRENT request


@dataclass
class ToolResultMessage:
    results: List[ToolResult] = field(default_factory=list)


NeutralMessage = Union[UserMessage, AssistantMessage, ToolResultMessage]


@dataclass
class ToolDeclaration:
    name: str
    description: str
    parameters: Dict[str, Any]


# ── Exceptions ───────────────────────────────────────────────────

class LLMError(Exception):
    """Base exception for LLM operations."""
    pass


class LLMMissingKeyError(LLMError):
    """Raised when GEMINI_API_KEY is missing or empty."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when the LLM request exceeds the timeout deadline."""
    pass


class LLMQuotaError(LLMError):
    """Raised when the LLM request fails due to rate limit or quota exhaustion (HTTP 429)."""
    pass


# ── Protocol ─────────────────────────────────────────────────────

@runtime_checkable
class LLMClient(Protocol):
    async def generate(
        self,
        system_instruction: str,
        messages: List[NeutralMessage],
        tools: List[ToolDeclaration],
    ) -> LLMTurn:
        """Generate the next turn (text or tool calls) from conversation history."""
        ...


# ── Helper to sanitize JSON schemas for Gemini ───────────────────

def sanitize_schema_for_gemini(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove or flatten schema constructs like '$defs', 'title', and 'anyOf'
    that can cause issues with the Gemini API.
    """
    cleaned: Dict[str, Any] = {}
    for k, v in schema.items():
        if k in ("$defs", "definitions", "title", "additionalProperties", "additional_properties"):
            continue
        if k == "anyOf" and isinstance(v, list):
            # Flatten nullable anyOf: [{'type': 'string'}, {'type': 'null'}] -> {'type': 'string'}
            non_null = [item for item in v if item.get("type") != "null"]
            if non_null:
                merged = sanitize_schema_for_gemini(non_null[0])
                cleaned.update(merged)
                continue
        if isinstance(v, dict):
            cleaned[k] = sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            cleaned[k] = [
                sanitize_schema_for_gemini(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            cleaned[k] = v
    return cleaned


# ── Gemini Implementation ────────────────────────────────────────

class GeminiClient:
    """
    Concrete implementation of LLMClient using google-genai.
    Keeps the model's default temperature (Google recommends 1.0 for Gemini 3; lower
    values can cause looping or degraded results) and explicitly disables automatic
    function calling so tool execution, blocks collection, and limits stay in our control.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.ASSISTANT_LLM_TIMEOUT_S
        )

    async def generate(
        self,
        system_instruction: str,
        messages: List[NeutralMessage],
        tools: List[ToolDeclaration],
    ) -> LLMTurn:
        if not self.api_key:
            raise LLMMissingKeyError("GEMINI_API_KEY is not configured")

        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise LLMError(f"google-genai SDK is not installed: {exc}") from exc

        # 1. Build tool declarations
        sdk_tools: List[genai_types.Tool] = []
        if tools:
            func_decls: List[genai_types.FunctionDeclaration] = []
            for td in tools:
                sanitized_params = sanitize_schema_for_gemini(td.parameters)
                func_decls.append(
                    genai_types.FunctionDeclaration(
                        name=td.name,
                        description=td.description,
                        parameters=sanitized_params,
                    )
                )
            sdk_tools.append(genai_types.Tool(function_declarations=func_decls))

        # 2. Build GenerateContentConfig with temperature 0.2 and AFC disabled
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=sdk_tools if sdk_tools else None,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )

        # 3. Convert neutral messages to SDK Content objects
        contents: List[genai_types.Content] = []
        for msg in messages:
            if isinstance(msg, UserMessage):
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[genai_types.Part.from_text(text=msg.text)],
                    )
                )
            elif isinstance(msg, AssistantMessage):
                if msg.raw is not None:
                    # Verbatim model turn (keeps thought signatures). Never rebuild it.
                    contents.append(msg.raw)
                    continue
                parts: List[genai_types.Part] = []
                if msg.text:
                    parts.append(genai_types.Part.from_text(text=msg.text))
                for tc in msg.tool_calls:
                    parts.append(genai_types.Part.from_function_call(name=tc.name, args=tc.args))
                if parts:
                    contents.append(genai_types.Content(role="model", parts=parts))
            elif isinstance(msg, ToolResultMessage):
                parts = []
                for tr in msg.results:
                    parts.append(
                        genai_types.Part.from_function_response(
                            name=tr.name,
                            response=tr.data,
                        )
                    )
                if parts:
                    contents.append(genai_types.Content(role="user", parts=parts))

        # 4. Invoke model with timeout and retry for transient 503/UNAVAILABLE spikes
        client = genai.Client(api_key=self.api_key)
        response = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=self.timeout_seconds,
                )
                break
            except asyncio.TimeoutError as exc:
                if attempt == max_attempts - 1:
                    raise LLMTimeoutError(f"LLM request timed out after {self.timeout_seconds}s") from exc
                await asyncio.sleep(1.0)
            except Exception as exc:
                err_msg = str(exc)
                code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                is_quota = (
                    code == 429
                    or "429" in err_msg
                    or "RESOURCE_EXHAUSTED" in err_msg
                    or "quota" in err_msg.lower()
                )
                is_transient = (
                    is_quota
                    or code in (503, 500, 502, 504)
                    or "503" in err_msg
                    or "UNAVAILABLE" in err_msg
                )
                if is_transient and attempt < max_attempts - 1:
                    logger.info("Retrying Gemini request after transient error (attempt %d): %s", attempt + 1, err_msg[:80])
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if is_quota:
                    raise LLMQuotaError(f"Gemini API quota exceeded: {exc}") from exc
                raise LLMError(f"Gemini API request failed: {exc}") from exc

        # 5. Parse response candidates into LLMTurn
        if not response.candidates:
            return LLMTurn(text="")

        first_candidate = response.candidates[0]
        if not first_candidate.content or not first_candidate.content.parts:
            return LLMTurn(text="")

        text_pieces: List[str] = []
        tool_calls: List[ToolCall] = []

        for part in first_candidate.content.parts:
            if getattr(part, "text", None):
                text_pieces.append(part.text)
            if getattr(part, "function_call", None):
                fc = part.function_call
                args_dict = dict(fc.args) if fc.args else {}
                tool_calls.append(ToolCall(name=fc.name, args=args_dict))

        return LLMTurn(
            text="\n".join(text_pieces) if text_pieces else None,
            tool_calls=tool_calls,
            raw=first_candidate.content,
        )


# ── Dependency Provider ──────────────────────────────────────────

def get_llm_client() -> LLMClient:
    """FastAPI dependency to retrieve the LLMClient instance."""
    return GeminiClient()
