"""
Pydantic schemas for risk alerts and notification payloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AlertResponse(BaseModel):
    """
    Public representation of an alert.
    Strictly excludes user_id to enforce information hygiene.
    """
    id: uuid.UUID
    category: str
    subcategory: Optional[str] = None
    kind: str = Field(description="Alert kind: 'threshold' | 'trend'")
    severity: str = Field(description="Severity tier: 'info' | 'warning' | 'risk'")
    message: str = Field(description="Human-readable explanation of risk condition")
    triggered_at: datetime = Field(description="Timestamp when condition was first detected")
    resolved_at: Optional[datetime] = Field(
        None,
        description="Timestamp when condition resolved (None if still active)",
    )

    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    """List response of active or historical alerts."""
    items: List[AlertResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)
