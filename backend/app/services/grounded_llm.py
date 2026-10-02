"""
Generic grounded LLM service — domain-agnostic foundation for safe AI integration.

This module has ZERO knowledge of any specific application domain, data models,
or business types. It takes a context dict, a system prompt, and a Pydantic
response schema, and returns validated output or None.

Failure modes (timeout, malformed JSON, schema validation, API error, missing key)
are all caught, logged server-side with full detail (exc_info=True), and translated
to a (None, outcome_str) return. The caller decides what "unavailable" means in
its own domain context.

SDK: google-genai (current), NOT google-generativeai (deprecated/EOL).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# Outcome codes — sanitized strings safe for client-visible debug fields.
# Never contain raw exception text.
OUTCOME_SUCCESS = "success"
OUTCOME_API_ERROR = "api_error"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_VALIDATION_ERROR = "validation_error"
OUTCOME_MISSING_API_KEY = "missing_api_key"
OUTCOME_PARSE_ERROR = "parse_error"


async def generate_grounded_recommendation(
    context: Dict[str, Any],
    system_prompt: str,
    response_schema: Type[BaseModel],
    timeout_seconds: int = 15,
    *,
    api_key: str = "",
    model: str = "gemini-3.6-flash",
) -> Tuple[Optional[BaseModel], str]:
    """
    Call Gemini with the given context and system prompt, request JSON-only
    output, and validate the response against response_schema.

    Returns:
        (validated_model, outcome) — validated_model is None on any failure.
        outcome is a sanitized string: "success", "api_error", "timeout",
        "validation_error", "missing_api_key", or "parse_error".

    This function never raises — all exceptions are caught and logged.
    """
    if not api_key:
        logger.warning("Grounded LLM: no API key configured — skipping generation")
        return None, OUTCOME_MISSING_API_KEY

    try:
        # Late import to avoid import-time side effects when key is missing
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)

        # Build the user message with the context
        user_message = (
            "CONTEXT DATA (base your response ONLY on these numbers):\n"
            f"```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
            "Generate your recommendations based strictly on the above context."
        )

        # Call the async API with structured output
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=user_message,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=0.2,
                ),
            ),
            timeout=timeout_seconds,
        )

        raw_text = response.text
        if not raw_text:
            logger.error("Grounded LLM: empty response text from Gemini")
            return None, OUTCOME_API_ERROR

        logger.debug("Grounded LLM: raw response text: %s", raw_text[:500])

        # Parse JSON
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.error(
                "Grounded LLM: malformed JSON from Gemini response",
                exc_info=True,
            )
            return None, OUTCOME_PARSE_ERROR

        # Validate against the strict Pydantic schema
        try:
            validated = response_schema.model_validate(parsed)
        except ValidationError:
            logger.error(
                "Grounded LLM: response failed schema validation against %s",
                response_schema.__name__,
                exc_info=True,
            )
            return None, OUTCOME_VALIDATION_ERROR

        logger.info("Grounded LLM: successfully generated and validated response")
        return validated, OUTCOME_SUCCESS

    except asyncio.TimeoutError:
        logger.error(
            "Grounded LLM: timed out after %d seconds",
            timeout_seconds,
            exc_info=True,
        )
        return None, OUTCOME_TIMEOUT

    except Exception:
        # Catch-all for any Gemini SDK error, network issue, etc.
        logger.error(
            "Grounded LLM: unexpected error during generation",
            exc_info=True,
        )
        return None, OUTCOME_API_ERROR
