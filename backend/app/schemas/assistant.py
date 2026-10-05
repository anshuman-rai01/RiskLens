"""
Pydantic v2 schemas for the AI assistant API.
Defines the request, response, and structured UI Block types (discriminated union).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Chat Messages ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(..., min_length=1, max_length=2000)


class AssistantChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, max_length=12)
    client_date: Optional[str] = Field(
        default=None,
        description="User local date in YYYY-MM-DD format"
    )

    @field_validator("client_date")
    @classmethod
    def validate_client_date(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
                raise ValueError("client_date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def validate_request_constraints(self) -> "AssistantChatRequest":
        if not self.messages:
            raise ValueError("messages list cannot be empty")
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user")

        total_chars = sum(len(m.text) for m in self.messages)
        if total_chars > 8000:
            raise ValueError(f"Total message text length ({total_chars}) exceeds limit of 8000 characters")

        return self


# ── Block Definitions ────────────────────────────────────────────

class MetricItem(BaseModel):
    label: str
    value: float
    format: Literal["currency", "number", "percent"]
    tone: Literal["neutral", "ok", "warn", "danger"] = "neutral"


class MetricsBlock(BaseModel):
    type: Literal["metrics"] = "metrics"
    id: str
    title: Optional[str] = None
    items: List[MetricItem] = Field(..., min_length=1, max_length=6)


class ChartSeries(BaseModel):
    key: str
    label: str
    role: Literal["income", "expense", "savings", "forecast", "neutral"]


class ChartBand(BaseModel):
    lower_key: str
    upper_key: str


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    id: str
    title: str
    subtitle: Optional[str] = None
    kind: Literal["line", "bar"]
    x_format: Literal["date", "category"]
    y_format: Literal["currency", "number"]
    series: List[ChartSeries] = Field(..., min_length=1, max_length=3)
    band: Optional[ChartBand] = None
    data: List[Dict[str, Any]] = Field(..., max_length=120)

    @field_validator("data")
    @classmethod
    def validate_data_rows(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i, row in enumerate(rows):
            if "x" not in row:
                raise ValueError(f"Row {i} in chart data is missing required 'x' key")
        return rows


class NoticeBlock(BaseModel):
    type: Literal["notice"] = "notice"
    id: str
    tone: Literal["info", "warn"]
    text: str


class TableColumn(BaseModel):
    key: str
    label: str
    align: Optional[Literal["left", "right", "center"]] = "left"


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    id: str
    title: str
    columns: List[TableColumn] = Field(..., min_length=1, max_length=8)
    rows: List[Dict[str, Any]] = Field(..., max_length=50)
    total_count: Optional[int] = None


class ConfirmEntryBlock(BaseModel):
    type: Literal["confirm_entry"] = "confirm_entry"
    id: str
    category: str
    payload: Dict[str, Any]
    preview: Dict[str, Any]
    summary: str


class ConfirmDeleteBlock(BaseModel):
    type: Literal["confirm_delete"] = "confirm_delete"
    id: str
    category: str
    entry_ids: List[str] = Field(..., min_length=1, max_length=25)
    entries: List[Dict[str, Any]] = Field(default_factory=list, max_length=25)
    summary: str


Block = Annotated[
    Union[MetricsBlock, ChartBlock, NoticeBlock, TableBlock, ConfirmEntryBlock, ConfirmDeleteBlock],
    Field(discriminator="type")
]


class AssistantChatResponse(BaseModel):
    id: str
    text: str
    blocks: List[Block] = Field(default_factory=list, max_length=10)
    outcome: Literal["ok", "degraded", "unavailable"]
