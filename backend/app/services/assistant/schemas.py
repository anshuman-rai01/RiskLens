"""
Pydantic schemas for the assistant chat endpoint.

The response uses a discriminated union of Block types so the frontend
can render rich, structured content (metrics cards, charts, notices)
alongside plain text.  Unknown block types are silently skipped by
the frontend, making the union extensible without lock-step deploys.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat message from the user."""
    message: str = Field(..., min_length=1, max_length=2000)


# ── Block types (discriminated union on "type") ─────────────────

class MetricItem(BaseModel):
    """A single labelled metric inside a MetricsBlock."""
    label: str
    value: str            # pre-formatted string, e.g. "₹12,340"
    detail: str = ""      # optional secondary line


class MetricsBlock(BaseModel):
    """A grid of key metrics — the frontend renders these as cards."""
    type: Literal["metrics"] = "metrics"
    title: str
    items: List[MetricItem]


class ChartPoint(BaseModel):
    """A single point in a chart series."""
    x: str                # label or date string
    y: float


class ChartSeries(BaseModel):
    """One series in a chart."""
    name: str
    data: List[ChartPoint]
    color: Optional[str] = None


class ChartBlock(BaseModel):
    """A chart block — the frontend renders this with Recharts."""
    type: Literal["chart"] = "chart"
    title: str
    chart_type: Literal["line", "bar", "area"] = "bar"
    series: List[ChartSeries]
    x_label: str = ""
    y_label: str = ""


class NoticeBlock(BaseModel):
    """
    An informational callout — info, success, warning, or error.
    Used for disclaimers, insufficient-data messages, and tips.
    """
    type: Literal["notice"] = "notice"
    level: Literal["info", "success", "warning", "error"] = "info"
    text: str


# The discriminated union — extend by adding new block models here.
Block = Union[MetricsBlock, ChartBlock, NoticeBlock]


# ── Response ─────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Complete response returned by POST /assistant/chat."""
    reply: str                       # Markdown-formatted prose
    blocks: List[Block] = []         # structured UI blocks
    tool_calls_made: int = 0         # how many tool rounds were used
    error: Optional[str] = None      # non-None only on hard failure
