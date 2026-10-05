"""
FastAPI router for the AI Assistant chat endpoint.
Provides POST /assistant/chat with per-user rate limiting, JWT authentication,
and structured UI blocks.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant.agent import run_assistant_agent
from app.services.assistant.llm import LLMClient, get_llm_client
from app.services.assistant.ratelimit import assistant_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def resolve_client_date(client_date_str: Optional[str]) -> date:
    """
    Resolve client_date. If it is more than 1 day from the server date (or missing/invalid),
    ignore it and use the server date.
    """
    server_today = date.today()
    if not client_date_str:
        return server_today
    try:
        parsed = date.fromisoformat(client_date_str)
        if abs((parsed - server_today).days) > 1:
            return server_today
        return parsed
    except Exception:
        return server_today


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    request: AssistantChatRequest,
    current_user: User = Depends(get_current_user),
    llm_client: LLMClient = Depends(get_llm_client),
) -> AssistantChatResponse:
    """
    Execute an assistant conversation turn.
    Performs rate limiting, runs the agent loop with deterministic tools,
    and returns prose text and structured UI blocks.
    """
    # 1. Rate limiting
    allowed, retry_after = await assistant_rate_limiter.acquire(
        user_id=str(current_user.id),
        limit=settings.ASSISTANT_RATE_LIMIT_PER_MIN,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # 2. Resolve client date (anchors 'today', 'past week', etc.)
    client_date = resolve_client_date(request.client_date)

    # 3. Run the agent loop
    response = await run_assistant_agent(
        request=request,
        user_id=str(current_user.id),
        client_date=client_date,
        llm_client=llm_client,
    )

    return response
